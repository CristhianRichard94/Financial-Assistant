# Deploying rag-api to AWS

This is a manual, step-by-step walkthrough for deploying this service to your
own AWS account using ECS Fargate + an Application Load Balancer, provisioned
via the AWS CDK app in [`infra/`](./infra). None of these commands have been
run in this repository's development environment (no AWS CLI or credentials
are available there) - verify each step against your own account.

## Prerequisites

- An AWS account and credentials configured locally (`aws configure` or
  equivalent), with permissions to create ECR repositories, ECS/Fargate
  resources, an ALB, IAM roles, and Secrets Manager secrets.
- Docker installed locally.
- Node.js (for the `aws-cdk` CLI) and Python 3.10+.
- A Supabase project with the `services/rag-pipeline/sql/*.sql` migrations
  already applied, an OpenAI API key, and an Anthropic API key.

## 1. Build and push the container image to ECR

```bash
# From the repository root:
aws ecr create-repository --repository-name finsight/rag-api

aws ecr get-login-password --region <your-region> \
  | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<your-region>.amazonaws.com

docker build -f services/rag-api/Dockerfile -t finsight/rag-api:latest .

docker tag finsight/rag-api:latest \
  <account-id>.dkr.ecr.<your-region>.amazonaws.com/finsight/rag-api:latest

docker push <account-id>.dkr.ecr.<your-region>.amazonaws.com/finsight/rag-api:latest
```

Note: the CDK stack (`infra/rag_api_stack.py`) builds and pushes the image
itself via `ecs.ContainerImage.from_asset(...)` when you run `cdk deploy`, so
this manual ECR push is only needed if you want to build/push the image
independently of CDK (e.g. to test it locally with `docker run` first, or to
push from a CI pipeline that doesn't run CDK).

## 2. Create the 5 required secrets in Secrets Manager

The CDK stack expects these exact secret names (see `SECRET_NAMES` in
`infra/rag_api_stack.py`), each holding a single plaintext string value (not
a JSON blob):

```bash
aws secretsmanager create-secret \
  --name finsight/rag-api/SUPABASE_URL \
  --secret-string "https://your-project-ref.supabase.co"

aws secretsmanager create-secret \
  --name finsight/rag-api/SUPABASE_SERVICE_KEY \
  --secret-string "your-supabase-service-role-key"

aws secretsmanager create-secret \
  --name finsight/rag-api/OPENAI_API_KEY \
  --secret-string "sk-your-openai-api-key"

aws secretsmanager create-secret \
  --name finsight/rag-api/ANTHROPIC_API_KEY \
  --secret-string "sk-ant-your-anthropic-api-key"

# A pre-shared secret the frontend must send back on every request as the
# X-Internal-Api-Key header (see rag_api/auth.py). Generate a long random
# value, e.g. `openssl rand -hex 32`, and reuse the same value for the
# frontend's own environment configuration in step 6.
aws secretsmanager create-secret \
  --name finsight/rag-api/INTERNAL_API_KEY \
  --secret-string "$(openssl rand -hex 32)"
```

## 3. Install the CDK app's Python dependencies

```bash
cd services/rag-api/infra
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm install -g aws-cdk   # if you don't already have the CDK CLI
```

## 4. Bootstrap and deploy

```bash
# Once per AWS account/region:
cdk bootstrap aws://<account-id>/<your-region>

# Synthesize the CloudFormation template (sanity check before deploying):
cdk synth

# Deploy - this builds the Docker image from the repo root, pushes it to a
# CDK-managed ECR asset repository, and creates the ECS Fargate service, ALB,
# and CloudFront distribution:
cdk deploy
```

`cdk deploy` will prompt you to approve any IAM/security-group changes it's
about to make - review and confirm.

No ACM certificate or custom domain is required. HTTPS is provided by the
CloudFront distribution in front of the ALB (see step 6), using CloudFront's
free default `*.cloudfront.net` domain and AWS-managed certificate - no
domain purchase or DNS validation needed to get started.

## 5. Find the ALB DNS name

After `cdk deploy` finishes, it prints a `LoadBalancerDnsName` output (also
visible any time via `aws cloudformation describe-stacks --stack-name
FinSightRagApiStack --query "Stacks[0].Outputs"`). It looks like:

```
FinSightRagApiStack.LoadBalancerDnsName = FinSi-RagAp-xxxxxxxxxxxx-1234567890.<region>.elb.amazonaws.com
```

**This ALB is public** (`public_load_balancer=True` in
`infra/rag_api_stack.py`) but HTTP-only - it has no HTTPS listener of its
own. Its security group only accepts inbound traffic on port 80 from
CloudFront's own IP ranges (the AWS-managed
`com.amazonaws.global.cloudfront.origin-facing` prefix list), not the open
internet, so the `LoadBalancerDnsName` value above is not meant to be used
directly - it's for reference/debugging only (e.g. checking ECS task health
from within the VPC). Use the CloudFront distribution domain from step 6
instead.

## 6. Find the CloudFront distribution domain

The same `cdk deploy` output also includes a `DistributionDomainName` output:

```
FinSightRagApiStack.DistributionDomainName = d1234abcdefgh.cloudfront.net
```

This is CloudFront's free default domain, with a working AWS-managed HTTPS
certificate already attached - no setup required. This is the URL to use as
`RAG_API_BASE_URL` in step 7.

(Optional, later: if you do end up owning a domain and want a nicer hostname
than `*.cloudfront.net`, you can add a CloudFront alternate domain name
(CNAME) pointing at this distribution, backed by an ACM certificate - but
note CloudFront requires that certificate to be requested **in the
`us-east-1` region specifically**, regardless of which region the rest of
this stack is deployed in. This is not required to use the API.)

## 7. Point the frontend at the deployed API

Set these in the frontend's server-side environment (e.g. Replit's
deployment secrets/environment variables, or `artifacts/finsight/.env.local`
for local testing):

```
RAG_API_BASE_URL=https://d1234abcdefgh.cloudfront.net
RAG_API_INTERNAL_KEY=<the same value you generated for INTERNAL_API_KEY in step 2>
```

Use the `DistributionDomainName` value from step 6, not the raw ALB DNS name.

The Next.js app's API routes proxy to this URL server-side (see
`artifacts/finsight/src/lib/ragApiClient.ts`), attaching `RAG_API_INTERNAL_KEY`
as the `X-Internal-Api-Key` header on every request - the browser never talks
to the ALB or CloudFront distribution directly, so no CORS configuration is
needed on this service, and `RAG_API_INTERNAL_KEY` never needs to exist in
client-side code (don't change that).

This is now a real internet-facing HTTPS endpoint, reachable from Replit's
deployed frontend or anywhere else on the internet - there is no VPC or
network-level trust boundary. Restricting the ALB's security group to
CloudFront's IP ranges only stops people from bypassing CloudFront and
hitting the ALB's raw DNS name directly; it does not restrict who can call
the CloudFront domain itself. The `X-Internal-Api-Key` shared secret is the
sole access-control gate in front of this service, so treat it like a real
credential: keep it out of any client-side code or logs, and rotate it
(update the Secrets Manager secret from step 2, then redeploy) immediately if
it's ever suspected of leaking.

## Tearing down

```bash
cd services/rag-api/infra
cdk destroy
```

No context flags are required - the stack no longer needs an ACM certificate
or custom domain (see step 4). Note that deleting a CloudFront distribution
takes several minutes (CloudFront has to disable it globally before it can be
removed), so `cdk destroy` will sit and wait on that step; this is normal, not
a hang.

This does not delete the Secrets Manager secrets created in step 2 (by
design, they're managed independently) - delete them manually with
`aws secretsmanager delete-secret` if you no longer need them.
