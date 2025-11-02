# Quick Start: IAM User for LucidLink Windows Client

This IAM user provides **secure, limited access** for running the LucidLink Windows client deployment script.

## Why This User?

Instead of using your admin AWS credentials, this dedicated IAM user:
- ✅ Works in **any AWS region** you choose (flexible for different ll-win-client locations)
- ✅ Can't access S3, RDS, Lambda, or other unrelated services (EC2-only)
- ✅ Can't modify your main AWS account settings
- ✅ Follows security best practices (least privilege)

---

## Setup (Choose One Method)

### Option A: Quick Setup with Script (Easiest)

```bash
cd iam
./setup.sh
```

The script will:
1. Create the IAM user `ll-win-client-deployer`
2. Attach the limited-permissions policy
3. Optionally create access keys
4. Optionally configure AWS CLI profile

**Save the Access Key ID and Secret Access Key shown at the end!**

---

### Option B: Terraform (Infrastructure as Code)

```bash
cd iam
terraform init
terraform apply
```

Then create access keys manually:
```bash
aws iam create-access-key --user-name ll-win-client-deployer
```

---

## Using with LucidLink Windows Client Script

Once you have the IAM user's access keys:

```bash
# From the repository root
uv run ll-win-client-aws.py
```

When prompted:
1. **AWS Region**: Enter your desired region (e.g., `us-west-2`, `us-east-1`, `eu-west-1`, `ap-southeast-1`)
2. **AWS Access Key ID**: Enter the Access Key ID from IAM user creation
3. **AWS Secret Access Key**: Enter the Secret Access Key from IAM user creation

The script will save these credentials locally in:
```
~/.ll-win-client/config.json
```

---

## What Can This User Do?

### ✅ Allowed in any AWS region:
- Create/destroy EC2 instances (Windows Server 2022)
- Create/manage VPCs, subnets, security groups
- Set Windows passwords via AWS Systems Manager (SSM)
- Connect to instances via SSM Session Manager
- Store LucidLink credentials in Secrets Manager
- Create CloudWatch log groups

### ❌ Not Allowed:
- Create IAM users or broad IAM policies
- Access S3, RDS, Lambda, ECS, EKS, or other non-EC2 services
- Modify billing or account settings
- Delete or modify unrelated AWS resources

---

## Testing Your Setup

After setup, test the credentials:

**Test 1: Verify identity**
```bash
aws sts get-caller-identity --profile ll-win-client
```

Expected: Shows `ll-win-client-deployer` user ARN ✓

**Test 2: Access any region (should work)**
```bash
aws ec2 describe-instances --region us-west-2 --profile ll-win-client
aws ec2 describe-instances --region us-east-1 --profile ll-win-client
aws ec2 describe-instances --region eu-west-1 --profile ll-win-client
```

Expected: Returns instance list for each region (may be empty) ✓

**Test 4: Try S3 (should fail)**
```bash
aws s3 ls --profile ll-win-client
```

Expected: Access Denied error ✓

---

## Example: Complete Workflow

```bash
# 1. Create the IAM user
cd iam
./setup.sh

# When prompted, create access key: yes
# When prompted, configure profile: yes
# Save the displayed credentials!

# 2. Test the credentials
aws sts get-caller-identity --profile ll-win-client

# 3. Run the deployment script (from repository root)
cd ..
uv run ll-win-client-aws.py

# 4. When prompted for AWS credentials:
#    Region: (your choice - e.g., us-west-2, us-east-1, eu-west-1)
#    Access Key ID: [from step 1]
#    Secret Access Key: [from step 1]

# 5. Choose "3. Deploy Client Instances"
# Script will use the limited IAM user to create resources

# 6. When done with ll-win-client:
#    Choose "5. Destroy Client Instances"
```

---

## Cleanup

When you no longer need the IAM user:

```bash
cd iam
./cleanup.sh
```

This removes:
- IAM user
- IAM policy
- All access keys
- AWS CLI profile (optional)

---

## Security Notes

### ✅ Best Practices:
- Store access keys in a password manager (1Password, LastPass, etc.)
- Rotate access keys every 90 days
- Don't commit credentials to Git
- Delete access keys when not actively using them

### ⚠️ Important:
- The credentials are saved locally at `~/.ll-win-client/config.json`
- This file contains base64-encoded credentials (not encrypted)
- Keep this file secure or delete it when done

### 🔒 Emergency Response:
If credentials are compromised:
```bash
# List access keys
aws iam list-access-keys --user-name ll-win-client-deployer

# Delete compromised key
aws iam delete-access-key --user-name ll-win-client-deployer --access-key-id AKIAXXXXXXXX

# Create new key
aws iam create-access-key --user-name ll-win-client-deployer
```

---

## Troubleshooting

### "User is not authorized to perform ec2:RunInstances"
- **Cause**: IAM policy not attached or incorrect permissions
- **Fix**: Verify policy attachment with `aws iam list-attached-user-policies --user-name ll-win-client-deployer`

### "User is not authorized to perform iam:CreateRole"
- **Cause**: IAM role name doesn't match pattern
- **Fix**: Terraform automatically uses `ll-win-client-` prefix (this should not happen)

### Access keys not working
- **Verify**: `aws sts get-caller-identity --profile ll-win-client`
- **Check**: Credentials in `~/.aws/credentials` under `[ll-win-client]` profile
- **Recreate**: Delete and create new access key if needed

---

## Support

- **IAM Policy**: `iam/ll-win-client-user-policy.json`
- **Full Documentation**: `iam/README.md`
- **Setup Script**: `iam/setup.sh`
- **Cleanup Script**: `iam/cleanup.sh`

---

**Last Updated**: 2025-02-01
**Purpose**: Secure, limited IAM user for LucidLink Windows client deployments
