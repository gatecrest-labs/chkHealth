# chkHealth — AWS Terraform (ECS Fargate)

Provisions a fully internal deployment of chkHealth on AWS ECS Fargate. No resource is
internet-accessible — all inbound traffic arrives via Site-to-Site VPN or Direct Connect.

## What gets created

| Resource | Purpose |
|---|---|
| VPC + private/public subnets (2 AZs) | Network isolation |
| Single NAT Gateway + Elastic IP | Static egress IP for internet-bound traffic (ECR, AWS APIs) only |
| Private NAT Gateway + dedicated subnet | **Static egress IP** for CP MDS/SMTP/RADIUS/SNMP (on-prem) allowlisting |
| Internal ALB (scheme=internal) | **Stable private ingress** — WAN-only, not internet-facing |
| ACM-managed TLS certificate | HTTPS on the internal ALB (add after initial apply) |
| ECS Fargate cluster + service | Single-replica container runtime |
| EFS + access point | Persistent data (`/app/data`) |
| ECR repository | Container image storage |
| Secrets Manager | `SECRET_KEY` and `CP_API_KEY` |
| KMS key | EFS at-rest encryption + Secrets Manager CMK |
| IAM task execution + task roles | Least-privilege ECR/Secrets/EFS/SSM access |
| CloudWatch log group | Container stdout/stderr |

## Prerequisites

- Terraform >= 1.6
- AWS CLI configured with permissions for VPC, ECR, ECS, EFS, ALB, IAM, Secrets Manager, KMS
- Docker (for building and pushing the image)
- Site-to-Site VPN or Direct Connect already attached to the AWS account

## Deployment

### Phase 1 — infrastructure

```bash
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: wan_cidr_blocks, cp_mds_primary at minimum

terraform init
terraform apply
```

Outputs include `ecr_repository_url`, `nat_gateway_public_ip`, `private_nat_gateway_ip`,
`secret_key_arn`, `cp_api_key_arn`.

**Give `private_nat_gateway_ip` to your network team for allowlisting on CP MDS/SMTP/RADIUS —
see [Static egress IP for on-prem traffic](#static-egress-ip-for-on-prem-traffic-provider-1-radius-smtp-snmp)
below.** `nat_gateway_public_ip` only covers internet-bound traffic (ECR, AWS APIs).

### Phase 2 — secrets

```bash
# Generate SECRET_KEY (run from the chkHealth repo root)
uv run python manage_users.py secret

aws secretsmanager put-secret-value \
  --secret-id "$(terraform output -raw secret_key_arn)" \
  --secret-string "PASTE_GENERATED_KEY"

aws secretsmanager put-secret-value \
  --secret-id "$(terraform output -raw cp_api_key_arn)" \
  --secret-string "YOUR_CP_API_KEY"
```

### Phase 3 — ACM certificate

Request a certificate for the internal hostname (e.g. `chkhealth.corp.example.com`) and add
the DNS validation CNAME to your internal DNS:

```bash
aws acm request-certificate \
  --domain-name chkhealth.corp.example.com \
  --validation-method DNS
```

Set `acm_certificate_arn` in `terraform.tfvars` once the certificate is issued.

### Phase 4 — container image + ECS service

```bash
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ECR=$(terraform output -raw ecr_repository_url)
GIT_SHA=$(git -C ../../ rev-parse --short HEAD)

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin $ECR

docker build --platform linux/amd64 -t $ECR:$GIT_SHA ../../
docker push $ECR:$GIT_SHA

# Set container_image in terraform.tfvars, then:
terraform apply
```

### Phase 5 — first admin user

```bash
CLUSTER=$(terraform output -raw ecs_cluster_name)
TASK=$(aws ecs list-tasks --cluster $CLUSTER --service chkhealth \
  --query taskArns[0] --output text | awk -F/ '{print $NF}')

aws ecs execute-command \
  --cluster $CLUSTER --task $TASK --container chkhealth \
  --interactive \
  --command "uv run python manage_users.py add admin --role admin"
```

### Phase 6 — DNS

In your private hosted zone, create a CNAME from `chkhealth.corp.example.com` to
`$(terraform output -raw alb_dns_name)`.

## Static egress IP for on-prem traffic (Provider-1, RADIUS, SMTP, SNMP)

The ECS task runs in its own dedicated subnet/route table (`<app_name>-ecs-task`), separate from
the internal ALB's subnets. This matters: the ALB's security group only admits `wan_cidr_blocks`
sources, so every ALB client is itself inside `wan_cidr_blocks` — if the ECS task shared a route
table with the ALB, redirecting `wan_cidr_blocks` traffic to the private NAT gateway would also
redirect the ALB's own reply traffic to every client, breaking inbound access to the app
entirely. Keeping the task in its own subnet avoids that.

Traffic to `wan_cidr_blocks` and `cp_mds_primary` (Provider-1) from the ECS task is routed through
a dedicated private NAT Gateway, giving it one stable source IP — unlike the public NAT Gateway's
IP, which only covers internet-bound traffic (ECR, AWS APIs) and is unaffected by any of this.

```bash
terraform output -raw private_nat_gateway_ip
```

Hand this IP to your network/firewall team to allow-list on Provider-1 (and any future on-prem
service this container reaches). It is stable across ECS task restarts, redeployments, and
`terraform apply` runs — it only changes if the `aws_nat_gateway.private` resource itself is
destroyed and recreated.

**You must set `vpn_gateway_id` (for a Virtual Private Gateway) or `transit_gateway_id` (for a
Transit Gateway — the gateway ID `tgw-...`, not the attachment ID `tgw-attach-...`) in
`terraform.tfvars` for this to work at all.** The ECS task's subnet is new and starts with no
route to the corporate network — unlike the old shared subnet, there is no existing
VGW-propagated or manually-added route to fall back to. Leaving both unset means `terraform
apply` still succeeds, but CP MDS/RADIUS/SMTP/SNMP traffic is blackholed, not merely
"not yet optimized" — the ECS task itself loses on-prem connectivity, not just the static IP
benefit, until one of these is set and you re-apply.

## Updating the application

```bash
docker build --platform linux/amd64 -t $ECR:$NEW_GIT_SHA ../../
docker push $ECR:$NEW_GIT_SHA
aws ecs update-service --cluster chkhealth --service chkhealth --force-new-deployment
```

Update `container_image` in `terraform.tfvars` to the new SHA for Terraform state consistency.

## Note on existing deployment docs

`docs/deployment-aws-ecs.md` shows an **internet-facing** ALB (`scheme internet-facing`).
This Terraform deploys an **internal** ALB instead. The Fargate task, EFS, and container
configuration are otherwise identical.
