# AWS ECS Fargate Deployment Guide

Deploys chkHealth on AWS ECS Fargate — **internal-only**, accessible via Site-to-Site VPN or
Direct Connect. No resource is internet-facing.

> **Single-replica constraint.** chkHealth uses SQLite for metrics and startup coordination.
> The ECS service runs exactly one Fargate task at all times — do not enable auto-scaling to > 1.

---

## Overview

This guide uses the Terraform module in `terraform/aws/`. It provisions:

| Resource | Purpose |
|---|---|
| VPC + private/public subnets (2 AZs) | Network isolation |
| Internal ALB (`scheme=internal`) | Stable private ingress — WAN-only, not internet-facing |
| ECS Fargate cluster + service | Single-replica container runtime |
| EFS + access point | Persistent data (`/app/data`) |
| ECR repository | Container image storage |
| Secrets Manager | `SECRET_KEY` and `CP_API_KEY` |
| KMS key | EFS at-rest encryption + Secrets Manager CMK |
| IAM task execution + task roles | Least-privilege ECR/Secrets/EFS/SSM access |
| CloudWatch log group | Container stdout/stderr |

## Prerequisites

- Terraform ≥ 1.6
- AWS CLI v2 configured with permissions for VPC, ECR, ECS, EFS, ALB, IAM, ACM, Secrets Manager, KMS
- Docker installed locally
- Site-to-Site VPN or Direct Connect already attached to the AWS account

---

## Phase 1 — Infrastructure

```bash
cd terraform/aws
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` — at minimum set:
- `wan_cidr_blocks` — your corporate WAN CIDRs that can reach the ALB (e.g. `["10.0.0.0/8"]`)
- `cp_mds_primary` — IP of the Check Point MDS appliance
- `cp_mds_primary_label` — display label shown in the UI

```bash
terraform init
terraform apply
```

Outputs to note:
- `ecr_repository_url` — used in Phase 3
- `alb_dns_name` — hand to your DNS team for Phase 6
- `secret_key_arn` / `cp_api_key_arn` — used in Phase 2
- `private_nat_gateway_ip` — hand to your network/firewall team to allow-list on Provider-1 (CP
  MDS) and any other on-prem service this container reaches. See
  `terraform/aws/README.md#static-egress-ip-for-on-prem-traffic-provider-1-radius-smtp-snmp` for
  the full explanation and the `vpn_gateway_id`/`transit_gateway_id` variables.

---

## Phase 2 — Secrets

```bash
# Generate SECRET_KEY (run from the chkHealth repo root)
uv run python manage_users.py secret

cd terraform/aws

aws secretsmanager put-secret-value \
  --secret-id "$(terraform output -raw secret_key_arn)" \
  --secret-string "PASTE_GENERATED_KEY"

aws secretsmanager put-secret-value \
  --secret-id "$(terraform output -raw cp_api_key_arn)" \
  --secret-string "YOUR_CP_API_KEY"
```

---

## Phase 3 — ACM Certificate

Request a certificate for the internal hostname you will use:

```bash
aws acm request-certificate \
  --domain-name chkhealth.corp.example.com \
  --validation-method DNS
```

Add the DNS validation CNAME to your internal DNS provider. Once ACM shows the certificate as
`Issued`, set `acm_certificate_arn` in `terraform.tfvars` and re-apply:

```bash
terraform apply
```

---

## Phase 4 — Container Image + ECS Service

```bash
cd terraform/aws
ECR=$(terraform output -raw ecr_repository_url)
GIT_SHA=$(git -C ../../ rev-parse --short HEAD)

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin "$(echo $ECR | cut -d/ -f1)"

docker build --platform linux/amd64 -t $ECR:$GIT_SHA ../../
docker push $ECR:$GIT_SHA
```

Set `container_image` in `terraform.tfvars` to the full URI (e.g.
`"123456789012.dkr.ecr.us-east-1.amazonaws.com/chkhealth:abc1234"`) and re-apply.
The ECS task definition and service are created at this step.

```bash
terraform apply
```

---

## Phase 5 — First Admin User

Wait for the service to stabilize:

```bash
CLUSTER=$(terraform output -raw ecs_cluster_name)
aws ecs wait services-stable --cluster $CLUSTER --services chkhealth
echo "Service stable"
```

Open an exec session into the running task:

```bash
TASK=$(aws ecs list-tasks --cluster $CLUSTER --service chkhealth \
  --query taskArns[0] --output text | awk -F/ '{print $NF}')

aws ecs execute-command \
  --cluster $CLUSTER --task $TASK --container chkhealth \
  --interactive \
  --command "uv run python manage_users.py add admin --role admin"
```

You will be prompted to set a password.

> **ECS Exec note:** requires the AWS CLI Session Manager plugin. Install it from the
> [AWS Systems Manager documentation](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)
> if the command fails with "SessionManagerPlugin is not found". Also wait 10–30 seconds
> after the task reaches `RUNNING` before retrying if you see "TargetNotConnected".

---

## Phase 6 — DNS

In your private hosted zone or internal DNS, create a CNAME:

```
chkhealth.corp.example.com  →  <alb_dns_name from terraform output>
```

Verify from inside the VPN:

```bash
curl -sk https://chkhealth.corp.example.com/healthz
```

---

## Authentication Setup

### Local Users

The admin account created in Phase 5 is the bootstrap account. Use it to log in and manage
additional users through the Admin UI (`/admin`). For CLI management from inside the container:

```bash
CLUSTER=$(terraform output -raw ecs_cluster_name)
TASK=$(aws ecs list-tasks --cluster $CLUSTER --service chkhealth \
  --query taskArns[0] --output text | awk -F/ '{print $NF}')

# Add a viewer-role user
aws ecs execute-command --cluster $CLUSTER --task $TASK --container chkhealth \
  --interactive --command "uv run python manage_users.py add alice --role viewer"

# List all users
aws ecs execute-command --cluster $CLUSTER --task $TASK --container chkhealth \
  --interactive --command "uv run python manage_users.py list"
```

> **Keep the local admin account.** It is your only recovery path if the remote auth
> provider is unreachable.

See [authentication.md](authentication.md) for the full user and group management reference.

### RADIUS Groups

To delegate authentication to a RADIUS server, store the shared secret in Secrets Manager and
add the RADIUS environment variables to the task definition.

**Step 1 — Store the RADIUS shared secret:**

```bash
RADIUS_SECRET_ARN=$(aws secretsmanager create-secret \
  --name chkhealth/RADIUS_SECRET \
  --secret-string "YOUR_RADIUS_SHARED_SECRET" \
  --query ARN --output text)
echo "RADIUS_SECRET_ARN=$RADIUS_SECRET_ARN"
```

**Step 2 — Grant the task execution role access:**

```bash
# Get the current execution role policy document, add RADIUS_SECRET_ARN to the Resource list,
# and put the updated policy:
aws iam put-role-policy \
  --role-name chkhealth-task-execution-role \
  --policy-name chkhealth-secrets \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
      \"Effect\": \"Allow\",
      \"Action\": \"secretsmanager:GetSecretValue\",
      \"Resource\": [
        \"$(aws secretsmanager describe-secret --secret-id chkhealth/SECRET_KEY --query ARN --output text)\",
        \"$(aws secretsmanager describe-secret --secret-id chkhealth/CP_API_KEY  --query ARN --output text)\",
        \"$RADIUS_SECRET_ARN\"
      ]
    }]
  }"
```

**Step 3 — Register a new task definition revision with RADIUS variables:**

Retrieve the current task definition, add the RADIUS entries, and register a new revision:

```bash
# Fetch current definition
aws ecs describe-task-definition --task-definition chkhealth \
  --query taskDefinition > /tmp/td.json

# Edit /tmp/td.json — in the containerDefinitions[0].environment array, add:
# { "name": "RADIUS_ENABLED",      "value": "true"           }
# { "name": "RADIUS_HOST",         "value": "10.x.x.x"       }
# { "name": "RADIUS_PORT",         "value": "1812"            }
# { "name": "RADIUS_GROUP_ADMIN",  "value": "network-admins"  }
# { "name": "RADIUS_GROUP_VIEWER", "value": "network-viewers" }
#
# In the containerDefinitions[0].secrets array, add:
# { "name": "RADIUS_SECRET", "valueFrom": "$RADIUS_SECRET_ARN" }

aws ecs register-task-definition --cli-input-json file:///tmp/td.json
aws ecs update-service --cluster chkhealth --service chkhealth --force-new-deployment
aws ecs wait services-stable --cluster chkhealth --services chkhealth
```

**Role resolution:** the RADIUS server must return `Filter-Id` (attribute 11) or `Class`
(attribute 25) reply attributes containing the group name. Values are matched
case-insensitively (substring). See [authentication.md](authentication.md) for all RADIUS
variables and role resolution rules.

**Smoke test** (run inside the container via execute-command):

```bash
uv run python -c "
from app.radius_auth import authenticate
print(authenticate('testuser', 'testpass',
    host='10.x.x.x', port=1812,
    secret='YOUR_SECRET', timeout=5,
    group_admin='network-admins',
    group_viewer='network-viewers'))
"
```

### Groups (RBAC)

After creating users, configure groups in the Admin UI (`/admin → Groups`) to control which
tabs and Check Point domains each user (or RADIUS group) can access.
See [authentication.md](authentication.md#groups) for the group model and an example
`groups.json`.

---

## Rotating the CP API Key

1. Generate a new read-only API key on the MDS CLI:
   ```bash
   mgmt_cli add api-key user-name <username> --format json
   ```
2. Write the new value to Secrets Manager:
   ```bash
   cd terraform/aws
   aws secretsmanager put-secret-value \
     --secret-id "$(terraform output -raw cp_api_key_arn)" \
     --secret-string "NEW_CP_API_KEY"
   ```
3. Force a new deployment so the task picks up the updated secret:
   ```bash
   aws ecs update-service --cluster chkhealth --service chkhealth --force-new-deployment
   aws ecs wait services-stable --cluster chkhealth --services chkhealth
   ```

---

## Deploying Updates

```bash
cd terraform/aws
ECR=$(terraform output -raw ecr_repository_url)
NEW_GIT_SHA=$(git -C ../../ rev-parse --short HEAD)

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin "$(echo $ECR | cut -d/ -f1)"

docker build --platform linux/amd64 -t $ECR:$NEW_GIT_SHA ../../
docker push $ECR:$NEW_GIT_SHA

aws ecs update-service --cluster chkhealth --service chkhealth --force-new-deployment
aws ecs wait services-stable --cluster chkhealth --services chkhealth && echo "Deployed"
```

Update `container_image` in `terraform.tfvars` to the new SHA to keep Terraform state consistent.

---

## Quick Reference

```bash
# Tail logs
aws logs tail /ecs/chkhealth --follow

# Open exec session
CLUSTER=$(cd terraform/aws && terraform output -raw ecs_cluster_name)
TASK=$(aws ecs list-tasks --cluster $CLUSTER --service chkhealth \
  --query taskArns[0] --output text | awk -F/ '{print $NF}')
aws ecs execute-command --cluster $CLUSTER --task $TASK --container chkhealth \
  --interactive --command /bin/bash

# Force restart
aws ecs update-service --cluster chkhealth --service chkhealth --force-new-deployment
```

---

## Troubleshooting

### Task immediately unhealthy or stops

```bash
aws logs tail /ecs/chkhealth --follow
```

Common causes:
- `SECRET_KEY is not set or is the insecure default` — the Secrets Manager secret ARN is wrong
  or the task execution role lacks `secretsmanager:GetSecretValue`.
- `Permission denied` writing to `/app/data` — the EFS access point POSIX owner must be
  UID/GID 1000. Re-check Phase 2d in the Terraform module.
- Gunicorn exits immediately — usually a Python import error; the full traceback is in the
  CloudWatch log stream.

### `execute-command` returns "TargetNotConnected"

The SSM agent takes 10–30 seconds after the task reaches `RUNNING`. Wait and retry. Confirm
the task role has the `ssmmessages:*` policy.

### EFS mount times out on task startup

Verify EFS mount targets exist in the same AZs as the private subnets used by the ECS service.
Verify the EFS security group allows TCP 2049 inbound from the ECS task SG.

### Session cookies not marked Secure

Confirm `COOKIE_SECURE=true` is in the task definition environment block — the Terraform module
sets this automatically. Without it, Flask does not set the `Secure` attribute on session cookies
even though the ALB terminates HTTPS.

### RADIUS authentication failing

Run the smoke test from inside the container. Confirm the RADIUS server is reachable from the
ECS task's private subnet (outbound UDP 1812 must be allowed in the ECS task SG).
Check that `Filter-Id` or `Class` attributes are returned by the RADIUS server for the test user.
