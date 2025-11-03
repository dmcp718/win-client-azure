<powershell>
# ==============================================================================
# LucidLink Windows Client Initialization Script
# ==============================================================================
# This PowerShell script configures Windows Server instances as LucidLink clients
#
# Variables provided by Terraform:
# - filespace_domain, filespace_user, filespace_password
# - mount_point, aws_region, installer_url, secret_arn

# Set error action preference
$ErrorActionPreference = "Continue"

# Logging function
function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] $Message"
    Write-Host $logMessage
    Add-Content -Path "C:\lucidlink-init.log" -Value $logMessage
}

Write-Log "==================================================================="
Write-Log "Starting LucidLink Client Initialization for Windows Server"
Write-Log "==================================================================="

# Get instance metadata
try {
    $instanceId = Invoke-RestMethod -Uri http://169.254.169.254/latest/meta-data/instance-id -TimeoutSec 5
    $instanceType = Invoke-RestMethod -Uri http://169.254.169.254/latest/meta-data/instance-type -TimeoutSec 5
    $availabilityZone = Invoke-RestMethod -Uri http://169.254.169.254/latest/meta-data/placement/availability-zone -TimeoutSec 5

    Write-Log "Instance ID: $instanceId"
    Write-Log "Instance Type: $instanceType"
    Write-Log "Availability Zone: $availabilityZone"
} catch {
    Write-Log "Warning: Could not retrieve instance metadata: $_"
}

# ==============================================================================
# Install AWS CLI (if not already installed)
# ==============================================================================
Write-Log "Checking for AWS CLI..."
$awsCliPath = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"

if (-not (Test-Path $awsCliPath)) {
    Write-Log "Installing AWS CLI v2..."
    try {
        $awsInstallerUrl = "https://awscli.amazonaws.com/AWSCLIV2.msi"
        $awsInstallerPath = "$env:TEMP\AWSCLIV2.msi"

        Write-Log "Downloading AWS CLI installer..."
        Invoke-WebRequest -Uri $awsInstallerUrl -OutFile $awsInstallerPath -UseBasicParsing

        Write-Log "Installing AWS CLI..."
        Start-Process msiexec.exe -ArgumentList "/i `"$awsInstallerPath`" /qn /norestart" -Wait -NoNewWindow

        Remove-Item -Path $awsInstallerPath -Force
        Write-Log "AWS CLI installed successfully"
    } catch {
        Write-Log "ERROR: Failed to install AWS CLI: $_"
    }
} else {
    Write-Log "AWS CLI already installed"
}

# Add AWS CLI to PATH for this session
$env:Path += ";C:\Program Files\Amazon\AWSCLIV2"

# ==============================================================================
# Install Amazon DCV Server (PRIORITY: Install first for remote access)
# ==============================================================================
Write-Log "Installing Amazon DCV Server..."
try {
    # VC++ Redistributable 2022
    $vc="$env:TEMP\vc.exe"
    iwr -Uri "https://aka.ms/vs/17/release/vc_redist.x64.exe" -OutFile $vc -UseBasicParsing
    Start-Process $vc -Args "/install","/quiet","/norestart" -Wait -NoNewWindow
    rm $vc -Force

    # DCV Server
    $dcv="$env:TEMP\dcv.msi"
    iwr -Uri "https://d1uj6qtbmh3dt5.cloudfront.net/2025.0/Servers/nice-dcv-server-x64-Release-2025.0-20103.msi" -OutFile $dcv -UseBasicParsing
    Start-Process msiexec -Args "/i `"$dcv`" /quiet /norestart /l*v C:\dcv.log" -Wait -NoNewWindow
    rm $dcv -Force

    # Config (use proper UTF-8 encoding without BOM)
    $d="C:\Program Files\NICE\DCV\Server\conf"
    mkdir $d -Force|Out-Null

    # Create dcv.conf with UTF-8 encoding (disable auto-create so we can set owner manually)
    $dcvConf = "[session-management]`r`ncreate-session=false`r`n[connectivity]`r`nenable-quic-frontend=true`r`n[security]`r`nauthentication=system`r`n"
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText("$d\dcv.conf", $dcvConf, $utf8NoBom)

    # Create default.perm with UTF-8 encoding (allow any authenticated user to connect)
    $permConf = "[permissions]`r`n%any% allow builtin`r`n"
    [System.IO.File]::WriteAllText("$d\default.perm", $permConf, $utf8NoBom)

    # Firewall & Service
    New-NetFirewallRule -DisplayName "DCV" -Direction Inbound -Protocol TCP -LocalPort 8443 -Action Allow -EA SilentlyContinue
    sleep 5
    Start-Service "DCV Server" -EA SilentlyContinue
    Set-Service "DCV Server" -StartupType Automatic -EA SilentlyContinue

    # Wait for service to fully start
    sleep 10

    # Create console session explicitly with Administrator as owner
    $dcvExe = "C:\Program Files\NICE\DCV\Server\bin\dcv.exe"
    if (Test-Path $dcvExe) {
        Write-Log "Creating DCV console session..."
        & $dcvExe create-session --type=console --owner Administrator --storage-root C:\DCV console
        Write-Log "DCV console session created with owner: Administrator"
    }

    Write-Log "DCV installed. Access on port 8443"
} catch {
    Write-Log "DCV install failed: $_"
}

# ==============================================================================
# Download and Install LucidLink
# ==============================================================================
Write-Log "Downloading LucidLink installer..."
$lucidlinkInstaller = "$env:TEMP\LucidLink-Setup.msi"
$installerUrl = "${installer_url}"

try {
    Write-Log "Installer URL: $installerUrl"

    # Use BITS transfer which handles redirects reliably
    Start-BitsTransfer -Source $installerUrl -Destination $lucidlinkInstaller

    $fileSize = (Get-Item $lucidlinkInstaller).Length
    Write-Log "Downloaded: $([math]::Round($fileSize/1MB, 2)) MB"

} catch {
    Write-Log "ERROR: Failed to download LucidLink: $_"
    Write-Log "Continuing with DCV installation..."
    $lucidlinkInstaller = $null
}

# Verify installer was downloaded
if (-not $lucidlinkInstaller -or -not (Test-Path $lucidlinkInstaller)) {
    Write-Log "WARNING: LucidLink installer not available, skipping LucidLink setup"
    $lucidlinkInstaller = $null
}

if ($lucidlinkInstaller -and (Test-Path $lucidlinkInstaller)) {
    Write-Log "Installing LucidLink MSI package..."
    $installLog = "C:\lucidlink-install.log"
    try {
        $msiArgs = @("/i","`"$lucidlinkInstaller`"","/quiet","/norestart","/log","`"$installLog`"")
        $process = Start-Process msiexec -Args $msiArgs -Wait -NoNewWindow -PassThru

        if ($process.ExitCode -eq 0 -or $process.ExitCode -eq 3010) {
            Write-Log "LucidLink installed successfully"
        } else {
            Write-Log "WARNING: LucidLink install failed (code: $($process.ExitCode))"
        }
    } catch {
        Write-Log "WARNING: LucidLink install error: $_"
    }
    Remove-Item $lucidlinkInstaller -Force -EA SilentlyContinue
} else {
    Write-Log "Skipping LucidLink installation"
}

# ==============================================================================
# Configure LucidLink as Windows Service (FIXED VERSION)
# ==============================================================================
$lucidPath = "C:\Program Files\LucidLink\bin\lucid.exe"

if (Test-Path $lucidPath) {
    Write-Log "Configuring LucidLink as Windows Service..."

    try {
        # Step 1: Install LucidLink service
        Write-Log "Installing LucidLink service..."
        & $lucidPath service --install
        Start-Sleep -Seconds 3

        # Step 2: Start the service
        Write-Log "Starting LucidLink service..."
        & $lucidPath service --start
        Start-Sleep -Seconds 5

        # Step 3: Retrieve credentials from Secrets Manager
        Write-Log "Retrieving credentials from Secrets Manager..."
        $secretJson = & "C:\Program Files\Amazon\AWSCLIV2\aws.exe" secretsmanager get-secret-value --secret-id "${secret_arn}" --region "${aws_region}" --query SecretString --output text
        $creds = $secretJson | ConvertFrom-Json

        # Step 4: Link to filespace (config persists across reboots!)
        Write-Log "Linking to filespace: $($creds.domain)"
        & $lucidPath link --fs $creds.domain --user $creds.username --password $creds.password --mount-point "${mount_point}"

        Start-Sleep -Seconds 10

        # Step 5: Verify service status
        Write-Log "Checking LucidLink service status..."
        $serviceStatus = & $lucidPath service --status
        Write-Log "LucidLink service status: $serviceStatus"

        # Step 6: Verify mount point
        if (Test-Path "${mount_point}") {
            Write-Log "SUCCESS: LucidLink mounted to ${mount_point}"
        } else {
            Write-Log "WARNING: Mount point not yet accessible (may need more time)"
        }

        Write-Log "LucidLink service configured successfully"

    } catch {
        Write-Log "ERROR: Failed to configure LucidLink service: $_"
    }
} else {
    Write-Log "WARNING: LucidLink executable not found at $lucidPath - skipping configuration"
}

# ==============================================================================
# Final Status Report
# ==============================================================================
Write-Log "==================================================================="
Write-Log "LucidLink Client Initialization Complete"
Write-Log "==================================================================="
Write-Log "Instance ID: $instanceId"
Write-Log "Filespace: ${filespace_domain}"
Write-Log "Mount Point: ${mount_point}"
Write-Log "Region: ${aws_region}"
Write-Log ""
Write-Log "Helper commands:"
Write-Log "  Check Status: PowerShell -File C:\Scripts\lucidlink-status.ps1"
Write-Log "  View Logs: Get-Content C:\lucidlink-init.log"
Write-Log "==================================================================="

# Test mount point one more time
Start-Sleep -Seconds 5
if (Test-Path "${mount_point}") {
    Write-Log "SUCCESS: Mount point ${mount_point} is accessible"
} else {
    Write-Log "WARNING: Mount point verification failed. Check LucidLink service status."
}

Write-Log "Initialization script completed"
</powershell>
