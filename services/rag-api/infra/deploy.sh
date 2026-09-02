#!/usr/bin/env bash
# Deploy the rag-api demo stack and print the CloudFront domain to use as
# RAG_API_BASE_URL. Run this a few minutes before a demo; run destroy.sh
# right after - see ../DEPLOYMENT.md.
set -euo pipefail

cd "$(dirname "$0")"

OUTPUTS_FILE="$(mktemp)"
trap 'rm -f "$OUTPUTS_FILE"' EXIT

cdk deploy --require-approval never --outputs-file "$OUTPUTS_FILE"

DOMAIN=$(jq -r '.[].DistributionDomainName' "$OUTPUTS_FILE")

if [ -z "$DOMAIN" ]; then
  echo "ERROR: could not read DistributionDomainName from CDK outputs" >&2
  exit 1
fi

echo ""
echo "=================================================================="
echo "Deploy complete. Set this in the frontend's environment as:"
echo ""
echo "  RAG_API_BASE_URL=https://${DOMAIN}"
echo ""
echo "Verify it's healthy before demoing:"
echo ""
echo "  curl https://${DOMAIN}/healthz"
echo "=================================================================="
