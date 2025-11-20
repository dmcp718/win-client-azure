# LucidLink Windows Client - Azure Deployment

Automated deployment tool for Windows 11 VMs with LucidLink client on Azure.

**Perfect for demonstrations, temporary cloud workstations, and remote workflows.**

GitHub Repository: https://github.com/dmcp718/win-client-azure.git

---

## What This Does

Deploy Windows 11 VMs on Azure in minutes:
- ✅ **One command deployment** - Interactive TUI guides you through setup
- ✅ **Windows 11 Pro** - Latest win11-23h2-pro image
- ✅ **RDP remote access** - Standard Windows Remote Desktop Protocol
- ✅ **LucidLink installation** - Automated MSI download and install
- ✅ **Automated password management** - Simple, secure credentials
- ✅ **Complete automation** - Terraform + Python TUI handles everything
- ✅ **Azure Key Vault** - Secure credential storage

**Deployment time**: 5-10 minutes | **Access via**: RDP (port 3389)

---

## Quick Start

```bash
# 1. Clone repository
git clone https://github.com/dmcp718/win-client-azure.git
cd win-client-azure

# 2. Install dependencies
uv sync

# 3. Ensure you're logged into Azure
az login

# 4. Run deployment
uv run ll-win-client.py
# Enter Azure credentials when prompted
```

---

## Prerequisites

### Required (Before You Start)

- ✅ **Azure Account** with appropriate permissions
- ✅ **LucidLink Credentials** (filespace domain, username, password)

### Local Tools (Must Be Installed)

- ✅ **Python 3.8+** - Check: `python3 --version`
- ✅ **uv** - Python package manager
  - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Homebrew: `brew install uv`
- ✅ **Terraform 1.2+** - Infrastructure as Code tool
  - Download: https://www.terraform.io/downloads
  - Homebrew: `brew install terraform`
- ✅ **Azure CLI** - Azure command-line interface
  - Download: https://learn.microsoft.com/cli/azure/install-azure-cli
  - Homebrew: `brew install azure-cli`

**Verify prerequisites:**
```bash
python3 --version  # Should show 3.8+
uv --version       # Should show uv installed
terraform -version # Should show 1.2+
az --version       # Should show azure-cli installed
```

**Quick install with Homebrew (macOS):**
```bash
brew install uv terraform azure-cli
```

---

## Installation

```bash
# Clone repository
git clone https://github.com/dmcp718/win-client-azure.git
cd win-client-azure

# Install Python dependencies
uv sync

# Login to Azure
az login

# Verify installation
uv run ll-win-client.py
```

---

## Features

### Infrastructure
- **Windows 11 Pro** (win11-23h2-pro) with latest updates
- **Flexible VM Sizes** - Choose from Azure's B-series (budget) to D-series (performance)
  - Default: Standard_B4ms (4 vCPU, 16GB RAM)
- **Virtual Network** with subnet and NSG for isolated networking
- **Network Security Group** with RDP (3389) access
- **Public IP addresses** for remote access
- **Azure Key Vault** for secure credential storage
- **User Assigned Identity** for VM permissions

### Automation
- **Interactive TUI** for configuration with Rich library
- **Terraform** for Infrastructure as Code
- **Custom Script Extension** - Automated software installation
  - PowerShell-based deployment
  - Start-BitsTransfer for reliable downloads
  - Error handling and logging

### LucidLink Installation
- **Automated MSI download** - Uses PowerShell Start-BitsTransfer
- **Silent installation** - No user interaction required
- **Manual configuration** - LucidLink installed, user configures credentials via UI
- **Service-ready** - Can be configured as Windows service post-deployment

### Remote Access
- **RDP** - Standard Windows Remote Desktop Protocol
  - Port 3389 access through NSG
  - TLS encryption
  - Full Windows 11 experience

### Cost Management
- **Stop/Start VMs** - Save costs when not in use
- **Complete destroy** - Remove everything when done permanently
- **Deallocate when stopped** - Only pay for storage

---

## What Gets Deployed

**Per deployment, Terraform creates:**

| Resource | Quantity | Purpose |
|----------|----------|---------|
| Resource Group | 1 | Container for all resources |
| Virtual Network | 1 | Isolated network |
| Subnet | 1 | VM subnet |
| Network Security Group | 1 | RDP access control |
| Public IP | 1 per VM | Internet access |
| Network Interface | 1 per VM | VM network connectivity |
| Windows 11 VM | 1 | Your workstation |
| User Assigned Identity | 1 | VM permissions for Key Vault |
| Key Vault | 1 | LucidLink credential storage |

**Estimated costs** (eastus2, example):
- Standard_B4ms: ~$0.166/hour per VM
- Standard SSD storage (128GB): ~$0.05/day
- Public IP: ~$0.005/hour
- **Stop/deallocate VMs when not in use to save money!**

---

## Configuration

### Main Script

Configuration stored at: `~/.ll-win-client/config.json`

**Contains:**
- Azure subscription ID
- Azure region
- Resource group name
- VM settings (size, count)
- LucidLink credentials (base64-encoded)
- Admin username and password

**Security Note**: File contains base64-encoded credentials (basic obfuscation, not encryption). Keep secure.

---

## Main Menu

```
╔══════════════════════════════════════════╗
║  LucidLink Windows Client Deployment     ║
║  Azure VM Provisioning                   ║
╚══════════════════════════════════════════╝

1. Configure Client Deployment
2. Configure LucidLink Credentials
3. Deploy Windows 11 VMs with LucidLink Client
4. Monitor Deployment Status
5. Destroy Client Infrastructure
6. Exit
```

**Typical workflow:**
1. Configure (Option 1) - Set up Azure, VM settings
2. Configure LucidLink (Option 2) - Set filespace credentials
3. Deploy (Option 3) - Launch infrastructure (~5-10 minutes)
4. Connect - Use RDP to VM's public IP
5. Destroy (Option 5) - Remove all resources when done

---

## Accessing Instances

### RDP Connection

**Connect to your VM:**
1. Get public IP from deployment output
2. Use Remote Desktop client
3. Connect to: `<public-ip>:3389`
4. Login:
   - Username: `azureuser` (or configured admin username)
   - Password: From configuration

**macOS users:**
- Download Microsoft Remote Desktop from Mac App Store
- Create new PC connection with VM's public IP

**Windows users:**
- Use built-in Remote Desktop Connection (mstsc.exe)
- Enter VM's public IP

---

## Project Structure

```
win-client-azure/
├── ll-win-client.py              # Main Python TUI application
├── pyproject.toml                 # Python dependencies
├── README.md                      # This file
│
└── terraform/azure/               # Azure Infrastructure as Code
    ├── main.tf                    # VNet, NSG, VMs, Key Vault
    ├── variables.tf               # Input variables
    ├── outputs.tf                 # Output values (IPs, VM names)
    ├── versions.tf                # Provider versions
    └── templates/
        └── windows-userdata.ps1   # VM initialization script
```

---

## Common Tasks

### Deploy New VMs
```bash
uv run ll-win-client.py
# Choose Option 3: Deploy Windows 11 VMs
```

### Check Deployment Status
```bash
uv run ll-win-client.py
# Choose Option 4: Monitor Deployment Status
```

### Destroy Everything
```bash
uv run ll-win-client.py
# Choose Option 5: Destroy Client Infrastructure
```

### Manual Terraform Commands
```bash
cd terraform/azure
terraform plan    # Preview changes
terraform apply   # Apply changes
terraform destroy # Remove all resources
```

---

## LucidLink Configuration

The deployment installs LucidLink client but **does not** auto-configure it. After connecting via RDP:

1. Launch LucidLink from Start Menu
2. Enter your filespace domain (e.g., `tc-east-1.dmpfs`)
3. Enter your credentials
4. Choose mount point (e.g., `L:`)
5. Connect

**Why manual configuration?**
- More secure - credentials entered directly in VM
- User-controlled - each user can use their own credentials
- Flexible - supports multiple filespaces per VM

---

## Security Notes

### Best Practices
- ✅ Use strong admin passwords for VMs
- ✅ Keep `~/.ll-win-client/config.json` secure (contains credentials)
- ✅ Stop/deallocate VMs when not in use
- ✅ Destroy resources when done permanently
- ✅ Enable MFA on Azure account
- ✅ Regularly update Windows via Windows Update

### What's Encrypted
- ✅ VM disks encrypted at rest by default
- ✅ LucidLink credentials in Azure Key Vault
- ✅ RDP connections use TLS encryption

### What's NOT Encrypted
- ⚠️ `~/.ll-win-client/config.json` - base64-encoded only
- ⚠️ Admin password in configuration file

---

## Cost Management

### Estimated Costs (eastus2)

**Per VM (example):**
| Component | Cost |
|-----------|------|
| Standard_B4ms (4 vCPU, 16GB) | ~$0.166/hour (~$120/month) |
| Standard SSD (128GB) | ~$0.05/day (~$1.50/month) |
| Public IP (Standard) | ~$0.005/hour (~$3.65/month) |

**Example**: 1× Standard_B4ms for 8 hours = ~$1.33

**Note**: Prices vary by region and VM size. Check Azure pricing for your selected region.

### Save Money
- ✅ **Stop/deallocate VMs when not in use** - Saves ~99% of VM costs, keeps data
- ✅ **Destroy when done permanently** - Removes everything
- ✅ Use smaller VM sizes for testing (e.g., Standard_B2ms)
- ✅ Monitor costs in Azure Cost Management
- ✅ Set up budget alerts in Azure

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
uv run ll-win-client.py
```

**Can't connect to Azure:**
```bash
# Verify Azure login
az account show

# List subscriptions
az account list
```

**Terraform errors:**
```bash
cd terraform/azure
terraform init    # Reinitialize
terraform validate # Check for errors
```

**Can't connect via RDP:**
- Verify VM is running: `az vm list -g ll-win-client-rg --query "[].{Name:name, State:powerState}" -o table`
- Check NSG allows RDP: `az network nsg rule list -g ll-win-client-rg --nsg-name ll-win-client-nsg -o table`
- Verify correct public IP
- Check admin password is correct

**LucidLink not installed:**
- Connect via RDP
- Check `C:\Windows\Temp\lucidlink_install.log` for errors
- Check downloaded file: `C:\Windows\Temp\lucid_update\lucidinstaller.msi`
- Manually run MSI if needed

---

## Cleanup

### Remove Deployment
```bash
uv run ll-win-client.py
# Choose Option 5: Destroy Client Infrastructure
```

This removes:
- All VMs
- Virtual Network and subnet
- Network Security Group
- Public IPs
- Key Vault (with soft-delete, purged after 7 days)
- User Assigned Identity
- Resource Group

### Remove Local Files
```bash
rm -rf ~/.ll-win-client/        # Configuration
```

---

## Support

### Getting Help

1. **Logs**:
   - VM Extension log: Check Azure Portal → VM → Extensions
   - LucidLink install log: `C:\Windows\Temp\lucidlink_install.log` (via RDP)
   - Terraform state: `terraform/azure/terraform.tfstate`

2. **GitHub Issues**: https://github.com/dmcp718/win-client-azure/issues

---

## License

MIT License - See LICENSE file for details.

---

## Acknowledgments

- **Microsoft Azure** - Cloud infrastructure platform
- **LucidLink** - Cloud-native filesystem
- **Terraform** - Infrastructure as Code
- **Rich** - Python TUI library

---

**Quick Links:**
- **Repository**: https://github.com/dmcp718/win-client-azure
- **Issues**: https://github.com/dmcp718/win-client-azure/issues
- **Azure CLI**: https://learn.microsoft.com/cli/azure/

**Last Updated**: 2025-11-20

---

## Recent Updates

**2025-11-20:**
- ✅ Migrated from AWS to Azure infrastructure
- ✅ Windows 11 Pro VMs with RDP access
- ✅ Automated LucidLink MSI installation via Custom Script Extension
- ✅ Azure Key Vault for credential storage
- ✅ Updated TUI for Azure compatibility
- ✅ Simplified deployment workflow
