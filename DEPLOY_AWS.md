# AWS Deployment Guide

## Architecture

```
Internet → EC2 t2.micro (ECS agent)
               └── groceror-api container (FastAPI)
                       ├── publishes → SQS user_events_queue → Lambda (groceror-users)
                       ├── publishes → SQS email_queue        → Lambda (groceror-email)
                       └── publishes → SQS order_queue        → Lambda (groceror-orders)
```

All sensitive config lives in **SSM Parameter Store** — nothing is committed to git.

---

## Cost expectations (free tier)

| Resource | Free tier | Cost if exceeded |
|---|---|---|
| EC2 t2.micro | 750 hrs/month for 12 months | ~$8.50/month after |
| Lambda | 1 M requests + 400K GB-s/month forever | fractions of a cent/month |
| SQS | 1 M requests/month forever | ~$0.40 per million |
| ECR | 500 MB/month | $0.10/GB after |
| Elastic IP | Free while attached to running instance | $0.005/hr if unattached |
| CloudWatch logs | 5 GB ingest + 5 GB storage/month | $0.50/GB after |

**Bottom line:** within free-tier limits this stack costs $0/month. After the 12-month t2.micro free tier expires it will be ~$8.50/month.

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

```bash
aws cloudformation describe-stacks \
  --stack-name groceror-infra-prod \
  --query "Stacks[0].Outputs[?OutputKey=='GrocerPublicIP'].OutputValue" \
  --output text
```

The API will be reachable at `http://<IP>:8000`.

---

## Redeploying after code changes

```bash
# Rebuild and push
docker build -t groceror-api /code/groceror
docker tag groceror-api:latest $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/groceror-api:latest
docker push $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/groceror-api:latest
aws ecs update-service --cluster groceror-cluster-prod --service groceror-api-prod --force-new-deployment --region us-east-1

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
3. Removes the infra CloudFormation stack (ECS, EC2, EIP, SQS, ECR, IAM, budget, alarm)
4. Releases any unattached Elastic IPs (these cost $0.005/hr even when idle)
5. Deletes SSM Parameter Store secrets under `/groceror/<stage>/`
6. Cleans up Serverless Framework deployment S3 buckets
7. Verifies no billable resources remain

After the script completes, check **AWS Billing → Cost Explorer** and **Billing → Free Tier Usage** to confirm $0 ongoing charges. Allow 10–15 minutes for the billing dashboard to refresh.

### Emergency stop (if costs spike unexpectedly)

If you receive a $10 budget alert and need to stop charges immediately without using the script:

```bash
# 1. Stop the ECS service (stops the EC2 task immediately)
aws ecs update-service \
  --cluster groceror-cluster-prod \
  --service groceror-api-prod \
  --desired-count 0 \
  --region us-east-1

# 2. Terminate the EC2 instance
INSTANCE_ID=$(aws ec2 describe-instances \
  --region us-east-1 \
  --filters "Name=tag:aws:cloudformation:stack-name,Values=groceror-infra-prod" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" --region us-east-1

# 3. Then run the full teardown when you're ready
./teardown_aws.sh
```
