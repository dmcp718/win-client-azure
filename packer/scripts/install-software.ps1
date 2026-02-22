# =============================================================================
# Software Installation Script for Packer Azure Image Build
# =============================================================================
# Installs all software that should be pre-baked into the managed image
# Environment variables INSTALL_VLC and INSTALL_VCREDIST control optional installs
# =============================================================================

$ErrorActionPreference = "Continue"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host $Message -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Yellow
}

# Create temp directory
New-Item -ItemType Directory -Path "C:\Temp" -Force | Out-Null

# =============================================================================
# Step 1: Install Google Chrome
# =============================================================================
Write-Step "Installing Google Chrome"

$chromeExe = "C:\Program Files\Google\Chrome\Application\chrome.exe"
if (Test-Path $chromeExe) {
    Write-Info "Google Chrome already installed"
} else {
    Write-Info "Downloading Chrome..."
    $chromeUrl = "https://dl.google.com/chrome/install/latest/chrome_installer.exe"
    $chromePath = "C:\Temp\chrome_installer.exe"
    Invoke-WebRequest -Uri $chromeUrl -OutFile $chromePath -TimeoutSec 300 -UseBasicParsing

    Write-Info "Installing Chrome..."
    Start-Process $chromePath -ArgumentList "/silent /install" -Wait -NoNewWindow
    Start-Sleep -Seconds 10

    if (Test-Path $chromeExe) {
        Write-Success "Google Chrome installed successfully"
    } else {
        Write-Host "[WARNING] Chrome installation may have failed" -ForegroundColor Red
    }
}

# =============================================================================
# Step 2: Install Visual C++ Redistributables (if enabled)
# =============================================================================
$installVcredist = $env:INSTALL_VCREDIST
if ($installVcredist -eq "true" -or $installVcredist -eq "True" -or $installVcredist -eq "1") {
    Write-Step "Installing Visual C++ Redistributables"

    # VC++ 2013 x64
    Write-Info "Downloading VC++ 2013 x64..."
    Invoke-WebRequest -Uri "https://aka.ms/highdpimfc2013x64enu" -OutFile "C:\Temp\vcredist_2013_x64.exe" -TimeoutSec 120 -UseBasicParsing
    Write-Info "Installing VC++ 2013 x64..."
    Start-Process "C:\Temp\vcredist_2013_x64.exe" -ArgumentList "/quiet /norestart" -Wait -NoNewWindow
    Write-Success "VC++ 2013 x64 installed"

    # VC++ 2013 x86
    Write-Info "Downloading VC++ 2013 x86..."
    Invoke-WebRequest -Uri "https://aka.ms/highdpimfc2013x86enu" -OutFile "C:\Temp\vcredist_2013_x86.exe" -TimeoutSec 120 -UseBasicParsing
    Write-Info "Installing VC++ 2013 x86..."
    Start-Process "C:\Temp\vcredist_2013_x86.exe" -ArgumentList "/quiet /norestart" -Wait -NoNewWindow
    Write-Success "VC++ 2013 x86 installed"

    # VC++ 2015-2022 x86
    Write-Info "Downloading VC++ 2015-2022 x86..."
    Invoke-WebRequest -Uri "https://aka.ms/vs/17/release/vc_redist.x86.exe" -OutFile "C:\Temp\vcredist_2022_x86.exe" -TimeoutSec 120 -UseBasicParsing
    Write-Info "Installing VC++ 2015-2022 x86..."
    Start-Process "C:\Temp\vcredist_2022_x86.exe" -ArgumentList "/quiet /norestart" -Wait -NoNewWindow
    Write-Success "VC++ 2015-2022 x86 installed"

    # VC++ 2015-2022 x64
    Write-Info "Downloading VC++ 2015-2022 x64..."
    Invoke-WebRequest -Uri "https://aka.ms/vs/17/release/vc_redist.x64.exe" -OutFile "C:\Temp\vcredist_2022_x64.exe" -TimeoutSec 120 -UseBasicParsing
    Write-Info "Installing VC++ 2015-2022 x64..."
    Start-Process "C:\Temp\vcredist_2022_x64.exe" -ArgumentList "/quiet /norestart" -Wait -NoNewWindow
    Write-Success "VC++ 2015-2022 x64 installed"

    Write-Success "All Visual C++ Redistributables installed"
} else {
    Write-Info "Skipping Visual C++ Redistributables (INSTALL_VCREDIST not set)"
}

# =============================================================================
# Step 3: Install VLC Media Player (if enabled)
# =============================================================================
$installVlc = $env:INSTALL_VLC
if ($installVlc -eq "true" -or $installVlc -eq "True" -or $installVlc -eq "1") {
    Write-Step "Installing VLC Media Player"

    $vlcExe = "C:\Program Files\VideoLAN\VLC\vlc.exe"
    if (Test-Path $vlcExe) {
        Write-Info "VLC already installed"
    } else {
        Write-Info "Downloading VLC..."

        # Auto-detect latest VLC exe from official directory listing
        $vlcDirUrl = "https://download.videolan.org/pub/videolan/vlc/last/win64/"
        try {
            $page = Invoke-WebRequest -Uri $vlcDirUrl -UseBasicParsing -TimeoutSec 30
            $exeLink = ($page.Links | Where-Object { $_.href -match "\.exe$" -and $_.href -notmatch "debug|src" } | Select-Object -First 1).href
            if (-not $exeLink) { throw "Could not find VLC exe download link" }
            $downloadUrl = $vlcDirUrl + $exeLink
        } catch {
            Write-Host "[WARNING] Could not auto-detect VLC version, falling back to mirrors" -ForegroundColor Yellow
            $downloadUrl = $null
        }

        # Fallback mirrors if auto-detect fails
        $vlcUrls = @()
        if ($downloadUrl) { $vlcUrls += $downloadUrl }
        $vlcUrls += @(
            "https://mirror.downloadvn.com/videolan/vlc/last/win64/",
            "https://mirrors.ocf.berkeley.edu/videolan-ftp/vlc/last/win64/",
            "https://ftp.osuosl.org/pub/videolan/vlc/last/win64/"
        )

        $vlcPath = "C:\Temp\vlc-installer.exe"
        $downloaded = $false
        foreach ($vlcUrl in $vlcUrls) {
            try {
                Write-Info "Trying: $vlcUrl"
                # If URL is a directory listing, find the exe link
                if ($vlcUrl -match "/$") {
                    $dirPage = Invoke-WebRequest -Uri $vlcUrl -UseBasicParsing -TimeoutSec 30
                    $link = ($dirPage.Links | Where-Object { $_.href -match "\.exe$" -and $_.href -notmatch "debug|src" } | Select-Object -First 1).href
                    if (-not $link) { continue }
                    $vlcUrl = $vlcUrl + $link
                }
                Invoke-WebRequest -Uri $vlcUrl -OutFile $vlcPath -TimeoutSec 300 -UseBasicParsing
                if ((Test-Path $vlcPath) -and (Get-Item $vlcPath).Length -gt 1MB) {
                    $downloaded = $true
                    Write-Success "Downloaded from: $vlcUrl"
                    break
                }
            } catch {
                Write-Host "[WARNING] Failed to download from $vlcUrl : $_" -ForegroundColor Yellow
            }
        }

        if ($downloaded) {
            Write-Info "Installing VLC..."
            $proc = Start-Process $vlcPath -ArgumentList "/S" -Wait -NoNewWindow -PassThru
            Start-Sleep -Seconds 5

            if (Test-Path $vlcExe) {
                Write-Success "VLC Media Player installed successfully"
            } else {
                Write-Host "[WARNING] VLC installation may have failed (exit code: $($proc.ExitCode))" -ForegroundColor Red
            }
        } else {
            Write-Host "[WARNING] Could not download VLC from any source - skipping" -ForegroundColor Red
        }
    }
} else {
    Write-Info "Skipping VLC Media Player (INSTALL_VLC not set)"
}

# =============================================================================
# Step 4: Pre-download LucidLink installer (but don't install)
# =============================================================================
Write-Step "Pre-downloading LucidLink installer"

$lucidlinkInstaller = "C:\Temp\LucidLink-Setup.msi"
Write-Info "Downloading LucidLink MSI (will be installed at deploy time)..."
& curl.exe -L -o $lucidlinkInstaller "https://www.lucidlink.com/download/new-ll-latest/win/stable/"
$fileSize = (Get-Item $lucidlinkInstaller).Length
Write-Success "LucidLink installer downloaded: $([math]::Round($fileSize/1MB, 2)) MB"
Write-Info "LucidLink will be configured at deployment time with credentials"

# =============================================================================
# Step 5: Install BGInfo
# =============================================================================
Write-Step "Installing BGInfo"

$bgInfoUrl = "https://live.sysinternals.com/Bginfo.exe"
$bgInfoPath = "C:\Windows\System32\bginfo.exe"
Invoke-WebRequest -Uri $bgInfoUrl -OutFile $bgInfoPath -UseBasicParsing
New-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "BGInfo" -Value "C:\Windows\System32\bginfo.exe /timer:0 /silent /nolicprompt" -Force
Write-Success "BGInfo installed and configured"

# =============================================================================
# Summary
# =============================================================================
Write-Step "Installation Summary"

Write-Host ""
Write-Host "Installed Software:" -ForegroundColor Green
Write-Host "  - Google Chrome" -ForegroundColor White
Write-Host "  - BGInfo" -ForegroundColor White

if ($installVcredist -eq "true" -or $installVcredist -eq "True" -or $installVcredist -eq "1") {
    Write-Host "  - Visual C++ 2013 x86/x64" -ForegroundColor White
    Write-Host "  - Visual C++ 2015-2022 x86/x64" -ForegroundColor White
}

if ($installVlc -eq "true" -or $installVlc -eq "True" -or $installVlc -eq "1") {
    Write-Host "  - VLC Media Player" -ForegroundColor White
}

Write-Host ""
Write-Host "Pre-downloaded (for deploy-time installation):" -ForegroundColor Yellow
Write-Host "  - LucidLink client MSI" -ForegroundColor White

Write-Host ""
Write-Host "To be configured at deployment:" -ForegroundColor Cyan
Write-Host "  - D: drive (data disk)" -ForegroundColor White
Write-Host "  - Admin password" -ForegroundColor White
Write-Host "  - LucidLink filespace connection" -ForegroundColor White

Write-Host ""
Write-Success "Image software installation complete!"
