#!/bin/bash
# =============================================================================
# LucidLink Windows Client IAM User Cleanup Script
# =============================================================================
# This script removes the IAM user and associated resources

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

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}LucidLink Windows Client IAM User Cleanup${NC}"
echo -e "${BLUE}========================================${NC}"
echo
echo -e "${RED}WARNING: This will delete the IAM user and all access keys!${NC}"
echo -e "${YELLOW}Are you sure you want to continue? (yes/no)${NC}"
read -r CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo -e "${YELLOW}Cleanup cancelled${NC}"
    exit 0
fi

# Get AWS account ID
echo
echo -e "${YELLOW}Getting AWS account ID...${NC}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Failed to get AWS account ID${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Account ID: $ACCOUNT_ID${NC}"

POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy${IAM_PATH}${POLICY_NAME}"

# Step 1: List and delete access keys
echo
echo -e "${YELLOW}Step 1: Deleting access keys...${NC}"
ACCESS_KEYS=$(aws iam list-access-keys --user-name "$IAM_USER_NAME" --query 'AccessKeyMetadata[].AccessKeyId' --output text 2>/dev/null || echo "")

if [ -n "$ACCESS_KEYS" ]; then
    for KEY in $ACCESS_KEYS; do
        echo -e "${YELLOW}  Deleting access key: $KEY${NC}"
        aws iam delete-access-key --user-name "$IAM_USER_NAME" --access-key-id "$KEY"
        echo -e "${GREEN}  ✓ Deleted${NC}"
    done
else
    echo -e "${YELLOW}⚠ No access keys found${NC}"
fi

# Step 2: Detach policy from user
echo
echo -e "${YELLOW}Step 2: Detaching policy from user...${NC}"
if aws iam get-user --user-name "$IAM_USER_NAME" &> /dev/null; then
    aws iam detach-user-policy \
        --user-name "$IAM_USER_NAME" \
        --policy-arn "$POLICY_ARN" 2>/dev/null || echo -e "${YELLOW}⚠ Policy not attached or already detached${NC}"
    echo -e "${GREEN}✓ Policy detached${NC}"
else
    echo -e "${YELLOW}⚠ User not found${NC}"
fi

# Step 3: Delete IAM policy
echo
echo -e "${YELLOW}Step 3: Deleting IAM policy...${NC}"
if aws iam get-policy --policy-arn "$POLICY_ARN" &> /dev/null; then
    aws iam delete-policy --policy-arn "$POLICY_ARN"
    echo -e "${GREEN}✓ Policy deleted${NC}"
else
    echo -e "${YELLOW}⚠ Policy not found${NC}"
fi

# Step 4: Delete IAM user
echo
echo -e "${YELLOW}Step 4: Deleting IAM user...${NC}"
if aws iam get-user --user-name "$IAM_USER_NAME" &> /dev/null; then
    aws iam delete-user --user-name "$IAM_USER_NAME"
    echo -e "${GREEN}✓ User deleted${NC}"
else
    echo -e "${YELLOW}⚠ User not found${NC}"
fi

# Step 5: Clean up AWS CLI profile (optional)
echo
echo -e "${YELLOW}Would you like to remove the 'll-win-client' AWS CLI profile? (y/n)${NC}"
read -r REMOVE_PROFILE

if [[ "$REMOVE_PROFILE" =~ ^[Yy]$ ]]; then
    if grep -q "\[profile ll-win-client\]" ~/.aws/config 2>/dev/null || grep -q "\[ll-win-client\]" ~/.aws/credentials 2>/dev/null; then
        # Remove from config
        sed -i.bak '/\[profile ll-win-client\]/,/^$/d' ~/.aws/config 2>/dev/null || true
        # Remove from credentials
        sed -i.bak '/\[ll-win-client\]/,/^$/d' ~/.aws/credentials 2>/dev/null || true
        echo -e "${GREEN}✓ AWS CLI profile removed${NC}"
    else
        echo -e "${YELLOW}⚠ Profile not found${NC}"
    fi
fi

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Cleanup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo -e "${BLUE}Removed:${NC}"
echo "  • IAM User: $IAM_USER_NAME"
echo "  • IAM Policy: $POLICY_NAME"
echo "  • All access keys"
echo
