# =============================================================================
# LucidLink Windows Client IAM User Setup
# =============================================================================
# This creates a limited IAM user for ll-win-client deployments with minimal
# required permissions for EC2, SSM, Secrets Manager, and networking in us-west-2

terraform {
  required_version = ">= 1.2"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# =============================================================================
# Variables
# =============================================================================

variable "aws_region" {
  description = "AWS region for IAM setup (IAM is global, but this sets the provider region)"
  type        = string
  default     = "us-east-1"
}

variable "iam_user_name" {
  description = "Name for the IAM user"
  type        = string
  default     = "ll-win-client-deployer"
}

# =============================================================================
# IAM User
# =============================================================================

resource "aws_iam_user" "ll-win-client_deployer" {
  name = var.iam_user_name
  path = "/ll-win-client/"

  tags = {
    Name        = var.iam_user_name
    Purpose     = "LucidLink Windows client deployments"
    Environment = "demo"
    ManagedBy   = "terraform"
  }
}

# =============================================================================
# IAM Policy
# =============================================================================

resource "aws_iam_policy" "ll-win-client_deployer_policy" {
  name        = "${var.iam_user_name}-policy"
  path        = "/ll-win-client/"
  description = "Limited permissions for ll-win-client Windows client deployments in any AWS region"

  policy = file("${path.module}/ll-win-client-user-policy.json")

  tags = {
    Name        = "${var.iam_user_name}-policy"
    Purpose     = "LucidLink deployment permissions"
    Environment = "demo"
    ManagedBy   = "terraform"
  }
}

# =============================================================================
# Attach Policy to User
# =============================================================================

resource "aws_iam_user_policy_attachment" "ll-win-client_deployer_attachment" {
  user       = aws_iam_user.ll-win-client_deployer.name
  policy_arn = aws_iam_policy.ll-win-client_deployer_policy.arn
}

# =============================================================================
# Access Key (optional - uncomment if you want Terraform to create it)
# =============================================================================

# WARNING: Storing access keys in Terraform state is a security risk!
# Prefer creating access keys manually via AWS Console or CLI
# and storing them securely (e.g., in AWS Secrets Manager)

# resource "aws_iam_access_key" "ll-win-client_deployer_key" {
#   user = aws_iam_user.ll-win-client_deployer.name
# }

# =============================================================================
# Outputs
# =============================================================================

output "iam_user_name" {
  description = "Name of the created IAM user"
  value       = aws_iam_user.ll-win-client_deployer.name
}

output "iam_user_arn" {
  description = "ARN of the created IAM user"
  value       = aws_iam_user.ll-win-client_deployer.arn
}

output "iam_policy_arn" {
  description = "ARN of the IAM policy"
  value       = aws_iam_policy.ll-win-client_deployer_policy.arn
}

output "next_steps" {
  description = "Instructions for next steps"
  value       = <<-EOT

    IAM User created successfully: ${aws_iam_user.ll-win-client_deployer.name}

    Next steps:
    1. Create access keys for this user:
       aws iam create-access-key --user-name ${aws_iam_user.ll-win-client_deployer.name}

    2. Save the Access Key ID and Secret Access Key securely

    3. Configure the ll-win-client deployment script with these credentials

    4. Test permissions (replace <region> with your desired region):
       aws sts get-caller-identity --profile ll-win-client
       aws ec2 describe-instances --region <region> --profile ll-win-client

    Security Notes:
    - This user can operate in ANY AWS region (choose region in ll-win-client script)
    - IAM resources must be prefixed with 'll-win-client-' or 'tc-'
    - Secrets must be prefixed with 'll-win-client-' or 'tc-'
    - User can create/destroy EC2 instances, VPCs, and related resources
    - User can set Windows passwords via SSM
    - User CANNOT access non-EC2 AWS services (S3, RDS, Lambda, etc.)
  EOT
}
