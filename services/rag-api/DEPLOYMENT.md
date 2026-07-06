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

## 4. Get an ACM certificate for your own domain

The frontend (Next.js/Express) is deployed on Replit's autoscale platform - a
separate cloud with no private network path into this AWS VPC - so this
service's ALB must be public and reachable over the internet. It's HTTPS-only,
and AWS will only issue/validate a certificate for a domain you actually
control, not for the `*.elb.amazonaws.com` hostname it assigns the ALB. So
before deploying, you need a domain (or subdomain) you own, pointed at this
service, with an ACM certificate covering it, **in the same AWS region as the
stack**.

If you don't already have a suitable certificate:

```bash
aws acm request-certificate \
  --domain-name rag-api.yourdomain.com \
  --validation-method DNS \
  --region <your-region>
```

This prints a certificate ARN. Follow the printed instructions (or
`aws acm describe-certificate --certificate-arn <arn>`) to add the DNS
validation CNAME record `request-certificate` gives you at your DNS provider.
The certificate stays `PENDING_VALIDATION` and is not usable until that DNS
record is created and has propagated - wait for
`aws acm describe-certificate ... --query "Certificate.Status"` to report
`ISSUED` before continuing. Keep the certificate ARN handy for the next step.

## 5. Bootstrap and deploy

```bash
# Once per AWS account/region:
cdk bootstrap aws://<account-id>/<your-region>

# Synthesize the CloudFormation template (sanity check before deploying):
cdk synth -c certificateArn=<the ACM certificate ARN from step 4>

# Deploy - this builds the Docker image from the repo root, pushes it to a
# CDK-managed ECR asset repository, and creates the ECS Fargate service + ALB:
cdk deploy -c certificateArn=<the ACM certificate ARN from step 4>
```

`cdk deploy` will prompt you to approve any IAM/security-group changes it's
about to make - review and confirm. If `certificateArn` is omitted, both
`cdk synth` and `cdk deploy` fail fast with an error pointing back here.

## 6. Find the ALB DNS name and point your domain at it

After `cdk deploy` finishes, it prints a `LoadBalancerDnsName` output (also
visible any time via `aws cloudformation describe-stacks --stack-name
FinSightRagApiStack --query "Stacks[0].Outputs"`). It looks like:

```
FinSightRagApiStack.LoadBalancerDnsName = FinSi-RagAp-xxxxxxxxxxxx-1234567890.<region>.elb.amazonaws.com
```

**This ALB is public** (`public_load_balancer=True` in
`infra/rag_api_stack.py`) and HTTPS-only: it has an HTTPS listener on 443
using the certificate from step 4, and an HTTP listener on 80 that only
issues a 301 redirect to HTTPS (`redirect_http=True`) - there is no
plaintext-HTTP path into the API.

The raw ALB DNS name above is not directly usable as `RAG_API_BASE_URL`,
since there's no valid certificate for that AWS-owned hostname. Instead,
create a DNS CNAME (or ALIAS, if your DNS provider is Route 53) record from
the domain you requested the certificate for (e.g. `rag-api.yourdomain.com`)
to this `LoadBalancerDnsName` value.

## 7. Point the frontend at the deployed API

Set these in the frontend's server-side environment (e.g. Replit's
deployment secrets/environment variables, or `artifacts/finsight/.env.local`
for local testing):

```
RAG_API_BASE_URL=https://rag-api.yourdomain.com
RAG_API_INTERNAL_KEY=<the same value you generated for INTERNAL_API_KEY in step 2>
```

Use your own custom domain from step 6, not the raw ALB DNS name.

The Next.js app's API routes proxy to this URL server-side (see
`artifacts/finsight/src/lib/ragApiClient.ts`), attaching `RAG_API_INTERNAL_KEY`
as the `X-Internal-Api-Key` header on every request - the browser never talks
to the ALB directly, so no CORS configuration is needed on this service, and
`RAG_API_INTERNAL_KEY` never needs to exist in client-side code (don't change
that).

This is now a real internet-facing HTTPS endpoint, reachable from Replit's
deployed frontend or anywhere else on the internet - there is no VPC or
network-level trust boundary anymore. The `X-Internal-Api-Key` shared secret
is the sole access-control gate in front of this service, so treat it like a
real credential: keep it out of any client-side code or logs, and rotate it
(update the Secrets Manager secret from step 2, then redeploy) immediately if
it's ever suspected of leaking.

## Tearing down

```bash
cd services/rag-api/infra
cdk destroy
```

This does not delete the Secrets Manager secrets created in step 2 (by
design, they're managed independently) - delete them manually with
`aws secretsmanager delete-secret` if you no longer need them.
