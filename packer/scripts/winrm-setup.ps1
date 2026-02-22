<powershell>
# =============================================================================
# WinRM Setup Script for Packer (Azure)
# =============================================================================
# This script enables WinRM for Packer provisioning on Azure VMs
# Azure Packer builder injects this automatically, but we include it
# for explicit control over WinRM configuration
# =============================================================================

# Set execution policy
Set-ExecutionPolicy Unrestricted -Scope LocalMachine -Force -ErrorAction SilentlyContinue

# Create log file
$logFile = "C:\winrm-setup.log"
function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp - $Message" | Out-File -FilePath $logFile -Append
    Write-Host $Message
}

Write-Log "Starting WinRM setup for Packer..."

# Enable WinRM
Write-Log "Enabling WinRM service..."
Set-Service -Name WinRM -StartupType Automatic
Start-Service WinRM

# Configure WinRM for HTTPS
Write-Log "Configuring WinRM for HTTPS..."

# Create self-signed certificate
$cert = New-SelfSignedCertificate -DnsName $env:COMPUTERNAME -CertStoreLocation Cert:\LocalMachine\My
Write-Log "Created self-signed certificate: $($cert.Thumbprint)"

# Create HTTPS listener
$selector = @{
    Address = "*"
    Transport = "HTTPS"
}
$valueset = @{
    CertificateThumbprint = $cert.Thumbprint
}

# Remove existing HTTPS listener if present
Remove-WSManInstance -ResourceURI winrm/config/Listener -SelectorSet $selector -ErrorAction SilentlyContinue

# Create new HTTPS listener
New-WSManInstance -ResourceURI winrm/config/Listener -SelectorSet $selector -ValueSet $valueset
Write-Log "Created HTTPS WinRM listener"

# Configure WinRM settings
Write-Log "Configuring WinRM settings..."
winrm set winrm/config '@{MaxTimeoutms="1800000"}'
winrm set winrm/config/service '@{AllowUnencrypted="false"}'
winrm set winrm/config/service/auth '@{Basic="true"}'
winrm set winrm/config/client/auth '@{Basic="true"}'

# Set firewall rules
Write-Log "Configuring firewall..."
netsh advfirewall firewall add rule name="WinRM HTTPS" protocol=TCP dir=in localport=5986 action=allow

# Verify WinRM is running
$winrmService = Get-Service WinRM
Write-Log "WinRM service status: $($winrmService.Status)"

Write-Log "WinRM setup complete!"
</powershell>
