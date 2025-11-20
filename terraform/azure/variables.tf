variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "eastus2"
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
  default     = "ll-win-client-rg"
}

variable "vm_size" {
  description = "Size of the VM"
  type        = string
  default     = "Standard_B4ms"
}

variable "instance_count" {
  description = "Number of VM instances to create"
  type        = number
  default     = 1
}

variable "admin_username" {
  description = "Admin username for the VM"
  type        = string
  default     = "azureuser"
}

variable "admin_password" {
  description = "Admin password for the VM"
  type        = string
  sensitive   = true
}

variable "filespace_domain" {
  description = "LucidLink filespace domain"
  type        = string
}

variable "filespace_user" {
  description = "LucidLink filespace username"
  type        = string
}

variable "filespace_password" {
  description = "LucidLink filespace password"
  type        = string
  sensitive   = true
}

variable "mount_point" {
  description = "Mount point for LucidLink filespace"
  type        = string
  default     = "L:"
}

variable "lucidlink_installer_url" {
  description = "URL to download LucidLink installer"
  type        = string
  default     = "https://www.lucidlink.com/download/new-ll-latest/win/stable/"
}
