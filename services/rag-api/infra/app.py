#!/usr/bin/env python3
"""CDK app entrypoint for the RAG API stack.

Usage (from services/rag-api/infra, after `pip install -r requirements.txt`):
    cdk bootstrap   # once per account/region
    cdk synth
    cdk deploy

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
