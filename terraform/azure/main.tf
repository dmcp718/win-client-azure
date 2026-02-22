locals {
  common_tags = {
    Project     = "ll-win-client"
    ManagedBy   = "Terraform"
    Environment = "production"
  }
}

# Data source for current Azure client config
# data "azurerm_client_config" "current" {}

# Resource Group
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.common_tags
}

# Virtual Network
resource "azurerm_virtual_network" "main" {
  name                = "ll-win-client-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

# Subnet
resource "azurerm_subnet" "main" {
  name                 = "ll-win-client-subnet"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.1.0/24"]
}

# Network Security Group
resource "azurerm_network_security_group" "main" {
  name                = "ll-win-client-nsg"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  security_rule {
    name                       = "RDP"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3389"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  tags = local.common_tags
}

# Public IP addresses
resource "azurerm_public_ip" "main" {
  count               = var.instance_count
  name                = "ll-win-client-pip-${count.index + 1}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.common_tags
}

# Network Interfaces
resource "azurerm_network_interface" "main" {
  count                         = var.instance_count
  name                          = "ll-win-client-nic-${count.index + 1}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  accelerated_networking_enabled = true  # Enable for up to 30 Gbps throughput

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.main.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.main[count.index].id
  }

  tags = local.common_tags
}

# Associate NSG with Network Interfaces
resource "azurerm_network_interface_security_group_association" "main" {
  count                     = var.instance_count
  network_interface_id      = azurerm_network_interface.main[count.index].id
  network_security_group_id = azurerm_network_security_group.main.id
}

# User Assigned Identity for VMs (currently unused, but keeping for future use)
resource "azurerm_user_assigned_identity" "vm_identity" {
  name                = "ll-win-client-identity"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

# Key Vault removed - caused slow destroy times (9+ minutes)
# Password is in terraform.tfvars (sensitive), Key Vault not needed
# If needed in future, uncomment and add back purge_soft_delete_on_destroy

# Windows 11 Virtual Machines
resource "azurerm_windows_virtual_machine" "main" {
  count               = var.instance_count
  name                = "ll-win-${count.index + 1}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  size                = var.vm_size
  admin_username      = var.admin_username
  admin_password      = var.admin_password
  # zone removed - northcentralus doesn't support availability zones

  network_interface_ids = [
    azurerm_network_interface.main[count.index].id,
  ]

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm_identity.id]
  }

  os_disk {
    name                 = "ll-win-${count.index + 1}-osdisk"
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = var.os_disk_size_gb
  }

  # Use custom Packer image if specified, otherwise use marketplace image
  source_image_id = var.custom_image_id != "" ? var.custom_image_id : null

  dynamic "source_image_reference" {
    for_each = var.custom_image_id == "" ? [1] : []
    content {
      publisher = "MicrosoftWindowsDesktop"
      offer     = "windows-11"
      sku       = "win11-23h2-pro"
      version   = "latest"
    }
  }

  tags = local.common_tags
}

# Custom Script Extension to install LucidLink and BGInfo
resource "azurerm_virtual_machine_extension" "lucidlink_install" {
  count                = var.instance_count
  name                 = "install-lucidlink"
  virtual_machine_id   = azurerm_windows_virtual_machine.main[count.index].id
  publisher            = "Microsoft.Compute"
  type                 = "CustomScriptExtension"
  type_handler_version = "1.10"

  protected_settings = jsonencode({
    commandToExecute = "powershell -ExecutionPolicy Bypass -Command \"Write-Host 'Disabling Windows OOBE privacy prompts...'; New-Item -Path 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\OOBE' -Force | Out-Null; Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\OOBE' -Name 'DisablePrivacyExperience' -Value 1 -Type DWord; Write-Host 'OOBE privacy prompts disabled'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $msiPath = (New-Item -Path 'C:\\Windows\\Temp\\lucid_update\\lucidinstaller.msi' -Force).FullName; Start-BitsTransfer -Description ' ' -Source '${var.lucidlink_installer_url}' -Destination $msiPath; $size = (Get-Item $msiPath).Length; Write-Host ('Downloaded file size: ' + $size + ' bytes'); if ($size -lt 1000000) { Write-Host 'WARNING: File too small - likely not the MSI. Check URL.' }; msiexec.exe /i $msiPath /quiet /norestart /l*v C:\\Windows\\Temp\\lucidlink_install.log; Start-Sleep -Seconds 30; $lucid = 'C:\\Program Files\\LucidLink\\bin\\lucid.exe'; $lucidAlt = 'C:\\Program Files\\LucidLink\\lucid.exe'; if ((Test-Path $lucid) -or (Test-Path $lucidAlt)) { Write-Host 'LucidLink installed successfully' } else { Write-Host 'LucidLink not installed - check C:\\Windows\\Temp\\lucidlink_install.log for errors' }; $bgInfoUrl = 'https://live.sysinternals.com/Bginfo.exe'; $bgInfoPath = 'C:\\Windows\\System32\\bginfo.exe'; Invoke-WebRequest -Uri $bgInfoUrl -OutFile $bgInfoPath; New-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run' -Name 'BGInfo' -Value 'C:\\Windows\\System32\\bginfo.exe /timer:0 /silent /nolicprompt' -Force; Start-Process -FilePath $bgInfoPath -ArgumentList '/timer:0', '/silent', '/nolicprompt' -NoNewWindow; Write-Host 'BGInfo installed and configured'\""
  })

  tags       = local.common_tags
  depends_on = [azurerm_virtual_machine_data_disk_attachment.data]
}

# NVIDIA GPU Driver Extension
resource "azurerm_virtual_machine_extension" "nvidia_gpu" {
  count                      = var.instance_count
  name                       = "NvidiaGpuDriverWindows"
  virtual_machine_id         = azurerm_windows_virtual_machine.main[count.index].id
  publisher                  = "Microsoft.HpcCompute"
  type                       = "NvidiaGpuDriverWindows"
  type_handler_version       = "1.6"
  auto_upgrade_minor_version = true

  tags       = local.common_tags
  depends_on = [azurerm_virtual_machine_extension.lucidlink_install]
}

# Managed Data Disk for Media/Projects (Premium SSD)
resource "azurerm_managed_disk" "data" {
  count                = var.instance_count
  name                 = "ll-win-${count.index + 1}-datadisk"
  location             = azurerm_resource_group.main.location
  resource_group_name  = azurerm_resource_group.main.name
  storage_account_type = "Premium_LRS"  # Changed from PremiumV2_LRS - northcentralus doesn't support zones
  create_option        = "Empty"
  disk_size_gb         = var.data_disk_size_gb
  # zone removed - northcentralus doesn't support availability zones

  # Premium SSD v1 - no custom IOPS/throughput settings

  tags = merge(local.common_tags, {
    Purpose = "Media and Project Storage"
  })
}

# Attach Data Disk to VM
resource "azurerm_virtual_machine_data_disk_attachment" "data" {
  count              = var.instance_count
  managed_disk_id    = azurerm_managed_disk.data[count.index].id
  virtual_machine_id = azurerm_windows_virtual_machine.main[count.index].id
  lun                = 0
  caching            = "ReadOnly"  # Premium SSD v1 supports caching
}
