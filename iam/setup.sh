#!/bin/bash
# =============================================================================
# LucidLink Windows Client IAM User Setup Script (AWS CLI Method)
# =============================================================================
# This script creates a limited IAM user for ll-win-client deployments
# Prerequisites: AWS CLI configured with admin credentials

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
IAM_USER_NAME="ll-win-client-deployer"
IAM_PATH="/ll-win-client/"
POLICY_NAME="ll-win-client-deployer-policy"
POLICY_FILE="ll-win-client-user-policy.json"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}LucidLink Windows Client IAM User Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}ERROR: AWS CLI is not installed${NC}"
    echo "Install from: https://aws.amazon.com/cli/"
    exit 1
fi

# Check if policy file exists
if [ ! -f "$POLICY_FILE" ]; then
    echo -e "${RED}ERROR: Policy file not found: $POLICY_FILE${NC}"
    echo "Make sure you're in the iam/ directory"
    exit 1
fi

# Get AWS account ID
echo -e "${YELLOW}Getting AWS account ID...${NC}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Failed to get AWS account ID${NC}"
    echo "Make sure AWS CLI is configured with valid credentials"
    exit 1
fi
echo -e "${GREEN}✓ Account ID: $ACCOUNT_ID${NC}"
echo

# Step 1: Create IAM user
echo -e "${YELLOW}Step 1: Creating IAM user '$IAM_USER_NAME'...${NC}"
if aws iam get-user --user-name "$IAM_USER_NAME" &> /dev/null; then
    echo -e "${YELLOW}⚠ User already exists, skipping...${NC}"
else
    aws iam create-user --user-name "$IAM_USER_NAME" --path "$IAM_PATH" --tags \
        Key=Name,Value="$IAM_USER_NAME" \
        Key=Purpose,Value="LucidLink Windows client deployments" \
        Key=Environment,Value=demo
    echo -e "${GREEN}✓ User created${NC}"
fi
echo

# Step 2: Create IAM policy
echo -e "${YELLOW}Step 2: Creating IAM policy '$POLICY_NAME'...${NC}"
POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy${IAM_PATH}${POLICY_NAME}"

if aws iam get-policy --policy-arn "$POLICY_ARN" &> /dev/null; then
    echo -e "${YELLOW}⚠ Policy already exists, skipping...${NC}"
else
    aws iam create-policy \
        --policy-name "$POLICY_NAME" \
        --path "$IAM_PATH" \
        --policy-document "file://$POLICY_FILE" \
        --description "Limited permissions for ll-win-client Windows client deployments in us-west-2" \
        --tags \
            Key=Name,Value="$POLICY_NAME" \
            Key=Purpose,Value="LucidLink deployment permissions" \
            Key=Environment,Value=demo
    echo -e "${GREEN}✓ Policy created${NC}"
fi
echo

# Step 3: Attach policy to user
echo -e "${YELLOW}Step 3: Attaching policy to user...${NC}"
aws iam attach-user-policy \
    --user-name "$IAM_USER_NAME" \
    --policy-arn "$POLICY_ARN"
echo -e "${GREEN}✓ Policy attached${NC}"
echo

# Step 4: Create access key
echo -e "${YELLOW}Step 4: Creating access key...${NC}"
echo -e "${BLUE}Do you want to create an access key now? (y/n)${NC}"
read -r CREATE_KEY

if [[ "$CREATE_KEY" =~ ^[Yy]$ ]]; then
    KEY_OUTPUT=$(aws iam create-access-key --user-name "$IAM_USER_NAME" --output json)
    ACCESS_KEY_ID=$(echo "$KEY_OUTPUT" | grep -o '"AccessKeyId": "[^"]*' | sed 's/"AccessKeyId": "//')
    SECRET_ACCESS_KEY=$(echo "$KEY_OUTPUT" | grep -o '"SecretAccessKey": "[^"]*' | sed 's/"SecretAccessKey": "//')

    echo
    echo -e "${GREEN}✓ Access key created successfully!${NC}"
    echo
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}SAVE THESE CREDENTIALS SECURELY!${NC}"
    echo -e "${RED}They will not be shown again.${NC}"
    echo -e "${RED}========================================${NC}"
    echo
    echo -e "${BLUE}Access Key ID:${NC} ${GREEN}$ACCESS_KEY_ID${NC}"
    echo -e "${BLUE}Secret Access Key:${NC} ${GREEN}$SECRET_ACCESS_KEY${NC}"
    echo
    echo -e "${YELLOW}Would you like to configure an AWS CLI profile now? (y/n)${NC}"
    read -r CONFIGURE_PROFILE

    if [[ "$CONFIGURE_PROFILE" =~ ^[Yy]$ ]]; then
        echo
        echo -e "${YELLOW}Which AWS region will you use? (e.g., us-west-2, us-east-1, eu-west-1)${NC}"
        read -r AWS_REGION
        AWS_REGION=${AWS_REGION:-us-west-2}  # Default to us-west-2 if empty

        aws configure set aws_access_key_id "$ACCESS_KEY_ID" --profile ll-win-client
        aws configure set aws_secret_access_key "$SECRET_ACCESS_KEY" --profile ll-win-client
        aws configure set region "$AWS_REGION" --profile ll-win-client
        aws configure set output json --profile ll-win-client
        echo -e "${GREEN}✓ AWS CLI profile 'll-win-client' configured for region: $AWS_REGION${NC}"
    fi
else
    echo -e "${YELLOW}Skipping access key creation${NC}"
    echo "You can create one later with:"
    echo "  aws iam create-access-key --user-name $IAM_USER_NAME"
fi

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo -e "${BLUE}IAM User:${NC} $IAM_USER_NAME"
echo -e "${BLUE}Policy ARN:${NC} $POLICY_ARN"
echo -e "${BLUE}Region Access:${NC} Any AWS region (user chooses in ll-win-client script)"
echo
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Test the IAM user:"
echo "   aws sts get-caller-identity --profile ll-win-client"
echo
echo "2. Test EC2 access in different regions (should work):"
echo "   aws ec2 describe-instances --region us-west-2 --profile ll-win-client"
echo "   aws ec2 describe-instances --region us-east-1 --profile ll-win-client"
echo
echo "3. Test service restriction (should fail):"
echo "   aws s3 ls --profile ll-win-client"
echo
echo "4. Use with ll-win-client script:"
echo "   cd /Users/davidphillips/Cursor_projects/ll-win-client-aws-client"
echo "   uv run ll-win-client-client-aws.py"
echo
echo -e "${BLUE}For cleanup, run:${NC}"
echo "  ./cleanup.sh"
echo
