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
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import custom_resources as cr
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
# `X-Internal-Api-Key` header on every request (see rag_api/auth.py). The
# public entry point into this service is the CloudFront distribution below,
# which forwards that header straight through - CloudFront and the ALB's
# security-group lockdown to CloudFront-only traffic (see below) are only a
# network-layer speed bump, not real access control, so this header check
# remains the *primary* access control for this service.
SECRET_NAMES: dict[str, str] = {
    "SUPABASE_URL": "finsight/rag-api/SUPABASE_URL",
    "SUPABASE_SERVICE_KEY": "finsight/rag-api/SUPABASE_SERVICE_KEY",
    "OPENAI_API_KEY": "finsight/rag-api/OPENAI_API_KEY",
    "INTERNAL_API_KEY": "finsight/rag-api/INTERNAL_API_KEY",
}


class RagApiStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: Any) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Pull all 4 required secrets from Secrets Manager - never plaintext
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
            # Public, HTTP-only ALB: the frontend (Next.js/Express) is
            # deployed on Replit's autoscale platform, a separate cloud with
            # no private network path into this AWS VPC, so an internal ALB
            # is not reachable from it. `public_load_balancer=True` attaches
            # the ALB to an internet gateway so the CloudFront distribution
            # below (and, in principle, anything else) can reach it.
            #
            # This ALB deliberately has no HTTPS listener of its own - TLS is
            # terminated at CloudFront instead, using CloudFront's free
            # default `*.cloudfront.net` domain and AWS-managed certificate,
            # which avoids requiring the caller to own a domain just to get
            # an ACM certificate issued. The ALB's security group is locked
            # down below so it only accepts plaintext HTTP from CloudFront's
            # own IP ranges, not the open internet, so this is not a
            # plaintext-over-the-internet path even though the listener
            # itself is HTTP.
            public_load_balancer=True,
            # Without this, CDK's `ApplicationLoadBalancedFargateService`
            # auto-creates an inline ingress rule opening port 80 to
            # 0.0.0.0/0 on the ALB's security group *in addition to* the
            # CloudFront-only rule added below via `connections.allow_from`
            # - `allow_from` only ever adds rules, it never removes CDK's
            # default one. Setting `open_listener=False` suppresses that
            # default rule so the CloudFront-only rule added below is the
            # *only* ingress rule on the ALB's security group.
            open_listener=False,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset(
                    str(REPO_ROOT),
                    file=DOCKERFILE_RELATIVE_PATH,
                    # Without an exclude list, CDK's asset-staging step
                    # copies the *entire* repo root (since REPO_ROOT is the
                    # build context - see the REPO_ROOT comment above) into
                    # `cdk.out/asset.<hash>/` on every `cdk synth`/`cdk
                    # deploy`. The Dockerfile only ever COPYs
                    # `services/rag-api` and `services/rag-pipeline` (see
                    # Dockerfile), so everything else here is dead weight -
                    # and left unexcluded, it silently accumulated ~9G
                    # across a handful of synths (multi-hundred-MB
                    # `node_modules/`, `artifacts/`, even stray feature
                    # worktrees under `.worktrees/`, duplicated into a new
                    # asset dir each time the source hash changed) until the
                    # codespace disk filled up. `services/rag-api/infra` in
                    # particular must stay excluded regardless: it's nested
                    # inside the tree being copied, so leaving it in would
                    # make asset-staging recurse into its own `cdk.out/`
                    # output, an unbounded self-referential copy loop.
                    #
                    # There is no repo-root `.dockerignore` for Docker
                    # itself to fall back on (the existing
                    # `services/rag-api/.dockerignore` /
                    # `Dockerfile.dockerignore` files are scoped to a
                    # `services/rag-api`-rooted context, not this
                    # REPO_ROOT-rooted one), so every top-level entry that
                    # isn't `services/` must be excluded explicitly here.
                    #
                    # `IgnoreMode.GLOB` (CDK's default here - no
                    # `dockerIgnoreSupport` context flag is set) anchors a
                    # bare pattern like `.venv` to the build-context root; it
                    # does NOT match at every depth the way `.gitignore`
                    # patterns do. So the per-service dev artifacts below
                    # (each service has its own `.venv`, `.pytest_cache`,
                    # etc. - e.g. services/rag-api/.venv is itself ~580MB)
                    # need an explicit `**/` prefix, or they silently ride
                    # along into the asset uncut.
                    exclude=[
                        ".claude",
                        ".git",
                        ".npmrc",
                        ".replit",
                        ".replitignore",
                        ".venv",
                        ".worktrees",
                        "AI_USAGE.md",
                        "BACKLOG.md",
                        "CLAUDE.md",
                        "README.md",
                        "artifacts",
                        "assets",
                        "lib",
                        "node_modules",
                        "package.json",
                        "pnpm-lock.yaml",
                        "pnpm-workspace.yaml",
                        "replit.md",
                        "scripts",
                        "tsconfig.base.json",
                        "tsconfig.json",
                        # Within services/, drop this stack's own CDK
                        # tooling (see above) plus local dev artifacts not
                        # needed in the image - mirrors
                        # services/rag-api/.dockerignore, but with `**/`
                        # since these live inside services/rag-api and
                        # services/rag-pipeline, not at the build-context
                        # root (see IgnoreMode.GLOB note above).
                        "services/rag-api/infra",
                        "**/__pycache__",
                        "**/*.pyc",
                        "**/*.pyo",
                        "**/.venv",
                        "**/.pytest_cache",
                        "**/tests",
                        "**/.env",
                        "**/.env.local",
                        "**/*.egg-info",
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

        # Lock the ALB's security group down to only accept inbound traffic
        # from CloudFront's own edge locations, identified by the
        # AWS-managed `com.amazonaws.global.cloudfront.origin-facing` prefix
        # list. Without this, `public_load_balancer=True` above would leave
        # port 80 open to 0.0.0.0/0, and anyone who discovered the ALB's own
        # `*.elb.amazonaws.com` DNS name could bypass CloudFront entirely and
        # hit the ALB directly in plaintext HTTP.
        #
        # The prefix list's ID is AWS-managed and differs per region/
        # partition (there is no single hardcoded ID that works everywhere -
        # e.g. it's pl-3b927c52 in us-east-1 but pl-5da64334 in sa-east-1),
        # so it must be looked up rather than hardcoded. `ec2.PrefixList.
        # from_lookup` (a synth-time CDK context lookup) would be the
        # simplest way to do that, but it's implemented via the CloudFormation
        # Cloud Control API (`cloudformation:ListResources`), which is a
        # broader/less commonly granted permission than plain EC2 read access
        # and may not be available to every deploying principal. Instead,
        # this uses an `AwsCustomResource` that calls the classic
        # `ec2:DescribeManagedPrefixLists` API directly, at CloudFormation
        # deploy time, via a CDK-managed Lambda scoped to exactly that one
        # read-only permission - no extra synth-time AWS credentials or IAM
        # grants are required locally, and the actual account/region lookup
        # happens automatically wherever this stack is deployed.
        prefix_list_lookup = cr.AwsCustomResource(
            self,
            "CloudFrontOriginFacingPrefixListLookup",
            on_update=cr.AwsSdkCall(
                service="EC2",
                action="describeManagedPrefixLists",
                parameters={
                    "Filters": [
                        {
                            "Name": "prefix-list-name",
                            "Values": ["com.amazonaws.global.cloudfront.origin-facing"],
                        }
                    ]
                },
                # Re-run on every deployment (rather than only on the first
                # create) so this stays correct if AWS ever changes the
                # prefix list ID for this account/region; the underlying API
                # call is read-only and cheap.
                physical_resource_id=cr.PhysicalResourceId.of(
                    "CloudFrontOriginFacingPrefixListLookup"
                ),
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE,
            ),
        )
        cloudfront_prefix_list_id = prefix_list_lookup.get_response_field(
            "PrefixLists.0.PrefixListId"
        )
        service.load_balancer.connections.allow_from(
            ec2.Peer.prefix_list(cloudfront_prefix_list_id),
            ec2.Port.tcp(80),
            "Allow inbound HTTP only from CloudFront origin-facing IP ranges",
        )

        # CloudFront distribution in front of the ALB. This is what makes
        # the service reachable over HTTPS without requiring the caller to
        # own a domain or provision an ACM certificate: CloudFront's default
        # `*.cloudfront.net` domain comes with a working AWS-managed
        # certificate out of the box. TLS is terminated here, then
        # CloudFront talks to the ALB over plain HTTP (the ALB has no HTTPS
        # listener - see the comment above).
        distribution = cloudfront.Distribution(
            self,
            "RagApiDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.LoadBalancerV2Origin(
                    service.load_balancer,
                    protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                # This is a dynamic API (RAG chat/document ingestion), not
                # static content - every response is per-request and must
                # never be served from cache to a different caller.
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                # CloudFront does not forward arbitrary request headers to
                # the origin by default, which would silently strip the
                # `X-Internal-Api-Key` header this service's sole
                # access-control check depends on (see rag_api/auth.py).
                # `ALL_VIEWER` forwards all headers, query strings, and
                # cookies through untouched, which is the simplest way to
                # guarantee that header (and anything else the app may rely
                # on, e.g. Content-Type on file uploads) reaches the origin.
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
                # The API uses GET (query/list documents), POST (chat query,
                # upload), and DELETE (remove document) - CloudFront's
                # default behavior only allows GET/HEAD, so every other verb
                # must be explicitly allowed through or CloudFront rejects
                # them before they ever reach the ALB.
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
            ),
        )

        cdk.CfnOutput(
            self,
            "LoadBalancerDnsName",
            value=service.load_balancer.load_balancer_dns_name,
            description=(
                "Public ALB DNS name, for reference/debugging only. Its "
                "security group only accepts inbound traffic from "
                "CloudFront's IP ranges, and it has no HTTPS listener, so "
                "this value is NOT usable directly as RAG_API_BASE_URL. Use "
                "the DistributionDomainName output instead."
            ),
        )

        cdk.CfnOutput(
            self,
            "DistributionDomainName",
            value=distribution.distribution_domain_name,
            description=(
                "CloudFront distribution domain name. Use "
                "https://<this value> as RAG_API_BASE_URL in the frontend's "
                "environment configuration - see DEPLOYMENT.md."
            ),
        )
