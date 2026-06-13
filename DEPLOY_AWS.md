# AWS Deployment Guide

## Architecture

```
Internet → ECS Fargate task (0.25 vCPU / 512 MB)
               └── groceror-api container (FastAPI)
                       ├── publishes → SQS user_events_queue → Lambda (groceror-users)
                       ├── publishes → SQS email_queue        → Lambda (groceror-email)
                       └── publishes → SQS order_queue        → Lambda (groceror-orders)
```

All sensitive config lives in **SSM Parameter Store** — nothing is committed to git.

---

## Cost expectations

| Resource | Free tier | Ongoing cost |
|---|---|---|
| ECS Fargate (0.25 vCPU + 0.5 GB) | None | ~$9.50/month |
| Lambda | 1 M requests + 400K GB-s/month forever | ~$0/month |
| SQS | 1 M requests/month forever | ~$0/month |
| ECR | 500 MB/month | $0.10/GB after |
| CloudWatch logs | 5 GB ingest + 5 GB storage/month | $0.50/GB after |

**Bottom line:** approximately **$9.50/month** to keep the Fargate task running continuously. Stop the task (desired count → 0) when not in use to pay only for the time it runs.

The `serverless.yml` includes an AWS Budget that sends email alerts to `siddharth.gangadhar@gmail.com` at **$5 (50%)**, **$8 (80%)**, **$10 (100%)**, and a forecasted overrun. A CloudWatch billing alarm fires at $8 actual spend.

### One-time prerequisite: enable billing alerts

AWS does not publish billing metrics by default. Do this once in your account before deploying:

1. Open [Billing Preferences](https://us-east-1.console.aws.amazon.com/billing/home#/preferences)
2. Check **"Receive Billing Alerts"** → Save

---

## Prerequisites

```bash
npm install -g serverless          # Serverless Framework v3
pip install awscli                 # AWS CLI
aws configure                      # set Access Key, Secret, region (us-east-1)
```

---

## Step 1 — Store secrets in SSM Parameter Store

Replace `...` with your real values:

```bash
STAGE=prod
REGION=us-east-1

aws ssm put-parameter --region $REGION --name /groceror/$STAGE/DATABASE_URL    --value "postgresql://..." --type SecureString
aws ssm put-parameter --region $REGION --name /groceror/$STAGE/JWT_SECRET_KEY  --value "your-secret"     --type SecureString
aws ssm put-parameter --region $REGION --name /groceror/$STAGE/TWILIO_ACCOUNT_SID --value "AC..."        --type SecureString
aws ssm put-parameter --region $REGION --name /groceror/$STAGE/TWILIO_AUTH_TOKEN  --value "..."          --type SecureString
aws ssm put-parameter --region $REGION --name /groceror/$STAGE/TWILIO_FROM_NUMBER --value "+1..."        --type SecureString
aws ssm put-parameter --region $REGION --name /groceror/$STAGE/MONGO_URI           --value "mongodb+srv://..." --type SecureString

# groceror-email SMTP (if using email notifications)
aws ssm put-parameter --region $REGION --name /groceror/$STAGE/SMTP_HOST --value "smtp.gmail.com" --type String
aws ssm put-parameter --region $REGION --name /groceror/$STAGE/SMTP_PORT --value "587"            --type String
aws ssm put-parameter --region $REGION --name /groceror/$STAGE/SMTP_USER --value "you@gmail.com"  --type SecureString
aws ssm put-parameter --region $REGION --name /groceror/$STAGE/SMTP_PASS --value "app-password"   --type SecureString
```

---

## Step 2 — Deploy infrastructure (ECS + SQS + ECR)

```bash
cd /code/groceror
serverless deploy --stage prod --region us-east-1
```

This creates:
- SQS queues (user_events_queue, email_queue, order_queue) + their DLQs
- ECR repository `groceror-api`
- ECS cluster + t2.micro EC2 instance + Elastic IP
- IAM roles for EC2 and ECS tasks
- CloudFormation exports so companion stacks can import queue ARNs

---

## Step 3 — Build and push the Docker image

```bash
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1

# Authenticate Docker with ECR
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$REGION.amazonaws.com

cd /code/groceror
docker build -t groceror-api .
docker tag groceror-api:latest $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/groceror-api:latest
docker push $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/groceror-api:latest
```

After the push, force the ECS service to pull the new image:

```bash
aws ecs update-service \
  --cluster groceror-cluster-prod \
  --service groceror-api-prod \
  --force-new-deployment \
  --region us-east-1
```

---

## Step 4 — Deploy companion Lambda services

Each service reads the queue ARNs from the infra stack's CloudFormation exports.

```bash
cd /code/groceror-users
serverless deploy --stage prod --region us-east-1

cd /code/groceror-email
serverless deploy --stage prod --region us-east-1

cd /code/groceror-orders
serverless deploy --stage prod --region us-east-1
```

---

## Step 5 — Find your API URL

Fargate tasks get a dynamic public IP (it changes on each restart). Look it up with:

```bash
REGION=us-east-1
CLUSTER=groceror-cluster-prod
SERVICE=groceror-api-prod

TASK_ARN=$(aws ecs list-tasks \
  --cluster $CLUSTER --service-name $SERVICE \
  --query 'taskArns[0]' --output text --region $REGION)

ENI_ID=$(aws ecs describe-tasks \
  --cluster $CLUSTER --tasks $TASK_ARN --region $REGION \
  --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
  --output text)

aws ec2 describe-network-interfaces \
  --network-interface-ids $ENI_ID --region $REGION \
  --query 'NetworkInterfaces[0].Association.PublicIp' --output text
```

The API will be reachable at `http://<IP>:8000`.

> **Tip:** if you need a stable URL, put an Application Load Balancer in front of the service (adds ~$16/month), or use a free DNS provider that supports dynamic IPs.

---

## Stopping the task to avoid charges

Since Fargate charges by the second, you can bring the cost to $0 by scaling down to zero tasks when not in use:

```bash
# Scale to zero (no charges while stopped)
aws ecs update-service \
  --cluster groceror-cluster-prod \
  --service groceror-api-prod \
  --desired-count 0 \
  --region us-east-1

# Scale back up when needed
aws ecs update-service \
  --cluster groceror-cluster-prod \
  --service groceror-api-prod \
  --desired-count 1 \
  --region us-east-1
```

---

## Redeploying after code changes

```bash
# Rebuild and push
docker build -t groceror-api /code/groceror
docker tag groceror-api:latest $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/groceror-api:latest
docker push $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/groceror-api:latest

# Force the service to pull the new image
aws ecs update-service \
  --cluster groceror-cluster-prod \
  --service groceror-api-prod \
  --force-new-deployment \
  --region us-east-1

# Companion services — just redeploy
cd /code/groceror-users && serverless deploy --stage prod
```

---

## Teardown — returning to zero cost

Use the teardown script to remove everything in the correct order and confirm no resources are left behind:

```bash
cd /code/groceror
./teardown_aws.sh           # tears down 'prod' stage
# or
./teardown_aws.sh staging   # for a different stage
```

The script:
1. Removes Lambda stacks first (they import CloudFormation exports from the infra stack)
2. Empties the ECR repository (CloudFormation can't delete a non-empty repo)
3. Removes the infra CloudFormation stack (ECS Fargate, VPC, SQS, ECR, IAM, budget, alarm)
4. Deletes SSM Parameter Store secrets under `/groceror/<stage>/`
5. Cleans up Serverless Framework deployment S3 buckets
6. Verifies no billable resources remain

After the script completes, check **AWS Billing → Cost Explorer** to confirm $0 ongoing charges. Allow 10–15 minutes for the billing dashboard to refresh.

### Emergency stop (if costs spike unexpectedly)

If you receive a $10 budget alert and need to stop Fargate charges immediately:

```bash
# Scale the service to zero — Fargate charges stop within seconds
aws ecs update-service \
  --cluster groceror-cluster-prod \
  --service groceror-api-prod \
  --desired-count 0 \
  --region us-east-1

# Then run the full teardown when you're ready
cd /code/groceror && ./teardown_aws.sh
```
