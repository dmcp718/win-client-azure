# =============================================================================
# Windows LucidLink Client EC2 Instance Configuration
# =============================================================================

# Get latest NVIDIA RTX Virtual Workstation - Windows Server 2022 AMI
# This AMI includes pre-installed NVIDIA GRID/RTX drivers for GPU acceleration
# Perfect for Adobe Creative Cloud and other professional graphics applications
# NOTE: Requires AWS Marketplace subscription (free): https://aws.amazon.com/marketplace/pp/prodview-f4reygwmtxipu
# This data source is only queried when use_nvidia_ami = true
data "aws_ami" "windows_2022_nvidia" {
  count       = var.use_nvidia_ami ? 1 : 0
  most_recent = true
  owners      = ["679593333241"]  # NVIDIA Corporation AWS Marketplace account

  filter {
    name   = "name"
    values = ["NVIDIA RTX Virtual Workstation - WinServer 2022-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }

  filter {
    name   = "product-code"
    values = ["8xqbhq7e8w4fck7pby8f3p2r3"]  # NVIDIA RTX Virtual Workstation product code
  }
}

# Get latest standard Windows Server 2022 AMI (fallback)
# Use this if you haven't subscribed to NVIDIA Marketplace AMI yet
data "aws_ami" "windows_2022_standard" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["Windows_Server-2022-English-Full-Base-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

# Select AMI based on variable
locals {
  selected_ami_id = var.use_nvidia_ami ? data.aws_ami.windows_2022_nvidia[0].id : data.aws_ami.windows_2022_standard.id
}

# Security Group for Windows Clients
resource "aws_security_group" "windows_client" {
  name        = "ll-win-client-sg"
  description = "Security group for Windows LucidLink client instances"
  vpc_id      = aws_vpc.main.id

  # Amazon DCV (NICE DCV) - Remote access for GPU-accelerated graphics
  ingress {
    description = "Amazon DCV HTTPS"
    from_port   = 8443
    to_port     = 8443
    protocol    = "tcp"
    cidr_blocks = var.allowed_rdp_cidr_blocks
  }

  # WinRM HTTPS (for remote management)
  ingress {
    description = "WinRM HTTPS"
    from_port   = 5986
    to_port     = 5986
    protocol    = "tcp"
    cidr_blocks = var.allowed_rdp_cidr_blocks
  }

  # Outbound traffic (required for LucidLink and internet access)
  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    local.common_tags,
    {
      Name = "ll-win-client-sg"
    }
  )
}

# IAM Role for Windows Client instances
resource "aws_iam_role" "windows_client" {
  name = "ll-win-client-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

# IAM Policy for Secrets Manager access
resource "aws_iam_role_policy" "windows_client_secrets" {
  name = "ll-win-client-secrets"
  role = aws_iam_role.windows_client.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:*:secret:ll-win-client/lucidlink/*"
      }
    ]
  })
}

# IAM Policy for CloudWatch logging
resource "aws_iam_role_policy" "windows_client_cloudwatch" {
  name = "ll-win-client-cloudwatch"
  role = aws_iam_role.windows_client.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:*:*"
      }
    ]
  })
}

# IAM Policy for Amazon DCV License (required for automatic licensing on EC2)
resource "aws_iam_role_policy" "windows_client_dcv_license" {
  name = "ll-win-client-dcv-license"
  role = aws_iam_role.windows_client.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject"
        ]
        Resource = "arn:aws:s3:::dcv-license.${var.aws_region}/*"
      }
    ]
  })
}

# Attach SSM policy for remote management
resource "aws_iam_role_policy_attachment" "windows_client_ssm" {
  role       = aws_iam_role.windows_client.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Instance Profile
resource "aws_iam_instance_profile" "windows_client" {
  name = "ll-win-client-profile"
  role = aws_iam_role.windows_client.name
}

# =============================================================================
# AWS Secrets Manager for LucidLink Credentials
# =============================================================================

resource "aws_secretsmanager_secret" "lucidlink_credentials" {
  count = var.filespace_domain != "" ? 1 : 0

  name                    = "ll-win-client/lucidlink/${var.filespace_domain}/credentials"
  description             = "LucidLink credentials for ${var.filespace_domain}"
  recovery_window_in_days = 0  # Allow immediate deletion and recreation

  tags = merge(
    local.common_tags,
    {
      Filespace = var.filespace_domain
    }
  )
}

resource "aws_secretsmanager_secret_version" "lucidlink_credentials" {
  count = var.filespace_domain != "" ? 1 : 0

  secret_id = aws_secretsmanager_secret.lucidlink_credentials[0].id
  secret_string = jsonencode({
    username = var.filespace_user
    password = var.filespace_password
    domain   = var.filespace_domain
  })
}

# =============================================================================
# Launch Template for Windows Clients
# =============================================================================

resource "aws_launch_template" "windows_client" {
  name_prefix   = "ll-win-client-"
  description   = "Launch template for Windows LucidLink client instances (v3 - curl.exe for redirects)"
  image_id      = local.selected_ami_id
  instance_type = var.instance_type
  key_name      = var.ssh_key_name != "" ? var.ssh_key_name : null

  iam_instance_profile {
    arn = aws_iam_instance_profile.windows_client.arn
  }

  vpc_security_group_ids = [aws_security_group.windows_client.id]

  # Root volume configuration for Windows (C: drive)
  block_device_mappings {
    device_name = "/dev/sda1"
    ebs {
      volume_type           = "gp3"
      volume_size           = var.root_volume_size
      iops                  = min(max(3000, var.root_volume_size * 3), 16000)
      throughput            = min(max(125, floor(min(var.root_volume_size * 3, 16000) / 3000 * 250)), 1000)
      delete_on_termination = true
      encrypted             = true
    }
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "enabled"
  }

  monitoring {
    enabled = true
  }

  # PowerShell userdata script (minified to stay under 16KB limit)
  user_data = var.filespace_domain != "" ? base64encode(templatefile("${path.module}/templates/windows-userdata-min.ps1", {
    filespace_domain     = var.filespace_domain
    filespace_user       = var.filespace_user
    filespace_password   = var.filespace_password
    mount_point          = var.mount_point
    aws_region           = var.aws_region
    installer_url        = var.lucidlink_installer_url
    secret_arn           = var.filespace_domain != "" ? aws_secretsmanager_secret.lucidlink_credentials[0].arn : ""
  })) : base64encode("<powershell>\nWrite-Host 'LucidLink configuration not provided'\n</powershell>")

  tag_specifications {
    resource_type = "instance"
    tags = merge(
      local.common_tags,
      {
        Name = "ll-win-client"
      }
    )
  }

  tag_specifications {
    resource_type = "volume"
    tags = merge(
      local.common_tags,
      {
        Name = "ll-win-client-volume"
      }
    )
  }

  tags = local.common_tags
}

# =============================================================================
# Windows Client EC2 Instances
# =============================================================================

resource "aws_instance" "windows_client" {
  count = var.instance_count

  launch_template {
    id      = aws_launch_template.windows_client.id
    version = "$Latest"
  }

  subnet_id = aws_subnet.public.id

  tags = merge(
    local.common_tags,
    {
      Name  = "ll-win-client-${count.index + 1}"
      Index = count.index + 1
    }
  )

  lifecycle {
    create_before_destroy = true
    replace_triggered_by = [
      aws_launch_template.windows_client.latest_version
    ]
  }
}

# =============================================================================
# CloudWatch Log Group for Windows Clients
# =============================================================================

resource "aws_cloudwatch_log_group" "windows_client" {
  name              = "/aws/ec2/ll-win-client"
  retention_in_days = 7

  tags = local.common_tags
}
