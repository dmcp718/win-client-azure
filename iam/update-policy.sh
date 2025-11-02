#!/bin/bash
# =============================================================================
# Update LucidLink Windows Client IAM Policy
# =============================================================================
# This script updates the existing IAM policy with new permissions

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
IAM_PATH="/ll-win-client/"
POLICY_NAME="ll-win-client-deployer-policy"
POLICY_FILE="ll-win-client-user-policy.json"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Update LucidLink Windows Client IAM Policy${NC}"
echo -e "${BLUE}========================================${NC}"
echo

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

POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy${IAM_PATH}${POLICY_NAME}"

# Check if policy exists
echo -e "${YELLOW}Checking if policy exists...${NC}"
if ! aws iam get-policy --policy-arn "$POLICY_ARN" &> /dev/null; then
    echo -e "${RED}ERROR: Policy not found: $POLICY_ARN${NC}"
    echo "Please run ./setup.sh first to create the IAM user and policy"
    exit 1
fi
echo -e "${GREEN}✓ Policy exists${NC}"
echo

# Create new policy version
echo -e "${YELLOW}Creating new policy version...${NC}"
echo -e "${BLUE}This will update the policy with ALL permissions from:${NC}"
echo "  $POLICY_FILE"
echo
echo -e "${BLUE}New permissions added include:${NC}"
echo "  EC2 Describe:"
echo "    - ec2:DescribeAvailabilityZones (Terraform needs this)"
echo "    - ec2:DescribeRegions (region validation)"
echo "    - ec2:DescribeVpcAttribute (VPC queries)"
echo "    - ec2:DescribeSubnetAttribute (subnet queries)"
echo "    - ec2:DescribeRouteTableAttribute (route table queries)"
echo "    - ec2:DescribeNetworkInterfaces (network interface queries)"
echo "    - ec2:DescribeNetworkInterfaceAttribute"
echo "    - ec2:DescribeNatGateways"
echo "    - ec2:DescribeNetworkAcls"
echo "    - ec2:DescribeVpcClassicLink"
echo "    - ec2:DescribeVpcClassicLinkDnsSupport"
echo

NEW_VERSION=$(aws iam create-policy-version \
    --policy-arn "$POLICY_ARN" \
    --policy-document "file://$POLICY_FILE" \
    --set-as-default \
    --query 'PolicyVersion.VersionId' \
    --output text)

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Policy updated successfully${NC}"
    echo -e "${GREEN}  New version: $NEW_VERSION${NC}"
else
    echo -e "${RED}ERROR: Failed to update policy${NC}"
    exit 1
fi

echo

# Clean up old versions (keep latest 2)
echo -e "${YELLOW}Checking for old policy versions to clean up...${NC}"
OLD_VERSIONS=$(aws iam list-policy-versions \
    --policy-arn "$POLICY_ARN" \
    --query 'Versions[?!IsDefaultVersion].VersionId' \
    --output text)

VERSION_COUNT=$(echo "$OLD_VERSIONS" | wc -w | xargs)

if [ "$VERSION_COUNT" -gt 1 ]; then
    echo -e "${YELLOW}Found $VERSION_COUNT old version(s). Cleaning up...${NC}"

    # Keep only the most recent non-default version, delete the rest
    SKIP_FIRST=true
    for VERSION in $OLD_VERSIONS; do
        if [ "$SKIP_FIRST" = true ]; then
            SKIP_FIRST=false
            echo -e "${BLUE}  Keeping recent backup version: $VERSION${NC}"
            continue
        fi

        echo -e "${YELLOW}  Deleting old version: $VERSION${NC}"
        aws iam delete-policy-version \
            --policy-arn "$POLICY_ARN" \
            --version-id "$VERSION" 2>/dev/null || true
    done
    echo -e "${GREEN}✓ Cleanup complete${NC}"
else
    echo -e "${BLUE}No cleanup needed (only $VERSION_COUNT old version)${NC}"
fi

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Policy Update Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo -e "${BLUE}Policy ARN:${NC} $POLICY_ARN"
echo -e "${BLUE}Active Version:${NC} $NEW_VERSION"
echo
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Test the updated permissions:"
echo "   cd /Users/davidphillips/Cursor_projects/ll-win-client-aws-client"
echo "   uv run ll-win-client-client-aws.py"
echo
echo "2. The Terraform plan should now work without authorization errors"
echo
