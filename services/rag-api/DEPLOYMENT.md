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
# CDK-managed ECR asset repository, and creates the ECS Fargate service + ALB:
cdk deploy
```

`cdk deploy` will prompt you to approve any IAM/security-group changes it's
about to make - review and confirm.

## 5. Find the ALB DNS name

After `cdk deploy` finishes, it prints a `LoadBalancerDnsName` output (also
visible any time via `aws cloudformation describe-stacks --stack-name
FinSightRagApiStack --query "Stacks[0].Outputs"`). It looks like:

```
FinSightRagApiStack.LoadBalancerDnsName = FinSi-RagAp-xxxxxxxxxxxx-1234567890.<region>.elb.amazonaws.com
```

**This ALB is internal** (`public_load_balancer=False` in
`infra/rag_api_stack.py`) - it is only resolvable/reachable from within the
same VPC, and is not attached to an internet gateway. It is not reachable
from the public internet, and the DNS name above will not resolve outside
the VPC.

## 5b. Required network setup for the frontend

This service has no user-facing authentication beyond the
`X-Internal-Api-Key` header check (see `rag_api/auth.py`) - it is designed
to be reached only by the Next.js/Express frontend layer, over the private
network. Since that frontend compute doesn't exist as a stack in this repo
yet, you must, when you deploy it:

1. Deploy the frontend's compute (e.g. an ECS service, EC2 instance, or
   anything else that can reach a private VPC resource) into the **same
   VPC** this stack creates (see the CDK app's VPC output, or
   `service.cluster.vpc` in `infra/rag_api_stack.py`).
2. Add the frontend's security group as an allowed ingress source on the
   RAG API's ALB security group (or the Fargate service's own security
   group), on port 80 (the ALB listener) - e.g. via
   `service.load_balancer.connections.allow_from(frontendSecurityGroup, ec2.Port.tcp(80))`
   in CDK, or the equivalent `aws ec2 authorize-security-group-ingress` call.
3. Without step 2, requests from the frontend will simply time out (not
   receive a 403) since they'll never reach the ALB's listener at the
   network layer.

Do not skip this and fall back to making the ALB public again to work around
connectivity issues - that reopens the exact internet-exposure issue this
setup is designed to prevent.

## 6. Point the frontend at the deployed API

Set these in the frontend's server-side environment (e.g. your hosting
platform's environment variables, or `artifacts/finsight/.env.local` for
local testing against the deployed API from a host that's in the same VPC
or otherwise has network access to the internal ALB):

```
RAG_API_BASE_URL=http://<the ALB DNS name from step 5>
RAG_API_INTERNAL_KEY=<the same value you generated for INTERNAL_API_KEY in step 2>
```

The Next.js app's API routes proxy to this URL server-side (see
`artifacts/finsight/src/lib/ragApiClient.ts`), attaching `RAG_API_INTERNAL_KEY`
as the `X-Internal-Api-Key` header on every request - the browser never talks
to the ALB directly, so no CORS configuration is needed on this service.

Consider adding HTTPS (an ACM certificate + HTTPS listener on the ALB) before
using this in front of real user data; the CDK stack as written creates a
plain HTTP listener for simplicity. Even on the internal network, prefer
HTTPS if the VPC is shared with less-trusted workloads.

## Tearing down

```bash
cd services/rag-api/infra
cdk destroy
```

This does not delete the Secrets Manager secrets created in step 2 (by
design, they're managed independently) - delete them manually with
`aws secretsmanager delete-secret` if you no longer need them.
