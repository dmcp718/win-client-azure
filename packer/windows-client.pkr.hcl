# =============================================================================
# Packer Template for LucidLink Windows Client Azure Image
# =============================================================================
# Creates a pre-configured managed image with all software installed
# for faster deployments
#
# Usage:
#   packer init .
#   packer validate .
#   packer build .
#
# Or via the TUI:
#   python3 ll-win-client.py -> Build Custom Image (Packer)
# =============================================================================

packer {
  required_plugins {
    azure = {
      source  = "github.com/hashicorp/azure"
      version = "~> 2"
    }
  }
}

# =============================================================================
# Variables
# =============================================================================

variable "subscription_id" {
  type        = string
  default     = ""
  description = "Azure subscription ID (uses az cli default if empty)"
}

variable "location" {
  type        = string
  default     = "eastus"
  description = "Azure region to build the image in"
}

variable "resource_group_name" {
  type        = string
  default     = "ll-win-client-packer-rg"
  description = "Resource group for the managed image"
}

variable "vm_size" {
  type        = string
  default     = "Standard_D4s_v3"
  description = "VM size for the build (does not need GPU)"
}

variable "image_prefix" {
  type        = string
  default     = "ll-win-client"
  description = "Prefix for the managed image name"
}

variable "install_vlc" {
  type        = bool
  default     = true
  description = "Install VLC Media Player"
}

variable "install_vcredist" {
  type        = bool
  default     = true
  description = "Install Visual C++ Redistributables"
}

# =============================================================================
# Source Image - Windows 11 Pro
# =============================================================================

source "azure-arm" "windows" {
  use_azure_cli_auth = true

  subscription_id = var.subscription_id != "" ? var.subscription_id : null

  # Build VM configuration
  location = var.location
  vm_size  = var.vm_size

  # Source image: Windows 11 Pro 23H2
  image_publisher = "MicrosoftWindowsDesktop"
  image_offer     = "windows-11"
  image_sku       = "win11-23h2-pro"

  # Output: Managed image
  managed_image_name                = "${var.image_prefix}-${formatdate("YYYYMMDDhhmmss", timestamp())}"
  managed_image_resource_group_name = var.resource_group_name

  # Tags
  azure_tags = {
    Project   = "ll-win-client"
    ManagedBy = "Packer"
    BuildDate = timestamp()
  }

  # OS disk
  os_type         = "Windows"
  os_disk_size_gb = 128

  # WinRM Configuration for Windows
  communicator   = "winrm"
  winrm_username = "packer"
  winrm_use_ssl  = true
  winrm_insecure = true
  winrm_timeout  = "45m"

  # Give Windows extra time to boot
  pause_before_connecting = "2m"
}

# =============================================================================
# Build Steps
# =============================================================================

build {
  sources = ["source.azure-arm.windows"]

  # Step 1: Wait for Windows to be ready
  provisioner "powershell" {
    inline = [
      "Write-Host 'Waiting for Windows to be fully ready...'",
      "Start-Sleep -Seconds 30"
    ]
  }

  # Step 2: Install all software
  provisioner "powershell" {
    script = "${path.root}/scripts/install-software.ps1"
    environment_vars = [
      "INSTALL_VLC=${var.install_vlc}",
      "INSTALL_VCREDIST=${var.install_vcredist}"
    ]
  }

  # Step 3: Enable Windows dark mode system-wide
  provisioner "powershell" {
    inline = [
      "Write-Host '=== Enabling Windows dark mode ==='",
      "",
      "# Set dark mode for current user (packer build user)",
      "$themePath = 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize'",
      "if (-not (Test-Path $themePath)) { New-Item -Path $themePath -Force | Out-Null }",
      "Set-ItemProperty -Path $themePath -Name 'AppsUseLightTheme' -Value 0 -Type DWord",
      "Set-ItemProperty -Path $themePath -Name 'SystemUsesLightTheme' -Value 0 -Type DWord",
      "",
      "# Set dark mode for Default user profile (new users inherit this)",
      "reg load HKU\\DefaultUser C:\\Users\\Default\\NTUSER.DAT",
      "reg add 'HKU\\DefaultUser\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' /v AppsUseLightTheme /t REG_DWORD /d 0 /f",
      "reg add 'HKU\\DefaultUser\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' /v SystemUsesLightTheme /t REG_DWORD /d 0 /f",
      "reg unload HKU\\DefaultUser",
      "",
      "Write-Host 'Dark mode enabled for current user and Default user profile'"
    ]
  }

  # Step 4: Cleanup and prepare for image
  provisioner "powershell" {
    inline = [
      "Write-Host '=== Cleaning up for image creation ==='",
      "",
      "# Clear temp files",
      "Remove-Item -Path 'C:\\Temp\\*' -Recurse -Force -ErrorAction SilentlyContinue",
      "Remove-Item -Path \"$env:TEMP\\*\" -Recurse -Force -ErrorAction SilentlyContinue",
      "",
      "# Clear Windows Update cache",
      "Stop-Service -Name wuauserv -Force -ErrorAction SilentlyContinue",
      "Remove-Item -Path 'C:\\Windows\\SoftwareDistribution\\Download\\*' -Recurse -Force -ErrorAction SilentlyContinue",
      "Start-Service -Name wuauserv -ErrorAction SilentlyContinue",
      "",
      "# Clear event logs",
      "wevtutil cl Application",
      "wevtutil cl Security",
      "wevtutil cl System",
      "",
      "Write-Host '=== Cleanup complete ==='"
    ]
  }

  # Step 5: Sysprep for Azure (required for managed images)
  provisioner "powershell" {
    inline = [
      "Write-Host '=== Running Sysprep ==='",
      "",
      "# Use Azure's built-in sysprep path",
      "& $env:SystemRoot\\System32\\Sysprep\\Sysprep.exe /oobe /generalize /quiet /quit /mode:vm",
      "",
      "# Wait for sysprep to complete",
      "while ($true) {",
      "    $imageState = Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Setup\\State' -Name 'ImageState' -ErrorAction SilentlyContinue",
      "    if ($imageState.ImageState -ne 'IMAGE_STATE_GENERALIZE_RESEAL_TO_OOBE') {",
      "        Write-Host \"Waiting for sysprep... Current state: $($imageState.ImageState)\"",
      "        Start-Sleep -Seconds 10",
      "    } else {",
      "        Write-Host 'Sysprep complete'",
      "        break",
      "    }",
      "}"
    ]
  }

  # Write manifest for TUI discovery
  post-processor "manifest" {
    output     = "${path.root}/manifest.json"
    strip_path = true
  }
}
