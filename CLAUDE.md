# LucidLink Windows Client Azure Deployment

## Project Overview

**Purpose:** Automated deployment tool for GPU-accelerated Windows 11 workstations with LucidLink client on Azure

**Status:** Production-ready Azure deployment

**Main Entry Point:** `ll-win-client.py` - Interactive TUI for managing deployments

## Quick Start

```bash
# Install dependencies
uv sync

# Login to Azure
az login

# Run deployment TUI
uv run ll-win-client.py

# Auto-approve prompts
uv run ll-win-client.py -y
```

## Project Structure

```
ll-win-client-aws/
├── ll-win-client.py              # Main Python TUI
├── pyproject.toml                # Dependencies
├── README.md                     # Main documentation
└── terraform/
    └── azure/                    # Azure infrastructure
        ├── main.tf               # All resources (VNet, VMs, Key Vault, etc.)
        ├── variables.tf          # Input variables
        ├── outputs.tf            # Output values
        └── versions.tf           # Provider requirements
```

## Architecture

```
User → Python TUI (ll-win-client.py) → Terraform → Azure
                    ↓
            Azure CLI Credentials (az login)
                    ↓
            Infrastructure Provisioning
                    ↓
            Custom Script Extension (LucidLink install)
```

### Deployment Flow
1. Terraform creates Resource Group, VNet, VMs, Key Vault
2. Custom Script Extension installs LucidLink MSI
3. RDP connection files generated to `~/Desktop/LucidLink-RDP/`

## Key Technologies

- **Python 3.8+** with Rich, azure-* libraries
- **Terraform 1.2+** for infrastructure
- **Azure CLI** for authentication

## Configuration

**Location:** `~/.ll-win-client/config.json`

Key settings:
- Azure location (eastus, westus2, etc.)
- Subscription ID
- Resource Group name
- VM size and count
- Admin username/password
- LucidLink filespace credentials

## Azure VM Sizes

GPU VMs supported:
- `Standard_NV6ads_A10_v5` - 6 vCPU, 55GB, NVIDIA A10 (default)
- `Standard_NV12ads_A10_v5` - 12 vCPU, 110GB, NVIDIA A10
- `Standard_NV36ads_A10_v5` - 36 vCPU, 440GB, NVIDIA A10
- `Standard_NC4as_T4_v3` - 4 vCPU, 28GB, NVIDIA T4
- `Standard_NC8as_T4_v3` - 8 vCPU, 56GB, NVIDIA T4

## Common Tasks

### Azure Login
```bash
az login
az account set --subscription "SUBSCRIPTION_ID"
```

### Terraform Operations
```bash
cd terraform/azure
terraform init
terraform validate
terraform plan
terraform apply
```

## Important Files

| File | Purpose |
|------|---------|
| `ll-win-client.py` | Main TUI application |
| `terraform/azure/main.tf` | All Azure resources |
| `terraform/azure/variables.tf` | Input variables |
| `terraform/azure/outputs.tf` | Output values |

## Remote Access

### RDP Connection
- Port: 3389
- Client: Built-in RDP (macOS/Windows/Linux)
- Files: `~/Desktop/LucidLink-RDP/*.rdp`

## Security

- Azure Key Vault for LucidLink credentials
- Encrypted VM disks at rest
- Network Security Group restricts access to RDP port
- Admin password set during deployment

## Cost Management

Use TUI menu options:
- **Option 6:** Stop All VMs (pause costs)
- **Option 7:** Start All VMs (resume)
- **Option 8:** Destroy Resources (remove all)

Estimated costs:
- Standard_NV6ads_A10_v5: ~$0.90/hour
- Standard_NC4as_T4_v3: ~$0.53/hour

## Troubleshooting

- **Logs:** `/tmp/ll-win-client-*.log`
- **Azure Portal:** Check VM boot diagnostics

Common issues:
- Location invalid: Use Azure format (eastus, not us-east-1)
- Auth fails: Run `az login` again
- VM not accessible: Check NSG allows RDP (3389)

## Development

```bash
# Install dependencies
uv sync

# Run application
uv run ll-win-client.py

# View configuration
cat ~/.ll-win-client/config.json
```

## Contribution Guidelines

- DO NOT include Claude/Anthropic as contributor or co-author in commits
- NEVER add attribution or co-author
- Follow existing code patterns
- Update documentation when adding features

## Resources

- [Azure CLI](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli)
- [Terraform](https://www.terraform.io/)
- [LucidLink](https://www.lucidlink.com/)
