# LucidLink Windows Client - IAM User Setup

This directory contains IAM configuration for creating a **limited-privilege user** specifically for LucidLink Windows client deployments.

## Prerequisites

Before setting up the IAM user, you must **subscribe to the NVIDIA RTX Virtual Workstation AMI** in AWS Marketplace:

1. **Visit AWS Marketplace:**
   https://aws.amazon.com/marketplace/pp/prodview-f4reygwmtxipu

2. **Click "Continue to Subscribe"**

3. **Accept the terms** (No additional software fees - included free with G4dn instances)

4. **Wait for subscription confirmation** (usually takes 1-2 minutes)

> **Note:** This is a one-time subscription per AWS account. The AMI includes pre-installed NVIDIA GRID/RTX drivers optimized for Adobe Creative Cloud and other professional graphics applications. There are **no hourly software charges** - you only pay for the EC2 instance and Windows licensing.

## Security Principles

This IAM user follows the **principle of least privilege**:

✅ **CAN DO:**
- Create/destroy EC2 instances in **any AWS region** (region chosen in script)
- Manage VPCs, subnets, security groups, route tables (in any region)
- Set Windows passwords via AWS Systems Manager (SSM)
- Connect to instances via SSM Session Manager
- Retrieve Windows passwords (if using SSH key method)
- Create/manage IAM roles for EC2 instances (prefixed with `ll-win-client-` or `tc-`)
- Store LucidLink credentials in Secrets Manager (prefixed with `ll-win-client-` or `tc-`)
- Create CloudWatch log groups for instance logs

❌ **CANNOT DO:**
- Create IAM users or modify IAM policies (except limited roles)
- Access S3, RDS, Lambda, or other non-EC2 AWS services
- Delete or modify resources not related to ll-win-client deployments
- Access billing information (except cost explorer read-only)

## Setup Methods

### Method 1: Terraform (Recommended)

**Step 1: Navigate to IAM directory**
```bash
cd iam
```

**Step 2: Initialize Terraform**
```bash
terraform init
```

**Step 3: Review the plan**
```bash
terraform plan
```

**Step 4: Create the IAM user**
```bash
terraform apply
```

**Step 5: Create access keys manually (more secure)**
```bash
aws iam create-access-key --user-name ll-win-client-deployer
```

Save the output securely! You'll need:
- `AccessKeyId`
- `SecretAccessKey`

**Step 6: Configure AWS CLI profile**
```bash
aws configure --profile ll-win-client
# Enter the Access Key ID and Secret Access Key from step 5
# Default region: (choose your preferred region, e.g., us-west-2, us-east-1, etc.)
# Default output format: json
```

---

### Method 2: AWS CLI

**Step 1: Create the IAM user**
```bash
aws iam create-user --user-name ll-win-client-deployer --path /ll-win-client/
```

**Step 2: Create the IAM policy**
```bash
aws iam create-policy \
  --policy-name ll-win-client-deployer-policy \
  --path /ll-win-client/ \
  --policy-document file://ll-win-client-user-policy.json
```

**Step 3: Get the policy ARN from output, then attach to user**
```bash
# Replace ACCOUNT_ID with your AWS account ID
export POLICY_ARN="arn:aws:iam::ACCOUNT_ID:policy/ll-win-client/ll-win-client-deployer-policy"

aws iam attach-user-policy \
  --user-name ll-win-client-deployer \
  --policy-arn $POLICY_ARN
```

**Step 4: Create access keys**
```bash
aws iam create-access-key --user-name ll-win-client-deployer
```

**Step 5: Configure AWS CLI profile**
```bash
aws configure --profile ll-win-client
# Enter the credentials from step 4
```

---

## Testing the IAM User

**Test 1: Verify identity**
```bash
aws sts get-caller-identity --profile ll-win-client
```

Expected output:
```json
{
    "UserId": "AIDAXXXXXXXXXXXXXXXXX",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/ll-win-client/ll-win-client-deployer"
}
```

**Test 2: List EC2 instances in any region (should work)**
```bash
aws ec2 describe-instances --region us-west-2 --profile ll-win-client
aws ec2 describe-instances --region us-east-1 --profile ll-win-client
aws ec2 describe-instances --region eu-west-1 --profile ll-win-client
```

Expected: Returns instance list (may be empty) ✓

**Test 4: Try to list S3 buckets (should fail)**
```bash
aws s3 ls --profile ll-win-client
```

Expected: Access Denied error ✓

---

## Using with LucidLink Windows Client Script

Run the deployment script and use these IAM credentials:

```bash
uv run ll-win-client-aws.py
```

When prompted for AWS credentials:
1. Enter the **Access Key ID** from the IAM user
2. Enter the **Secret Access Key** from the IAM user
3. Select region: **Choose any AWS region for deployment** (e.g., us-west-2, us-east-1, eu-west-1, ap-southeast-1, etc.)

The script will automatically use these credentials for all AWS operations.

---

## Resource Naming Conventions

This IAM user can only manage resources with specific naming patterns:

| Resource Type | Required Prefix |
|---------------|----------------|
| IAM Roles | `ll-win-client-*` or `tc-*` |
| IAM Instance Profiles | `ll-win-client-*` or `tc-*` |
| Secrets Manager Secrets | `ll-win-client-*` or `tc-*` |
| CloudWatch Log Groups | `/aws/ec2/ll-win-client-*` or `/aws/ec2/tc-*` |

**Why?** This prevents the user from accidentally modifying unrelated AWS resources.

---

## Permission Details

### EC2 Permissions
- Full instance lifecycle management (run, stop, start, terminate)
- Network management (VPC, subnets, internet gateways, route tables)
- Security group management
- Key pair management
- AMI discovery (read-only)
- Password retrieval via GetPasswordData

### SSM Permissions
- Send commands to instances (for password setting)
- Get command execution status
- Start/terminate SSM sessions
- Describe instance information

### IAM Permissions
- Create/delete roles for EC2 instances (limited by naming pattern)
- Create/delete instance profiles (limited by naming pattern)
- Pass roles to EC2 service only

### Secrets Manager Permissions
- Full secret management (limited by naming pattern)
- Used for storing LucidLink credentials

### CloudWatch Logs Permissions
- Create/delete log groups (limited by naming pattern)
- Set log retention policies

---

## Security Best Practices

### ✅ DO:
- Store access keys in AWS Secrets Manager or password manager
- Rotate access keys regularly (every 90 days)
- Use AWS CloudTrail to monitor API calls
- Delete access keys when no longer needed
- Use MFA on the root account that created this user

### ❌ DON'T:
- Commit access keys to Git repositories
- Share access keys via email or chat
- Store access keys in plaintext files
- Use root account credentials for deployments
- Give this user broader permissions

---

## Cleanup

### Remove IAM User (Terraform)
```bash
cd iam
terraform destroy
```

### Remove IAM User (AWS CLI)
```bash
# List and delete access keys first
aws iam list-access-keys --user-name ll-win-client-deployer
aws iam delete-access-key --user-name ll-win-client-deployer --access-key-id AKIAXXXXXXXXXXXXXXXX

# Detach policy
aws iam detach-user-policy \
  --user-name ll-win-client-deployer \
  --policy-arn arn:aws:iam::ACCOUNT_ID:policy/ll-win-client/ll-win-client-deployer-policy

# Delete policy
aws iam delete-policy \
  --policy-arn arn:aws:iam::ACCOUNT_ID:policy/ll-win-client/ll-win-client-deployer-policy

# Delete user
aws iam delete-user --user-name ll-win-client-deployer
```

---

## Troubleshooting

### Error: "User: ... is not authorized to perform: ec2:RunInstances"

**Cause:** Missing IAM permissions or policy not attached

**Solution:** Verify the policy is attached: `aws iam list-attached-user-policies --user-name ll-win-client-deployer`

---

### Error: "User: ... is not authorized to perform: iam:CreateRole"

**Cause:** IAM role name doesn't match required pattern

**Solution:** Ensure role names start with `ll-win-client-` or `tc-`

---

### Error: "User: ... is not authorized to perform: secretsmanager:CreateSecret"

**Cause:** Secret name doesn't match required pattern

**Solution:** Ensure secret names start with `ll-win-client-` or `tc-`

---

## Cost Monitoring

This IAM user has read-only access to Cost Explorer:

```bash
# View current month costs
aws ce get-cost-and-usage \
  --time-period Start=2025-01-01,End=2025-02-01 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --profile ll-win-client
```

---

## Support

For issues or questions:
1. Check CloudTrail logs for denied API calls
2. Review IAM policy in `ll-win-client-user-policy.json`
3. Test permissions using AWS Policy Simulator

---

**Last Updated:** 2025-02-01
**Policy Version:** 1.0
