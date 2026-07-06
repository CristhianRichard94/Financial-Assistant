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
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
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
# `X-Internal-Api-Key` header on every request (see rag_api/auth.py) - an
# application-level, defense-in-depth check on top of the network isolation
# below, since the ALB is internal but that network boundary alone is easy
# to misconfigure or drift later.
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

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "RagApiService",
            cpu=512,
            memory_limit_mib=1024,
            desired_count=1,
            # Internal ALB: this is a data-plane API with no user-facing
            # authentication of its own (it relies on network isolation,
            # reinforced by the X-Internal-Api-Key header check in
            # rag_api/auth.py). It must never be reachable directly from the
            # public internet. `public_load_balancer=False` places the ALB
            # (and, by the pattern's default, the Fargate tasks) in private
            # subnets with no internet-facing listener.
            #
            # IMPORTANT: whichever compute runs the Next.js/Express frontend
            # layer must be deployed into the *same VPC* as this service, and
            # its security group must be added to `service.service.connections`
            # (or the ALB's security group) as an allowed ingress source on
            # port 8000/80 - see ../DEPLOYMENT.md for the exact steps, since
            # that frontend compute stack doesn't exist in this repo yet and
            # can't be wired up here automatically.
            public_load_balancer=False,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset(
                    str(REPO_ROOT),
                    file=DOCKERFILE_RELATIVE_PATH,
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
                "Internal ALB DNS name (only reachable from within the VPC). "
                "Use http://<this value> as RAG_API_BASE_URL in the "
                "frontend's environment configuration, from a service "
                "deployed in the same VPC - see DEPLOYMENT.md."
            ),
        )
