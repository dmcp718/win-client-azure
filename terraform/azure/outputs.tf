output "resource_group_name" {
  value       = azurerm_resource_group.main.name
  description = "Name of the resource group"
}

output "vm_names" {
  value       = azurerm_windows_virtual_machine.main[*].name
  description = "Names of the Windows VMs"
}

output "public_ips" {
  value       = azurerm_public_ip.main[*].ip_address
  description = "Public IP addresses of the VMs"
}

output "key_vault_name" {
  value       = azurerm_key_vault.main.name
  description = "Name of the Key Vault"
}

output "admin_username" {
  value       = var.admin_username
  description = "Admin username for RDP access"
}

output "filespace_domain" {
  value       = var.filespace_domain
  description = "LucidLink filespace domain"
}

output "mount_point" {
  value       = var.mount_point
  description = "Mount point for LucidLink filespace"
}
