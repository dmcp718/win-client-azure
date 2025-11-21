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

output "vm_size" {
  value       = var.vm_size
  description = "VM size/SKU"
}

output "data_disk_size_gb" {
  value       = var.data_disk_size_gb
  description = "Data disk size in GB"
}

output "data_disk_iops" {
  value       = var.data_disk_iops
  description = "Data disk IOPS"
}

output "data_disk_throughput_mbps" {
  value       = var.data_disk_throughput_mbps
  description = "Data disk throughput in MB/s"
}
