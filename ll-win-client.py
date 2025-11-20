#!/usr/bin/env python3
"""
LucidLink Windows Client AWS Setup - Interactive TUI for deploying Windows LucidLink clients on AWS

This script provides an interactive terminal interface to:
1. Configure AWS VPC and network settings
2. Configure LucidLink filespace credentials
3. Deploy Windows Server instances with LucidLink client
4. Monitor deployment status
5. Destroy client infrastructure when needed

Run with: uv run ll-win-client-aws.py

Dependencies are managed via pyproject.toml

Examples:
  ll-win-client-aws.py                     # Interactive mode
  ll-win-client-aws.py -y                  # Auto-approve deployment/destroy prompts
  ll-win-client-aws.py --yes               # Same as -y
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
log_file = f"/tmp/ll-win-client-aws-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
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


class LLWinClientAWSSetup:
    def __init__(self, auto_approve: bool = False):
        self.script_dir = Path(__file__).parent.absolute()
        self.config_dir = Path.home() / ".ll-win-client"
        self.client_config_file = self.config_dir / "config.json"
        self.instance_types_cache_file = self.config_dir / "ec2-instance-types.json"
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

        # Validate instance type
        if 'instance_type' in config:
            instance_type = config['instance_type']
            # If we have the valid types list, check against it
            if self.valid_instance_types:
                if instance_type not in self.valid_instance_types:
                    errors.append(f"Invalid instance type: {instance_type}")
                    errors.append(f"Not available in configured region")
            # Otherwise use regex validation
            elif not self.is_valid_instance_type(instance_type):
                errors.append(f"Invalid instance type format: {instance_type}")

        # Validate root volume size
        if 'root_volume_size' in config:
            size = config.get('root_volume_size', 0)
            if size < 30 or size > 1000:
                errors.append(f"Root volume size must be between 30 and 1000 GB: {size}")

        # Validate VPC CIDR
        if 'vpc_cidr' in config:
            cidr = config['vpc_cidr']
            # Basic CIDR validation
            if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$', cidr):
                errors.append(f"Invalid VPC CIDR format: {cidr}")

        # Validate credentials exist
        if not config.get('filespace_user'):
            errors.append("Filespace username is required")
        if not config.get('filespace_password'):
            errors.append("Filespace password is required")

        return (len(errors) == 0, errors)

    def validate_aws_credentials(self) -> bool:
        """Validate AWS credentials by making a simple API call"""
        try:
            import boto3

            # Use credentials from config if available
            session_kwargs = {'region_name': self.config.get('region', 'us-east-1')}
            if self.config.get('aws_access_key_id'):
                session_kwargs['aws_access_key_id'] = self.config['aws_access_key_id']
            if self.config.get('aws_secret_access_key'):
                session_kwargs['aws_secret_access_key'] = self.config['aws_secret_access_key']

            # Try to list regions as a simple test
            ec2 = boto3.client('ec2', **session_kwargs)
            ec2.describe_regions()
            return True
        except Exception as e:
            logger.error(f"AWS credentials validation failed: {e}")
            return False

    def fetch_ec2_instance_types(self, region: str = None) -> set:
        """Fetch all available EC2 instance types from AWS"""
        try:
            import boto3
            from datetime import datetime, timedelta

            # Check if we have a cached version that's less than 7 days old
            if self.instance_types_cache_file.exists():
                try:
                    with open(self.instance_types_cache_file, 'r') as f:
                        cache_data = json.load(f)
                        cache_time = datetime.fromisoformat(cache_data.get('timestamp', ''))
                        if datetime.now() - cache_time < timedelta(days=7):
                            logger.info(f"Using cached EC2 instance types ({len(cache_data['instance_types'])} types)")
                            return set(cache_data['instance_types'])
                except Exception as e:
                    logger.debug(f"Could not load cache: {e}")

            # Need to fetch fresh data
            console.print("[dim]Fetching EC2 instance types from AWS...[/dim]")

            # Use provided region or default
            if not region:
                region = self.config.get('region', 'us-east-1')

            # Set up AWS credentials
            session_kwargs = {'region_name': region}
            if self.config.get('aws_access_key_id'):
                session_kwargs['aws_access_key_id'] = self.config['aws_access_key_id']
            if self.config.get('aws_secret_access_key'):
                session_kwargs['aws_secret_access_key'] = self.config['aws_secret_access_key']

            ec2 = boto3.client('ec2', **session_kwargs)

            # Fetch all instance types
            instance_types = set()
            paginator = ec2.get_paginator('describe_instance_types')

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Fetching instance types...", total=None)

                for page in paginator.paginate():
                    for instance_type in page['InstanceTypes']:
                        instance_types.add(instance_type['InstanceType'])

                progress.update(task, completed=100)

            # Cache the results
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'region': region,
                'instance_types': sorted(list(instance_types))
            }
            with open(self.instance_types_cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

            logger.info(f"Fetched {len(instance_types)} EC2 instance types from AWS")
            console.print(f"[{self.colors['success']}]✓ Found {len(instance_types)} available instance types[/]")

            return instance_types

        except ImportError:
            logger.warning("boto3 not available, using basic validation")
            return set()
        except Exception as e:
            logger.warning(f"Could not fetch instance types: {e}")
            console.print(f"[{self.colors['warning']}]Could not fetch instance types from AWS, using basic validation[/]")
            return set()

    def is_valid_instance_type(self, instance_type: str) -> bool:
        """Check if an instance type is valid"""
        # First check against cached list if available
        if self.valid_instance_types and instance_type in self.valid_instance_types:
            return True

        # Fall back to regex pattern validation
        # Matches: family (letters) + generation (digits) + attributes (optional letters) + . + size
        # Examples: t3.large, c6id.xlarge, m5n.xlarge, r5dn.2xlarge
        return bool(re.match(r'^[a-z]+[0-9]+[a-z]*\.[a-z0-9]+$', instance_type.lower()))

    def fetch_gpu_instance_types(self, region: str = None) -> List[Dict]:
        """Fetch GPU instance types (g-series) with detailed specifications from AWS API"""
        try:
            import boto3

            console.print("[dim]Fetching GPU instance types from AWS...[/dim]")

            # Use provided region or default
            if not region:
                region = self.config.get('region', 'us-east-1')

            # Set up AWS credentials
            session_kwargs = {'region_name': region}
            if self.config.get('aws_access_key_id'):
                session_kwargs['aws_access_key_id'] = self.config['aws_access_key_id']
            if self.config.get('aws_secret_access_key'):
                session_kwargs['aws_secret_access_key'] = self.config['aws_secret_access_key']

            ec2 = boto3.client('ec2', **session_kwargs)

            # Fetch g-series instance types with details
            gpu_instances = []
            paginator = ec2.get_paginator('describe_instance_types')

            # Filter for g-series instances (GPU instances)
            filters = [{'Name': 'instance-type', 'Values': ['g*']}]

            for page in paginator.paginate(Filters=filters):
                for instance in page['InstanceTypes']:
                    instance_type = instance['InstanceType']

                    # Get GPU info
                    gpu_info = instance.get('GpuInfo', {})
                    gpus = gpu_info.get('Gpus', [])

                    if gpus:  # Only include if it has GPU info
                        gpu_count = sum(gpu.get('Count', 0) for gpu in gpus)
                        gpu_manufacturer = gpus[0].get('Manufacturer', 'Unknown') if gpus else 'Unknown'
                        gpu_name = gpus[0].get('Name', 'Unknown') if gpus else 'Unknown'
                        gpu_memory = gpus[0].get('MemoryInfo', {}).get('SizeInMiB', 0) if gpus else 0
                        gpu_memory_gb = gpu_memory // 1024 if gpu_memory else 0

                        gpu_instances.append({
                            'type': instance_type,
                            'vcpu': instance.get('VCpuInfo', {}).get('DefaultVCpus', 0),
                            'memory_mb': instance.get('MemoryInfo', {}).get('SizeInMiB', 0),
                            'memory_gb': instance.get('MemoryInfo', {}).get('SizeInMiB', 0) // 1024,
                            'gpu_count': gpu_count,
                            'gpu_manufacturer': gpu_manufacturer,
                            'gpu_name': gpu_name,
                            'gpu_memory_gb': gpu_memory_gb,
                            'network_performance': instance.get('NetworkInfo', {}).get('NetworkPerformance', 'Unknown')
                        })

            # Sort by instance family, then by size
            gpu_instances.sort(key=lambda x: (x['type'].split('.')[0], x['vcpu']))

            logger.info(f"Found {len(gpu_instances)} GPU instance types in {region}")
            console.print(f"[{self.colors['success']}]✓ Found {len(gpu_instances)} GPU instance types available in {region}[/]")

            return gpu_instances

        except ImportError:
            logger.warning("boto3 not available, using fallback GPU instance list")
            console.print(f"[{self.colors['warning']}]Using default GPU instance types (boto3 not available)[/]")
            return self._get_fallback_gpu_instances()
        except Exception as e:
            logger.warning(f"Could not fetch GPU instance types: {e}")
            console.print(f"[{self.colors['warning']}]Could not fetch from AWS, using default GPU instance types[/]")
            return self._get_fallback_gpu_instances()

    def _get_fallback_gpu_instances(self) -> List[Dict]:
        """Fallback list of GPU instances if AWS API is unavailable"""
        return [
            {
                'type': 'g4dn.xlarge',
                'vcpu': 4,
                'memory_gb': 16,
                'gpu_count': 1,
                'gpu_manufacturer': 'NVIDIA',
                'gpu_name': 'T4',
                'gpu_memory_gb': 16
            },
            {
                'type': 'g4dn.2xlarge',
                'vcpu': 8,
                'memory_gb': 32,
                'gpu_count': 1,
                'gpu_manufacturer': 'NVIDIA',
                'gpu_name': 'T4',
                'gpu_memory_gb': 16
            },
            {
                'type': 'g4dn.4xlarge',
                'vcpu': 16,
                'memory_gb': 64,
                'gpu_count': 1,
                'gpu_manufacturer': 'NVIDIA',
                'gpu_name': 'T4',
                'gpu_memory_gb': 16
            },
            {
                'type': 'g5.xlarge',
                'vcpu': 4,
                'memory_gb': 16,
                'gpu_count': 1,
                'gpu_manufacturer': 'NVIDIA',
                'gpu_name': 'A10G',
                'gpu_memory_gb': 24
            },
            {
                'type': 'g5.2xlarge',
                'vcpu': 8,
                'memory_gb': 32,
                'gpu_count': 1,
                'gpu_manufacturer': 'NVIDIA',
                'gpu_name': 'A10G',
                'gpu_memory_gb': 24
            },
            {
                'type': 'g5.4xlarge',
                'vcpu': 16,
                'memory_gb': 64,
                'gpu_count': 1,
                'gpu_manufacturer': 'NVIDIA',
                'gpu_name': 'A10G',
                'gpu_memory_gb': 24
            }
        ]

    def pre_deployment_checks(self) -> bool:
        """Run all pre-deployment validation checks"""
        console.print("\n[bold]Running Pre-Deployment Checks...[/bold]\n")

        checks_passed = True

        # Check 1: AWS credentials valid
        console.print("1. Validating AWS credentials...")
        if self.config.get('aws_access_key_id'):
            if not self.validate_aws_credentials():
                console.print(f"  [{self.colors['error']}]✗ AWS credentials invalid[/]")
                checks_passed = False
            else:
                console.print(f"  [{self.colors['success']}]✓ AWS credentials valid[/]")
        else:
            console.print(f"  [{self.colors['warning']}]⚠ AWS credentials not configured yet[/]")

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

        # Step 1: AWS Region
        console.print("[bold cyan]Step 1: AWS Region[/bold cyan]")
        config['region'] = Prompt.ask(
            "AWS Region",
            default=existing_config.get('region', 'us-east-1')
        )
        console.print()

        # Step 2: AWS Credentials
        console.print("[bold cyan]Step 2: AWS Credentials[/bold cyan]")
        if existing_config.get('aws_access_key_id'):
            console.print(f"[dim]Using existing AWS credentials[/dim]")
            config['aws_access_key_id'] = existing_config['aws_access_key_id']
            config['aws_secret_access_key'] = existing_config.get('aws_secret_access_key', '')

            if Confirm.ask("Update AWS credentials?", default=False):
                config['aws_access_key_id'] = Prompt.ask("AWS Access Key ID")
                config['aws_secret_access_key'] = Prompt.ask("AWS Secret Access Key", password=True)
        else:
            config['aws_access_key_id'] = Prompt.ask("AWS Access Key ID")
            config['aws_secret_access_key'] = Prompt.ask("AWS Secret Access Key", password=True)
        console.print()

        # Step 3: VPC Configuration
        console.print("[bold cyan]Step 3: VPC Configuration[/bold cyan]")
        config['vpc_cidr'] = Prompt.ask(
            "VPC CIDR Block",
            default=existing_config.get('vpc_cidr', '10.0.0.0/16')
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

        # Step 5: Instance Configuration
        console.print("[bold cyan]Step 5: Instance Configuration[/bold cyan]")

        # Fetch GPU instance types dynamically from AWS
        gpu_instance_types = self.fetch_gpu_instance_types(config.get('region'))

        if not gpu_instance_types:
            console.print(f"[{self.colors['error']}]No GPU instance types found. Please check your AWS configuration.[/]")
            return None

        # Display available GPU instances organized by family
        console.print("\n[bold]Available GPU Instance Types:[/bold]")

        # Group by instance family
        families = {}
        for instance in gpu_instance_types:
            family = instance['type'].split('.')[0]
            if family not in families:
                families[family] = []
            families[family].append(instance)

        # Display with grouping
        for idx, instance in enumerate(gpu_instance_types, 1):
            gpu_desc = f"{instance['gpu_count']}x {instance['gpu_manufacturer']} {instance['gpu_name']}"
            if instance.get('gpu_memory_gb'):
                gpu_desc += f" ({instance['gpu_memory_gb']} GB)"

            console.print(f"  {idx:2d}. [cyan]{instance['type']:15s}[/cyan] - {instance['vcpu']:2d} vCPUs, {instance['memory_gb']:3d} GB RAM, {gpu_desc}")

        # Mark recommended instances
        recommended = ['g4dn.xlarge', 'g4dn.2xlarge', 'g4dn.4xlarge']
        rec_indices = [idx for idx, inst in enumerate(gpu_instance_types, 1) if inst['type'] in recommended]
        if rec_indices:
            console.print(f"\n[dim]Recommended for Adobe Creative Cloud: {', '.join(str(i) for i in rec_indices)}[/dim]")

        # Get existing instance type index or default to 1
        existing_type = existing_config.get('instance_type', 'g4dn.xlarge')
        default_choice = next((idx for idx, inst in enumerate(gpu_instance_types, 1) if inst['type'] == existing_type), 1)

        # Build choices list
        valid_choices = [str(i) for i in range(1, len(gpu_instance_types) + 1)]

        while True:
            try:
                choice = IntPrompt.ask(
                    f"\nSelect instance type (1-{len(gpu_instance_types)})",
                    default=default_choice,
                    choices=valid_choices
                )
                if 1 <= choice <= len(gpu_instance_types):
                    config['instance_type'] = gpu_instance_types[choice - 1]['type']
                    console.print(f"[{self.colors['success']}]✓ Selected: {config['instance_type']}[/]")
                    break
                else:
                    console.print(f"[{self.colors['error']}]Please select a number between 1 and {len(gpu_instance_types)}[/]")
            except (ValueError, KeyboardInterrupt):
                console.print(f"[{self.colors['error']}]Invalid selection[/]")

        config['instance_count'] = IntPrompt.ask(
            "Number of Client Instances (1-10)",
            default=existing_config.get('instance_count', 1)
        )

        # Validate instance count
        if config['instance_count'] < 1:
            config['instance_count'] = 1
        elif config['instance_count'] > 10:
            config['instance_count'] = 10

        config['root_volume_size'] = IntPrompt.ask(
            "Root Volume Size (GB)",
            default=existing_config.get('root_volume_size', 100)
        )
        console.print()

        # Step 6: Additional Settings
        console.print("[bold cyan]Step 6: Additional Settings[/bold cyan]")
        config['ssh_key_name'] = Prompt.ask(
            "EC2 Key Pair Name (optional, press Enter to skip)",
            default=existing_config.get('ssh_key_name', '')
        )
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
        if 'aws_secret_access_key' in display_config:
            display_config['aws_secret_access_key'] = '***MASKED***'
        if 'filespace_password' in display_config:
            display_config['filespace_password'] = '***MASKED***'

        # Group settings
        aws_settings = {
            'Region': display_config.get('region', 'Not set'),
            'VPC CIDR': display_config.get('vpc_cidr', 'Not set'),
        }

        filespace_settings = {
            'Filespace Domain': display_config.get('filespace_domain', 'Not set'),
            'Username': display_config.get('filespace_user', 'Not set'),
            'Password': display_config.get('filespace_password', 'Not set'),
            'Mount Point': display_config.get('mount_point', 'Not set'),
            'Auto-configure LucidLink': display_config.get('auto_configure_lucidlink', 'yes'),
        }

        instance_settings = {
            'Instance Type': display_config.get('instance_type', 'Not set'),
            'Instance Count': str(display_config.get('instance_count', 1)),
            'Root Volume Size': f"{display_config.get('root_volume_size', 100)} GB",
            'SSH Key': display_config.get('ssh_key_name', 'None'),
        }

        # Add settings to table
        table.add_row("[bold]AWS Settings[/bold]", "")
        for key, value in aws_settings.items():
            table.add_row(f"  {key}", value)

        table.add_row("", "")
        table.add_row("[bold]Filespace Settings[/bold]", "")
        for key, value in filespace_settings.items():
            table.add_row(f"  {key}", value)

        table.add_row("", "")
        table.add_row("[bold]Instance Settings[/bold]", "")
        for key, value in instance_settings.items():
            table.add_row(f"  {key}", value)

        console.print(table)
        console.print()

        # Show estimated costs
        instance_count = display_config.get('instance_count', 1)
        instance_type = display_config.get('instance_type', 't3.large')

        resources_text = f"[yellow]Estimated Resources:[/yellow]\n"
        resources_text += f"• {instance_count} × {instance_type} EC2 instances\n"
        resources_text += f"• {instance_count} × {display_config.get('root_volume_size', 100)} GB gp3 volumes\n"
        resources_text += f"• 1 × VPC ({display_config.get('vpc_cidr', '10.0.0.0/16')})\n"
        resources_text += f"• 1 × Internet Gateway\n"
        resources_text += f"• 1 × Security Group\n"
        resources_text += f"• 1 × IAM Role + Instance Profile"

        console.print(Panel.fit(resources_text, border_style="yellow"))

        console.print()
        Prompt.ask("Press Enter to continue")

    def generate_tfvars(self, config: Dict) -> str:
        """Generate Terraform tfvars file content for client deployment"""
        tfvars = f"""# LucidLink Windows Client Deployment Variables
# Generated at {datetime.now().isoformat()}
# Generated by: ll-win-client-aws.py

# AWS Configuration
aws_region = "{config.get('region', 'us-east-1')}"
vpc_cidr   = "{config.get('vpc_cidr', '10.0.0.0/16')}"

# Instance Configuration
instance_type       = "{config.get('instance_type', 't3.large')}"
instance_count      = {config.get('instance_count', 1)}
root_volume_size    = {config.get('root_volume_size', 100)}

# LucidLink Configuration
filespace_domain   = "{config.get('filespace_domain', '')}"
filespace_user     = "{config.get('filespace_user', '')}"
filespace_password = "{config.get('filespace_password', '')}"
mount_point        = "{config.get('mount_point', 'L:')}"

# Windows AMI - Latest Windows Server 2022
# This will be looked up dynamically by Terraform
windows_ami_name_filter = "Windows_Server-2022-English-Full-Base-*"

# LucidLink installer URL (Windows) - CORRECT URL for .msi installer
lucidlink_installer_url = "https://www.lucidlink.com/download/new-ll-latest/win/stable/"

# SSH Configuration
ssh_key_name = "{config.get('ssh_key_name', '')}"
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

    def run_terraform_command(self, command: str, auto_approve: bool = False) -> Tuple[bool, str]:
        """Execute a Terraform command with progress tracking"""
        env = os.environ.copy()

        # Set TMPDIR to writable location (fixes macOS permission issues)
        tmpdir = '/tmp/terraform-tmp'
        os.makedirs(tmpdir, exist_ok=True)
        env['TMPDIR'] = tmpdir

        # Set AWS credentials from config
        if self.config.get('aws_access_key_id'):
            env['AWS_ACCESS_KEY_ID'] = self.config['aws_access_key_id']
        if self.config.get('aws_secret_access_key'):
            env['AWS_SECRET_ACCESS_KEY'] = self.config['aws_secret_access_key']
        if self.config.get('region'):
            env['AWS_REGION'] = self.config['region']
            env['AWS_DEFAULT_REGION'] = self.config['region']

        # Check if AMI override file exists
        ami_override_file = self.terraform_dir / "ami-override.tfvars"
        use_ami_override = ami_override_file.exists()

        # Build command
        if command == 'init':
            cmd = ['terraform', 'init']
        elif command == 'validate':
            cmd = ['terraform', 'validate']
        elif command == 'plan':
            cmd = ['terraform', 'plan']
            if use_ami_override:
                cmd.extend(['-var-file=ami-override.tfvars'])
        elif command == 'apply':
            cmd = ['terraform', 'apply']
            if use_ami_override:
                cmd.extend(['-var-file=ami-override.tfvars'])
            if auto_approve:
                cmd.append('-auto-approve')
        elif command == 'destroy':
            cmd = ['terraform', 'destroy']
            if use_ami_override:
                cmd.extend(['-var-file=ami-override.tfvars'])
            if auto_approve:
                cmd.append('-auto-approve')
        else:
            return False, f"Unknown command: {command}"

        # Inform user if using AMI override
        if use_ami_override and command in ['plan', 'apply', 'destroy']:
            console.print(f"[{self.colors['info']}]ℹ Using ami-override.tfvars (Standard Windows AMI)[/]")
            console.print(f"[dim]To use NVIDIA AMI, delete or rename terraform/azure/ami-override.tfvars[/dim]")

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

    def get_windows_password(self, instance_id: str, key_path: str) -> Optional[str]:
        """Retrieve Windows administrator password using EC2 key pair"""
        try:
            import boto3

            # Set up AWS credentials
            session_kwargs = {'region_name': self.config.get('region', 'us-east-1')}
            if self.config.get('aws_access_key_id'):
                session_kwargs['aws_access_key_id'] = self.config['aws_access_key_id']
            if self.config.get('aws_secret_access_key'):
                session_kwargs['aws_secret_access_key'] = self.config['aws_secret_access_key']

            ec2 = boto3.client('ec2', **session_kwargs)

            # Wait for password to be available (can take 5-10 minutes after launch)
            console.print(f"[dim]Waiting for Windows password to be available for {instance_id}...[/dim]")

            max_attempts = 30
            for attempt in range(max_attempts):
                try:
                    response = ec2.get_password_data(InstanceId=instance_id)
                    password_data = response.get('PasswordData', '')

                    if password_data:
                        # Decrypt password using private key
                        if os.path.exists(key_path):
                            from cryptography.hazmat.primitives import serialization
                            from cryptography.hazmat.primitives.asymmetric import padding
                            from cryptography.hazmat.backends import default_backend

                            # Load private key
                            with open(key_path, 'rb') as key_file:
                                private_key = serialization.load_pem_private_key(
                                    key_file.read(),
                                    password=None,
                                    backend=default_backend()
                                )

                            # Decrypt password
                            encrypted_password = base64.b64decode(password_data)
                            decrypted_password = private_key.decrypt(
                                encrypted_password,
                                padding.PKCS1v15()
                            )

                            return decrypted_password.decode('utf-8')
                        else:
                            logger.warning(f"Key file not found: {key_path}")
                            return None

                    if attempt < max_attempts - 1:
                        time.sleep(10)

                except Exception as e:
                    logger.debug(f"Attempt {attempt + 1}: Password not available yet")
                    if attempt < max_attempts - 1:
                        time.sleep(10)

            logger.warning(f"Password not available after {max_attempts} attempts")
            return None

        except ImportError:
            logger.warning("cryptography library not available for password decryption")
            return None
        except Exception as e:
            logger.error(f"Failed to get Windows password: {e}")
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

    def check_ssm_agent_status(self, instance_id: str) -> str:
        """Check if SSM agent is registered and online for an instance"""
        try:
            import boto3

            # Set up AWS credentials
            session_kwargs = {'region_name': self.config.get('region', 'us-east-1')}
            if self.config.get('aws_access_key_id'):
                session_kwargs['aws_access_key_id'] = self.config['aws_access_key_id']
            if self.config.get('aws_secret_access_key'):
                session_kwargs['aws_secret_access_key'] = self.config['aws_secret_access_key']

            ssm = boto3.client('ssm', **session_kwargs)

            # Check if instance is registered with SSM
            response = ssm.describe_instance_information(
                Filters=[
                    {
                        'Key': 'InstanceIds',
                        'Values': [instance_id]
                    }
                ]
            )

            if response['InstanceInformationList']:
                instance_info = response['InstanceInformationList'][0]
                ping_status = instance_info.get('PingStatus', 'Unknown')
                return ping_status  # Online, ConnectionLost, Inactive, etc.
            else:
                return 'NotRegistered'

        except Exception as e:
            logger.debug(f"Failed to check SSM agent status: {e}")
            return 'Unknown'

    def check_dcv_status(self, public_ip: str) -> str:
        """Check if Amazon DCV server is accessible on port 8443

        Args:
            public_ip: Public IP address of the instance

        Returns:
            'Ready', 'NotReady', or 'Unknown'
        """
        try:
            import socket

            if not public_ip or public_ip == "N/A":
                return 'Unknown'

            # Try to connect to port 8443 with 3 second timeout
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)

            result = sock.connect_ex((public_ip, 8443))
            sock.close()

            if result == 0:
                return 'Ready'  # Port is open
            else:
                return 'NotReady'  # Port is closed

        except Exception as e:
            logger.debug(f"Failed to check DCV status for {public_ip}: {e}")
            return 'Unknown'

    def wait_for_ssm_ready(self, instance_ids: List[str], timeout_minutes: int = 15) -> Dict[str, bool]:
        """Wait for SSM agent to be ready on instances

        Returns dict mapping instance_id -> ready status (True/False)
        """
        console.print(f"\n[bold yellow]Waiting for SSM agent to be ready on instances...[/bold yellow]")
        console.print(f"[dim]This typically takes 5-10 minutes after Windows boot[/dim]")
        console.print()

        timeout_seconds = timeout_minutes * 60
        check_interval = 30  # Check every 30 seconds
        max_checks = timeout_seconds // check_interval

        ready_instances = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task(
                f"Waiting for {len(instance_ids)} instance(s)...",
                total=max_checks
            )

            for check_num in range(max_checks):
                # Check status of all instances
                all_ready = True
                status_lines = []

                for inst_id in instance_ids:
                    if inst_id in ready_instances:
                        continue  # Already ready

                    status = self.check_ssm_agent_status(inst_id)

                    if status == 'Online':
                        ready_instances[inst_id] = True
                        status_lines.append(f"  [{self.colors['success']}]✓[/] {inst_id}: Ready")
                    else:
                        all_ready = False
                        status_lines.append(f"  [dim]{inst_id}: {status}[/dim]")

                # Update progress description with current status
                ready_count = len(ready_instances)
                progress.update(
                    task,
                    description=f"{ready_count}/{len(instance_ids)} ready",
                    completed=check_num + 1
                )

                # Print status for this check
                if check_num % 2 == 0:  # Print every minute (every 2nd check)
                    console.print(f"\n[dim]Check {check_num + 1}/{max_checks}:[/dim]")
                    for line in status_lines:
                        console.print(line)

                if all_ready:
                    progress.update(task, completed=max_checks)
                    console.print(f"\n[{self.colors['success']}]✓ All {len(instance_ids)} instance(s) are ready![/]")
                    break

                # Wait before next check (unless this is the last check)
                if check_num < max_checks - 1:
                    time.sleep(check_interval)

            # Return status for all instances (mark not-ready ones as False)
            for inst_id in instance_ids:
                if inst_id not in ready_instances:
                    ready_instances[inst_id] = False

        return ready_instances

    def set_windows_password_via_ssm(self, instance_id: str, password: Optional[str] = None) -> Optional[str]:
        """Automatically set Windows Administrator password via SSM"""
        try:
            import boto3

            # Generate password if not provided
            if not password:
                password = self.generate_secure_password()

            # Set up AWS credentials
            session_kwargs = {'region_name': self.config.get('region', 'us-east-1')}
            if self.config.get('aws_access_key_id'):
                session_kwargs['aws_access_key_id'] = self.config['aws_access_key_id']
            if self.config.get('aws_secret_access_key'):
                session_kwargs['aws_secret_access_key'] = self.config['aws_secret_access_key']

            ssm = boto3.client('ssm', **session_kwargs)

            console.print(f"[dim]Setting password for {instance_id} via SSM...[/dim]")

            # Send command to set password using PowerShell (more reliable than net user)
            # Escape password for PowerShell by doubling any single quotes
            ps_escaped_password = password.replace("'", "''")

            response = ssm.send_command(
                InstanceIds=[instance_id],
                DocumentName='AWS-RunPowerShellScript',
                Parameters={
                    'commands': [
                        # Use PowerShell cmdlets for more reliable password setting
                        f"$password = ConvertTo-SecureString '{ps_escaped_password}' -AsPlainText -Force",
                        "Set-LocalUser -Name 'Administrator' -Password $password",
                        "Write-Host 'Password set successfully'",
                        # Verify the password was set by checking the account
                        "Get-LocalUser -Name 'Administrator' | Select-Object Name, Enabled, PasswordLastSet | Format-List"
                    ]
                },
                Comment='Set Windows Administrator password via ll-win-client-aws'
            )

            command_id = response['Command']['CommandId']
            logger.info(f"SSM command sent: {command_id}")

            # Wait for command to complete
            console.print(f"[dim]Waiting for SSM command to complete...[/dim]")
            max_attempts = 30
            for attempt in range(max_attempts):
                time.sleep(2)

                try:
                    result = ssm.get_command_invocation(
                        CommandId=command_id,
                        InstanceId=instance_id
                    )

                    status = result['Status']

                    if status == 'Success':
                        # Show command output for verification
                        stdout = result.get('StandardOutputContent', '').strip()
                        stderr = result.get('StandardErrorContent', '').strip()

                        if stdout:
                            logger.info(f"SSM output: {stdout}")
                        if stderr:
                            logger.warning(f"SSM stderr: {stderr}")

                        console.print(f"[{self.colors['success']}]✓ Password set successfully via SSM[/]")
                        return password
                    elif status in ['Failed', 'Cancelled', 'TimedOut']:
                        # Get detailed error information
                        stdout = result.get('StandardOutputContent', '').strip()
                        stderr = result.get('StandardErrorContent', '').strip()

                        logger.error(f"SSM command failed with status: {status}")
                        if stdout:
                            logger.error(f"SSM stdout: {stdout}")
                            console.print(f"[dim]Output: {stdout[:200]}[/dim]")
                        if stderr:
                            logger.error(f"SSM stderr: {stderr}")
                            console.print(f"[{self.colors['warning']}]Error: {stderr[:200]}[/]")

                        console.print(f"[{self.colors['warning']}]⚠ SSM command failed: {status}[/]")
                        return None
                    elif status in ['Pending', 'InProgress', 'Delayed']:
                        # Still running, continue waiting
                        continue

                except ssm.exceptions.InvocationDoesNotExist:
                    # Command not yet registered, keep waiting
                    continue

            logger.warning("SSM command timed out")
            console.print(f"[{self.colors['warning']}]⚠ SSM command timed out[/]")
            return None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to set password via SSM: {e}")

            # Provide helpful context based on error type
            if "InvalidInstanceId" in error_msg or "not in a valid state" in error_msg:
                console.print(f"[{self.colors['warning']}]⚠ Instance not ready yet - SSM agent is still starting up[/]")
            else:
                console.print(f"[{self.colors['warning']}]⚠ Could not set password via SSM: {error_msg}[/]")
            return None

    def generate_dcv_file(self, instance_ip: str, instance_name: str, username: str = None, password: Optional[str] = None) -> str:
        """Generate Amazon DCV connection file on Desktop

        Args:
            instance_ip: Public IP of the instance
            instance_name: Name for the DCV file
            username: Optional username (if None, DCV will prompt for username)
            password: Optional password (if provided, will be embedded in file)
        """
        # Save to user's Desktop for easy access
        desktop_dir = Path.home() / "Desktop" / "LucidLink-DCV"
        desktop_dir.mkdir(parents=True, exist_ok=True)

        dcv_file_path = desktop_dir / f"{instance_name}.dcv"

        # DCV connection file content (INI format)
        dcv_content = f"""[version]
format=1.0

[connect]
host={instance_ip}
port=8443
sessionid=console
"""

        # Add username if specified (omit to let DCV prompt for username)
        if username:
            dcv_content += f"user={username}\n"

        # Add password if provided (user will need to enter it if not)
        if password:
            dcv_content += f"password={password}\n"

        dcv_content += f"""
[options]
fullscreen=false
preferred-video-codec=h264
"""

        # Write DCV file
        with open(dcv_file_path, 'w') as f:
            f.write(dcv_content)

        logger.info(f"Generated DCV file: {dcv_file_path}")
        return str(dcv_file_path)

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
            "This will deploy Windows LucidLink client instances to AWS using Terraform.",
            border_style="blue"
        ))
        console.print()

        # Show deployment summary
        console.print("[bold]Deployment Summary:[/bold]")
        console.print(f"  • Region: {self.config.get('region', 'us-east-1')}")
        console.print(f"  • VPC CIDR: {self.config.get('vpc_cidr', '10.0.0.0/16')}")
        console.print(f"  • Instance Type: {self.config.get('instance_type', 't3.large')}")
        console.print(f"  • Instance Count: {self.config.get('instance_count', 1)}")
        console.print(f"  • Root Volume: {self.config.get('root_volume_size', 100)} GB")
        console.print(f"  • Filespace: {self.config.get('filespace_domain', 'Not set')}")
        console.print(f"  • Mount Point: {self.config.get('mount_point', 'L:')}")
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
                f"[{self.colors['success']}]Client deployment completed successfully![/]\n"
                "Windows instances are initializing...",
                border_style="green"
            ))

            # Show access information
            outputs = self.get_terraform_outputs()
            if outputs:
                console.print("\n[bold]Deployment Information:[/bold]")
                if 'instance_ids' in outputs:
                    console.print(f"\nInstance IDs: {', '.join(outputs['instance_ids'])}")
                if 'private_ips' in outputs:
                    console.print(f"Private IPs: {', '.join(outputs['private_ips'])}")
                if 'public_ips' in outputs:
                    console.print(f"Public IPs: {', '.join(outputs['public_ips'])}")

                # Run deployment script to install DCV, LucidLink, etc.
                console.print(f"\n[bold]Step 6: Running deployment script on instances...[/bold]")
                instance_ids = outputs.get('instance_ids', [])
                public_ips = outputs.get('public_ips', [])
                region = self.config.get('region', 'us-east-1')

                # Generate password and save to file
                dcv_password = self.generate_secure_password(16)
                passwords_file = Path.home() / "Desktop" / "LucidLink-DCV" / "PASSWORDS.txt"
                passwords_file.parent.mkdir(parents=True, exist_ok=True)

                with open(passwords_file, 'w') as f:
                    f.write("Windows Administrator Password\n")
                    f.write("=" * 60 + "\n\n")
                    f.write("IMPORTANT: Keep this file secure!\n\n")
                    f.write("ONE PASSWORD FOR ALL INSTANCES:\n")
                    f.write(f"  Password: {dcv_password}\n\n")
                    f.write("This password works for:\n")
                    for idx, (instance_id, public_ip) in enumerate(zip(instance_ids, public_ips)):
                        f.write(f"  {idx + 1}. {instance_id} ({public_ip}) - ✓ Password set\n")
                    f.write("\nConnection Info:\n")
                    f.write("  Username: Administrator\n")
                    f.write(f"  Password: {dcv_password}\n")
                    f.write("  (Same password for all instances)\n")

                console.print(f"  [{self.colors['info']}]Generated DCV password and saved to {passwords_file}[/]")

                # Wait for SSM and run deployment script on each instance
                deployment_script = self.script_dir / "deployment" / "deploy-windows-client.sh"

                for idx, instance_id in enumerate(instance_ids):
                    instance_name = f"ll-win-client-{idx + 1}"
                    console.print(f"\n  [{self.colors['info']}]Deploying software to {instance_name} ({instance_id})...[/]")

                    # Wait for instance to be fully ready
                    console.print(f"    Waiting for instance to be ready...")
                    max_wait = 300  # 5 minutes
                    wait_interval = 10
                    ssm_online = False

                    for attempt in range(max_wait // wait_interval):
                        try:
                            # Check EC2 instance state
                            ec2_result = subprocess.run(
                                ['aws', 'ec2', 'describe-instances',
                                 '--instance-ids', instance_id,
                                 '--region', region,
                                 '--query', 'Reservations[0].Instances[0].State.Name',
                                 '--output', 'text'],
                                capture_output=True,
                                text=True,
                                timeout=10
                            )
                            instance_state = ec2_result.stdout.strip()

                            # Check SSM agent status
                            ssm_result = subprocess.run(
                                ['aws', 'ssm', 'describe-instance-information',
                                 '--filters', f'Key=InstanceIds,Values={instance_id}',
                                 '--region', region,
                                 '--query', 'InstanceInformationList[0].PingStatus',
                                 '--output', 'text'],
                                capture_output=True,
                                text=True,
                                timeout=10
                            )
                            ssm_status = ssm_result.stdout.strip()

                            if instance_state == 'running' and ssm_status == 'Online':
                                if not ssm_online:
                                    console.print(f"    [{self.colors['success']}]✓[/] Instance running and SSM agent online")
                                    console.print(f"    Waiting 60 seconds for Windows initialization...")
                                    ssm_online = True
                                    time.sleep(60)  # Buffer period for Windows to fully initialize
                                console.print(f"    [{self.colors['success']}]✓[/] Instance ready for deployment")
                                break
                        except:
                            pass
                        time.sleep(wait_interval)

                    if not ssm_online:
                        console.print(f"    [{self.colors['warning']}]⚠[/] Instance may not be fully ready, proceeding anyway...")
                        logger.warning(f"Instance {instance_id} did not fully initialize within timeout")

                    # Run deployment script
                    console.print(f"    Running deployment script (this takes ~5-10 minutes)...")
                    try:
                        env = os.environ.copy()
                        env['DCV_ADMIN_PASSWORD'] = dcv_password
                        # Pass LucidLink auto-configuration flag
                        env['AUTO_CONFIGURE_LUCIDLINK'] = '1' if self.config.get('auto_configure_lucidlink') == 'yes' else '0'
                        result = subprocess.run(
                            [str(deployment_script), instance_id, region],
                            env=env,
                            capture_output=True,
                            text=True,
                            timeout=1200  # 20 minutes
                        )
                        if result.returncode == 0:
                            console.print(f"    [{self.colors['success']}]✓[/] Deployment completed successfully")
                        else:
                            console.print(f"    [{self.colors['error']}]✗[/] Deployment failed - check logs")
                            logger.error(f"Deployment script failed for {instance_id}: {result.stderr}")
                    except subprocess.TimeoutExpired:
                        console.print(f"    [{self.colors['warning']}]⚠[/] Deployment timed out - may still be running")
                    except Exception as e:
                        console.print(f"    [{self.colors['error']}]✗[/] Deployment error: {e}")
                        logger.error(f"Deployment script error for {instance_id}: {e}")

                # Generate connection files for each instance
                console.print(f"\n[bold]Generating connection files...[/bold]")
                instance_ids = outputs.get('instance_ids', [])
                public_ips = outputs.get('public_ips', [])
                dcv_files = []

                for idx, (instance_id, public_ip) in enumerate(zip(instance_ids, public_ips)):
                    instance_name = f"ll-win-client-{idx + 1}"
                    try:
                        # Generate DCV file
                        dcv_file = self.generate_dcv_file(public_ip, instance_name)
                        dcv_files.append(dcv_file)
                        console.print(f"  [{self.colors['success']}]✓[/] DCV: {instance_name}.dcv")
                    except Exception as e:
                        console.print(f"  [{self.colors['warning']}]⚠[/] Failed to generate DCV file for {instance_name}: {e}")

                # Show connection info
                dcv_location = Path.home() / "Desktop" / "LucidLink-DCV"

                console.print(f"\n[bold cyan]═══════════════════════════════════════════════════════════[/bold cyan]")
                console.print(f"[bold cyan]Connection Files Generated[/bold cyan]")
                console.print(f"[bold cyan]═══════════════════════════════════════════════════════════[/bold cyan]")

                console.print(f"\n[bold green]Amazon DCV Connection[/bold green]")
                console.print(f"Location: [bold]{dcv_location}[/bold]")
                console.print(f"\n[bold]To connect using DCV:[/bold]")
                console.print(f"1. Download the DCV client from: [cyan]https://download.nice-dcv.com/[/cyan]")
                console.print(f"2. Install the DCV client on your local machine")
                console.print(f"3. Open your Desktop and find the 'LucidLink-DCV' folder")
                console.print(f"4. Double-click the .dcv file for the instance you want to access")
                console.print(f"5. When prompted, enter Username: [bold]Administrator[/bold]")
                console.print(f"6. Password will auto-fill (or check PASSWORDS.txt)")
                console.print(f"\n[dim]Note: DCV provides superior performance for graphics-intensive applications like Adobe Creative Cloud[/dim]")

                # Try to retrieve Windows password if SSH key is configured
                ssh_key_name = self.config.get('ssh_key_name', '')
                if ssh_key_name:
                    console.print(f"\n[bold yellow]Retrieving Windows Administrator password...[/bold yellow]")
                    console.print(f"[dim]Note: This may take 5-10 minutes after instance launch[/dim]")

                    # Prompt for key path
                    default_key_path = os.path.expanduser(f"~/.ssh/{ssh_key_name}.pem")
                    console.print(f"\n[dim]Default key path: {default_key_path}[/dim]")

                    if Confirm.ask("Retrieve Windows password now?", default=False):
                        key_path = Prompt.ask("Path to private key file", default=default_key_path)

                        if os.path.exists(key_path):
                            # Try to get password for first instance
                            password = self.get_windows_password(instance_ids[0], key_path)
                            if password:
                                console.print(f"\n[{self.colors['success']}]Windows Administrator Password:[/]")
                                console.print(Panel.fit(
                                    f"[bold white]{password}[/bold white]",
                                    border_style="green",
                                    title="Copy this password"
                                ))
                                console.print(f"\n[dim]Use this password when connecting via DCV[/dim]")

                                # Save password to a text file on Desktop
                                password_file = Path.home() / "Desktop" / "LucidLink-DCV" / "PASSWORDS.txt"
                                with open(password_file, 'w') as f:
                                    f.write(f"Windows Administrator Passwords\n")
                                    f.write(f"=================================\n\n")
                                    f.write(f"Password: {password}\n\n")
                                    f.write(f"This password works for all instances:\n")
                                    for idx, inst_id in enumerate(instance_ids, 1):
                                        public_ip = public_ips[idx-1] if idx-1 < len(public_ips) else "N/A"
                                        f.write(f"  {idx}. {inst_id} ({public_ip})\n")
                                    f.write(f"\nConnection Info:\n")
                                    f.write(f"  Username: Administrator\n")
                                    f.write(f"  Password: {password}\n")
                                console.print(f"\n[{self.colors['info']}]Password also saved to: {password_file}[/]")

                                # Regenerate DCV files with password
                                console.print(f"\n[dim]Updating DCV files with password...[/dim]")
                                for idx, (instance_id, public_ip) in enumerate(zip(instance_ids, public_ips)):
                                    instance_name = f"ll-win-client-{idx + 1}"
                                    try:
                                        self.generate_dcv_file(public_ip, instance_name, password=password)
                                    except Exception as e:
                                        logger.warning(f"Failed to regenerate DCV file with password: {e}")
                            else:
                                console.print(f"\n[{self.colors['warning']}]Could not retrieve password at this time.[/]")
                                console.print(f"You can retrieve it later using AWS CLI:")
                                console.print(f"  aws ec2 get-password-data --instance-id {instance_ids[0]} \\")
                                console.print(f"    --priv-launch-key {key_path} --region {self.config.get('region', 'us-east-1')}")
                        else:
                            console.print(f"[{self.colors['error']}]Key file not found: {key_path}[/]")
                else:
                    # No SSH key - use automated SSM password setting
                    console.print(f"\n[bold yellow]🔐 Setting Windows Administrator passwords automatically...[/bold yellow]")
                    console.print(f"[dim]Using AWS Systems Manager to set one password for all instances[/dim]")
                    console.print()

                    # Wait for SSM agents to be ready
                    ssm_ready = self.wait_for_ssm_ready(instance_ids, timeout_minutes=15)
                    console.print()

                    # Check if any instances are ready
                    ready_instances = [inst_id for inst_id, ready in ssm_ready.items() if ready]
                    not_ready_instances = [inst_id for inst_id, ready in ssm_ready.items() if not ready]

                    if not ready_instances:
                        console.print(f"[{self.colors['warning']}]⚠ No instances are ready for password setting yet[/]")
                        console.print(f"[dim]SSM agents are still initializing. Please try again in a few minutes.[/dim]")
                    else:
                        # Generate one password for all instances
                        shared_password = self.generate_secure_password()
                        console.print(f"[bold]Generated password: [green]{shared_password}[/green][/bold]")
                        console.print(f"[dim]Setting this password on ready instances...[/dim]")
                        console.print()

                        passwords = {}
                        success_count = 0

                        # Set password on ready instances
                        for idx, inst_id in enumerate(instance_ids, 1):
                            if inst_id in ready_instances:
                                console.print(f"Instance {idx} ({inst_id}):")
                                password = self.set_windows_password_via_ssm(inst_id, shared_password)
                                if password:
                                    passwords[inst_id] = password
                                    success_count += 1
                                else:
                                    console.print(f"[{self.colors['warning']}]⚠ Failed to set password[/]")
                                console.print()
                            else:
                                console.print(f"Instance {idx} ({inst_id}): [{self.colors['warning']}]Skipped - SSM not ready[/]")
                                console.print()

                        if success_count > 0:
                            console.print(f"[{self.colors['success']}]✓ Password set on {success_count}/{len(instance_ids)} instance(s)[/]")

                        # Save password if any were set
                        if passwords:
                            password_file = Path.home() / "Desktop" / "LucidLink-DCV" / "PASSWORDS.txt"
                            with open(password_file, 'w') as f:
                                f.write("Windows Administrator Password\n")
                                f.write("=" * 60 + "\n\n")
                                f.write("IMPORTANT: Keep this file secure!\n\n")
                                f.write(f"ONE PASSWORD FOR ALL INSTANCES:\n")
                                f.write(f"  Password: {shared_password}\n\n")
                                f.write("This password works for:\n")
                                for idx, inst_id in enumerate(instance_ids, 1):
                                    public_ip = public_ips[idx-1] if idx-1 < len(public_ips) else "N/A"
                                    status = "✓ Password set" if inst_id in passwords else "✗ Not set"
                                    f.write(f"  {idx}. {inst_id} ({public_ip}) - {status}\n")
                                f.write("\nConnection Info:\n")
                                f.write("  Username: Administrator\n")
                                f.write(f"  Password: {shared_password}\n")
                                f.write("  (Same password for all instances)\n")

                            console.print(f"[{self.colors['success']}]Password saved to: {password_file}[/]")

                            # Display password
                            console.print()
                            console.print(Panel.fit(
                                f"[bold]Windows Administrator Password[/bold]\n\n"
                                f"[bold green]{shared_password}[/bold green]\n\n"
                                f"[dim]This password works for ALL {len(instance_ids)} instance(s)[/dim]",
                                border_style="green",
                                title="Copy this password"
                            ))

                            # Regenerate DCV files with password
                            console.print(f"\n[dim]Updating DCV files with password...[/dim]")
                            for idx, (instance_id, public_ip) in enumerate(zip(instance_ids, public_ips)):
                                instance_name = f"ll-win-client-{idx + 1}"
                                try:
                                    self.generate_dcv_file(public_ip, instance_name, password=shared_password)
                                except Exception as e:
                                    logger.warning(f"Failed to regenerate DCV file with password: {e}")
                        else:
                            console.print(f"[{self.colors['warning']}]⚠ No passwords were set[/]")
                            console.print(f"[dim]You can use Menu Option 5 to try again later[/dim]")
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
        if not outputs or 'instance_ids' not in outputs:
            console.print(f"[{self.colors['warning']}]No client deployments found.[/]")
            console.print("Deploy infrastructure first using option 3.")
            Prompt.ask("\nPress Enter to continue")
            return

        # Extract client information
        instance_ids = outputs.get('instance_ids', [])
        private_ips = outputs.get('private_ips', [])
        public_ips = outputs.get('public_ips', [])
        filespace_domain = outputs.get('filespace_domain', 'Not configured')
        mount_point = outputs.get('mount_point', 'L:')

        if not instance_ids:
            console.print(f"[{self.colors['warning']}]No client instances found.[/]")
            Prompt.ask("\nPress Enter to continue")
            return

        # Create deployment summary table
        summary_table = Table(title="Deployment Summary", box=box.ROUNDED, border_style="blue")
        summary_table.add_column("Property", style="cyan", no_wrap=True)
        summary_table.add_column("Value", style="white")

        summary_table.add_row("Total Instances", str(len(instance_ids)))
        summary_table.add_row("Filespace Domain", filespace_domain)
        summary_table.add_row("Mount Point", mount_point)
        summary_table.add_row("Region", self.config.get('region', 'unknown'))
        summary_table.add_row("VPC CIDR", self.config.get('vpc_cidr', 'unknown'))

        console.print(summary_table)
        console.print()

        # Create instances table
        instances_table = Table(title="Client Instances", box=box.ROUNDED, border_style="green")
        instances_table.add_column("Index", style="cyan", no_wrap=True)
        instances_table.add_column("Instance ID", style="white")
        instances_table.add_column("Private IP", style="white")
        instances_table.add_column("Public IP", style="white")
        instances_table.add_column("EC2 Status", style="green")
        instances_table.add_column("SSM Status", style="yellow")
        instances_table.add_column("DCV Status", style="magenta")

        # Check instance status if boto3 available
        instance_statuses = {}
        ssm_statuses = {}
        try:
            import boto3
            session_kwargs = {'region_name': self.config.get('region', 'us-east-1')}
            if self.config.get('aws_access_key_id'):
                session_kwargs['aws_access_key_id'] = self.config['aws_access_key_id']
            if self.config.get('aws_secret_access_key'):
                session_kwargs['aws_secret_access_key'] = self.config['aws_secret_access_key']

            ec2 = boto3.client('ec2', **session_kwargs)

            # Get EC2 instance statuses
            if instance_ids:
                ec2_response = ec2.describe_instances(InstanceIds=instance_ids)
                for reservation in ec2_response['Reservations']:
                    for instance in reservation['Instances']:
                        instance_statuses[instance['InstanceId']] = instance['State']['Name']

            # Get SSM agent statuses
            for instance_id in instance_ids:
                ssm_status = self.check_ssm_agent_status(instance_id)
                ssm_statuses[instance_id] = ssm_status
        except:
            # If boto3 not available or API fails, show unknown status
            pass

        for idx, instance_id in enumerate(instance_ids):
            private_ip = private_ips[idx] if idx < len(private_ips) else "N/A"
            public_ip = public_ips[idx] if idx < len(public_ips) else "N/A"

            # Get EC2 status
            status = instance_statuses.get(instance_id, "unknown")
            if status == "running":
                status = "[green]running[/green]"
            elif status == "stopped":
                status = "[yellow]stopped[/yellow]"
            elif status == "terminated":
                status = "[red]terminated[/red]"
            else:
                status = "[dim]unknown[/dim]"

            # Get SSM status
            ssm_status = ssm_statuses.get(instance_id, "Unknown")
            if ssm_status == "Online":
                ssm_status_display = "[green]Online[/green]"
            elif ssm_status == "NotRegistered":
                ssm_status_display = "[yellow]Not Registered[/yellow]"
            elif ssm_status == "ConnectionLost":
                ssm_status_display = "[red]Connection Lost[/red]"
            elif ssm_status == "Inactive":
                ssm_status_display = "[yellow]Inactive[/yellow]"
            else:
                ssm_status_display = "[dim]Unknown[/dim]"

            # Get DCV status
            dcv_status = self.check_dcv_status(public_ip)
            if dcv_status == "Ready":
                dcv_status_display = "[green]Ready[/green]"
            elif dcv_status == "NotReady":
                dcv_status_display = "[yellow]Not Ready[/yellow]"
            else:
                dcv_status_display = "[dim]Unknown[/dim]"

            instances_table.add_row(
                str(idx + 1),
                instance_id,
                private_ip,
                public_ip,
                status,
                ssm_status_display,
                dcv_status_display
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

        # Check if there's anything to destroy
        outputs = self.get_terraform_outputs()
        if not outputs or 'instance_ids' not in outputs:
            console.print(f"[{self.colors['info']}]No client deployments found to destroy.[/]")
            Prompt.ask("\nPress Enter to continue")
            return

        instance_ids = outputs.get('instance_ids', [])
        if not instance_ids:
            console.print(f"[{self.colors['info']}]No client instances to destroy.[/]")
            Prompt.ask("\nPress Enter to continue")
            return

        # Show what will be destroyed
        console.print("[bold]The following resources will be destroyed:[/bold]")
        console.print(f"  • {len(instance_ids)} client instance(s)")
        for idx, instance_id in enumerate(instance_ids, 1):
            console.print(f"    - Instance {idx}: {instance_id}")
        console.print(f"  • VPC and networking components")
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
                "All client instances and VPC have been terminated.",
                border_style="green"
            ))

            # Clear client configuration
            if self.config.get('filespace_domain'):
                console.print()
                if Confirm.ask("Clear stored client configuration?", default=False):
                    # Keep AWS credentials but clear client-specific config
                    preserved_keys = ['aws_access_key_id', 'aws_secret_access_key', 'region']
                    new_config = {k: v for k, v in self.config.items() if k in preserved_keys}
                    self.config = new_config
                    self.save_config(new_config)
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
        """Regenerate DCV connection files on Desktop"""
        console.clear()
        self.show_banner()

        console.print(Panel.fit(
            "[bold]Regenerate Connection Files[/bold]\n"
            "This will create fresh RDP files on your Desktop and set passwords automatically",
            border_style="blue"
        ))
        console.print()

        # Get terraform outputs
        outputs = self.get_terraform_outputs()
        if not outputs or 'instance_ids' not in outputs:
            console.print(f"[{self.colors['warning']}]No client deployments found.[/]")
            console.print("Deploy infrastructure first using option 3.")
            Prompt.ask("\nPress Enter to continue")
            return

        instance_ids = outputs.get('instance_ids', [])
        public_ips = outputs.get('public_ips', [])

        if not instance_ids or not public_ips:
            console.print(f"[{self.colors['warning']}]No instances with public IPs found.[/]")
            Prompt.ask("\nPress Enter to continue")
            return

        # Step 1: Set passwords via SSM
        console.print(f"\n[bold yellow]Step 1: Setting Windows Administrator passwords via SSM...[/bold yellow]")
        console.print(f"[dim]Generating one password for all instances (easier for tradeshow use)[/dim]")
        console.print()

        # Wait for SSM agents to be ready
        ssm_ready = self.wait_for_ssm_ready(instance_ids, timeout_minutes=15)
        console.print()

        # Check if any instances are ready
        ready_instances = [inst_id for inst_id, ready in ssm_ready.items() if ready]
        not_ready_instances = [inst_id for inst_id, ready in ssm_ready.items() if not ready]

        if not ready_instances:
            console.print(f"[{self.colors['warning']}]⚠ No instances are ready for password setting yet[/]")
            console.print(f"[dim]SSM agents are still initializing. Please try again in a few minutes.[/dim]")
            console.print()
            Prompt.ask("Press Enter to continue")
            return

        # Generate one password for all instances
        shared_password = self.generate_secure_password()
        console.print(f"[bold]Generated password: [green]{shared_password}[/green][/bold]")
        console.print(f"[dim]Setting this password on ready instances...[/dim]")
        console.print()

        passwords = {}
        success_count = 0

        # Set password on ready instances
        for idx, instance_id in enumerate(instance_ids, 1):
            if instance_id in ready_instances:
                console.print(f"Instance {idx} ({instance_id}):")
                password = self.set_windows_password_via_ssm(instance_id, shared_password)
                if password:
                    passwords[instance_id] = password
                    success_count += 1
                else:
                    console.print(f"[{self.colors['warning']}]⚠ Failed to set password[/]")
                console.print()
            else:
                console.print(f"Instance {idx} ({instance_id}): [{self.colors['warning']}]Skipped - SSM not ready[/]")
                console.print()

        if success_count > 0:
            console.print(f"[{self.colors['success']}]✓ Password set on {success_count}/{len(instance_ids)} instance(s)[/]")

        if success_count < len(instance_ids):
            console.print()
            console.print(f"[{self.colors['info']}]Note: {len(instance_ids) - success_count} instance(s) not ready[/]")
            console.print(f"[dim]Run this option again later to set passwords on remaining instances[/dim]")

        console.print()

        # Step 2: Generate DCV files
        console.print(f"[bold yellow]Step 2: Generating connection files...[/bold yellow]")
        dcv_files = []

        for idx, (instance_id, public_ip) in enumerate(zip(instance_ids, public_ips)):
            instance_name = f"ll-win-client-{idx + 1}"

            # Generate DCV file with password
            try:
                dcv_file = self.generate_dcv_file(public_ip, instance_name, password=shared_password)
                dcv_files.append(dcv_file)
                console.print(f"  [{self.colors['success']}]✓[/] DCV: {instance_name}.dcv")
            except Exception as e:
                console.print(f"  [{self.colors['warning']}]⚠[/] Failed to generate DCV file for {instance_name}: {e}")

        dcv_location = Path.home() / "Desktop" / "LucidLink-DCV"

        # Step 3: Save passwords to file
        if passwords:
            console.print()
            console.print(f"[bold yellow]Step 3: Saving password to file...[/bold yellow]")
            password_file = dcv_location / "PASSWORDS.txt"
            with open(password_file, 'w') as f:
                f.write("Windows Administrator Password\n")
                f.write("=" * 60 + "\n\n")
                f.write("IMPORTANT: Keep this file secure!\n\n")
                f.write(f"ONE PASSWORD FOR ALL INSTANCES:\n")
                f.write(f"  Password: {shared_password}\n\n")
                f.write("This password works for:\n")
                for idx, (instance_id, public_ip) in enumerate(zip(instance_ids, public_ips), 1):
                    status = "✓ Password set" if instance_id in passwords else "✗ Not set"
                    f.write(f"  {idx}. {instance_id} ({public_ip}) - {status}\n")
                f.write("\nConnection Info:\n")
                f.write("  Username: Administrator\n")
                f.write(f"  Password: {shared_password}\n")
                f.write("  (Same password for all instances)\n")

            console.print(f"  [{self.colors['success']}]✓[/] Password saved to: {password_file}")

            # Display password in terminal
            console.print()
            console.print(Panel.fit(
                f"[bold]Windows Administrator Password[/bold]\n\n"
                f"[bold green]{shared_password}[/bold green]\n\n"
                f"[dim]This password works for ALL {len(instance_ids)} instance(s)[/dim]",
                border_style="green",
                title="Copy this password"
            ))

        console.print()
        console.print(Panel.fit(
            f"[{self.colors['success']}]Setup completed successfully![/]\n\n"
            f"Location: [bold]{dcv_location}[/bold]\n\n"
            f"DCV Files: {len(dcv_files)}\n"
            f"Passwords Set: {len(passwords)}/{len(instance_ids)}",
            border_style="green"
        ))

        console.print()
        console.print(f"[bold]To connect:[/bold]")
        console.print(f"1. Open your Desktop and find the 'LucidLink-DCV' folder")
        console.print(f"2. Double-click the .dcv file for the instance you want to access")
        console.print(f"3. When DCV prompts, enter Username: [bold]Administrator[/bold]")
        console.print(f"4. Password will auto-fill (or see PASSWORDS.txt in LucidLink-DCV folder)")

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

        instance_ids = outputs.get('instance_ids', [])
        if not instance_ids:
            console.print(f"[{self.colors['warning']}]No instances found in deployment.[/]")
            console.print()
            Prompt.ask("Press Enter to continue")
            return

        console.print(f"Found {len(instance_ids)} instance(s):")
        for idx, instance_id in enumerate(instance_ids):
            console.print(f"  {idx + 1}. {instance_id}")
        console.print()

        # Check current status
        import boto3
        region = self.config.get('region', 'us-east-1')
        ec2 = boto3.client('ec2', region_name=region)

        try:
            response = ec2.describe_instances(InstanceIds=instance_ids)
            running_instances = []
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    state = instance['State']['Name']
                    console.print(f"  {instance['InstanceId']}: [{self.colors['info']}]{state}[/]")
                    if state == 'running':
                        running_instances.append(instance['InstanceId'])

            if not running_instances:
                console.print(f"\n[{self.colors['warning']}]No running instances to stop.[/]")
                console.print()
                Prompt.ask("Press Enter to continue")
                return

            console.print(f"\n[{self.colors['warning']}]This will stop {len(running_instances)} running instance(s).[/]")
            console.print(f"[{self.colors['info']}]Stopped instances still incur storage charges but not compute charges.[/]")

            if not Confirm.ask("\nProceed with stopping instances?", default=False):
                console.print(f"[{self.colors['info']}]Operation cancelled.[/]")
                console.print()
                Prompt.ask("Press Enter to continue")
                return

            # Attempt graceful shutdown via SSM first
            console.print(f"\n[bold yellow]Initiating graceful Windows shutdown...[/bold yellow]")

            try:
                ssm = boto3.client('ssm', region_name=region)

                # Send shutdown command to Windows
                console.print(f"[{self.colors['info']}]Sending shutdown command via AWS Systems Manager...[/]")
                ssm.send_command(
                    InstanceIds=running_instances,
                    DocumentName='AWS-RunPowerShellScript',
                    Parameters={
                        'commands': [
                            'shutdown /s /t 30 /c "Graceful shutdown initiated by LucidLink deployment tool"'
                        ]
                    },
                    TimeoutSeconds=60
                )

                console.print(f"[{self.colors['success']}]✓ Shutdown command sent to Windows[/]")
                console.print(f"[dim]Windows will shutdown gracefully in 30 seconds...[/dim]")

                # Wait for instances to stop (Windows shutdown will trigger EC2 stop)
                console.print(f"\n[bold yellow]Waiting for graceful shutdown to complete...[/bold yellow]")
                with console.status("[bold yellow]Monitoring shutdown progress...[/bold yellow]"):
                    waiter = ec2.get_waiter('instance_stopped')
                    try:
                        # Wait up to 5 minutes for graceful shutdown
                        waiter.wait(
                            InstanceIds=running_instances,
                            WaiterConfig={'Delay': 15, 'MaxAttempts': 20}
                        )
                        console.print(f"[{self.colors['success']}]✓ Instances shut down gracefully[/]")
                    except Exception as wait_error:
                        # Graceful shutdown timed out, force stop
                        logger.warning(f"Graceful shutdown timed out, forcing stop: {wait_error}")
                        console.print(f"\n[{self.colors['warning']}]Graceful shutdown timed out, forcing stop...[/]")
                        ec2.stop_instances(InstanceIds=running_instances)
                        waiter.wait(InstanceIds=running_instances)
                        console.print(f"[{self.colors['warning']}]⚠ Instances force-stopped[/]")

            except Exception as ssm_error:
                # SSM command failed, fall back to direct EC2 stop
                logger.warning(f"SSM graceful shutdown failed, using direct stop: {ssm_error}")
                console.print(f"\n[{self.colors['warning']}]Graceful shutdown unavailable, using direct stop...[/]")
                console.print(f"[dim]Reason: {str(ssm_error)}[/dim]")

                ec2.stop_instances(InstanceIds=running_instances)
                with console.status("[bold yellow]Waiting for instances to stop...[/bold yellow]"):
                    waiter = ec2.get_waiter('instance_stopped')
                    waiter.wait(InstanceIds=running_instances)
                console.print(f"[{self.colors['warning']}]⚠ Instances stopped (non-graceful)[/]")

            console.print(f"\n[{self.colors['success']}]✓ Successfully stopped {len(running_instances)} instance(s)[/]")
            console.print(f"\n[{self.colors['info']}]To resume work, use 'Start All Instances' from the main menu.[/]")

        except Exception as e:
            console.print(f"\n[{self.colors['error']}]Error stopping instances: {e}[/]")
            logger.error(f"Error stopping instances: {e}", exc_info=True)

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

        instance_ids = outputs.get('instance_ids', [])
        if not instance_ids:
            console.print(f"[{self.colors['warning']}]No instances found in deployment.[/]")
            console.print()
            Prompt.ask("Press Enter to continue")
            return

        console.print(f"Found {len(instance_ids)} instance(s):")
        for idx, instance_id in enumerate(instance_ids):
            console.print(f"  {idx + 1}. {instance_id}")
        console.print()

        # Check current status
        import boto3
        region = self.config.get('region', 'us-east-1')
        ec2 = boto3.client('ec2', region_name=region)

        try:
            response = ec2.describe_instances(InstanceIds=instance_ids)
            stopped_instances = []
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    state = instance['State']['Name']
                    console.print(f"  {instance['InstanceId']}: [{self.colors['info']}]{state}[/]")
                    if state == 'stopped':
                        stopped_instances.append(instance['InstanceId'])

            if not stopped_instances:
                console.print(f"\n[{self.colors['warning']}]No stopped instances to start.[/]")
                console.print()
                Prompt.ask("Press Enter to continue")
                return

            console.print(f"\n[{self.colors['info']}]This will start {len(stopped_instances)} stopped instance(s).[/]")
            console.print(f"[{self.colors['warning']}]Compute charges will resume once instances are running.[/]")

            if not Confirm.ask("\nProceed with starting instances?", default=True):
                console.print(f"[{self.colors['info']}]Operation cancelled.[/]")
                console.print()
                Prompt.ask("Press Enter to continue")
                return

            # Start instances
            console.print(f"\n[bold green]Starting instances...[/bold green]")
            ec2.start_instances(InstanceIds=stopped_instances)

            # Wait for running state
            with console.status("[bold green]Waiting for instances to start...[/bold green]"):
                waiter = ec2.get_waiter('instance_running')
                waiter.wait(InstanceIds=stopped_instances)

            console.print(f"\n[{self.colors['success']}]✓ Successfully started {len(stopped_instances)} instance(s)[/]")

            # Get NEW public IPs after start (they changed!)
            console.print(f"\n[{self.colors['info']}]Updating DCV connection files with new IP addresses...[/]")
            response = ec2.describe_instances(InstanceIds=instance_ids)
            public_ips = []
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    public_ip = instance.get('PublicIpAddress', 'N/A')
                    public_ips.append(public_ip)

            # Try to read existing password from PASSWORDS.txt
            password = None
            dcv_location = Path.home() / "Desktop" / "LucidLink-DCV"
            password_file = dcv_location / "PASSWORDS.txt"
            if password_file.exists():
                try:
                    with open(password_file, 'r') as f:
                        for line in f:
                            if line.strip().startswith("Password:"):
                                password = line.split(":", 1)[1].strip()
                                break
                except Exception as e:
                    logger.warning(f"Could not read password from file: {e}")

            # Regenerate DCV files with new IPs
            for idx, (instance_id, public_ip) in enumerate(zip(instance_ids, public_ips)):
                instance_name = f"ll-win-client-{idx + 1}"
                try:
                    self.generate_dcv_file(public_ip, instance_name, password=password)
                    console.print(f"  [{self.colors['success']}]✓[/] Updated: {instance_name}.dcv ({public_ip})")
                except Exception as e:
                    logger.warning(f"Failed to regenerate DCV file: {e}")

            console.print(f"\n[{self.colors['success']}]✓ DCV connection files updated with new IP addresses[/]")
            console.print(f"[{self.colors['info']}]Connection files: ~/Desktop/LucidLink-DCV/[/]")
            console.print(f"[dim]Note: Public IPs change when instances are stopped/started[/dim]")

        except Exception as e:
            console.print(f"\n[{self.colors['error']}]Error starting instances: {e}[/]")
            logger.error(f"Error starting instances: {e}", exc_info=True)

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
            console.print("9. Exit")
            console.print()

            choice = Prompt.ask(
                "Select an option",
                choices=['1', '2', '3', '4', '5', '6', '7', '8', '9'],
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
            elif choice == '9':
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
        description='LucidLink Windows Client AWS Setup - Deploy Windows LucidLink clients to AWS',
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

    console.print("\n[bold cyan]LucidLink Windows Client AWS Setup[/bold cyan]")
    console.print(f"Log file: {log_file}\n")

    # Check dependencies
    missing_deps = []
    for cmd in ['terraform', 'aws']:
        if not shutil.which(cmd):
            missing_deps.append(cmd)

    if missing_deps:
        console.print(f"[bold red]Missing required dependencies:[/bold red] {', '.join(missing_deps)}")
        console.print("\nPlease install:")
        if 'terraform' in missing_deps:
            console.print("  • Terraform: https://www.terraform.io/downloads")
        if 'aws' in missing_deps:
            console.print("  • AWS CLI: https://aws.amazon.com/cli/")
        sys.exit(1)

    app = LLWinClientAWSSetup(auto_approve=args.auto_approve)
    app.run()


if __name__ == "__main__":
    main()
