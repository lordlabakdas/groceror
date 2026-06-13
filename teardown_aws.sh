#!/usr/bin/env bash
# teardown_aws.sh — Remove all groceror AWS resources and return to zero cost.
#
# Usage:
#   ./teardown_aws.sh              # tears down 'prod' stage
#   ./teardown_aws.sh staging      # tears down a different stage
#
# What this removes:
#   - Lambda functions + event source mappings (groceror-users, email, orders)
#   - SQS queues + DLQs (user_events, email, order)
#   - ECS service + task definition + cluster
#   - EC2 t2.micro instance + Elastic IP
#   - ECR repository + all images
#   - CloudWatch log group, billing alarm, SNS topic
#   - AWS Budget
#   - IAM roles + instance profile
#   - Serverless Framework deployment S3 buckets
#   - SSM Parameter Store secrets under /groceror/<stage>/
#
# What this does NOT remove:
#   - Your Supabase / external PostgreSQL database
#   - Your MongoDB Atlas cluster
#   - Your Twilio account
#   - AWS account-level settings

set -euo pipefail

STAGE=${1:-prod}
REGION=us-east-1

# ── Preflight ────────────────────────────────────────────────────────────────

command -v aws       >/dev/null 2>&1 || { echo "ERROR: aws CLI not found. Install with: pip install awscli"; exit 1; }
command -v serverless >/dev/null 2>&1 || { echo "ERROR: serverless not found. Install with: npm install -g serverless"; exit 1; }
command -v python3   >/dev/null 2>&1 || { echo "ERROR: python3 not found."; exit 1; }

ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) || {
  echo "ERROR: AWS credentials not configured. Run: aws configure"
  exit 1
}

echo ""
echo "========================================="
echo "  groceror AWS teardown"
echo "  Stage   : $STAGE"
echo "  Region  : $REGION"
echo "  Account : $ACCOUNT"
echo "========================================="
echo ""
echo "This will PERMANENTLY DELETE all groceror AWS resources in stage '$STAGE'."
echo "External services (Supabase, MongoDB, Twilio) are NOT affected."
echo ""
read -rp "Type 'yes' to continue: " confirm
[[ "$confirm" == "yes" ]] || { echo "Aborted."; exit 0; }
echo ""

# ── Helper ───────────────────────────────────────────────────────────────────

step() { echo ""; echo "── $* ──────────────────────────────────"; }
ok()   { echo "   ✓ $*"; }
warn() { echo "   ⚠ $*"; }

# ── Step 1: Remove companion Lambda stacks ───────────────────────────────────
# Must go first — they import CloudFormation exports from the infra stack.

step "Removing companion Lambda stacks"

# Script lives inside the groceror repo; companion services are sibling dirs.
REPO_PARENT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for svc in groceror-users groceror-email groceror-orders; do
  svc_dir="$REPO_PARENT/$svc"
  if [ -f "$svc_dir/serverless.yml" ]; then
    echo "   Removing $svc..."
    (cd "$svc_dir" && serverless remove --stage "$STAGE" --region "$REGION" 2>&1 \
      | grep -v "^Serverless" | grep -v "^\." || true) \
      && ok "$svc removed" \
      || warn "$svc stack not found or already removed — continuing"
  else
    warn "$svc_dir/serverless.yml not found — skipping"
  fi
done

# ── Step 2: Delete ECR images ─────────────────────────────────────────────────
# CloudFormation cannot delete a non-empty ECR repository.

step "Deleting ECR images for groceror-api"

ECR_REPO="groceror-api"
IMAGE_IDS=$(aws ecr list-images \
  --repository-name "$ECR_REPO" \
  --region "$REGION" \
  --query 'imageIds[*]' \
  --output json 2>/dev/null || echo "[]")

if [[ "$IMAGE_IDS" != "[]" && "$IMAGE_IDS" != "" ]]; then
  IMAGE_COUNT=$(echo "$IMAGE_IDS" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")
  aws ecr batch-delete-image \
    --repository-name "$ECR_REPO" \
    --region "$REGION" \
    --image-ids "$IMAGE_IDS" \
    --output text >/dev/null 2>&1 \
    && ok "Deleted $IMAGE_COUNT image(s) from ECR" \
    || warn "Could not delete ECR images — may fail during stack removal"
else
  ok "ECR repository is empty or does not exist"
fi

# ── Step 3: Remove infra stack ────────────────────────────────────────────────
# Deletes ECS, EC2, Elastic IP, SQS, ECR, IAM roles, budget, billing alarm.

step "Removing groceror-infra CloudFormation stack"

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$INFRA_DIR/serverless.yml" ]; then
  (cd "$INFRA_DIR" && serverless remove --stage "$STAGE" --region "$REGION" 2>&1 \
    | grep -v "^Serverless" | grep -v "^\." || true) \
    && ok "groceror-infra stack removed" \
    || warn "groceror-infra stack not found or already removed — continuing"
else
  warn "$INFRA_DIR/serverless.yml not found — skipping stack removal"
fi

# ── Step 4: Delete SSM Parameter Store secrets ────────────────────────────────

step "Deleting SSM parameters under /groceror/$STAGE/"

PARAMS=$(aws ssm describe-parameters \
  --region "$REGION" \
  --parameter-filters "Key=Name,Option=BeginsWith,Values=/groceror/$STAGE/" \
  --query 'Parameters[*].Name' \
  --output json 2>/dev/null || echo "[]")

if [[ "$PARAMS" != "[]" && "$PARAMS" != "" ]]; then
  PARAM_COUNT=$(echo "$PARAMS" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")
  echo "   Deleting $PARAM_COUNT parameter(s)..."
  # SSM delete-parameters accepts up to 10 names at a time
  echo "$PARAMS" | python3 -c "
import json, sys, subprocess
params = json.load(sys.stdin)
for i in range(0, len(params), 10):
    batch = params[i:i+10]
    subprocess.run(
        ['aws', 'ssm', 'delete-parameters', '--region', '$REGION', '--names'] + batch,
        capture_output=True
    )
" && ok "Deleted $PARAM_COUNT SSM parameter(s)"
else
  ok "No SSM parameters found under /groceror/$STAGE/"
fi

# ── Step 6: Remove Serverless Framework deployment S3 buckets ─────────────────
# Serverless Framework creates a bucket per service (holds CloudFormation templates
# and Lambda ZIPs). These are not deleted by 'serverless remove' by default.

step "Cleaning up Serverless Framework deployment S3 buckets"

SLS_BUCKETS=$(aws s3api list-buckets \
  --query "Buckets[?contains(Name, 'serverless') && contains(Name, '$REGION')].Name" \
  --output json 2>/dev/null || echo "[]")

if [[ "$SLS_BUCKETS" != "[]" && "$SLS_BUCKETS" != "" ]]; then
  echo "   Found Serverless deployment buckets:"
  echo "$SLS_BUCKETS" | python3 -c "
import json, sys, subprocess

buckets = json.load(sys.stdin)
for bucket in buckets:
    print(f'   → {bucket}')
    # Empty the bucket first (versioned buckets need --include all versions)
    subprocess.run(
        ['aws', 's3', 'rm', f's3://{bucket}', '--recursive', '--region', '$REGION'],
        capture_output=True
    )
    # Delete the bucket
    result = subprocess.run(
        ['aws', 's3api', 'delete-bucket', '--bucket', bucket, '--region', '$REGION'],
        capture_output=True, text=True
    )
    status = '✓ deleted' if result.returncode == 0 else f'⚠ {result.stderr.strip()}'
    print(f'     {status}')
"
else
  ok "No Serverless deployment buckets found"
fi

# ── Step 5: Verify nothing is still running ───────────────────────────────────

step "Verifying no billable resources remain"

# Check for Fargate tasks still running (Fargate charges by the second)
RUNNING_TASKS=$(aws ecs list-tasks \
  --region "$REGION" \
  --cluster "groceror-cluster-$STAGE" \
  --query 'taskArns' \
  --output json 2>/dev/null || echo "[]")

ECS_CLUSTERS=$(aws ecs list-clusters \
  --region "$REGION" \
  --query "clusterArns[?contains(@, 'groceror')]" \
  --output json 2>/dev/null || echo "[]")

if [[ "$RUNNING_TASKS" != "[]" && "$RUNNING_TASKS" != "" ]]; then
  warn "Fargate tasks still running: $RUNNING_TASKS"
  warn "Scale to zero: aws ecs update-service --cluster groceror-cluster-$STAGE --service groceror-api-$STAGE --desired-count 0 --region $REGION"
else
  ok "No Fargate tasks running"
fi

if [[ "$ECS_CLUSTERS" != "[]" && "$ECS_CLUSTERS" != "" ]]; then
  warn "ECS clusters still exist: $ECS_CLUSTERS"
  warn "Check the AWS Console → ECS for stuck resources"
else
  ok "No groceror ECS clusters found"
fi

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "========================================="
echo "  Teardown complete"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Wait 10–15 minutes for charges to stop."
echo "  2. Check AWS Billing → Cost Explorer to confirm $0 ongoing cost."
echo "  3. Review AWS Billing → Free Tier Usage to stay within limits."
echo ""
echo "To re-deploy later: follow the steps in DEPLOY_AWS.md"
echo ""
