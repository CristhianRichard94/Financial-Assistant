#!/usr/bin/env bash
# Tear down the rag-api demo stack after a demo, to stop billing (ECS
# Fargate, ALB, CloudFront). Run this right after every demo - see
# ../DEPLOYMENT.md.
set -euo pipefail

cd "$(dirname "$0")"

cdk destroy --force
