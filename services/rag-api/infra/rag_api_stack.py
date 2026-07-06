"""CDK stack: ECS Fargate service running the RAG API behind an ALB.

ECS Fargate (rather than Lambda + API Gateway) is used specifically because
the `/upload` endpoint schedules document ingestion via FastAPI
`BackgroundTasks`, which needs a long-lived process to reliably finish:
Lambda freezes the execution environment immediately after the HTTP response
is returned, so a background task started inside a Lambda handler is not
guaranteed to run to completion. A Fargate task keeps running as a normal
long-lived process, so the background task behaves exactly as it does in
local development.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aws_cdk as cdk
from aws_cdk import Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

# This file lives at services/rag-api/infra/rag_api_stack.py, so the repo
# root (needed as the Docker build context, since the image also copies in
# the sibling services/rag-pipeline package) is three directories up.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DOCKERFILE_RELATIVE_PATH = "services/rag-api/Dockerfile"

# Secrets Manager secret names this stack expects to already exist (see
# ../DEPLOYMENT.md for how to create them). Each secret is a single plaintext
# string value (not a JSON blob with named keys), matching
# `ecs.Secret.from_secrets_manager(secret)` with no `field=` argument.
#
# INTERNAL_API_KEY is a pre-shared secret the frontend must send back as the
# `X-Internal-Api-Key` header on every request (see rag_api/auth.py). Since
# the ALB is public (see the comment on `public_load_balancer` below), this
# header check is the *primary* access control for this service, not just
# defense-in-depth - there is no network boundary backing it up.
SECRET_NAMES: dict[str, str] = {
    "SUPABASE_URL": "finsight/rag-api/SUPABASE_URL",
    "SUPABASE_SERVICE_KEY": "finsight/rag-api/SUPABASE_SERVICE_KEY",
    "OPENAI_API_KEY": "finsight/rag-api/OPENAI_API_KEY",
    "ANTHROPIC_API_KEY": "finsight/rag-api/ANTHROPIC_API_KEY",
    "INTERNAL_API_KEY": "finsight/rag-api/INTERNAL_API_KEY",
}


class RagApiStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: Any) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Pull all 5 required secrets from Secrets Manager - never plaintext
        # environment variables for credentials.
        ecs_secrets = {
            env_var_name: ecs.Secret.from_secrets_manager(
                secretsmanager.Secret.from_secret_name_v2(
                    self, f"{env_var_name}SecretRef", secret_name
                )
            )
            for env_var_name, secret_name in SECRET_NAMES.items()
        }

        # ACM certificate for the ALB's HTTPS listener. This must be a
        # certificate the caller already owns and has DNS-validated for their
        # own custom domain (e.g. rag-api.yourdomain.com) - AWS controls the
        # `*.elb.amazonaws.com` hostname it assigns the ALB, so it's not
        # possible to get a valid public certificate for that raw hostname.
        # Passed in via CDK context (`cdk deploy -c certificateArn=...`)
        # rather than hardcoded, since it's account/domain-specific and
        # created out-of-band - see ../DEPLOYMENT.md for how to request and
        # validate one.
        certificate_arn = self.node.try_get_context("certificateArn")
        if not certificate_arn:
            raise ValueError(
                "Missing required CDK context value 'certificateArn'. Pass "
                "it with `cdk deploy -c certificateArn=<your ACM certificate "
                "ARN>` (and likewise for `cdk synth`). See the 'Bootstrap "
                "and deploy' section of ../DEPLOYMENT.md for how to request "
                "and validate a certificate for your own domain first."
            )
        certificate = acm.Certificate.from_certificate_arn(
            self, "RagApiCertificate", certificate_arn
        )

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "RagApiService",
            cpu=512,
            memory_limit_mib=1024,
            desired_count=1,
            # Public, HTTPS-only ALB: the frontend (Next.js/Express) is
            # deployed on Replit's autoscale platform, a separate cloud with
            # no private network path into this AWS VPC, so an internal ALB
            # is not reachable from it. `public_load_balancer=True` attaches
            # the ALB to an internet gateway.
            #
            # This service has no other user-facing authentication of its
            # own, so with the network boundary gone, the `X-Internal-Api-Key`
            # shared-secret header check (see rag_api/auth.py) is now the
            # *primary* access control, not defense-in-depth. Treat that
            # secret like a real credential: generate it as a long random
            # value (see ../DEPLOYMENT.md) and rotate it immediately if it's
            # ever suspected of leaking.
            #
            # `protocol=HTTPS` + `certificate=...` add an HTTPS listener on
            # 443, and `redirect_http=True` adds a listener on 80 that only
            # issues a 301 redirect to the HTTPS listener - so there is no
            # plaintext-HTTP path to reach the API, only a redirect off of it.
            public_load_balancer=True,
            protocol=elbv2.ApplicationProtocol.HTTPS,
            certificate=certificate,
            redirect_http=True,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset(
                    str(REPO_ROOT),
                    file=DOCKERFILE_RELATIVE_PATH,
                    # Without this, CDK's asset-staging copy of the build
                    # context (which is the whole repo root - see the
                    # REPO_ROOT comment above) recurses into this very
                    # directory's own `cdk.out/` output, which is nested
                    # inside the tree being copied, causing an unbounded
                    # self-referential copy loop during `cdk synth`/`cdk
                    # deploy`. There is no repo-root `.dockerignore` for
                    # Docker itself to fall back on (the existing
                    # `services/rag-api/.dockerignore` /
                    # `Dockerfile.dockerignore` files are scoped to a
                    # `services/rag-api`-rooted context, not this
                    # REPO_ROOT-rooted one), so this must be excluded
                    # explicitly here.
                    exclude=[
                        "services/rag-api/infra/cdk.out",
                        "services/rag-api/infra/.venv",
                        ".git",
                    ],
                ),
                container_port=8000,
                secrets=ecs_secrets,
            ),
        )

        # ALB health check hits /healthz (no auth, no dependency checks - see
        # rag_api/routes/health.py).
        service.target_group.configure_health_check(
            path="/healthz",
            healthy_http_codes="200",
        )

        cdk.CfnOutput(
            self,
            "LoadBalancerDnsName",
            value=service.load_balancer.load_balancer_dns_name,
            description=(
                "Public ALB DNS name. This raw value is NOT directly usable "
                "as RAG_API_BASE_URL - there is no valid certificate for the "
                "*.elb.amazonaws.com hostname AWS assigns it, so HTTPS "
                "requests to it directly will fail certificate validation. "
                "Instead, point your own custom domain (the one the ACM "
                "certificate passed via -c certificateArn was issued for, "
                "e.g. rag-api.yourdomain.com) at this value with a DNS "
                "CNAME/ALIAS record, then use https://<your custom domain> "
                "as RAG_API_BASE_URL - see DEPLOYMENT.md."
            ),
        )
