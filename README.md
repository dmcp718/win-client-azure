# LucidLink Windows Client - AWS Deployment

Automated deployment tool for Windows Server instances with LucidLink client on AWS.

**Perfect for demonstrations, temporary cloud workstations, and remote GPU-accelerated workflows.**

GitHub Repository: https://github.com/dmcp718/ll-win-client-aws.git

---

## What This Does

Deploy GPU-accelerated Windows Server 2022 instances on AWS in minutes:
- ✅ **One command deployment** - Interactive TUI guides you through setup
- ✅ **GPU-accelerated graphics** - NVIDIA T4 GPUs for Adobe Creative Cloud
- ✅ **Amazon DCV remote access** - Superior graphics performance over RDP
- ✅ **Flexible LucidLink setup** - Auto-configure or install for manual setup
- ✅ **Automated password management** - No SSH keys needed (SSM-based)
- ✅ **Multi-instance support** - Deploy 1-10 instances simultaneously
- ✅ **Complete automation** - Terraform + Python TUI handles everything
- ✅ **Robust deployment** - Improved instance readiness checks prevent early failures

**Deployment time**: 10-15 minutes | **Access via**: Amazon DCV (port 8443)

---

## Quick Start Decision Tree

**Choose your path based on your situation:**

### 🆕 First-Time User (Recommended Path)

**You need**: AWS account with admin access (to create IAM user)

```bash
# 1. Clone repository
git clone https://github.com/dmcp718/ll-win-client-aws.git
cd ll-win-client-aws

# 2. Install dependencies
uv sync

# 3. Create IAM user (5 minutes)
cd iam
./setup.sh
# Save the Access Key ID and Secret Access Key!

# 4. Run deployment
cd ..
uv run ll-win-client-aws.py
# Enter IAM credentials when prompted

# 5. (Optional) Subscribe to NVIDIA AMI for pre-installed drivers
#    Only needed if you want use_nvidia_ami = true
#    Visit: https://aws.amazon.com/marketplace/pp/prodview-f4reygwmtxipu
```

**Next**: See [IAM Setup Guide](docs/IAM-SETUP.md) for detailed IAM instructions

---

### 🔧 Advanced User (Already Have IAM User or Using Admin Credentials)

**You need**: AWS credentials (IAM user or admin)

```bash
# 1. Clone and setup
git clone https://github.com/dmcp718/ll-win-client-aws.git
cd ll-win-client-aws
uv sync

# 2. Run deployment
uv run ll-win-client-aws.py
# Enter your AWS credentials when prompted
```

**Next**: See [Deployment Guide](docs/DEPLOYMENT-GUIDE.md) for detailed deployment steps

---

### 🔄 Returning User (Already Configured)

**You have**: Previously configured `~/.ll-win-client/config.json`

```bash
cd ll-win-client-aws
uv run ll-win-client-aws.py
# Your credentials are saved - just choose deploy!
```

---

## Prerequisites

### Required (Before You Start)

- ✅ **AWS Account** with appropriate permissions
- ✅ **LucidLink Credentials** (filespace domain, username, password)

### Optional (For Enhanced GPU Performance)

- 🔧 **NVIDIA RTX AMI Subscription** (one-time, free): [Subscribe Here](https://aws.amazon.com/marketplace/pp/prodview-f4reygwmtxipu)
  - Pre-installed NVIDIA GRID/RTX drivers
  - Required only if you set `use_nvidia_ami = true` in configuration
  - Default: Uses standard Windows Server 2022 AMI (drivers install via Windows Update)
  - Recommended for professional graphics workloads

### Local Tools (Must Be Installed)

- ✅ **Python 3.8+** - Check: `python3 --version`
- ✅ **uv** - Python package manager
  - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Homebrew: `brew install uv`
- ✅ **Terraform 1.2+** - Infrastructure as Code tool
  - Download: https://www.terraform.io/downloads
  - Homebrew: `brew install terraform`
- ✅ **AWS CLI v2** - AWS command-line interface
  - Download: https://aws.amazon.com/cli/
  - Homebrew: `brew install awscli`

**Verify prerequisites:**
```bash
python3 --version  # Should show 3.8+
uv --version       # Should show uv installed
terraform -version # Should show 1.2+
aws --version      # Should show aws-cli/2.x
```

**Quick install with Homebrew (macOS):**
```bash
brew install uv terraform awscli
```

---

## Installation

```bash
# Clone repository
git clone https://github.com/dmcp718/ll-win-client-aws.git
cd ll-win-client-aws

# Install Python dependencies
uv sync

# Verify installation
uv run ll-win-client-aws.py --help
```

---

## Features

### Infrastructure
- **Windows Server 2022** with NVIDIA RTX drivers pre-installed
- **All GPU Instance Types** - Dynamically fetched from AWS API based on your region
  - g4dn series (NVIDIA T4 GPUs)
  - g5 series (NVIDIA A10G GPUs)
  - g6 series (NVIDIA L4 GPUs)
  - g4ad series (AMD Radeon Pro V520 GPUs)
  - And more as AWS releases new GPU instances
- **VPC with Internet Gateway** for isolated networking
- **Security Groups** with DCV (8443) and SSM access
- **Encrypted EBS Volumes** at rest

### Automation
- **Interactive TUI** for configuration with Rich library
- **Terraform** for Infrastructure as Code
- **AWS SSM Deployment** - Reliable remote script execution
  - Robust instance readiness checks (EC2 state + SSM agent + initialization buffer)
  - Prevents premature deployment failures
  - ~5 minute wait ensures Windows is fully initialized
- **Flexible LucidLink Configuration**
  - **Auto-configure mode** (default): Installs as Windows service, auto-mounts filespace
  - **Manual mode**: Installs client only, users configure credentials themselves
  - Credentials stored in AWS Secrets Manager (auto mode)
- **CloudWatch Logs** for instance monitoring
- **Modular Optional Software Framework**
  - **Enabled by default**: VLC Media Player, Adobe Creative Cloud
  - **Available**: 7-Zip, Notepad++
  - **Control via environment variables**: `INSTALL_VLC=0`, `INSTALL_ADOBE_CC=0`, etc.
  - Easy to add custom applications

### Remote Access
- **Amazon DCV** (primary) - GPU-accelerated remote desktop
  - Hardware-accelerated rendering
  - Optimized for Adobe Creative Cloud
  - QUIC protocol support
  - TLS encryption
- **AWS SSM** (alternative) - Command-line access without inbound ports

### Password Management
- **Automated via SSM** (default) - No SSH key needed
- **SSH Key method** (optional) - Traditional password decryption
- **One password for all instances** - Easy for demonstrations

### Cost Management
- **Stop/Start instances** - Save ~95% of costs when not in use
- **Complete destroy** - Remove everything when done permanently
- **No running charges when stopped** - Only pay for storage (~$0.01/hour)

---

## What Gets Deployed

**Per deployment, Terraform creates:**

| Resource | Quantity | Purpose |
|----------|----------|---------|
| VPC | 1 | Isolated network |
| Subnet | 1 | Public subnet with auto-assign IP |
| Internet Gateway | 1 | Internet access |
| Security Group | 1 | DCV + SSM access |
| S3 Bucket | 1 | Userdata scripts storage (bypasses 16KB limit) |
| Windows Instances | 1-10 | Your workstations |
| IAM Role | 1 | Instance permissions (Secrets Manager, CloudWatch, S3) |
| Secrets Manager Secret | 1 | LucidLink credentials |
| CloudWatch Log Group | 1 | Instance logs |

**Estimated costs** (us-east-1, examples):
- g4dn.xlarge (NVIDIA T4): ~$0.50/hour per instance
- g5.xlarge (NVIDIA A10G): ~$1.00/hour per instance
- g6.xlarge (NVIDIA L4): ~$0.84/hour per instance
- Storage (100GB): ~$0.01/hour
- **Stop instances when not in use to save money!**
- Pricing varies by region and instance type - check AWS pricing for your selected GPU instance

---

## Configuration

### Main Script

Configuration stored at: `~/.ll-win-client/config.json`

**Contains:**
- AWS region and credentials (base64-encoded)
- VPC CIDR block
- LucidLink credentials (base64-encoded)
- LucidLink auto-configuration mode (yes/no)
- Instance preferences (type, count, volume size)

**Security Note**: File contains base64-encoded credentials (basic obfuscation, not encryption). Keep secure.

### Connection Files

Generated at: `~/Desktop/LucidLink-DCV/`

**Contains:**
- `ll-win-client-1.dcv`, `ll-win-client-2.dcv`, etc. - DCV connection files
- `PASSWORDS.txt` - Windows Administrator password

---

## Main Menu

```
╔══════════════════════════════════════════╗
║  LucidLink Windows Client Deployment     ║
║  Multi-Instance Windows Provisioning     ║
╚══════════════════════════════════════════╝

1. Configure Client Deployment
2. View Configuration
3. Deploy Client Instances
4. View Deployment Status
5. Regenerate Connection Files (DCV)
6. Stop All Instances
7. Start All Instances
8. Destroy Client Instances
9. Exit
```

**Typical workflow:**
1. Configure (Option 1) - Set up AWS, LucidLink, instance settings
2. Deploy (Option 3) - Launch infrastructure (~10-15 minutes)
3. Connect - Use DCV files from Desktop
4. Stop (Option 6) - Pause instances when not in use to save money
5. Start (Option 7) - Resume instances to continue work
6. Destroy (Option 8) - Remove all resources when done permanently

---

## Accessing Instances

### Amazon DCV Connection (Recommended)

**First-time setup:**
1. Download DCV client: https://download.nice-dcv.com/
2. Install on your local machine
3. Open `~/Desktop/LucidLink-DCV/`
4. Double-click `.dcv` file for your instance
5. Login: Username `Administrator`, password from `PASSWORDS.txt`

**Why DCV?**
- Superior graphics performance vs RDP
- GPU-accelerated rendering
- Optimized for professional applications
- QUIC protocol for high-latency networks

**For detailed instructions**: See [Deployment Guide - Accessing Instances](docs/DEPLOYMENT-GUIDE.md#accessing-your-instances)

---

## Project Structure

```
ll-win-client-aws/
├── ll-win-client-aws.py          # Main Python TUI application
├── pyproject.toml                 # Python dependencies
├── README.md                      # This file
│
├── docs/                          # Comprehensive documentation
│   ├── IAM-SETUP.md              # IAM user setup guide
│   ├── DEPLOYMENT-GUIDE.md       # Complete deployment walkthrough
│   └── TROUBLESHOOTING.md        # All troubleshooting solutions
│
├── deployment/                    # Production SSM deployment scripts
│   ├── deploy-windows-client.sh  # Main deployment script (DCV, LucidLink, software)
│   ├── README.md                 # Deployment documentation
│   └── terraform-provisioner.tf  # Terraform integration example
│
├── iam/                           # IAM user configuration
│   ├── setup.sh                  # Automated IAM setup
│   ├── cleanup.sh                # Automated IAM cleanup
│   ├── ll-win-client-user-policy.json  # IAM policy
│   ├── main.tf                   # Terraform for IAM
│   └── README.md                 # IAM directory guide
│
└── terraform/clients/             # Infrastructure as Code
    ├── main.tf                    # VPC and networking
    ├── variables.tf               # Input variables
    ├── ec2-client.tf              # Windows instances and IAM
    ├── s3-userdata.tf             # S3 bucket for userdata scripts
    ├── outputs.tf                 # Output values
    └── templates/
        ├── windows-userdata.ps1   # Full setup script (uploaded to S3)
        └── minimal-userdata.ps1   # Bootstrap script (in EC2 userdata)
```

---

## Documentation

### Getting Started
- **[IAM Setup Guide](docs/IAM-SETUP.md)** - Create secure IAM user (recommended)
- **[Deployment Guide](docs/DEPLOYMENT-GUIDE.md)** - Complete deployment walkthrough
- **[Troubleshooting Guide](docs/TROUBLESHOOTING.md)** - Common issues and solutions

### Testing
- **[Testing Guide](docs/TESTING.md)** - Automated testing with `test-deployment.sh`
- **[Test Plan](docs/TEST-PLAN.md)** - Manual test plan with 14 test cases

### Quick References
- **IAM Quick Start**: `cd iam && ./setup.sh`
- **Deploy**: `uv run ll-win-client-aws.py`
- **Config Location**: `~/.ll-win-client/config.json`
- **Connection Files**: `~/Desktop/LucidLink-DCV/`
- **CloudWatch Logs**: `/aws/ec2/ll-win-client`

---

## Common Tasks

### Deploy New Instances
```bash
uv run ll-win-client-aws.py
# Choose Option 3: Deploy Client Instances
```

### Regenerate Passwords/Connection Files
```bash
uv run ll-win-client-aws.py
# Choose Option 5: Regenerate Connection Files
```

### Check Deployment Status
```bash
uv run ll-win-client-aws.py
# Choose Option 4: View Deployment Status
```

### Stop Instances (Save Money)
```bash
uv run ll-win-client-aws.py
# Choose Option 6: Stop All Instances
# Stops compute, keeps storage - saves ~95% of costs
```

### Start Instances (Resume Work)
```bash
uv run ll-win-client-aws.py
# Choose Option 7: Start All Instances
# Resumes stopped instances
# Note: DCV connection files are automatically regenerated with new public IPs
```

### Destroy Everything
```bash
uv run ll-win-client-aws.py
# Choose Option 8: Destroy Client Instances
```

### Manual Terraform Commands
```bash
cd terraform/clients
terraform plan    # Preview changes
terraform apply   # Apply changes
terraform destroy # Remove all resources
```

### Enable NVIDIA AMI (Optional)

By default, the deployment uses **standard Windows Server 2022 AMI** and GPU drivers install via Windows Update. To use the **NVIDIA RTX Virtual Workstation AMI** with pre-installed drivers:

**Prerequisites:**
1. Subscribe to NVIDIA AMI (one-time, free): https://aws.amazon.com/marketplace/pp/prodview-f4reygwmtxipu
2. Click "Continue to Subscribe" → Accept terms

**Enable NVIDIA AMI:**

**Option 1: Edit `terraform/clients/ami-override.tfvars`** (recommended)
```bash
# Edit the file
nano terraform/clients/ami-override.tfvars

# Change from:
use_nvidia_ami = false

# Change to:
use_nvidia_ami = true
```

**Option 2: Edit generated `terraform.tfvars`**
```bash
# After running TUI configuration, edit:
nano terraform/clients/terraform.tfvars

# Add or change:
use_nvidia_ami = true
```

**Deploy:**
```bash
# The TUI automatically uses these settings when deploying
uv run ll-win-client-aws.py
# Choose Option 3: Deploy Client Instances
```

**Benefits of NVIDIA AMI:**
- ✅ Pre-installed NVIDIA GRID/RTX drivers
- ✅ Faster initial setup (no driver download/install)
- ✅ Tested and certified driver version
- ✅ Recommended for production graphics workloads

**Standard AMI works fine for:**
- ⚡ Testing and development
- ⚡ Basic graphics workloads
- ⚡ When Marketplace subscription isn't feasible

### LucidLink Configuration Modes

During TUI configuration (Step 4), you'll be asked:
```
Auto-configure LucidLink as Windows service and connect to filespace? [yes/no] (yes):
```

**Auto-configure mode (yes)** - Default, recommended for demos and single-user scenarios:
- ✅ Installs LucidLink client
- ✅ Configures as Windows service
- ✅ Retrieves credentials from AWS Secrets Manager
- ✅ Auto-mounts filespace to configured drive letter (e.g., L:)
- ✅ Filespace ready to use immediately after login

**Manual mode (no)** - For multi-user or custom credential scenarios:
- ✅ Installs LucidLink client
- ❌ Does NOT configure service or mount
- 👤 End users configure credentials themselves via LucidLink UI
- Use cases: Multiple users with different credentials, manual preference

### Install Optional Applications

The deployment includes a **modular optional software framework** with environment variable control.

**Default Configuration** (what gets installed):
- ✅ **Core Software** (always installed):
  - AWS CLI
  - Amazon DCV Server (remote desktop)
  - Google Chrome
  - LucidLink client
- ✅ **Optional Software** (enabled by default):
  - VLC Media Player
  - Adobe Creative Cloud Desktop
- 📦 **Available** (disabled by default):
  - 7-Zip
  - Notepad++

**Control Optional Software via Environment Variables:**

```bash
# Disable default optional software
INSTALL_VLC=0 INSTALL_ADOBE_CC=0 ./deployment/deploy-windows-client.sh i-xxx us-east-1

# Enable additional tools
INSTALL_7ZIP=1 INSTALL_NOTEPAD_PP=1 ./deployment/deploy-windows-client.sh i-xxx us-east-1

# Mix and match
INSTALL_VLC=0 INSTALL_7ZIP=1 ./deployment/deploy-windows-client.sh i-xxx us-east-1
```

**Note**: The TUI automatically calls the deployment script. To customize software, you'll need to:
1. Deploy with TUI (gets core + defaults)
2. Manually run deployment script with custom env vars to adjust software, OR
3. Modify `ll-win-client-aws.py` to set environment variables based on user prompts

**Add Your Own Software:**

Edit `deployment/deploy-windows-client.sh` and add to the optional software section:

```bash
# Add new optional software controlled by environment variable
if [ "${INSTALL_YOUR_APP:-0}" = "1" ]; then
    run_ssm "Installing Your Application" \
        'choco install your-package -y'
fi
```

**Installation Logs:**
- CloudWatch: `/aws/ec2/ll-win-client`
- SSM command output available in AWS Console

---

## Security Notes

### Best Practices
- ✅ Use IAM user with least-privilege permissions ([IAM Setup Guide](docs/IAM-SETUP.md))
- ✅ Rotate AWS access keys every 90 days
- ✅ Delete `~/Desktop/LucidLink-DCV/PASSWORDS.txt` after saving elsewhere
- ✅ Keep `~/.ll-win-client/config.json` secure (contains credentials)
- ✅ Stop instances when not in use (Option 6), or destroy when done permanently (Option 8)
- ✅ Enable MFA on AWS root account

### What's Encrypted
- ✅ EBS volumes encrypted at rest
- ✅ LucidLink credentials in AWS Secrets Manager
- ✅ DCV connections use TLS encryption

### What's NOT Encrypted
- ⚠️ `~/.ll-win-client/config.json` - base64-encoded only
- ⚠️ `PASSWORDS.txt` - plaintext on Desktop

---

## Cost Management

### Estimated Costs (us-east-1)

**Per Instance (examples):**
| Component | GPU | Cost |
|-----------|-----|------|
| g4dn.xlarge (4 vCPU, 16GB) | NVIDIA T4 | ~$0.50/hour |
| g4dn.2xlarge (8 vCPU, 32GB) | NVIDIA T4 | ~$0.75/hour |
| g4dn.4xlarge (16 vCPU, 64GB) | NVIDIA T4 | ~$1.20/hour |
| g5.xlarge (4 vCPU, 16GB) | NVIDIA A10G | ~$1.00/hour |
| g5.2xlarge (8 vCPU, 32GB) | NVIDIA A10G | ~$1.50/hour |
| g6.xlarge (4 vCPU, 16GB) | NVIDIA L4 | ~$0.84/hour |
| EBS Storage (100GB) | - | ~$0.01/hour |
| Data Transfer Out | - | Varies |

**Example**: 2× g4dn.xlarge for 8 hours = ~$8-10
**Note**: Prices vary by region and instance type. Check AWS pricing page for your selected region and GPU instance.

### Save Money
- ✅ **Stop instances when not in use** (Option 6) - Saves ~95% of costs, keeps your data
- ✅ **Destroy when done permanently** (Option 8) - Removes everything
- ✅ Use smaller instances for testing
- ✅ Monitor costs in AWS Cost Explorer
- ✅ Set up billing alerts in AWS

**Stop vs Destroy:**
- **Stop**: Saves compute costs (~$0.50-1.20/hour), keeps storage (~$0.01/hour), can resume work
  - Note: Public IPs change on start; DCV files are automatically regenerated
- **Destroy**: Removes everything, no costs, cannot resume (must redeploy)

---

## Troubleshooting

### Quick Diagnostics

**Script won't start:**
```bash
# Check Python
python3 --version

# Reinstall dependencies
uv sync

# Check for errors
uv run ll-win-client-aws.py --help
```

**Can't connect to AWS:**
```bash
# Verify AWS credentials
aws sts get-caller-identity --profile ll-win-client

# Test EC2 access
aws ec2 describe-instances --region us-east-1
```

**Terraform errors:**
```bash
cd terraform/clients
terraform init    # Reinitialize
terraform validate # Check for errors
```

**Can't connect to DCV:**
- Wait 15-20 minutes after deployment for full initialization
- Check instance is running in AWS Console
- Verify DCV client is installed on your local machine
- Check `PASSWORDS.txt` for correct password

**For detailed troubleshooting**: See [Troubleshooting Guide](docs/TROUBLESHOOTING.md)

---

## Cleanup

### Remove Deployment
```bash
uv run ll-win-client-aws.py
# Choose Option 6: Destroy Client Instances
```

This removes:
- All EC2 instances
- VPC and networking
- Security groups
- IAM roles
- Secrets
- CloudWatch logs

### Remove IAM User (when done with project)
```bash
cd iam
./cleanup.sh
```

### Remove Local Files
```bash
rm -rf ~/.ll-win-client/        # Configuration
rm -rf ~/Desktop/LucidLink-DCV/ # Connection files
```

---

## Support

### Getting Help

1. **Documentation**:
   - [IAM Setup Guide](docs/IAM-SETUP.md)
   - [Deployment Guide](docs/DEPLOYMENT-GUIDE.md)
   - [Troubleshooting Guide](docs/TROUBLESHOOTING.md)

2. **Logs**:
   - Script log: `/tmp/ll-win-client-aws-*.log`
   - CloudWatch: `/aws/ec2/ll-win-client`
   - Instance log: `C:\lucidlink-init.log` (via SSM)

3. **GitHub Issues**: https://github.com/dmcp718/ll-win-client-aws/issues

4. **Terraform State**: `terraform/clients/terraform.tfstate`

---

## Contributing

We welcome contributions! To contribute:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

**Please ensure:**
- All documentation is updated
- Code follows existing style
- Terraform configurations are validated
- Scripts are tested

---

## License

MIT License - See LICENSE file for details.

---

## Acknowledgments

- **Amazon DCV** - High-performance remote desktop protocol
- **NVIDIA** - GPU drivers and RTX Virtual Workstation AMI
- **LucidLink** - Cloud-native filesystem
- **Terraform** - Infrastructure as Code
- **Rich** - Python TUI library

---

**Quick Links:**
- **Repository**: https://github.com/dmcp718/ll-win-client-aws
- **Issues**: https://github.com/dmcp718/ll-win-client-aws/issues
- **AWS DCV Client**: https://download.nice-dcv.com/
- **NVIDIA AMI**: https://aws.amazon.com/marketplace/pp/prodview-f4reygwmtxipu

**Last Updated**: 2025-11-04

---

## Recent Updates

**2025-11-04:**
- ✅ Added optional LucidLink auto-configuration mode
  - Choose between auto-configure (service + mount) or manual setup during TUI configuration
  - Default: auto-configure (maintains existing behavior)
- ✅ Improved deployment reliability with robust instance readiness checks
  - Now waits for both EC2 state=running AND SSM agent online
  - Added 60-second buffer after checks pass for Windows initialization
  - Prevents "InvalidInstanceId... not in valid state" errors
- ✅ Enhanced modular optional software framework
  - VLC and Adobe CC enabled by default
  - 7-Zip and Notepad++ available (disabled by default)
  - Control via environment variables: `INSTALL_VLC=0`, `INSTALL_ADOBE_CC=0`, etc.
