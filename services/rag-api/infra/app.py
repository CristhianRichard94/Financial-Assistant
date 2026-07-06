#!/usr/bin/env python3
"""CDK app entrypoint for the RAG API stack.

Usage (from services/rag-api/infra, after `pip install -r requirements.txt`):
    cdk bootstrap   # once per account/region
    cdk synth -c certificateArn=<your ACM certificate ARN>
    cdk deploy -c certificateArn=<your ACM certificate ARN>

`certificateArn` is required (see RagApiStack for validation) and is passed
as CDK context rather than hardcoded here, since it's account/domain-specific
and provisioned out-of-band - see ../DEPLOYMENT.md for how to request and
validate a certificate for your own domain first.

See ../DEPLOYMENT.md for the full manual deployment walkthrough (ECR push,
Secrets Manager setup, etc.) - this is not runnable in this environment since
it needs real AWS credentials.
"""

from __future__ import annotations

import aws_cdk as cdk

from rag_api_stack import RagApiStack

app = cdk.App()

RagApiStack(
    app,
    "FinSightRagApiStack",
    description="FinSight RAG API: ECS Fargate service behind an ALB, exposing the RAG pipeline over HTTP.",
)

app.synth()
