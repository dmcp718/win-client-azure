#!/usr/bin/env python3
"""
LucidLink Windows Client Azure Setup - Interactive TUI for deploying Windows LucidLink clients on Azure

This script provides an interactive terminal interface to:
1. Configure Azure VNet and network settings
2. Configure LucidLink filespace credentials
3. Deploy Windows Server VMs with LucidLink client
4. Monitor deployment status
5. Destroy client infrastructure when needed

Run with: uv run ll-win-client.py

Dependencies are managed via pyproject.toml

Examples:
  ll-win-client.py                     # Interactive mode
  ll-win-client.py -y                  # Auto-approve deployment/destroy prompts
  ll-win-client.py --yes               # Same as -y
"""

import os
import sys
import json
import subprocess
import shutil
import time
import re
import base64
import secrets
import string
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging

# Rich imports for TUI
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich import box

# Setup logging
log_file = f"/tmp/ll-win-client-azure-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)
console = Console()


class LLWinClientAzureSetup:
    def __init__(self, auto_approve: bool = False):
        self.script_dir = Path(__file__).parent.absolute()
        self.config_dir = Path.home() / ".ll-win-client"
        self.client_config_file = self.config_dir / "config.json"
        self.vm_sizes_cache_file = self.config_dir / "azure-vm-sizes.json"
        self.terraform_dir = self.script_dir / "terraform" / "azure"
        self.templates_dir = self.terraform_dir / "templates"

        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Configuration state
        self.config = {}
        self.valid_instance_types = set()
        self.auto_approve = auto_approve

        # Color palette
        self.colors = {
            'primary': '#3b82f6',
            'success': '#10b981',
            'warning': '#f59e0b',
            'error': '#ef4444',
            'info': '#6b7280',
        }

        # Valid Azure US locations
        self.azure_us_locations = [
            ('eastus', 'East US', 'Virginia'),
            ('eastus2', 'East US 2', 'Virginia'),
            ('centralus', 'Central US', 'Iowa'),
            ('northcentralus', 'North Central US', 'Illinois'),
            ('southcentralus', 'South Central US', 'Texas'),
            ('westcentralus', 'West Central US', 'Wyoming'),
            ('westus', 'West US', 'California'),
            ('westus2', 'West US 2', 'Washington'),
            ('westus3', 'West US 3', 'Arizona'),
        ]

    # ========== Configuration Management ==========

    def load_config(self) -> Dict:
        """Load client configuration from JSON file"""
        if self.client_config_file.exists():
            try:
                with open(self.client_config_file, 'r') as f:
                    self.config = json.load(f)

                # Decode password if it was base64 encoded
                if self.config.get('_password_encoded') and self.config.get('filespace_password'):
                    try:
                        password_bytes = base64.b64decode(self.config['filespace_password'])
                        self.config['filespace_password'] = password_bytes.decode('utf-8')
                        # Remove the encoding flag from runtime config
                        del self.config['_password_encoded']
                    except Exception as e:
                        logger.warning(f"Failed to decode password: {e}")

                logger.info(f"Loaded client configuration from {self.client_config_file}")
                return self.config
            except Exception as e:
                logger.error(f"Failed to load client config: {e}")
                console.print(f"[{self.colors['error']}]Failed to load client configuration: {e}[/]")
                return {}
        return {}

    def save_config(self, config: Dict) -> bool:
        """Save client configuration to JSON file"""
        try:
            # Obfuscate sensitive data in saved config (base64 encode)
            safe_config = config.copy()
            if 'filespace_password' in safe_config and safe_config['filespace_password']:
                # Base64 encode the password for obfuscation (not encryption, just to avoid plain text)
                password_bytes = safe_config['filespace_password'].encode('utf-8')
                safe_config['filespace_password'] = base64.b64encode(password_bytes).decode('utf-8')
                safe_config['_password_encoded'] = True  # Flag to indicate encoding

            with open(self.client_config_file, 'w') as f:
                json.dump(safe_config, f, indent=2)
            logger.info(f"Saved client configuration to {self.client_config_file}")
            console.print(f"[{self.colors['success']}]✓ Configuration saved to {self.client_config_file}[/]")
            return True
        except Exception as e:
            logger.error(f"Failed to save client config: {e}")
            console.print(f"[{self.colors['error']}]Failed to save configuration: {e}[/]")
            return False

    def validate_config(self, config: Dict) -> Tuple[bool, List[str]]:
        """Validate configuration values"""
        errors = []

        # Validate filespace domain
        if 'filespace_domain' in config:
            domain = config['filespace_domain']
            # Allow more flexible format for LucidLink filespace naming
            if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9\-_.]*\.[a-zA-Z0-9][a-zA-Z0-9\-_.]*$', domain):
                errors.append(f"Invalid filespace domain: {domain}")
                errors.append("Expected format: filespace.domain (e.g., myfilespace.domain)")

        # Validate mount point (Windows format)
        if 'mount_point' in config:
            mount_point = config['mount_point']
            # Windows path format: Drive letter (L:) or full path (C:\LucidLink)
            if not re.match(r'^[A-Za-z]:(\\.*)?$', mount_point):
                errors.append(f"Mount point must be a Windows drive letter (e.g., L:) or path (e.g., C:\\LucidLink): {mount_point}")

        # Validate instance count
        if 'instance_count' in config:
            count = config.get('instance_count', 1)
            if count < 1 or count > 10:
                errors.append(f"Instance count must be between 1 and 10: {count}")

        # Validate VM size
        if 'vm_size' in config:
            vm_size = config['vm_size']
            # Basic Azure VM size format validation
            if not vm_size.startswith('Standard_'):
                errors.append(f"Invalid VM size format: {vm_size}")

        # Validate OS disk size
        if 'os_disk_size_gb' in config:
            size = config.get('os_disk_size_gb', 0)
            if size < 30 or size > 4095:
                errors.append(f"OS disk size must be between 30 and 4095 GB: {size}")

        # Validate data disk size
        if 'data_disk_size_gb' in config:
            size = config.get('data_disk_size_gb', 0)
            if size > 0 and (size < 100 or size > 65536):
                errors.append(f"Data disk size must be between 100 and 65536 GB: {size}")

        # Validate VNet CIDR
        if 'vnet_cidr' in config:
            cidr = config['vnet_cidr']
            # Basic CIDR validation
            if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$', cidr):
                errors.append(f"Invalid VNet CIDR format: {cidr}")

        # Validate Azure location
        if 'location' in config:
            location = config['location']
            if not location:
                errors.append("Azure location is required")

        # Validate admin credentials
        if 'admin_username' in config:
            if not config['admin_username']:
                errors.append("Admin username is required")
        if 'admin_password' in config:
            password = config['admin_password']
            if len(password) < 8:
                errors.append("Admin password must be at least 8 characters")

        # Validate credentials exist
        if not config.get('filespace_user'):
            errors.append("Filespace username is required")
        if not config.get('filespace_password'):
            errors.append("Filespace password is required")

        return (len(errors) == 0, errors)

    def validate_azure_credentials(self) -> bool:
        """Validate Azure credentials by checking az cli login status"""
        try:
            # Check if az cli is installed
            if not shutil.which('az'):
                logger.error("Azure CLI (az) not found")
                return False

            # Check if logged in by trying to get account info
            result = subprocess.run(
                ['az', 'account', 'show'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                return True
            else:
                logger.error(f"Azure login check failed: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Azure credentials validation failed: {e}")
            return False

    def fetch_azure_vm_sizes(self, location: str = None) -> set:
        """Fetch all available Azure VM sizes for a location"""
        try:
            # Check if we have a cached version that's less than 7 days old
            if self.vm_sizes_cache_file.exists():
                try:
                    with open(self.vm_sizes_cache_file, 'r') as f:
                        cache_data = json.load(f)
                        cache_time = datetime.fromisoformat(cache_data.get('timestamp', ''))
                        if datetime.now() - cache_time < timedelta(days=7):
                            logger.info(f"Using cached Azure VM sizes ({len(cache_data['vm_sizes'])} sizes)")
                            return set(cache_data['vm_sizes'])
                except Exception as e:
                    logger.debug(f"Could not load cache: {e}")

            # Need to fetch fresh data
            console.print("[dim]Fetching Azure VM sizes...[/dim]")

            # Use provided location or default
            if not location:
                location = self.config.get('location', 'eastus')

            # Use Azure CLI to fetch VM sizes
            result = subprocess.run(
                ['az', 'vm', 'list-sizes', '--location', location, '--output', 'json'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                vm_data = json.loads(result.stdout)
                vm_sizes = set(vm['name'] for vm in vm_data)

                # Cache the results
                cache_data = {
                    'timestamp': datetime.now().isoformat(),
                    'location': location,
                    'vm_sizes': sorted(list(vm_sizes))
                }
                with open(self.vm_sizes_cache_file, 'w') as f:
                    json.dump(cache_data, f, indent=2)

                logger.info(f"Fetched {len(vm_sizes)} Azure VM sizes")
                console.print(f"[{self.colors['success']}]✓ Found {len(vm_sizes)} available VM sizes[/]")

                return vm_sizes
            else:
                logger.warning(f"Could not fetch VM sizes: {result.stderr}")
                return set()

        except Exception as e:
            logger.warning(f"Could not fetch VM sizes: {e}")
            console.print(f"[{self.colors['warning']}]Could not fetch VM sizes from Azure, using basic validation[/]")
            return set()

    def is_valid_vm_size(self, vm_size: str) -> bool:
        """Check if a VM size is valid"""
        # First check against cached list if available
        if self.valid_instance_types and vm_size in self.valid_instance_types:
            return True

        # Fall back to Azure VM size pattern validation
        # Azure VM sizes follow pattern: Standard_[Family][Version][Variant]_[Size]
        # Examples: Standard_NV6ads_A10_v5, Standard_NC4as_T4_v3, Standard_D2s_v3
        return bool(re.match(r'^Standard_[A-Z]+[0-9]+[a-z]*(_[A-Z0-9]+)?_v[0-9]+$', vm_size))

    def fetch_gpu_vm_sizes(self, location: str = None) -> List[Dict]:
        """Fetch GPU VM sizes with detailed specifications from Azure"""
        try:
            console.print("[dim]Fetching Azure GPU VM sizes...[/dim]")

            # Use provided location or default
            if not location:
                location = self.config.get('location', 'eastus')

            # Use Azure CLI to fetch VM sizes
            result = subprocess.run(
                ['az', 'vm', 'list-sizes', '--location', location, '--output', 'json'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                vm_data = json.loads(result.stdout)

                # Filter for GPU VMs (NC and NV series)
                gpu_vms = []
                for vm in vm_data:
                    vm_name = vm['name']
                    # Include NC (compute) and NV (visualization) series
                    if vm_name.startswith('Standard_NC') or vm_name.startswith('Standard_NV'):
                        # Parse the VM size to extract details
                        gpu_vms.append({
                            'type': vm_name,
                            'vcpu': vm.get('numberOfCores', 0),
                            'memory_mb': vm.get('memoryInMb', 0),
                            'memory_gb': vm.get('memoryInMb', 0) // 1024,
                            'gpu_count': 1,  # Azure GPU VMs typically have 1 GPU per size
                            'gpu_manufacturer': 'NVIDIA',
                            'gpu_name': 'T4' if '_T4_' in vm_name else 'A10' if '_A10_' in vm_name else 'Unknown',
                            'gpu_memory_gb': 16 if '_T4_' in vm_name else 24 if '_A10_' in vm_name else 0,
                        })

                # Sort by VM family, then by vCPU
                gpu_vms.sort(key=lambda x: (x['type'].split('_')[1] if '_' in x['type'] else x['type'], x['vcpu']))

                if gpu_vms:
                    logger.info(f"Found {len(gpu_vms)} GPU VM sizes in {location}")
                    console.print(f"[{self.colors['success']}]✓ Found {len(gpu_vms)} GPU VM sizes available in {location}[/]")
                    return gpu_vms
                else:
                    logger.info(f"No GPU VMs found via Azure CLI, using fallback list")
                    return self._get_fallback_gpu_instances()
            else:
                logger.warning(f"Could not fetch GPU VM sizes: {result.stderr}")
                return self._get_fallback_gpu_instances()

        except Exception as e:
            logger.warning(f"Could not fetch GPU VM sizes: {e}")
            console.print(f"[{self.colors['warning']}]Could not fetch from Azure, using default GPU VM sizes[/]")
            return self._get_fallback_gpu_instances()

    def _get_fallback_gpu_instances(self) -> List[Dict]:
        """Fallback list of Azure VM sizes (GPU and non-GPU)"""
        return [
            {
                'type': 'Standard_F16s_v2',
                'vcpu': 16,
                'memory_gb': 32,
                'gpu_count': 0,
                'gpu_manufacturer': None,
                'gpu_name': 'None - Compute Optimized',
                'gpu_memory_gb': 0
            },
            {
                'type': 'Standard_L8s_v3',
                'vcpu': 8,
                'memory_gb': 64,
                'gpu_count': 0,
                'gpu_manufacturer': None,
                'gpu_name': 'None - Storage Optimized',
                'gpu_memory_gb': 0
            },
            {
                'type': 'Standard_NC4as_T4_v3',
                'vcpu': 4,
                'memory_gb': 28,
                'gpu_count': 1,
                'gpu_manufacturer': 'NVIDIA',
                'gpu_name': 'T4',
                'gpu_memory_gb': 16
            },
            {
                'type': 'Standard_NC8as_T4_v3',
                'vcpu': 8,
                'memory_gb': 56,
                'gpu_count': 1,
                'gpu_manufacturer': 'NVIDIA',
                'gpu_name': 'T4',
                'gpu_memory_gb': 16
            },
            {
                'type': 'Standard_NC16as_T4_v3',
                'vcpu': 16,
                'memory_gb': 110,
                'gpu_count': 1,
                'gpu_manufacturer': 'NVIDIA',
                'gpu_name': 'T4',
                'gpu_memory_gb': 16
            },
            {
                'type': 'Standard_NC64as_T4_v3',
                'vcpu': 64,
                'memory_gb': 440,
                'gpu_count': 4,
                'gpu_manufacturer': 'NVIDIA',
                'gpu_name': 'T4',
                'gpu_memory_gb': 64
            },
            {
                'type': 'Standard_NV6ads_A10_v5',
                'vcpu': 6,
                'memory_gb': 55,
                'gpu_count': 1,
                'gpu_manufacturer': 'NVIDIA',
                'gpu_name': 'A10',
                'gpu_memory_gb': 24
            },
            {
                'type': 'Standard_NV12ads_A10_v5',
                'vcpu': 12,
                'memory_gb': 110,
                'gpu_count': 1,
                'gpu_manufacturer': 'NVIDIA',
                'gpu_name': 'A10',
                'gpu_memory_gb': 24
            },
            {
                'type': 'Standard_NV18ads_A10_v5',
                'vcpu': 18,
                'memory_gb': 220,
                'gpu_count': 1,
                'gpu_manufacturer': 'NVIDIA',
                'gpu_name': 'A10',
                'gpu_memory_gb': 24
            },
            {
                'type': 'Standard_NV36ads_A10_v5',
                'vcpu': 36,
                'memory_gb': 440,
                'gpu_count': 1,
                'gpu_manufacturer': 'NVIDIA',
                'gpu_name': 'A10',
                'gpu_memory_gb': 24
            }
        ]

    def pre_deployment_checks(self) -> bool:
        """Run all pre-deployment validation checks"""
        console.print("\n[bold]Running Pre-Deployment Checks...[/bold]\n")

        checks_passed = True

        # Check 1: Azure credentials valid
        console.print("1. Validating Azure credentials...")
        if not shutil.which('az'):
            console.print(f"  [{self.colors['error']}]✗ Azure CLI not installed[/]")
            console.print("  Install from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli")
            checks_passed = False
        elif not self.validate_azure_credentials():
            console.print(f"  [{self.colors['warning']}]⚠ Not logged in to Azure (run 'az login')[/]")
            checks_passed = False
        else:
            console.print(f"  [{self.colors['success']}]✓ Azure credentials valid[/]")

        # Check 2: Terraform installed
        console.print("\n2. Checking Terraform installation...")
        if not shutil.which('terraform'):
            console.print(f"  [{self.colors['error']}]✗ Terraform not found[/]")
            console.print("  Install from: https://www.terraform.io/downloads")
            checks_passed = False
        else:
            # Get terraform version
            try:
                result = subprocess.run(['terraform', 'version'], capture_output=True, text=True)
                version_line = result.stdout.split('\n')[0] if result.stdout else "Unknown"
                console.print(f"  [{self.colors['success']}]✓ {version_line}[/]")
            except:
                console.print(f"  [{self.colors['success']}]✓ Terraform installed[/]")

        # Check 3: Packer (optional, informational only)
        console.print("\n3. Checking Packer installation (optional)...")
        if shutil.which('packer'):
            try:
                result = subprocess.run(['packer', 'version'], capture_output=True, text=True)
                version_line = result.stdout.strip().split('\n')[0] if result.stdout else "Unknown"
                console.print(f"  [{self.colors['success']}]✓ {version_line}[/]")
            except:
                console.print(f"  [{self.colors['success']}]✓ Packer installed[/]")
        else:
            console.print(f"  [{self.colors['info']}]ℹ Packer not installed (optional, needed for custom image builds)[/]")

        console.print()
        return checks_passed

    # ========== Interactive TUI Workflows ==========

    def show_banner(self):
        """Display application banner"""
        banner = Text()
        banner.append("╔══════════════════════════════════════════╗\n", style="bold blue")
        banner.append("║  LucidLink Windows Client Deployment     ║\n", style="bold blue")
        banner.append("║  Multi-Instance Windows Provisioning     ║\n", style="bold blue")
        banner.append("╚══════════════════════════════════════════╝", style="bold blue")
        console.print(banner)
        console.print()

    def configure_deployment(self):
        """Interactive configuration wizard"""
        console.clear()
        self.show_banner()

        console.print(Panel.fit(
            "[bold]Client Deployment Configuration Wizard[/bold]\n"
            "This wizard will guide you through configuring Windows LucidLink client deployments.",
            border_style="blue"
        ))
        console.print()

        config = {}

        # Load existing values if available
        existing_config = self.load_config()

        # Step 1: Azure Location
        console.print("[bold cyan]Step 1: Azure Location[/bold cyan]")

        # Display table of valid US locations
        location_table = Table(title="Available Azure US Locations", box=box.ROUNDED)
        location_table.add_column("#", style="cyan", justify="right", width=3)
        location_table.add_column("Location ID", style="green")
        location_table.add_column("Display Name", style="white")
        location_table.add_column("Region", style="dim")

        for idx, (loc_id, display_name, region) in enumerate(self.azure_us_locations, 1):
            location_table.add_row(str(idx), loc_id, display_name, region)

        console.print(location_table)
        console.print()

        # Get default location index
        default_location = existing_config.get('location', 'eastus')
        default_idx = '1'
        for idx, (loc_id, _, _) in enumerate(self.azure_us_locations, 1):
            if loc_id == default_location:
                default_idx = str(idx)
                break

        location_choice = Prompt.ask(
            "Select location (enter number or location ID)",
            default=default_idx
        )

        # Parse selection - could be number or location ID
        if location_choice.isdigit():
            idx = int(location_choice)
            if 1 <= idx <= len(self.azure_us_locations):
                config['location'] = self.azure_us_locations[idx - 1][0]
            else:
                console.print(f"[{self.colors['warning']}]Invalid selection, using default: eastus[/]")
                config['location'] = 'eastus'
        else:
            # Check if it's a valid location ID
            valid_ids = [loc[0] for loc in self.azure_us_locations]
            if location_choice.lower() in valid_ids:
                config['location'] = location_choice.lower()
            else:
                console.print(f"[{self.colors['warning']}]Unknown location '{location_choice}', using as-is[/]")
                config['location'] = location_choice

        console.print(f"[{self.colors['success']}]✓ Selected location: {config['location']}[/]")
        console.print()

        # Step 2: Azure Credentials
        console.print("[bold cyan]Step 2: Azure Credentials[/bold cyan]")
        console.print("[dim]Checking Azure CLI login status...[/dim]")
        if self.validate_azure_credentials():
            console.print(f"[{self.colors['success']}]✓ Already logged in to Azure[/]")
        else:
            console.print(f"[{self.colors['warning']}]⚠ Not logged in to Azure[/]")
            console.print("[dim]Please run 'az login' before continuing[/dim]")
            if not Confirm.ask("Continue anyway?", default=False):
                return None
        console.print()

        # Step 3: Virtual Network Configuration
        console.print("[bold cyan]Step 3: Virtual Network Configuration[/bold cyan]")
        config['vnet_cidr'] = Prompt.ask(
            "VNet CIDR Block",
            default=existing_config.get('vnet_cidr', '10.0.0.0/16')
        )
        console.print()

        # Step 4: LucidLink Filespace Configuration
        console.print("[bold cyan]Step 4: LucidLink Filespace Configuration[/bold cyan]")

        config['filespace_domain'] = Prompt.ask(
            "Filespace Domain (e.g., filespace.domain)",
            default=existing_config.get('filespace_domain', 'filespace.domain')
        )
        config['filespace_user'] = Prompt.ask(
            "Filespace Username",
            default=existing_config.get('filespace_user', '')
        )
        config['filespace_password'] = Prompt.ask("Filespace Password", password=True)
        config['mount_point'] = Prompt.ask(
            "Mount Point (Windows drive letter or path)",
            default=existing_config.get('mount_point', 'L:')
        )

        # Ask if LucidLink should be auto-configured as service
        auto_config_default = existing_config.get('auto_configure_lucidlink', 'yes')
        auto_configure = Prompt.ask(
            "Auto-configure LucidLink as Windows service and connect to filespace?",
            choices=['yes', 'no'],
            default=auto_config_default
        )
        config['auto_configure_lucidlink'] = auto_configure

        if auto_configure == 'no':
            console.print(f"  [{self.colors['info']}]ℹ LucidLink will be installed but not configured. End users will need to configure and connect manually.[/]")
        console.print()

        # Step 5: VM Configuration
        console.print("[bold cyan]Step 5: VM Configuration[/bold cyan]")

        # Use fallback GPU instances (Azure VM sizes)
        gpu_instance_types = self._get_fallback_gpu_instances()

        if not gpu_instance_types:
            console.print(f"[{self.colors['error']}]No GPU VM sizes available.[/]")
            return None

        # Display available VMs organized by family
        console.print("\n[bold]Available VM Sizes:[/bold]")

        # Group by instance family (NC-series vs NV-series)
        families = {}
        for instance in gpu_instance_types:
            if 'NC' in instance['type']:
                family = 'NC-series (T4)'
            elif 'NV' in instance['type']:
                family = 'NV-series (A10)'
            else:
                family = 'Other'
            if family not in families:
                families[family] = []
            families[family].append(instance)

        # Display with grouping
        for idx, instance in enumerate(gpu_instance_types, 1):
            # Handle both GPU and non-GPU VMs
            if instance['gpu_count'] > 0:
                gpu_desc = f"{instance['gpu_count']}x {instance['gpu_manufacturer']} {instance['gpu_name']}"
                if instance.get('gpu_memory_gb'):
                    gpu_desc += f" ({instance['gpu_memory_gb']} GB VRAM)"
            else:
                gpu_desc = instance['gpu_name']  # Shows "None - Compute Optimized" etc.

            console.print(f"  {idx:2d}. [cyan]{instance['type']:25s}[/cyan] - {instance['vcpu']:2d} vCPUs, {instance['memory_gb']:3d} GB RAM, {gpu_desc}")

        # Mark recommended instances
        recommended_gpu = ['Standard_NV6ads_A10_v5', 'Standard_NV12ads_A10_v5', 'Standard_NV18ads_A10_v5']
        recommended_lucidlink = ['Standard_F16s_v2', 'Standard_L8s_v3']

        rec_gpu_indices = [idx for idx, inst in enumerate(gpu_instance_types, 1) if inst['type'] in recommended_gpu]
        rec_ll_indices = [idx for idx, inst in enumerate(gpu_instance_types, 1) if inst['type'] in recommended_lucidlink]

        if rec_gpu_indices:
            console.print(f"\n[dim]Recommended for GPU workflows: {', '.join(str(i) for i in rec_gpu_indices)}[/dim]")
        if rec_ll_indices:
            console.print(f"[dim]Recommended for LucidLink testing: {', '.join(str(i) for i in rec_ll_indices)}[/dim]")

        # Get existing VM type index or default to NV6ads_A10_v5 (graphics-enabled)
        existing_type = existing_config.get('vm_size', 'Standard_NV6ads_A10_v5')
        default_choice = next((idx for idx, inst in enumerate(gpu_instance_types, 1) if inst['type'] == existing_type), 3)

        # Build choices list
        valid_choices = [str(i) for i in range(1, len(gpu_instance_types) + 1)]

        while True:
            try:
                choice = IntPrompt.ask(
                    f"\nSelect VM size (1-{len(gpu_instance_types)})",
                    default=default_choice,
                    choices=valid_choices
                )
                if 1 <= choice <= len(gpu_instance_types):
                    config['vm_size'] = gpu_instance_types[choice - 1]['type']
                    console.print(f"[{self.colors['success']}]✓ Selected: {config['vm_size']}[/]")
                    break
                else:
                    console.print(f"[{self.colors['error']}]Please select a number between 1 and {len(gpu_instance_types)}[/]")
            except (ValueError, KeyboardInterrupt):
                console.print(f"[{self.colors['error']}]Invalid selection[/]")

        config['instance_count'] = IntPrompt.ask(
            "Number of VM Instances (1-10)",
            default=existing_config.get('instance_count', 1)
        )

        # Validate instance count
        if config['instance_count'] < 1:
            config['instance_count'] = 1
        elif config['instance_count'] > 10:
            config['instance_count'] = 10

        config['os_disk_size_gb'] = IntPrompt.ask(
            "OS Disk Size (GB)",
            default=existing_config.get('os_disk_size_gb', 256)
        )

        config['data_disk_size_gb'] = IntPrompt.ask(
            "Data Disk Size (GB) for media/projects",
            default=existing_config.get('data_disk_size_gb', 2048)
        )
        console.print()

        # Step 6: VM Admin Credentials
        console.print("[bold cyan]Step 6: VM Admin Credentials[/bold cyan]")
        config['admin_username'] = Prompt.ask(
            "Admin Username",
            default=existing_config.get('admin_username', 'azureuser')
        )

        generate_password = Confirm.ask("Auto-generate secure password?", default=True)
        if generate_password:
            config['admin_password'] = self.generate_secure_password(16)
            console.print(f"  [{self.colors['success']}]Generated: {config['admin_password']}[/]")
        else:
            config['admin_password'] = Prompt.ask("Admin Password (for RDP access)", password=True)
        console.print()

        # Step 7: Optional Software
        console.print("[bold cyan]Step 7: Optional Software[/bold cyan]")
        console.print("[dim]Select which software to install on VMs after deployment[/dim]")
        config['install_vlc'] = Confirm.ask("  VLC Media Player", default=existing_config.get('install_vlc', True))
        config['install_vcredist'] = Confirm.ask("  Visual C++ Redistributables", default=existing_config.get('install_vcredist', False))
        config['install_7zip'] = Confirm.ask("  7-Zip", default=existing_config.get('install_7zip', False))
        config['install_notepad_pp'] = Confirm.ask("  Notepad++", default=existing_config.get('install_notepad_pp', False))
        config['install_adobe_cc'] = Confirm.ask("  Adobe Creative Cloud installer", default=existing_config.get('install_adobe_cc', False))
        console.print()

        # Validate configuration
        valid, errors = self.validate_config(config)
        if not valid:
            console.print(f"[{self.colors['error']}]Configuration validation failed:[/]")
            for error in errors:
                console.print(f"  • {error}")
            console.print()
            if not Confirm.ask("Save configuration anyway?", default=False):
                return

        # Save configuration (save_config will base64 encode password on disk)
        # The real password is kept in memory for immediate deployment
        self.config = config  # Keep real password in memory
        if self.save_config(config):  # This will base64 encode password when saving to disk
            console.print()
            console.print(Panel.fit(
                f"[{self.colors['success']}]Configuration saved successfully![/]\n"
                f"Configuration file: {self.client_config_file}",
                border_style="green"
            ))

        Prompt.ask("\nPress Enter to continue")

    def show_configuration_summary(self):
        """Display current configuration"""
        console.clear()
        self.show_banner()

        if not self.config:
            console.print(f"[{self.colors['warning']}]No configuration loaded. Please configure deployment first.[/]")
            Prompt.ask("\nPress Enter to continue")
            return

        # Create main configuration table
        table = Table(title="Current Client Configuration", box=box.ROUNDED, border_style="blue")
        table.add_column("Setting", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        # Display configuration (mask sensitive data)
        display_config = self.config.copy()
        if 'filespace_password' in display_config:
            display_config['filespace_password'] = '***MASKED***'
        if 'admin_password' in display_config:
            display_config['admin_password'] = '***MASKED***'

        # Group settings
        azure_settings = {
            'Location': display_config.get('location', 'Not set'),
            'Resource Group': display_config.get('resource_group_name', 'Not set'),
            'VNet CIDR': display_config.get('vnet_cidr', 'Not set'),
        }

        filespace_settings = {
            'Filespace Domain': display_config.get('filespace_domain', 'Not set'),
            'Username': display_config.get('filespace_user', 'Not set'),
            'Password': display_config.get('filespace_password', 'Not set'),
            'Mount Point': display_config.get('mount_point', 'Not set'),
            'Auto-configure LucidLink': display_config.get('auto_configure_lucidlink', 'yes'),
        }

        vm_settings = {
            'VM Size': display_config.get('vm_size', 'Not set'),
            'Instance Count': str(display_config.get('instance_count', 1)),
            'OS Disk Size': f"{display_config.get('os_disk_size_gb', 256)} GB",
            'Data Disk Size': f"{display_config.get('data_disk_size_gb', 2048)} GB",
            'Admin Username': display_config.get('admin_username', 'Not set'),
            'Admin Password': display_config.get('admin_password', 'Not set'),
        }

        # Add settings to table
        table.add_row("[bold]Azure Settings[/bold]", "")
        for key, value in azure_settings.items():
            table.add_row(f"  {key}", value)

        table.add_row("", "")
        table.add_row("[bold]Filespace Settings[/bold]", "")
        for key, value in filespace_settings.items():
            table.add_row(f"  {key}", value)

        table.add_row("", "")
        table.add_row("[bold]VM Settings[/bold]", "")
        for key, value in vm_settings.items():
            table.add_row(f"  {key}", value)

        console.print(table)
        console.print()

        # Show estimated costs
        instance_count = display_config.get('instance_count', 1)
        vm_size = display_config.get('vm_size', 'Standard_NV6ads_A10_v5')

        resources_text = f"[yellow]Estimated Resources:[/yellow]\n"
        resources_text += f"• {instance_count} × {vm_size} Virtual Machines\n"
        resources_text += f"• {instance_count} × {display_config.get('os_disk_size_gb', 256)} GB OS Disks\n"
        resources_text += f"• {instance_count} × {display_config.get('data_disk_size_gb', 2048)} GB Data Disks\n"
        resources_text += f"• 1 × VNet ({display_config.get('vnet_cidr', '10.0.0.0/16')})\n"
        resources_text += f"• 1 × Network Security Group\n"
        resources_text += f"• 1 × Azure Key Vault (for LucidLink credentials)"

        console.print(Panel.fit(resources_text, border_style="yellow"))

        console.print()
        Prompt.ask("Press Enter to continue")

    def generate_tfvars(self, config: Dict) -> str:
        """Generate Terraform tfvars file content for Azure deployment"""
        tfvars = f"""# LucidLink Windows Client Deployment Variables - Azure
# Generated at: {datetime.now().strftime('%Y-%m-%d')}

# Azure Configuration
location           = "{config.get('location', 'eastus')}"
resource_group_name = "{config.get('resource_group_name', 'll-win-client-rg')}"

# VM Configuration
vm_size            = "{config.get('vm_size', 'Standard_NV6ads_A10_v5')}"
instance_count     = {config.get('instance_count', 1)}

# Disk Configuration
os_disk_size_gb    = {config.get('os_disk_size_gb', 256)}
data_disk_size_gb  = {config.get('data_disk_size_gb', 2048)}

# Admin Credentials
admin_username     = "{config.get('admin_username', 'azureuser')}"
admin_password     = "{config.get('admin_password', '')}"

# LucidLink Configuration
filespace_domain   = "{config.get('filespace_domain', '')}"
filespace_user     = "{config.get('filespace_user', '')}"
filespace_password = "{config.get('filespace_password', '')}"
mount_point        = "{config.get('mount_point', 'L:')}"

# LucidLink installer URL (Windows MSI)
lucidlink_installer_url = "{config.get('lucidlink_installer_url', 'https://www.lucidlink.com/download/new-ll-latest/win/stable/')}"
"""

        # Add custom_image_id if set
        custom_image_id = config.get('custom_image_id', '')
        if custom_image_id:
            tfvars += f"""
# Custom Image (Packer-built)
custom_image_id = "{custom_image_id}"
"""

        return tfvars

    def write_terraform_files(self, config: Dict) -> bool:
        """Write Terraform configuration files for client deployment"""
        try:
            # Write client tfvars
            tfvars_path = self.terraform_dir / "terraform.tfvars"
            tfvars_content = self.generate_tfvars(config)
            with open(tfvars_path, 'w') as f:
                f.write(tfvars_content)
            logger.info(f"Written Terraform tfvars to {tfvars_path}")

            console.print(f"[{self.colors['success']}]✓ Terraform files generated successfully[/]")
            return True

        except Exception as e:
            logger.error(f"Failed to write Terraform files: {e}")
            console.print(f"[{self.colors['error']}]Failed to write Terraform files: {e}[/]")
            return False

    def ensure_terraform_initialized(self) -> bool:
        """Ensure terraform is initialized before running commands"""
        lock_file = self.terraform_dir / ".terraform.lock.hcl"
        terraform_dir = self.terraform_dir / ".terraform"

        # If lock file and .terraform directory exist, assume it's initialized
        if lock_file.exists() and terraform_dir.exists():
            return True

        # Need to initialize
        console.print(f"[{self.colors['info']}]ℹ Initializing Terraform...[/]")
        success, _ = self.run_terraform_init()
        return success

    def run_terraform_init(self) -> Tuple[bool, str]:
        """Run terraform init without checking if already initialized"""
        env = os.environ.copy()

        # Set TMPDIR to writable location
        tmpdir = '/tmp/terraform-tmp'
        os.makedirs(tmpdir, exist_ok=True)
        env['TMPDIR'] = tmpdir

        try:
            result = subprocess.run(
                ['terraform', 'init'],
                cwd=str(self.terraform_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                console.print(f"[{self.colors['success']}]✓ Terraform initialized[/]")
                return True, result.stdout
            else:
                console.print(f"[{self.colors['error']}]✗ Terraform init failed[/]")
                logger.error(f"Terraform init failed: {result.stderr}")
                return False, result.stderr
        except Exception as e:
            logger.error(f"Terraform init failed: {e}")
            console.print(f"[{self.colors['error']}]Terraform init failed: {e}[/]")
            return False, str(e)

    def _cleanup_stale_lock(self, tf_dir: Path):
        """Remove stale Terraform lock files from dead processes."""
        lock_file = tf_dir / '.terraform.tfstate.lock.info'
        if not lock_file.exists():
            return
        try:
            # Check if any terraform process has the state file open
            state_file = tf_dir / 'terraform.tfstate'
            result = subprocess.run(
                ['lsof', str(state_file)],
                capture_output=True, text=True
            )
            if result.returncode != 0:  # No process has the file open
                lock_file.unlink()
                console.print(f"[{self.colors['warning']}]Removed stale Terraform lock file[/]")
        except Exception:
            pass  # If we can't check, let Terraform handle it

    def run_terraform_command(self, command: str, auto_approve: bool = False) -> Tuple[bool, str]:
        """Execute a Terraform command with progress tracking"""
        self._cleanup_stale_lock(self.terraform_dir)

        # Ensure terraform is initialized (except for init command itself)
        if command != 'init' and not self.ensure_terraform_initialized():
            return False, "Terraform initialization failed"

        env = os.environ.copy()

        # Set TMPDIR to writable location (fixes macOS permission issues)
        tmpdir = '/tmp/terraform-tmp'
        os.makedirs(tmpdir, exist_ok=True)
        env['TMPDIR'] = tmpdir

        # Check for var files
        tfvars_path = self.terraform_dir / "terraform.tfvars"
        image_override_file = self.terraform_dir / "image-override.tfvars"
        use_tfvars = tfvars_path.exists()
        use_image_override = image_override_file.exists()

        # Build command
        if command == 'init':
            cmd = ['terraform', 'init']
        elif command == 'validate':
            cmd = ['terraform', 'validate']
        elif command == 'plan':
            cmd = ['terraform', 'plan', '-out=tfplan']
            if use_tfvars:
                cmd.extend(['-var-file=terraform.tfvars'])
            if use_image_override:
                cmd.extend(['-var-file=image-override.tfvars'])
        elif command == 'apply':
            # Use saved plan file if available (no -auto-approve needed with saved plans)
            plan_file = self.terraform_dir / "tfplan"
            if plan_file.exists():
                cmd = ['terraform', 'apply', 'tfplan']
            else:
                cmd = ['terraform', 'apply']
                if use_tfvars:
                    cmd.extend(['-var-file=terraform.tfvars'])
                if use_image_override:
                    cmd.extend(['-var-file=image-override.tfvars'])
                if auto_approve:
                    cmd.append('-auto-approve')
        elif command == 'destroy':
            cmd = ['terraform', 'destroy']
            if use_tfvars:
                cmd.extend(['-var-file=terraform.tfvars'])
            if use_image_override:
                cmd.extend(['-var-file=image-override.tfvars'])
            if auto_approve:
                cmd.append('-auto-approve')
        else:
            return False, f"Unknown command: {command}"

        # Inform user if using image override
        if use_image_override and command in ['plan', 'apply', 'destroy']:
            console.print(f"[{self.colors['info']}]ℹ Using image-override.tfvars (Standard Windows Image)[/]")
            console.print(f"[dim]To use NVIDIA VM Image, delete or rename terraform/azure/image-override.tfvars[/dim]")

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console
            ) as progress:
                task = progress.add_task(f"Running terraform {command}...", total=None)

                process = subprocess.Popen(
                    cmd,
                    cwd=str(self.terraform_dir),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                output_lines = []
                for line in process.stdout:
                    output_lines.append(line)
                    # Print important lines
                    if any(keyword in line for keyword in ['Error', 'Apply complete', 'Plan:', 'Destroy complete']):
                        console.print(line.strip())
                    logger.info(line.strip())

                process.wait()
                output = ''.join(output_lines)

                # Clean up saved plan file after apply (used or not, it's now stale)
                if command in ('apply', 'destroy'):
                    plan_file = self.terraform_dir / "tfplan"
                    plan_file.unlink(missing_ok=True)

                if process.returncode == 0:
                    progress.update(task, completed=100)
                    console.print(f"[{self.colors['success']}]✓ Terraform {command} completed successfully[/]")
                    return True, output
                else:
                    console.print(f"[{self.colors['error']}]✗ Terraform {command} failed[/]")
                    return False, output

        except Exception as e:
            logger.error(f"Terraform {command} failed: {e}")
            console.print(f"[{self.colors['error']}]Terraform {command} failed: {e}[/]")
            return False, str(e)

    def get_terraform_outputs(self) -> Optional[Dict]:
        """Get Terraform outputs"""
        try:
            result = subprocess.run(
                ['terraform', 'output', '-json'],
                cwd=str(self.terraform_dir),
                capture_output=True,
                text=True,
                check=True
            )

            outputs = json.loads(result.stdout)
            return {k: v['value'] for k, v in outputs.items()}
        except Exception as e:
            logger.error(f"Failed to get Terraform outputs: {e}")
            return None


    def generate_secure_password(self, length: int = 16) -> str:
        """Generate a secure random password"""
        # Password requirements: uppercase, lowercase, digits, special chars
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(length))

        # Ensure it has at least one of each type
        if not any(c.isupper() for c in password):
            password = password[:-1] + secrets.choice(string.ascii_uppercase)
        if not any(c.islower() for c in password):
            password = password[:-2] + secrets.choice(string.ascii_lowercase) + password[-1]
        if not any(c.isdigit() for c in password):
            password = password[:-3] + secrets.choice(string.digits) + password[-2:]

        return password


    def check_rdp_status(self, public_ip: str) -> str:
        """Check if RDP server is accessible on port 3389

        Args:
            public_ip: Public IP address of the VM

        Returns:
            'Ready', 'NotReady', or 'Unknown'
        """
        try:
            import socket

            if not public_ip or public_ip == "N/A":
                return 'Unknown'

            # Try to connect to port 3389 (RDP) with 3 second timeout
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)

            result = sock.connect_ex((public_ip, 3389))
            sock.close()

            if result == 0:
                return 'Ready'  # Port is open
            else:
                return 'NotReady'  # Port is closed

        except Exception as e:
            logger.debug(f"Failed to check RDP status for {public_ip}: {e}")
            return 'Unknown'


    def generate_rdp_file(self, vm_ip: str, vm_name: str, username: str = None) -> str:
        """Generate RDP connection file on Desktop

        Args:
            vm_ip: Public IP of the VM
            vm_name: Name for the RDP file
            username: Optional username
        """
        # Save to user's Desktop for easy access
        desktop_dir = Path.home() / "Desktop" / "LucidLink-RDP"
        desktop_dir.mkdir(parents=True, exist_ok=True)

        rdp_file_path = desktop_dir / f"{vm_name}.rdp"

        # RDP connection file content
        rdp_content = f"""full address:s:{vm_ip}:3389
username:s:{username if username else ''}
screen mode id:i:2
use multimon:i:0
desktopwidth:i:1920
desktopheight:i:1080
session bpp:i:32
compression:i:1
keyboardhook:i:2
audiocapturemode:i:0
videoplaybackmode:i:1
connection type:i:7
networkautodetect:i:1
bandwidthautodetect:i:1
displayconnectionbar:i:1
enableworkspacereconnect:i:0
disable wallpaper:i:0
allow font smoothing:i:1
allow desktop composition:i:1
disable full window drag:i:0
disable menu anims:i:0
disable themes:i:0
disable cursor setting:i:0
bitmapcachepersistenable:i:1
audiomode:i:0
redirectprinters:i:0
redirectcomports:i:0
redirectsmartcards:i:0
redirectclipboard:i:1
redirectposdevices:i:0
autoreconnection enabled:i:1
authentication level:i:2
prompt for credentials:i:0
negotiate security layer:i:1
remoteapplicationmode:i:0
alternate shell:s:
shell working directory:s:
gatewayhostname:s:
gatewayusagemethod:i:0
gatewaycredentialssource:i:0
gatewayprofileusagemethod:i:1
promptcredentialonce:i:0
gatewaybrokeringtype:i:0
use redirection server name:i:0
rdgiskdcproxy:i:0
kdcproxyname:s:
"""

        # Write RDP file
        with open(rdp_file_path, 'w') as f:
            f.write(rdp_content)

        logger.info(f"Generated RDP file: {rdp_file_path}")
        return str(rdp_file_path)

    def deploy_infrastructure(self):
        """Deploy client infrastructure using Terraform"""
        console.clear()
        self.show_banner()

        if not self.config:
            console.print(f"[{self.colors['error']}]No configuration loaded. Please configure deployment first.[/]")
            Prompt.ask("\nPress Enter to continue")
            return

        console.print(Panel.fit(
            "[bold]Client Infrastructure Deployment[/bold]\n"
            "This will deploy Windows LucidLink client VMs to Azure using Terraform.",
            border_style="blue"
        ))
        console.print()

        # Check for custom images
        custom_image_id = self.config.get('custom_image_id', '')
        if not custom_image_id:
            # Check local registry
            images_file = self.config_dir / "azure-images.json"
            if images_file.exists():
                try:
                    with open(images_file, 'r') as f:
                        images = json.load(f)
                    if images:
                        console.print("[bold]Custom Images Available:[/bold]")
                        for idx, img in enumerate(images[-3:], 1):  # Show last 3
                            console.print(f"  {idx}. {img.get('name', 'unknown')} ({img.get('created', 'unknown')[:10]})")
                        console.print()
                        if Confirm.ask("Use a custom image?", default=False):
                            if len(images) == 1:
                                custom_image_id = images[0]['image_id']
                            else:
                                img_choice = Prompt.ask(
                                    "Select image number",
                                    default=str(min(len(images), len(images[-3:])))
                                )
                                try:
                                    idx = int(img_choice) - 1
                                    recent = images[-3:]
                                    if 0 <= idx < len(recent):
                                        custom_image_id = recent[idx]['image_id']
                                except (ValueError, IndexError):
                                    console.print(f"[{self.colors['warning']}]Invalid selection, using default image[/]")
                            if custom_image_id:
                                self.config['custom_image_id'] = custom_image_id
                                console.print(f"[{self.colors['success']}]✓ Using custom image[/]")
                        console.print()
                except Exception:
                    pass

        # Show deployment summary
        console.print("[bold]Deployment Summary:[/bold]")
        console.print(f"  • Location: {self.config.get('location', 'Not configured')}")
        console.print(f"  • VNet CIDR: {self.config.get('vnet_cidr', 'Not configured')}")
        console.print(f"  • VM Size: {self.config.get('vm_size', 'Not configured')}")
        console.print(f"  • VM Count: {self.config.get('instance_count', 'Not configured')}")
        console.print(f"  • OS Disk: {self.config.get('os_disk_size_gb', 'Not configured')} GB")
        console.print(f"  • Data Disk: {self.config.get('data_disk_size_gb', 'Not configured')} GB")
        console.print(f"  • Filespace: {self.config.get('filespace_domain', 'Not configured')}")
        console.print(f"  • Mount Point: {self.config.get('mount_point', 'Not configured')}")
        if custom_image_id:
            console.print(f"  • Image: [bold cyan]Custom (Packer-built)[/bold cyan]")
        else:
            console.print(f"  • Image: Windows 11 Pro 23H2 (marketplace)")
        console.print()

        # Confirm deployment (skip if auto-approve is enabled)
        if not self.auto_approve:
            if not Confirm.ask("Proceed with deployment?", default=True):
                return
        else:
            console.print(f"[{self.colors['info']}]Auto-approve enabled, skipping confirmation[/]")

        # Write Terraform files
        console.print("\n[bold]Step 1: Generating Terraform configuration...[/bold]")
        if not self.write_terraform_files(self.config):
            console.print(f"[{self.colors['error']}]Failed to generate Terraform files[/]")
            Prompt.ask("\nPress Enter to continue")
            return

        # Terraform init (if needed)
        console.print("\n[bold]Step 2: Initializing Terraform...[/bold]")
        success, output = self.run_terraform_command('init')
        if not success:
            console.print(f"[{self.colors['error']}]Terraform init failed. Check logs for details.[/]")
            Prompt.ask("\nPress Enter to continue")
            return

        # Terraform validate
        console.print("\n[bold]Step 3: Validating Terraform configuration...[/bold]")
        success, output = self.run_terraform_command('validate')
        if not success:
            console.print(f"[{self.colors['error']}]Terraform validation failed. Check logs for details.[/]")
            Prompt.ask("\nPress Enter to continue")
            return

        # Terraform plan
        console.print("\n[bold]Step 4: Planning infrastructure changes...[/bold]")
        success, output = self.run_terraform_command('plan')
        if not success:
            console.print(f"[{self.colors['error']}]Terraform plan failed. Check logs for details.[/]")
            Prompt.ask("\nPress Enter to continue")
            return

        console.print()
        if not self.auto_approve:
            if not Confirm.ask("Apply these changes?", default=True):
                return
        else:
            console.print(f"[{self.colors['info']}]Auto-approve enabled, proceeding with apply[/]")

        # Terraform apply
        console.print("\n[bold]Step 5: Applying infrastructure changes...[/bold]")
        console.print(f"[{self.colors['warning']}]This may take 5-10 minutes...[/]")
        success, output = self.run_terraform_command('apply', auto_approve=True)

        if success:
            console.print()
            console.print(Panel.fit(
                f"[{self.colors['success']}]Terraform apply completed successfully![/]\n"
                "Windows instances are initializing...",
                border_style="green"
            ))

            # Show access information
            outputs = self.get_terraform_outputs()
            if outputs:
                console.print("\n[bold]Deployment Information:[/bold]")
                if 'vm_names' in outputs:
                    console.print(f"\nVM Names: {', '.join(outputs['vm_names'])}")
                if 'resource_group_name' in outputs:
                    console.print(f"Resource Group: {outputs['resource_group_name']}")
                if 'public_ips' in outputs:
                    console.print(f"Public IPs: {', '.join(outputs['public_ips'])}")

                vm_names = outputs.get('vm_names', [])
                public_ips = outputs.get('public_ips', [])
                resource_group = outputs.get('resource_group_name', self.config.get('resource_group_name', 'll-win-client-rg'))
                admin_username = self.config.get('admin_username', 'azureuser')
                admin_password = self.config.get('admin_password', '')

                # Step 6: Run deployment script on each VM
                deploy_script = self.script_dir / "deployment" / "deploy-windows-client-azure.sh"
                if deploy_script.exists() and vm_names:
                    console.print(f"\n[bold]Step 6: Deploying software to VMs...[/bold]")
                    console.print(f"[{self.colors['warning']}]Waiting 60s for Windows initialization...[/]")
                    time.sleep(60)

                    # Build environment variables for deployment script
                    deploy_env = os.environ.copy()
                    deploy_env['ADMIN_PASSWORD'] = admin_password
                    deploy_env['INSTALL_VLC'] = '1' if self.config.get('install_vlc', True) else '0'
                    deploy_env['INSTALL_VCREDIST'] = '1' if self.config.get('install_vcredist', False) else '0'
                    deploy_env['INSTALL_7ZIP'] = '1' if self.config.get('install_7zip', False) else '0'
                    deploy_env['INSTALL_NOTEPAD_PP'] = '1' if self.config.get('install_notepad_pp', False) else '0'
                    deploy_env['INSTALL_ADOBE_CC'] = '1' if self.config.get('install_adobe_cc', False) else '0'

                    for vm_name in vm_names:
                        console.print(f"\n[bold]Deploying software to {vm_name}...[/bold]")
                        try:
                            process = subprocess.Popen(
                                [str(deploy_script), vm_name, resource_group],
                                env=deploy_env,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                                bufsize=1
                            )
                            for line in process.stdout:
                                console.print(line.rstrip())
                                logger.info(line.rstrip())
                            process.wait()
                            if process.returncode == 0:
                                console.print(f"[{self.colors['success']}]✓ Software deployment completed for {vm_name}[/]")
                            else:
                                console.print(f"[{self.colors['error']}]✗ Software deployment failed for {vm_name} (exit code: {process.returncode})[/]")
                        except Exception as e:
                            console.print(f"[{self.colors['error']}]✗ Failed to run deployment script for {vm_name}: {e}[/]")
                else:
                    console.print(f"\n[{self.colors['info']}]Software deployment handled by Terraform Custom Script Extension[/]")

                # Generate connection files for each VM
                console.print(f"\n[bold]Generating connection files...[/bold]")
                rdp_files = []

                for idx, (vm_name, public_ip) in enumerate(zip(vm_names, public_ips)):
                    rdp_name = f"ll-win-client-{idx + 1}"
                    try:
                        # Generate RDP file
                        rdp_file = self.generate_rdp_file(public_ip, rdp_name, admin_username)
                        rdp_files.append(rdp_file)
                        console.print(f"  [{self.colors['success']}]✓[/] RDP: {rdp_name}.rdp")
                    except Exception as e:
                        console.print(f"  [{self.colors['warning']}]⚠[/] Failed to generate RDP file for {rdp_name}: {e}")

                # Show connection info
                rdp_location = Path.home() / "Desktop" / "LucidLink-RDP"

                console.print(f"\n[bold cyan]═══════════════════════════════════════════════════════════[/bold cyan]")
                console.print(f"[bold cyan]Connection Files Generated[/bold cyan]")
                console.print(f"[bold cyan]═══════════════════════════════════════════════════════════[/bold cyan]")

                console.print(f"\n[bold green]RDP Connection[/bold green]")
                console.print(f"Location: [bold]{rdp_location}[/bold]")
                console.print(f"\n[bold]To connect using RDP:[/bold]")
                console.print(f"1. Open your Desktop and find the 'LucidLink-RDP' folder")
                console.print(f"2. Double-click the .rdp file for the VM you want to access")
                console.print(f"3. When prompted, enter your credentials:")
                console.print(f"   Username: [bold]{admin_username}[/bold]")
                console.print(f"   Password: [bold]{self.config.get('admin_password', '***')}[/bold]")
                console.print(f"\n[dim]Note: RDP is built into Windows and macOS. For Linux, install Remmina or similar.[/dim]")

                # Save connection info to a text file on Desktop
                password_file = Path.home() / "Desktop" / "LucidLink-RDP" / "CONNECTION_INFO.txt"
                with open(password_file, 'w') as f:
                    f.write(f"Windows VM Connection Information\n")
                    f.write(f"==================================\n\n")
                    f.write(f"Username: {admin_username}\n")
                    f.write(f"Password: {self.config.get('admin_password', '***')}\n\n")
                    f.write(f"VMs:\n")
                    for idx, vm_name in enumerate(vm_names, 1):
                        public_ip = public_ips[idx-1] if idx-1 < len(public_ips) else "N/A"
                        f.write(f"  {idx}. {vm_name}\n")
                        f.write(f"      IP: {public_ip}\n")
                        f.write(f"      RDP: {rdp_location / f'll-win-client-{idx}.rdp'}\n\n")
                    f.write(f"\nTo Connect:\n")
                    f.write(f"  1. Double-click the .rdp file\n")
                    f.write(f"  2. Enter the username and password above\n")

                console.print(f"\n[{self.colors['info']}]Connection info saved to: {password_file}[/]")
        else:
            console.print()
            console.print(Panel.fit(
                f"[{self.colors['error']}]Deployment failed. Check logs for details.[/]\n"
                f"Log file: {log_file}",
                border_style="red"
            ))

        console.print()
        Prompt.ask("Press Enter to continue")

    def view_deployment_status(self):
        """View detailed deployment status and outputs"""
        console.clear()
        self.show_banner()

        console.print(Panel.fit(
            "[bold]Client Deployment Status[/bold]",
            border_style="blue"
        ))
        console.print()

        # Get terraform outputs
        outputs = self.get_terraform_outputs()
        if not outputs or 'vm_names' not in outputs:
            console.print(f"[{self.colors['warning']}]No client deployments found.[/]")
            console.print("Deploy infrastructure first using option 3.")
            Prompt.ask("\nPress Enter to continue")
            return

        # Extract client information
        vm_names = outputs.get('vm_names', [])
        public_ips = outputs.get('public_ips', [])
        filespace_domain = outputs.get('filespace_domain', 'Not configured')
        mount_point = outputs.get('mount_point', 'L:')

        if not vm_names:
            console.print(f"[{self.colors['warning']}]No VMs found.[/]")
            Prompt.ask("\nPress Enter to continue")
            return

        # Create deployment summary table
        summary_table = Table(title="Deployment Summary", box=box.ROUNDED, border_style="blue")
        summary_table.add_column("Property", style="cyan", no_wrap=True)
        summary_table.add_column("Value", style="white")

        summary_table.add_row("Total VMs", str(len(vm_names)))
        summary_table.add_row("Filespace Domain", filespace_domain)
        summary_table.add_row("Mount Point", mount_point)
        summary_table.add_row("Location", self.config.get('location', 'Not configured'))
        summary_table.add_row("Resource Group", outputs.get('resource_group_name', 'unknown'))

        console.print(summary_table)
        console.print()

        # Create instances table
        instances_table = Table(title="Windows 11 VMs", box=box.ROUNDED, border_style="green")
        instances_table.add_column("Index", style="cyan", no_wrap=True)
        instances_table.add_column("VM Name", style="white")
        instances_table.add_column("Private IP", style="white")
        instances_table.add_column("Public IP", style="white")
        instances_table.add_column("VM Status", style="green")
        instances_table.add_column("RDP Access", style="magenta")

        # Check VM status using Azure CLI
        vm_statuses = {}
        rdp_statuses = {}
        resource_group = outputs.get('resource_group_name', 'll-win-client-rg')

        try:
            import json
            import subprocess

            # Get VM statuses using Azure CLI
            for vm_name in vm_names:
                try:
                    result = subprocess.run(
                        ['az', 'vm', 'get-instance-view',
                         '--name', vm_name,
                         '--resource-group', resource_group,
                         '--query', 'instanceView.statuses[?starts_with(code, `PowerState`)].displayStatus',
                         '--output', 'json'],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode == 0:
                        statuses = json.loads(result.stdout)
                        if statuses:
                            # Extract status like "VM running" -> "running"
                            vm_statuses[vm_name] = statuses[0].replace('VM ', '').lower()
                except:
                    pass
        except:
            # If Azure CLI not available or fails, show unknown status
            pass

        for idx, vm_name in enumerate(vm_names):
            public_ip = public_ips[idx] if idx < len(public_ips) else "N/A"

            # Get VM status
            status = vm_statuses.get(vm_name, "unknown")
            if status == "running":
                status_display = "[green]running[/green]"
            elif status in ["stopped", "deallocated"]:
                status_display = "[yellow]stopped[/yellow]"
            elif status == "starting":
                status_display = "[cyan]starting[/cyan]"
            else:
                status_display = "[dim]unknown[/dim]"

            # Check RDP accessibility (port 3389)
            rdp_status_display = "[dim]Unknown[/dim]"
            if public_ip != "N/A" and status == "running":
                try:
                    import socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)
                    result = sock.connect_ex((public_ip, 3389))
                    sock.close()
                    if result == 0:
                        rdp_status_display = "[green]Ready[/green]"
                    else:
                        rdp_status_display = "[yellow]Not Ready[/yellow]"
                except:
                    rdp_status_display = "[yellow]Not Ready[/yellow]"

            instances_table.add_row(
                str(idx + 1),
                vm_name,
                "N/A",  # Private IPs not exposed in Terraform outputs
                public_ip,
                status_display,
                rdp_status_display
            )

        console.print(instances_table)
        console.print()
        Prompt.ask("Press Enter to continue")

    def destroy_infrastructure(self):
        """Destroy client infrastructure"""
        console.clear()
        self.show_banner()

        console.print(Panel.fit(
            "[bold red]Destroy Client Infrastructure[/bold red]\n"
            "WARNING: This will permanently delete all client instances!",
            border_style="red"
        ))
        console.print()

        # Check if there's anything to destroy by checking terraform state
        try:
            result = subprocess.run(
                ['terraform', 'state', 'list'],
                cwd=str(self.terraform_dir),
                capture_output=True,
                text=True,
                timeout=30
            )
            state_output = result.stdout.strip()

            if result.returncode != 0 or not state_output:
                console.print(f"[{self.colors['info']}]No resources found in terraform state. Nothing to destroy.[/]")
                Prompt.ask("\nPress Enter to continue")
                return
        except Exception as e:
            console.print(f"[{self.colors['error']}]Failed to check terraform state: {e}[/]")
            Prompt.ask("\nPress Enter to continue")
            return

        # Get outputs if available (VM might not have been created)
        outputs = self.get_terraform_outputs()
        vm_names = outputs.get('vm_names', []) if outputs else []

        # Show what will be destroyed
        console.print("[bold]The following resources will be destroyed:[/bold]")
        if vm_names:
            console.print(f"  • {len(vm_names)} client VM(s)")
            for idx, vm_name in enumerate(vm_names, 1):
                console.print(f"    - VM {idx}: {vm_name}")
        else:
            console.print(f"  • 0 VMs (VM creation may have failed, but other resources exist)")
        console.print(f"  • VNet and networking components")
        console.print(f"  • Azure Key Vault")
        console.print(f"  • Data disks and other managed resources")
        console.print()

        # Single confirmation (skip if auto-approve is enabled)
        if not self.auto_approve:
            if not Confirm.ask("[bold red]Destroy all resources?[/]", default=False):
                console.print(f"[{self.colors['info']}]Destruction cancelled.[/]")
                Prompt.ask("\nPress Enter to continue")
                return
        else:
            console.print(f"[{self.colors['warning']}]Auto-approve enabled, skipping confirmation[/]")

        console.print(f"\n[{self.colors['warning']}]Destroying client infrastructure...[/]")
        console.print("[dim]This may take a few minutes...[/dim]")

        # Run terraform destroy
        success, output = self.run_terraform_command('destroy', auto_approve=True)

        if success:
            console.print()
            console.print(Panel.fit(
                f"[{self.colors['success']}]Client infrastructure destroyed successfully![/]\n"
                "All client VMs and VNet have been terminated.",
                border_style="green"
            ))

            # Clear client configuration
            if self.config.get('filespace_domain'):
                console.print()
                if Confirm.ask("Clear stored client configuration?", default=False):
                    # Clear all client-specific config
                    self.config = {}
                    self.save_config({})
                    console.print(f"[{self.colors['success']}]✓ Client configuration cleared[/]")
        else:
            console.print()
            console.print(Panel.fit(
                f"[{self.colors['error']}]Destroy failed. Check logs for details.[/]\n"
                f"Log file: {log_file}",
                border_style="red"
            ))

        console.print()
        Prompt.ask("Press Enter to continue")

    def regenerate_connection_files(self):
        """Regenerate RDP connection files on Desktop with existing credentials"""
        console.clear()
        self.show_banner()

        console.print(Panel.fit(
            "[bold]Regenerate Connection Files[/bold]\n"
            "This will create fresh RDP files on your Desktop with your admin credentials",
            border_style="blue"
        ))
        console.print()

        # Get terraform outputs
        outputs = self.get_terraform_outputs()
        if not outputs or 'vm_names' not in outputs:
            console.print(f"[{self.colors['warning']}]No VM deployments found.[/]")
            console.print("Deploy infrastructure first using option 3.")
            Prompt.ask("\nPress Enter to continue")
            return

        vm_names = outputs.get('vm_names', [])
        public_ips = outputs.get('public_ips', [])

        if not vm_names or not public_ips:
            console.print(f"[{self.colors['warning']}]No VMs with public IPs found.[/]")
            Prompt.ask("\nPress Enter to continue")
            return

        # Get admin credentials from config
        admin_username = self.config.get('admin_username', 'azureuser')
        admin_password = self.config.get('admin_password', '')

        if not admin_password:
            console.print(f"[{self.colors['warning']}]Admin password not found in configuration.[/]")
            console.print("[dim]The password was set during deployment. Check your config file or CONNECTION_INFO.txt[/dim]")
            Prompt.ask("\nPress Enter to continue")
            return

        # Generate RDP files
        console.print(f"[bold yellow]Generating RDP connection files...[/bold yellow]")
        rdp_files = []
        rdp_location = Path.home() / "Desktop" / "LucidLink-RDP"
        rdp_location.mkdir(parents=True, exist_ok=True)

        for idx, (vm_name, public_ip) in enumerate(zip(vm_names, public_ips), 1):
            rdp_name = f"ll-win-client-{idx}"
            try:
                rdp_file = self.generate_rdp_file(public_ip, rdp_name, username=admin_username)
                rdp_files.append(rdp_file)
                console.print(f"  [{self.colors['success']}]✓[/] RDP: {rdp_name}.rdp")
            except Exception as e:
                console.print(f"  [{self.colors['warning']}]⚠[/] Failed to generate RDP file for {rdp_name}: {e}")

        # Save connection info to file
        console.print()
        console.print(f"[bold yellow]Saving connection info...[/bold yellow]")
        connection_file = rdp_location / "CONNECTION_INFO.txt"
        with open(connection_file, 'w') as f:
            f.write("Azure Windows VM Connection Information\n")
            f.write("=" * 60 + "\n\n")
            f.write("IMPORTANT: Keep this file secure!\n\n")
            f.write(f"Admin Credentials:\n")
            f.write(f"  Username: {admin_username}\n")
            f.write(f"  Password: {admin_password}\n\n")
            f.write("Virtual Machines:\n")
            for idx, (vm_name, public_ip) in enumerate(zip(vm_names, public_ips), 1):
                f.write(f"  {idx}. {vm_name}\n")
                f.write(f"     Public IP: {public_ip}\n")
                f.write(f"     RDP Port: 3389\n\n")

        console.print(f"  [{self.colors['success']}]✓[/] Connection info saved to: {connection_file}")

        # Display summary
        console.print()
        console.print(Panel.fit(
            f"[{self.colors['success']}]Connection files regenerated successfully![/]\n\n"
            f"Location: [bold]{rdp_location}[/bold]\n\n"
            f"RDP Files: {len(rdp_files)}\n"
            f"VMs: {len(vm_names)}",
            border_style="green"
        ))

        console.print()
        console.print(f"[bold]To connect:[/bold]")
        console.print(f"1. Open your Desktop and find the 'LucidLink-RDP' folder")
        console.print(f"2. Double-click the .rdp file for the VM you want to access")
        console.print(f"3. Click 'Connect' when prompted")
        console.print(f"4. Credentials are embedded in the RDP file")

        console.print()
        Prompt.ask("Press Enter to continue")

    def stop_all_instances(self):
        """Stop all running instances to save money"""
        console.clear()
        self.show_banner()

        console.print(Panel.fit(
            "[bold]Stop All Instances[/bold]\n"
            "This will stop all running instances to save compute costs.\n"
            "Storage costs will still apply. You can start them again later.",
            border_style="yellow"
        ))
        console.print()

        # Get terraform outputs
        outputs = self.get_terraform_outputs()
        if not outputs:
            console.print(f"[{self.colors['error']}]No deployment found. Please deploy instances first.[/]")
            console.print()
            Prompt.ask("Press Enter to continue")
            return

        vm_names = outputs.get('vm_names', [])
        resource_group = outputs.get('resource_group_name', self.config.get('resource_group_name', 'll-win-client-rg'))
        if not vm_names:
            console.print(f"[{self.colors['warning']}]No instances found in deployment.[/]")
            console.print()
            Prompt.ask("Press Enter to continue")
            return

        console.print(f"Found {len(vm_names)} VM(s):")
        for idx, vm_name in enumerate(vm_names):
            console.print(f"  {idx + 1}. {vm_name}")
        console.print()

        # Check current status using Azure CLI (resource_group already set above)

        try:
            # Get VM statuses
            result = subprocess.run(
                ['az', 'vm', 'list',
                 '--resource-group', resource_group,
                 '--query', '[].{name:name, state:powerState}',
                 '--output', 'json'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                console.print(f"[{self.colors['error']}]Failed to get VM statuses: {result.stderr}[/]")
                console.print()
                Prompt.ask("Press Enter to continue")
                return

            vm_statuses = json.loads(result.stdout)
            running_vms = []

            # Display status and collect running VMs
            for vm in vm_statuses:
                vm_name = vm['name']
                state = vm['state']
                console.print(f"  {vm_name}: [{self.colors['info']}]{state}[/]")
                if 'VM running' in state:
                    running_vms.append(vm_name)

            if not running_vms:
                console.print(f"\n[{self.colors['warning']}]No running VMs to stop.[/]")
                console.print()
                Prompt.ask("Press Enter to continue")
                return

            console.print(f"\n[{self.colors['warning']}]This will deallocate {len(running_vms)} running VM(s).[/]")
            console.print(f"[{self.colors['info']}]Deallocated VMs do not incur compute charges (only storage).[/]")
            console.print(f"[dim]Note: Using 'deallocate' instead of 'stop' to avoid continued compute billing.[/dim]")

            if not Confirm.ask("\nProceed with deallocating VMs?", default=False):
                console.print(f"[{self.colors['info']}]Operation cancelled.[/]")
                console.print()
                Prompt.ask("Press Enter to continue")
                return

            # Deallocate VMs (stops billing for compute)
            console.print(f"\n[bold yellow]Deallocating VMs...[/bold yellow]")
            console.print(f"[dim]This may take a few minutes...[/dim]")

            # Deallocate running VMs by name
            deallocate_result = subprocess.run(
                ['az', 'vm', 'deallocate',
                 '--resource-group', resource_group,
                 '--names'] + running_vms + ['--no-wait'],
                capture_output=True,
                text=True,
                timeout=60
            )

            if deallocate_result.returncode == 0:
                console.print(f"[{self.colors['success']}]✓ Deallocation initiated for {len(running_vms)} VM(s)[/]")
                console.print(f"[dim]VMs are shutting down in the background...[/dim]")

                # Wait for VMs to deallocate
                console.print(f"\n[bold yellow]Waiting for VMs to deallocate...[/bold yellow]")
                with console.status("[bold yellow]Monitoring deallocation progress...[/bold yellow]"):
                    all_deallocated = False
                    max_attempts = 40  # 40 attempts * 15 seconds = 10 minutes
                    for attempt in range(max_attempts):
                        time.sleep(15)

                        # Check status
                        check_result = subprocess.run(
                            ['az', 'vm', 'list',
                             '--resource-group', resource_group,
                             '--query', '[].{name:name, state:powerState}',
                             '--output', 'json'],
                            capture_output=True,
                            text=True,
                            timeout=30
                        )

                        if check_result.returncode == 0:
                            statuses = json.loads(check_result.stdout)
                            running_count = sum(1 for vm in statuses if 'VM running' in vm['state'] and vm['name'] in running_vms)

                            if running_count == 0:
                                all_deallocated = True
                                break

                    if all_deallocated:
                        console.print(f"[{self.colors['success']}]✓ VMs deallocated successfully[/]")
                    else:
                        console.print(f"[{self.colors['warning']}]⚠ Some VMs may still be deallocating[/]")
                        console.print(f"[dim]Check Azure Portal for final status[/dim]")

                console.print(f"\n[{self.colors['success']}]✓ Successfully deallocated {len(running_vms)} VM(s)[/]")
                console.print(f"\n[{self.colors['info']}]To resume work, use 'Start All Instances' from the main menu.[/]")
            else:
                console.print(f"[{self.colors['error']}]Failed to deallocate VMs: {deallocate_result.stderr}[/]")

        except Exception as e:
            console.print(f"\n[{self.colors['error']}]Error stopping VMs: {e}[/]")
            logger.error(f"Error stopping VMs: {e}", exc_info=True)

        console.print()
        Prompt.ask("Press Enter to continue")

    def start_all_instances(self):
        """Start all stopped instances"""
        console.clear()
        self.show_banner()

        console.print(Panel.fit(
            "[bold]Start All Instances[/bold]\n"
            "This will start all stopped instances so you can resume work.",
            border_style="green"
        ))
        console.print()

        # Get terraform outputs
        outputs = self.get_terraform_outputs()
        if not outputs:
            console.print(f"[{self.colors['error']}]No deployment found. Please deploy instances first.[/]")
            console.print()
            Prompt.ask("Press Enter to continue")
            return

        vm_names = outputs.get('vm_names', [])
        resource_group = outputs.get('resource_group_name', self.config.get('resource_group_name', 'll-win-client-rg'))
        if not vm_names:
            console.print(f"[{self.colors['warning']}]No instances found in deployment.[/]")
            console.print()
            Prompt.ask("Press Enter to continue")
            return

        console.print(f"Found {len(vm_names)} VM(s):")
        for idx, vm_name in enumerate(vm_names):
            console.print(f"  {idx + 1}. {vm_name}")
        console.print()

        # Check current status using Azure CLI (resource_group already set above)

        try:
            # Get VM statuses
            result = subprocess.run(
                ['az', 'vm', 'list',
                 '--resource-group', resource_group,
                 '--query', '[].{name:name, state:powerState}',
                 '--output', 'json'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                console.print(f"[{self.colors['error']}]Failed to get VM statuses: {result.stderr}[/]")
                console.print()
                Prompt.ask("Press Enter to continue")
                return

            vm_statuses = json.loads(result.stdout)
            stopped_vms = []

            # Display status and collect stopped/deallocated VMs
            for vm in vm_statuses:
                vm_name = vm['name']
                state = vm['state']
                console.print(f"  {vm_name}: [{self.colors['info']}]{state}[/]")
                if 'VM running' not in state:
                    stopped_vms.append(vm_name)

            if not stopped_vms:
                console.print(f"\n[{self.colors['warning']}]No stopped VMs to start.[/]")
                console.print()
                Prompt.ask("Press Enter to continue")
                return

            console.print(f"\n[{self.colors['info']}]This will start {len(stopped_vms)} stopped VM(s).[/]")
            console.print(f"[{self.colors['warning']}]Compute charges will resume once VMs are running.[/]")

            if not Confirm.ask("\nProceed with starting VMs?", default=True):
                console.print(f"[{self.colors['info']}]Operation cancelled.[/]")
                console.print()
                Prompt.ask("Press Enter to continue")
                return

            # Start VMs
            console.print(f"\n[bold green]Starting VMs...[/bold green]")
            console.print(f"[dim]This may take a few minutes...[/dim]")

            # Start stopped VMs by name
            start_result = subprocess.run(
                ['az', 'vm', 'start',
                 '--resource-group', resource_group,
                 '--names'] + stopped_vms + ['--no-wait'],
                capture_output=True,
                text=True,
                timeout=60
            )

            if start_result.returncode == 0:
                console.print(f"[{self.colors['success']}]✓ Start initiated for {len(stopped_vms)} VM(s)[/]")
                console.print(f"[dim]VMs are starting in the background...[/dim]")

                # Wait for VMs to start
                console.print(f"\n[bold green]Waiting for VMs to start...[/bold green]")
                with console.status("[bold green]Monitoring startup progress...[/bold green]"):
                    all_running = False
                    max_attempts = 40  # 40 attempts * 15 seconds = 10 minutes
                    for attempt in range(max_attempts):
                        time.sleep(15)

                        # Check status
                        check_result = subprocess.run(
                            ['az', 'vm', 'list',
                             '--resource-group', resource_group,
                             '--query', '[].{name:name, state:powerState}',
                             '--output', 'json'],
                            capture_output=True,
                            text=True,
                            timeout=30
                        )

                        if check_result.returncode == 0:
                            statuses = json.loads(check_result.stdout)
                            running_count = sum(1 for vm in statuses if 'VM running' in vm['state'] and vm['name'] in stopped_vms)

                            if running_count == len(stopped_vms):
                                all_running = True
                                break

                    if all_running:
                        console.print(f"[{self.colors['success']}]✓ VMs started successfully[/]")
                    else:
                        console.print(f"[{self.colors['warning']}]⚠ Some VMs may still be starting[/]")
                        console.print(f"[dim]Check Azure Portal for final status[/dim]")

                console.print(f"\n[{self.colors['success']}]✓ Successfully started {len(stopped_vms)} VM(s)[/]")

                # Get updated public IPs
                console.print(f"\n[{self.colors['info']}]Updating RDP connection files with new IP addresses...[/]")

                # Get all VMs with their public IPs
                ip_result = subprocess.run(
                    ['az', 'vm', 'list-ip-addresses',
                     '--resource-group', resource_group,
                     '--output', 'json'],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                public_ips = []
                if ip_result.returncode == 0:
                    ip_data = json.loads(ip_result.stdout)
                    for vm in ip_data:
                        # Extract public IP from the nested structure
                        public_ip = "N/A"
                        if vm.get('virtualMachine', {}).get('network', {}).get('publicIpAddresses'):
                            public_ip_list = vm['virtualMachine']['network']['publicIpAddresses']
                            if public_ip_list:
                                public_ip = public_ip_list[0].get('ipAddress', 'N/A')
                        public_ips.append(public_ip)

                # Try to read existing password from CONNECTION_INFO.txt
                password = None
                rdp_location = Path.home() / "Desktop" / "LucidLink-RDP"
                password_file = rdp_location / "CONNECTION_INFO.txt"
                if password_file.exists():
                    try:
                        with open(password_file, 'r') as f:
                            for line in f:
                                if line.strip().startswith("Password:"):
                                    password = line.split(":", 1)[1].strip()
                                    break
                    except Exception as e:
                        logger.warning(f"Could not read password from file: {e}")

                # Regenerate RDP files with new IPs
                admin_username = self.config.get('admin_username', 'azureuser')
                for idx, (vm_name, public_ip) in enumerate(zip(vm_names, public_ips)):
                    rdp_name = f"ll-win-client-{idx + 1}"
                    try:
                        self.generate_rdp_file(public_ip, rdp_name, username=admin_username)
                        console.print(f"  [{self.colors['success']}]✓[/] Updated: {rdp_name}.rdp ({public_ip})")
                    except Exception as e:
                        logger.warning(f"Failed to regenerate RDP file: {e}")

                console.print(f"\n[{self.colors['success']}]✓ RDP connection files updated with new IP addresses[/]")
                console.print(f"[{self.colors['info']}]Connection files: ~/Desktop/LucidLink-RDP/[/]")
                console.print(f"[dim]Note: Public IPs may change when VMs are stopped/started[/dim]")
            else:
                console.print(f"[{self.colors['error']}]Failed to start VMs: {start_result.stderr}[/]")

        except Exception as e:
            console.print(f"\n[{self.colors['error']}]Error starting VMs: {e}[/]")
            logger.error(f"Error starting VMs: {e}", exc_info=True)

        console.print()
        Prompt.ask("Press Enter to continue")

    def build_custom_image(self):
        """Build a custom managed image using Packer with pre-installed software"""
        console.clear()
        self.show_banner()

        console.print(Panel.fit(
            "[bold]Build Custom Image (Packer)[/bold]\n\n"
            "Create a pre-configured Azure managed image with all software installed.\n"
            "This speeds up deployments significantly.",
            border_style="cyan"
        ))
        console.print()

        # Check if Packer is installed
        try:
            result = subprocess.run(['packer', 'version'], capture_output=True, text=True)
            packer_version = result.stdout.strip().split('\n')[0] if result.returncode == 0 else None
        except FileNotFoundError:
            packer_version = None

        if not packer_version:
            console.print(f"[{self.colors['error']}]Packer is not installed![/]")
            console.print()
            console.print("[bold]To install Packer:[/bold]")
            console.print("  macOS:   brew install packer")
            console.print("  Linux:   See https://developer.hashicorp.com/packer/install")
            console.print()
            Prompt.ask("Press Enter to continue")
            return

        console.print(f"[{self.colors['success']}]✓ Packer found: {packer_version}[/]")
        console.print()

        # Show base image info
        console.print("[bold]Base Image:[/bold] Windows 11 Pro 23H2")
        console.print()

        # Show what will be built
        console.print("[bold]Software to be pre-installed:[/bold]")
        console.print("  - Google Chrome")
        console.print("  - BGInfo")
        console.print("  - Visual C++ Redistributables (2013, 2015-2022)")
        console.print("  - VLC Media Player")
        console.print("  - LucidLink installer (pre-downloaded)")
        console.print()
        console.print("[bold]Configured at deployment time:[/bold]")
        console.print("  - D: drive (data disk)")
        console.print("  - Admin password")
        console.print("  - LucidLink filespace connection")
        console.print()

        # Get location
        location = self.config.get('location', 'eastus') if self.config else 'eastus'
        resource_group = self.config.get('resource_group_name', 'll-win-client-rg') if self.config else 'll-win-client-rg'
        packer_rg = f"{resource_group}-packer"

        console.print(f"[bold]Build Location:[/bold] {location}")
        console.print(f"[bold]Image Resource Group:[/bold] {packer_rg}")
        console.print(f"[bold]VM Size:[/bold] Standard_D4s_v3 (build VM, no GPU needed)")
        console.print()

        console.print(f"[{self.colors['warning']}]Note: Building an image takes 15-30 minutes and incurs Azure VM charges.[/]")
        console.print()

        if not Confirm.ask("Start Packer build?", default=False):
            console.print("\n[bold]Build cancelled.[/bold]")
            Prompt.ask("Press Enter to continue")
            return

        # Setup paths
        packer_dir = self.script_dir / "packer"
        if not packer_dir.exists():
            console.print(f"[{self.colors['error']}]Packer directory not found: {packer_dir}[/]")
            Prompt.ask("Press Enter to continue")
            return

        # Ensure resource group exists for the image
        console.print(f"\n[{self.colors['info']}]Ensuring resource group '{packer_rg}' exists...[/]")
        try:
            subprocess.run(
                ['az', 'group', 'create', '--name', packer_rg, '--location', location],
                capture_output=True, text=True, check=True
            )
            console.print(f"[{self.colors['success']}]✓ Resource group ready[/]")
        except subprocess.CalledProcessError as e:
            console.print(f"[{self.colors['error']}]Failed to create resource group: {e.stderr}[/]")
            Prompt.ask("Press Enter to continue")
            return

        env = os.environ.copy()
        console.print()

        # Step 1: Packer init
        console.print(f"[{self.colors['primary']}][1/3] Running packer init...[/]")
        try:
            result = subprocess.run(
                ['packer', 'init', '.'],
                cwd=str(packer_dir),
                env=env,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                console.print(f"[{self.colors['error']}]Packer init failed:[/]")
                console.print(result.stderr)
                Prompt.ask("Press Enter to continue")
                return
            console.print(f"[{self.colors['success']}]✓ Packer initialized[/]")
        except Exception as e:
            console.print(f"[{self.colors['error']}]Error running packer init: {e}[/]")
            Prompt.ask("Press Enter to continue")
            return

        # Build packer variables list
        packer_vars = [
            '-var', f'location={location}',
            '-var', f'resource_group_name={packer_rg}',
        ]

        # Step 2: Packer validate
        console.print(f"[{self.colors['primary']}][2/3] Running packer validate...[/]")
        try:
            result = subprocess.run(
                ['packer', 'validate'] + packer_vars + ['.'],
                cwd=str(packer_dir),
                env=env,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                console.print(f"[{self.colors['error']}]Packer validate failed:[/]")
                console.print(result.stderr)
                Prompt.ask("Press Enter to continue")
                return
            console.print(f"[{self.colors['success']}]✓ Packer template valid[/]")
        except Exception as e:
            console.print(f"[{self.colors['error']}]Error running packer validate: {e}[/]")
            Prompt.ask("Press Enter to continue")
            return

        # Step 3: Packer build
        console.print(f"[{self.colors['primary']}][3/3] Running packer build (this takes 15-30 minutes)...[/]")
        console.print()

        # Remove stale manifest before build
        manifest_file = packer_dir / "manifest.json"
        if manifest_file.exists():
            manifest_file.unlink()

        image_id = None
        build_failed = False
        try:
            process = subprocess.Popen(
                ['packer', 'build'] + packer_vars + ['-color=false', '.'],
                cwd=str(packer_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # Stream output
            for line in process.stdout:
                line = line.rstrip()
                # Look for managed image ID in output
                if '/images/' in line:
                    match = re.search(r'/subscriptions/[^"]+/resourceGroups/[^"]+/providers/Microsoft\.Compute/images/[^"\s]+', line)
                    if match:
                        image_id = match.group(0)

                # Show important lines
                if any(x in line.lower() for x in ['error', 'image', 'artifact', 'finished', 'creating', 'waiting', 'provisioning']):
                    console.print(f"  {line}")

            process.wait()

            if process.returncode != 0:
                build_failed = True

        except Exception as e:
            console.print(f"[{self.colors['error']}]Error running packer build: {e}[/]")
            build_failed = True

        console.print()

        # Read image ID from Packer manifest (most reliable)
        if manifest_file.exists():
            try:
                with open(manifest_file, 'r') as f:
                    manifest = json.load(f)
                builds = manifest.get('builds', [])
                if builds:
                    artifact_id = builds[-1].get('artifact_id', '')
                    if artifact_id:
                        image_id = artifact_id
            except Exception as e:
                logger.warning(f"Failed to read Packer manifest: {e}")

        if build_failed and not image_id:
            console.print(f"[{self.colors['error']}]Packer build failed![/]")
            Prompt.ask("Press Enter to continue")
            return

        if image_id:
            if build_failed:
                console.print(f"[{self.colors['warning']}]Packer reported errors but image was created.[/]")
            console.print(f"[{self.colors['success']}]✓ Image built successfully![/]")
            console.print(f"[bold]Image ID:[/bold] {image_id}")

            # Save to local registry
            images_file = self.config_dir / "azure-images.json"
            images = []
            if images_file.exists():
                try:
                    with open(images_file, 'r') as f:
                        images = json.load(f)
                except Exception:
                    pass
            images.append({
                'image_id': image_id,
                'location': location,
                'resource_group': packer_rg,
                'name': f"ll-win-client-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                'created': datetime.now().isoformat()
            })
            with open(images_file, 'w') as f:
                json.dump(images, f, indent=2)

            console.print()

            # Ask if user wants to use this image
            if Confirm.ask("Use this image for future deployments?", default=True):
                if not self.config:
                    self.config = {}
                self.config['custom_image_id'] = image_id
                self.save_config(self.config)
                console.print(f"[{self.colors['success']}]✓ Configuration updated to use custom image[/]")
                console.print()
                console.print("[bold]Next steps:[/bold]")
                console.print("1. Deploy new instances - they will use your custom image")
                console.print("2. Deployments will be faster (software pre-installed)")
        else:
            console.print(f"[{self.colors['warning']}]Build completed but image ID not captured.[/]")
            console.print("Check Azure Portal for the new managed image.")

        console.print()
        Prompt.ask("Press Enter to continue")

    def show_main_menu(self):
        """Display main menu"""
        while True:
            console.clear()
            self.show_banner()

            # Load existing config if available
            if not self.config and self.client_config_file.exists():
                self.load_config()

            # Build status line
            if self.config and self.config.get('filespace_domain'):
                config_status = f"[{self.colors['success']}]Configured ({self.config.get('filespace_domain')})[/]"
            else:
                config_status = f"[{self.colors['warning']}]Not Configured[/]"

            console.print(Panel.fit(
                f"[bold]Main Menu[/bold]\n\n"
                f"Client Config: {config_status}\n"
                f"Config File: {self.client_config_file}",
                border_style="blue"
            ))
            console.print()

            console.print("1. Configure Client Deployment")
            console.print("2. View Configuration")
            console.print("3. Deploy Client Instances")
            console.print("4. View Deployment Status")
            console.print("5. Regenerate Connection Files (RDP)")
            console.print("6. Stop All Instances")
            console.print("7. Start All Instances")
            console.print("8. Destroy Client Instances")
            console.print("B. Build Custom Image (Packer)")
            console.print("0. Exit")
            console.print()

            choice = Prompt.ask(
                "Select an option",
                choices=['1', '2', '3', '4', '5', '6', '7', '8', 'b', 'B', '0'],
                default='1'
            )

            if choice == '1':
                self.configure_deployment()
            elif choice == '2':
                self.show_configuration_summary()
            elif choice == '3':
                self.deploy_infrastructure()
            elif choice == '4':
                self.view_deployment_status()
            elif choice == '5':
                self.regenerate_connection_files()
            elif choice == '6':
                self.stop_all_instances()
            elif choice == '7':
                self.start_all_instances()
            elif choice == '8':
                self.destroy_infrastructure()
            elif choice.upper() == 'B':
                self.build_custom_image()
            elif choice == '0':
                console.print("\n[bold cyan]Goodbye![/bold cyan]")
                sys.exit(0)

    def run(self):
        """Main entry point"""
        try:
            # Run pre-deployment checks
            if not self.pre_deployment_checks():
                console.print(f"\n[{self.colors['warning']}]Some pre-deployment checks failed.[/]")
                if not Confirm.ask("Continue anyway?", default=False):
                    console.print("\n[bold cyan]Exiting...[/bold cyan]")
                    sys.exit(1)

            self.show_main_menu()
        except KeyboardInterrupt:
            console.print("\n\n[bold yellow]Interrupted by user[/bold yellow]")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            console.print(f"\n[{self.colors['error']}]Unexpected error: {e}[/]")
            console.print(f"Check log file: {log_file}")
            sys.exit(1)


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='LucidLink Windows Client Azure Setup - Deploy Windows LucidLink clients to Azure',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s                     # Interactive mode
  %(prog)s -y                  # Auto-approve deployment/destroy prompts
  %(prog)s --yes               # Same as -y
        '''
    )
    parser.add_argument(
        '-y', '--yes',
        action='store_true',
        dest='auto_approve',
        help='Automatically approve deployment and destroy prompts (non-interactive)'
    )

    args = parser.parse_args()

    console.print("\n[bold cyan]LucidLink Windows Client Azure Setup[/bold cyan]")
    console.print(f"Log file: {log_file}\n")

    # Check dependencies
    missing_deps = []
    for cmd in ['terraform', 'az']:
        if not shutil.which(cmd):
            missing_deps.append(cmd)

    if missing_deps:
        console.print(f"[bold red]Missing required dependencies:[/bold red] {', '.join(missing_deps)}")
        console.print("\nPlease install:")
        if 'terraform' in missing_deps:
            console.print("  • Terraform: https://www.terraform.io/downloads")
        if 'az' in missing_deps:
            console.print("  • Azure CLI: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli")
        sys.exit(1)

    app = LLWinClientAzureSetup(auto_approve=args.auto_approve)
    app.run()


if __name__ == "__main__":
    main()
