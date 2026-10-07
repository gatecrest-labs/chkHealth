# AWS ECS Fargate Deployment Guide

Deploy chkHealth on AWS ECS Fargate with:
- **EFS** for persistent data (users, groups, settings, metrics)
- **ALB** for HTTPS with an ACM-managed certificate
- **Secrets Manager** for `SECRET_KEY` and `CP_API_KEY`
- **ECR** as the container registry

> **Single-replica constraint.** chkHealth uses SQLite for metrics and
> startup coordination. Run exactly one Fargate task at all times —
> do not enable auto-scaling to > 1.

## Prerequisites

- AWS CLI v2 configured (`aws configure`) with permissions to create
  ECR, ECS, EFS, ALB, IAM, ACM, and Secrets Manager resources
- Docker installed locally (for building and pushing the image)
- An existing VPC with at least two public subnets and two private
  subnets across two AZs
- A registered domain name with DNS you can edit (for ACM DNS validation)

Set these shell variables once; they are reused throughout this guide:

```bash
export AWS_REGION=us-east-1          # change to your region
export AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export APP=chkhealth
export VPC_ID=vpc-xxxxxxxxxxxxxxxxx  # your VPC
```

---

## Phase 1 — Container Registry (ECR)

```bash
# Create the repository
aws ecr create-repository \
  --repository-name $APP \
  --region $AWS_REGION

# Authenticate Docker to ECR
aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS \
      --password-stdin $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com

# Build and push the initial image
docker build --platform linux/amd64 -t $APP .
docker tag $APP:latest \
  $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$APP:latest
docker push \
  $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$APP:latest
```

---

## Phase 2 — EFS Persistent Volume

### 2a. Create the file system

```bash
EFS_ID=$(aws efs create-file-system \
  --performance-mode generalPurpose \
  --throughput-mode bursting \
  --tags Key=Name,Value=$APP \
  --query FileSystemId --output text)
echo "EFS_ID=$EFS_ID"
```

### 2b. Create a security group for EFS

```bash
EFS_SG=$(aws ec2 create-security-group \
  --group-name $APP-efs-sg \
  --description "chkhealth EFS mount targets" \
  --vpc-id $VPC_ID \
  --query GroupId --output text)
echo "EFS_SG=$EFS_SG"
```

NFS inbound from the ECS task SG is added in Phase 6 after the ECS SG exists.

### 2c. Create mount targets (one per AZ)

Run this once per private subnet:

```bash
# Repeat for each private subnet in your VPC
aws efs create-mount-target \
  --file-system-id $EFS_ID \
  --subnet-id subnet-xxxxxxxxxxxxxxx \
  --security-groups $EFS_SG
```

### 2d. Create the access point

```bash
AP_ID=$(aws efs create-access-point \
  --file-system-id $EFS_ID \
  --posix-user Uid=1000,Gid=1000 \
  --root-directory \
    "Path=/chkhealth-data,CreationInfo={OwnerUid=1000,OwnerGid=1000,Permissions=755}" \
  --tags Key=Name,Value=$APP \
  --query AccessPointId --output text)
echo "AP_ID=$AP_ID"
```

The container mounts this access point at `/app/data`. UID/GID 1000 matches
the `app` user in the container image.

---

## Phase 3 — Secrets Manager

Generate a `SECRET_KEY` locally (requires the app dependencies installed):

```bash
uv run python manage_users.py secret
```

Store the secrets (replace placeholder values):

```bash
aws secretsmanager create-secret \
  --name $APP/SECRET_KEY \
  --secret-string "PASTE_GENERATED_KEY_HERE"

aws secretsmanager create-secret \
  --name $APP/CP_API_KEY \
  --secret-string "PASTE_YOUR_CP_API_KEY_HERE"

# Capture the ARNs for use in the Task Definition
SECRET_KEY_ARN=$(aws secretsmanager describe-secret \
  --secret-id $APP/SECRET_KEY --query ARN --output text)
CP_API_KEY_ARN=$(aws secretsmanager describe-secret \
  --secret-id $APP/CP_API_KEY --query ARN --output text)
echo "SECRET_KEY_ARN=$SECRET_KEY_ARN"
echo "CP_API_KEY_ARN=$CP_API_KEY_ARN"
```

---

## Phase 4 — IAM Roles

### 4a. Task Execution Role

This role is used by ECS to pull the image from ECR, write logs to
CloudWatch, fetch secrets from Secrets Manager, and mount EFS.

```bash
# Create the role
aws iam create-role \
  --role-name $APP-task-execution-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Attach the managed ECS execution policy
aws iam attach-role-policy \
  --role-name $APP-task-execution-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Allow reading the two secrets
aws iam put-role-policy \
  --role-name $APP-task-execution-role \
  --policy-name $APP-secrets \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
      \"Effect\": \"Allow\",
      \"Action\": \"secretsmanager:GetSecretValue\",
      \"Resource\": [\"$SECRET_KEY_ARN\", \"$CP_API_KEY_ARN\"]
    }]
  }"

# Allow EFS mount
EFS_ARN="arn:aws:elasticfilesystem:$AWS_REGION:$AWS_ACCOUNT:file-system/$EFS_ID"
aws iam put-role-policy \
  --role-name $APP-task-execution-role \
  --policy-name $APP-efs \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
      \"Effect\": \"Allow\",
      \"Action\": [
        \"elasticfilesystem:ClientMount\",
        \"elasticfilesystem:ClientWrite\"
      ],
      \"Resource\": \"$EFS_ARN\"
    }]
  }"

EXEC_ROLE_ARN=$(aws iam get-role \
  --role-name $APP-task-execution-role --query Role.Arn --output text)
echo "EXEC_ROLE_ARN=$EXEC_ROLE_ARN"
```

### 4b. Task Role

The task role is assumed by the running application process. It needs
SSM Session Manager permissions so you can run `aws ecs execute-command`
to create the first admin user.

```bash
aws iam create-role \
  --role-name $APP-task-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

aws iam put-role-policy \
  --role-name $APP-task-role \
  --policy-name $APP-ecs-exec \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": [
        "ssmmessages:CreateControlChannel",
        "ssmmessages:CreateDataChannel",
        "ssmmessages:OpenControlChannel",
        "ssmmessages:OpenDataChannel"
      ],
      "Resource": "*"
    }]
  }'

TASK_ROLE_ARN=$(aws iam get-role \
  --role-name $APP-task-role --query Role.Arn --output text)
echo "TASK_ROLE_ARN=$TASK_ROLE_ARN"
```

---

## Phase 5 — Task Definition

Create `task-definition.json` (save locally; not committed to git):

```bash
cat > task-definition.json << EOF
{
  "family": "$APP",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "$EXEC_ROLE_ARN",
  "taskRoleArn": "$TASK_ROLE_ARN",
  "containerDefinitions": [
    {
      "name": "$APP",
      "image": "$AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$APP:latest",
      "portMappings": [
        { "containerPort": 8080, "protocol": "tcp" }
      ],
      "environment": [
        { "name": "COOKIE_SECURE",        "value": "true" },
        { "name": "CP_MDS_PRIMARY",       "value": "10.x.x.x" },
        { "name": "CP_MDS_PRIMARY_LABEL", "value": "HQ MDS (Provider-1)" },
        { "name": "CP_VERIFY_SSL",        "value": "false" },
        { "name": "CP_TIMEOUT",           "value": "30" },
        { "name": "GAIA_TIMEOUT",         "value": "15" }
      ],
      "secrets": [
        { "name": "SECRET_KEY", "valueFrom": "$SECRET_KEY_ARN" },
        { "name": "CP_API_KEY", "valueFrom": "$CP_API_KEY_ARN" }
      ],
      "mountPoints": [
        {
          "sourceVolume": "$APP-data",
          "containerPath": "/app/data",
          "readOnly": false
        }
      ],
      "healthCheck": {
        "command": [
          "CMD-SHELL",
          "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')\" || exit 1"
        ],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 30
      },
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/$APP",
          "awslogs-region": "$AWS_REGION",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "essential": true
    }
  ],
  "volumes": [
    {
      "name": "$APP-data",
      "efsVolumeConfiguration": {
        "fileSystemId": "$EFS_ID",
        "transitEncryption": "ENABLED",
        "authorizationConfig": {
          "accessPointId": "$AP_ID",
          "iam": "ENABLED"
        }
      }
    }
  ]
}
EOF
```

Create the CloudWatch log group and register the task definition:

```bash
aws logs create-log-group --log-group-name /ecs/$APP

TASK_DEF_ARN=$(aws ecs register-task-definition \
  --cli-input-json file://task-definition.json \
  --query taskDefinition.taskDefinitionArn --output text)
echo "TASK_DEF_ARN=$TASK_DEF_ARN"
```

> **Important:** `COOKIE_SECURE=true` must be present in the `environment`
> block. Without it, Flask will not set the `Secure` attribute on session
> cookies even though HTTPS is handled by the ALB. Browsers will transmit
> the cookie over HTTP if this is missing.

Fill in your actual `CP_MDS_PRIMARY` and other optional appliance
addresses (see `.env.example` for all supported variables) in the
`environment` block before registering.

---

## Phase 6 — Security Groups

```bash
# ALB security group
ALB_SG=$(aws ec2 create-security-group \
  --group-name $APP-alb-sg \
  --description "chkhealth ALB" \
  --vpc-id $VPC_ID \
  --query GroupId --output text)
aws ec2 authorize-security-group-ingress \
  --group-id $ALB_SG --protocol tcp --port 443 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress \
  --group-id $ALB_SG --protocol tcp --port 80 --cidr 0.0.0.0/0
echo "ALB_SG=$ALB_SG"

# ECS task security group
ECS_SG=$(aws ec2 create-security-group \
  --group-name $APP-ecs-sg \
  --description "chkhealth ECS task" \
  --vpc-id $VPC_ID \
  --query GroupId --output text)
aws ec2 authorize-security-group-ingress \
  --group-id $ECS_SG --protocol tcp --port 8080 --source-group $ALB_SG
# Outbound: NFS to EFS, HTTPS to CP MDS appliances + Secrets Manager
aws ec2 authorize-security-group-egress \
  --group-id $ECS_SG --protocol tcp --port 2049 --source-group $EFS_SG
aws ec2 authorize-security-group-egress \
  --group-id $ECS_SG --protocol tcp --port 443 --cidr 0.0.0.0/0
echo "ECS_SG=$ECS_SG"

# Allow EFS to accept NFS from the ECS task SG
aws ec2 authorize-security-group-ingress \
  --group-id $EFS_SG --protocol tcp --port 2049 --source-group $ECS_SG
```

---

## Phase 7 — ALB, ACM Certificate + Target Group

The target group must exist before the ECS service is created so the
service can wire up the load balancer in a single step.

### 7a. Request an ACM certificate

Start this first — DNS validation takes a few minutes.

```bash
CERT_ARN=$(aws acm request-certificate \
  --domain-name chkhealth.yourdomain.com \
  --validation-method DNS \
  --query CertificateArn --output text)
echo "CERT_ARN=$CERT_ARN"
```

Add the CNAME record shown in the ACM console to your DNS provider.

### 7b. Create the ALB

```bash
ALB_ARN=$(aws elbv2 create-load-balancer \
  --name $APP \
  --type application \
  --scheme internet-facing \
  --subnets subnet-xxxxxxxx subnet-yyyyyyyy \
  --security-groups $ALB_SG \
  --query LoadBalancers[0].LoadBalancerArn --output text)
echo "ALB_ARN=$ALB_ARN"
```

Replace the subnet IDs with your **public** subnet IDs.

### 7c. Create the target group

```bash
TG_ARN=$(aws elbv2 create-target-group \
  --name $APP \
  --protocol HTTP \
  --port 8080 \
  --vpc-id $VPC_ID \
  --target-type ip \
  --health-check-path /healthz \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3 \
  --health-check-interval-seconds 30 \
  --query TargetGroups[0].TargetGroupArn --output text)
echo "TG_ARN=$TG_ARN"
```

---

## Phase 8 — ECS Cluster + Service

### 8a. Wait for the ACM certificate to be issued

```bash
aws acm wait certificate-validated --certificate-arn $CERT_ARN
echo "Certificate issued"
```

### 8b. Create the ECS cluster

```bash
aws ecs create-cluster --cluster-name $APP
```

### 8c. Create the ECS service

The `--load-balancers` flag wires the target group at service creation
time — this is the recommended approach and avoids post-hoc updates.

```bash
aws ecs create-service \
  --cluster $APP \
  --service-name $APP \
  --task-definition $TASK_DEF_ARN \
  --desired-count 1 \
  --launch-type FARGATE \
  --enable-execute-command \
  --deployment-configuration \
    "deploymentCircuitBreaker={enable=true,rollback=true}" \
  --load-balancers \
    "targetGroupArn=$TG_ARN,containerName=$APP,containerPort=8080" \
  --network-configuration \
    "awsvpcConfiguration={
       subnets=[subnet-xxxxxxxx,subnet-yyyyyyyy],
       securityGroups=[$ECS_SG],
       assignPublicIp=DISABLED
     }"
```

Replace `subnet-xxxxxxxx,subnet-yyyyyyyy` with your two **private** subnet IDs.
The task gets no public IP; it is only reachable from the ALB via the
security group.

### 8d. Add ALB listeners

```bash
# HTTP → HTTPS redirect
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTP --port 80 \
  --default-actions \
    "Type=redirect,RedirectConfig={Protocol=HTTPS,Port=443,StatusCode=HTTP_301}"

# HTTPS → target group
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTPS --port 443 \
  --certificates CertificateArn=$CERT_ARN \
  --default-actions \
    "Type=forward,TargetGroupArn=$TG_ARN"
```

### 8e. Create a DNS record

In your DNS provider, create a CNAME from `chkhealth.yourdomain.com` to
the ALB DNS name:

```bash
aws elbv2 describe-load-balancers \
  --load-balancer-arns $ALB_ARN \
  --query LoadBalancers[0].DNSName --output text
```

---

## Phase 9 — Create the First Admin User

Wait for the task to reach `RUNNING` state:

```bash
aws ecs wait services-stable --cluster $APP --services $APP
```

Get the task ID:

```bash
TASK_ID=$(aws ecs list-tasks --cluster $APP --service $APP \
  --query taskArns[0] --output text | awk -F/ '{print $NF}')
echo "TASK_ID=$TASK_ID"
```

Open an interactive shell into the running task and create the admin user:

```bash
aws ecs execute-command \
  --cluster $APP \
  --task $TASK_ID \
  --container $APP \
  --interactive \
  --command "uv run python manage_users.py add admin --role admin"
```

You will be prompted to set a password. After this command completes,
open `https://chkhealth.yourdomain.com` and log in.

> **ECS Exec note:** `execute-command` requires the AWS CLI Session Manager
> plugin. Install it from the
> [AWS Systems Manager documentation](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)
> if the command fails with "SessionManagerPlugin is not found".

---

## Phase 10 — Deploying Updates

```bash
# Re-authenticate to ECR (tokens expire after 12 hours)
aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS \
      --password-stdin $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com

# Build and push the new image
docker build --platform linux/amd64 -t $APP .
docker tag $APP:latest \
  $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$APP:latest
docker push \
  $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$APP:latest

# Force ECS to pull the new image
aws ecs update-service \
  --cluster $APP \
  --service $APP \
  --force-new-deployment
```

ECS starts a new task, waits for it to pass health checks (`/healthz`), then
stops the old task. During the transition, two tasks briefly coexist — both
read from EFS. Because `desired_count = 1`, the overlap is short and writes
during the rollover window are unlikely for a low-traffic internal dashboard.

To monitor the rollout:

```bash
aws ecs wait services-stable --cluster $APP --services $APP && echo "Deployed"
```

---

## Troubleshooting

### Task immediately unhealthy / stops after start

Check CloudWatch logs at `/ecs/chkhealth`:

```bash
aws logs tail /ecs/$APP --follow
```

Common causes:
- `SECRET_KEY is not set or is the insecure default` — the Secrets Manager
  secret ARN in the Task Definition is wrong, or the Execution Role lacks
  `secretsmanager:GetSecretValue`.
- `Permission denied` writing to `/app/data` — the EFS access point POSIX
  owner is not UID/GID 1000. Re-check Phase 2d.
- Gunicorn exits immediately — usually a Python import error; the full
  traceback appears in the CloudWatch log stream.

### Session cookies not being marked Secure

Verify the Task Definition `environment` block contains
`"name": "COOKIE_SECURE", "value": "true"`. Without this, Flask does not
set the `Secure` attribute on cookies even when the ALB terminates HTTPS.
Re-register the Task Definition and force a new deployment.

### `aws ecs execute-command` returns "TargetNotConnected"

The SSM session manager agent is injected by ECS Fargate automatically, but
the connection takes 10–30 seconds after the task reaches `RUNNING`. Wait
and retry. Also confirm the Task Role has the `ssmmessages:*` policy from
Phase 4b.

### EFS mount times out on task startup

Verify the EFS mount targets exist in the same AZs as the private subnets
used by the ECS Service (Phase 2c). Verify the EFS security group allows
TCP 2049 inbound from `$ECS_SG` (Phase 6).
