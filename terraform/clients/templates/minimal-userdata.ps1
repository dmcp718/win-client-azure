<powershell>
# Minimal EC2 userdata - Downloads full setup script from S3 (no 16KB limit)
$LogFile = "C:\lucidlink-bootstrap.log"

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp - $Message" | Out-File -FilePath $LogFile -Append
    Write-Host $Message
}

try {
    Write-Log "========================================="
    Write-Log "LucidLink Windows Client - Bootstrap"
    Write-Log "========================================="

    # Install AWS CLI if not present
    $awsCliPath = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
    if (-not (Test-Path $awsCliPath)) {
        Write-Log "Installing AWS CLI v2..."
        $awsInstallerUrl = "https://awscli.amazonaws.com/AWSCLIV2.msi"
        $awsInstallerPath = "$env:TEMP\AWSCLIV2.msi"
        Write-Log "Downloading AWS CLI installer..."
        Invoke-WebRequest -Uri $awsInstallerUrl -OutFile $awsInstallerPath -UseBasicParsing
        Write-Log "Installing AWS CLI..."
        Start-Process msiexec.exe -ArgumentList "/i `"$awsInstallerPath`" /qn /norestart" -Wait -NoNewWindow
        Remove-Item -Path $awsInstallerPath -Force
        Write-Log "AWS CLI installed successfully"
    } else {
        Write-Log "AWS CLI already installed"
    }

    Write-Log "Downloading full setup script from S3..."

    # Download the full setup script from S3
    $BucketName = "${bucket_name}"
    $ScriptKey = "windows-setup.ps1"
    $LocalScript = "C:\windows-setup.ps1"

    # Use AWS CLI to download the script
    $AwsCommand = "`"$awsCliPath`" s3 cp s3://$BucketName/$ScriptKey $LocalScript --region ${aws_region}"
    Write-Log "Running: $AwsCommand"

    $process = Start-Process -FilePath $awsCliPath -ArgumentList "s3","cp","s3://$BucketName/$ScriptKey",$LocalScript,"--region","${aws_region}" -Wait -PassThru -NoNewWindow

    if ($process.ExitCode -ne 0) {
        throw "Failed to download setup script from S3. Exit code: $($process.ExitCode)"
    }

    Write-Log "Successfully downloaded setup script"
    Write-Log "Script size: $((Get-Item $LocalScript).Length) bytes"
    Write-Log "========================================="
    Write-Log "Executing full setup script..."
    Write-Log "========================================="

    # Execute the downloaded script
    PowerShell -ExecutionPolicy Bypass -File $LocalScript

    Write-Log "========================================="
    Write-Log "Setup script execution completed"
    Write-Log "========================================="

} catch {
    Write-Log "ERROR: Bootstrap failed - $_"
    Write-Log "Stack trace: $($_.ScriptStackTrace)"
    exit 1
}
</powershell>
