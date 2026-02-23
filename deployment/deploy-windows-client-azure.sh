#!/bin/bash
#
# Deploy Windows Client Configuration via Azure Run Command
# Uses az vm run-command invoke to execute PowerShell on Windows VMs after creation
#
# Usage:
#   This script is called by ll-win-client.py to deploy software
#
#   Manual usage:
#     ADMIN_PASSWORD="YourPassword" ./deploy-windows-client-azure.sh VM_NAME RESOURCE_GROUP [LOCATION]
#
# Required Environment Variables:
#   ADMIN_PASSWORD - Windows admin password
#
# Optional Software Control (set to 1 to enable, 0 to disable):
#   INSTALL_VLC=0 ./deploy-windows-client-azure.sh          # Disable VLC
#   INSTALL_VCREDIST=1 ./deploy-windows-client-azure.sh     # Enable VC++ Redistributables
#   INSTALL_7ZIP=1 ./deploy-windows-client-azure.sh         # Enable 7-Zip
#   INSTALL_NOTEPAD_PP=1 ./deploy-windows-client-azure.sh   # Enable Notepad++
#   INSTALL_ADOBE_CC=1 ./deploy-windows-client-azure.sh     # Enable Adobe CC installer download
#   INSTALL_TC_BENCHMARK=1 ./deploy-windows-client-azure.sh  # Enable TC Benchmark download
#
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Arguments
VM_NAME="${1:?Usage: $0 VM_NAME RESOURCE_GROUP [LOCATION]}"
RESOURCE_GROUP="${2:?Usage: $0 VM_NAME RESOURCE_GROUP [LOCATION]}"
LOCATION="${3:-}"

# Admin password - MUST be provided via environment variable
if [ -z "$ADMIN_PASSWORD" ]; then
    echo -e "${RED}ERROR: ADMIN_PASSWORD environment variable is required${NC}"
    echo "This script is called by ll-win-client.py which generates the password."
    echo "To run manually: ADMIN_PASSWORD=\"YourPassword\" $0 $@"
    exit 1
fi

# Optional Software Configuration (set to 1 to enable, 0 to disable)
INSTALL_VLC="${INSTALL_VLC:-1}"              # VLC Media Player (default: enabled)
INSTALL_VCREDIST="${INSTALL_VCREDIST:-1}"    # Visual C++ Redistributables (default: enabled, needed by tframetest)
INSTALL_7ZIP="${INSTALL_7ZIP:-0}"            # 7-Zip (default: disabled)
INSTALL_NOTEPAD_PP="${INSTALL_NOTEPAD_PP:-0}" # Notepad++ (default: disabled)
INSTALL_ADOBE_CC="${INSTALL_ADOBE_CC:-0}"    # Adobe Creative Cloud (default: disabled)
INSTALL_TC_BENCHMARK="${INSTALL_TC_BENCHMARK:-0}" # TC Benchmark client (default: disabled)

# Helper function to run Azure Run Command and display result
run_azure_cmd() {
    local description="$1"
    local script="$2"

    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} ${description}..."

    local output
    output=$(az vm run-command invoke \
        --resource-group "$RESOURCE_GROUP" \
        --name "$VM_NAME" \
        --command-id RunPowerShellScript \
        --scripts "$script" \
        --query "value[0].message" \
        --output tsv 2>&1)

    local exit_code=$?

    if [ $exit_code -eq 0 ]; then
        echo -e "  ${GREEN}✓ Success${NC}"
        if [ -n "$output" ]; then
            echo "$output" | sed 's/^/    /'
        fi
        return 0
    else
        echo -e "  ${RED}✗ Failed${NC}"
        if [ -n "$output" ]; then
            echo "$output" | sed 's/^/    /'
        fi
        return 1
    fi
}

# Main deployment
main() {
    echo "=================================================="
    echo "  Windows Client Deployment via Azure Run Command"
    echo "=================================================="
    echo "VM Name:         $VM_NAME"
    echo "Resource Group:  $RESOURCE_GROUP"
    [ -n "$LOCATION" ] && echo "Location:        $LOCATION"
    echo ""
    echo "Optional Software:"
    echo "  VLC Media Player:       $([ "$INSTALL_VLC" = "1" ] && echo -e "${GREEN}ENABLED${NC}" || echo -e "${YELLOW}DISABLED${NC}")"
    echo "  VC++ Redistributables:  $([ "$INSTALL_VCREDIST" = "1" ] && echo -e "${GREEN}ENABLED${NC}" || echo -e "${YELLOW}DISABLED${NC}")"
    echo "  7-Zip:                  $([ "$INSTALL_7ZIP" = "1" ] && echo -e "${GREEN}ENABLED${NC}" || echo -e "${YELLOW}DISABLED${NC}")"
    echo "  Notepad++:              $([ "$INSTALL_NOTEPAD_PP" = "1" ] && echo -e "${GREEN}ENABLED${NC}" || echo -e "${YELLOW}DISABLED${NC}")"
    echo "  Adobe Creative Cloud:   $([ "$INSTALL_ADOBE_CC" = "1" ] && echo -e "${GREEN}ENABLED${NC}" || echo -e "${YELLOW}DISABLED${NC}")"
    echo "  TC Benchmark:           $([ "$INSTALL_TC_BENCHMARK" = "1" ] && echo -e "${GREEN}ENABLED${NC}" || echo -e "${YELLOW}DISABLED${NC}")"
    echo "=================================================="
    echo

    # Step 1: Set admin password
    run_azure_cmd "Setting admin password" \
        "\$adminUser = (Get-LocalUser | Where-Object { \$_.Enabled -eq \$true -and \$_.Name -ne 'DefaultAccount' -and \$_.Name -ne 'WDAGUtilityAccount' } | Select-Object -First 1).Name; Write-Host \"Setting password for: \$adminUser\"; Set-LocalUser -Name \$adminUser -Password (ConvertTo-SecureString '${ADMIN_PASSWORD}' -AsPlainText -Force); Write-Host \"Password set successfully for \$adminUser\""

    # Step 2: Initialize data disk (D: drive)
    run_azure_cmd "Initializing data disk (D: drive)" \
        "Write-Host 'Looking for raw data disk at LUN 0...'; \$disk = Get-Disk | Where-Object { \$_.PartitionStyle -eq 'RAW' -and \$_.Number -ne 0 }; if (\$disk) { Write-Host \"Found raw disk: \$(\$disk.Number) - Size: \$([math]::Round(\$disk.Size/1GB, 2)) GB\"; Write-Host 'Initializing disk as GPT...'; Initialize-Disk -Number \$disk.Number -PartitionStyle GPT -Confirm:\$false; Write-Host 'Creating NTFS partition...'; \$partition = New-Partition -DiskNumber \$disk.Number -UseMaximumSize -DriveLetter D; Write-Host 'Formatting as NTFS with label Data...'; Format-Volume -DriveLetter D -FileSystem NTFS -NewFileSystemLabel 'Data' -Confirm:\$false; Write-Host 'D: drive initialized successfully'; Get-Volume -DriveLetter D | Format-Table DriveLetter, FileSystemLabel, Size, SizeRemaining -AutoSize } else { Write-Host 'No raw data disk found (may already be initialized)'; if (Test-Path 'D:\\') { Write-Host 'D: drive already exists' } }"

    # Step 3: Expand OS disk (C: drive)
    run_azure_cmd "Extending C: drive to use full OS disk" \
        "\$partition = Get-Partition -DriveLetter C; \$size = Get-PartitionSupportedSize -DriveLetter C; \$currentGB = [math]::Round(\$partition.Size / 1GB, 2); \$maxGB = [math]::Round(\$size.SizeMax / 1GB, 2); if (\$partition.Size -lt \$size.SizeMax) { Write-Host \"Extending C: from \$currentGB GB to \$maxGB GB...\"; Resize-Partition -DriveLetter C -Size \$size.SizeMax; Write-Host 'C: drive extended successfully' } else { Write-Host \"C: drive already at maximum size (\$currentGB GB)\" }"

    # Step 4: Install Google Chrome (skip if already installed)
    run_azure_cmd "Installing Google Chrome" \
        "\$chromeExe = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'; if (Test-Path \$chromeExe) { Write-Host 'Chrome already installed (custom image)' } else { Write-Host 'Downloading Chrome...'; \$chromeUrl = 'https://dl.google.com/chrome/install/latest/chrome_installer.exe'; \$chromePath = 'C:\\Temp\\chrome_installer.exe'; New-Item -ItemType Directory -Path 'C:\\Temp' -Force | Out-Null; Invoke-WebRequest -Uri \$chromeUrl -OutFile \$chromePath -TimeoutSec 300; Write-Host 'Installing Chrome...'; Start-Process \$chromePath -ArgumentList '/silent /install' -Wait; Write-Host 'Chrome installed successfully' }"

    # ==================================================================
    # OPTIONAL SOFTWARE INSTALLATIONS
    # ==================================================================

    # Step 5: Install VLC Media Player (if enabled, skip if already installed)
    if [ "$INSTALL_VLC" = "1" ]; then
        run_azure_cmd "Installing VLC Media Player" \
            "\$vlcExe = 'C:\\Program Files\\VideoLAN\\VLC\\vlc.exe'; if (Test-Path \$vlcExe) { Write-Host 'VLC already installed (custom image)' } else { Write-Host 'Downloading VLC...'; \$vlcUrl = 'https://download.videolan.org/pub/videolan/vlc/last/win64/'; \$page = Invoke-WebRequest -Uri \$vlcUrl -UseBasicParsing -TimeoutSec 30; \$msiLink = (\$page.Links | Where-Object { \$_.href -match '\\.msi\$' } | Select-Object -First 1).href; if (-not \$msiLink) { throw 'Could not find VLC MSI download link' }; \$downloadUrl = \$vlcUrl + \$msiLink; Write-Host \"Downloading \$downloadUrl\"; \$vlcPath = 'C:\\Temp\\vlc.msi'; Invoke-WebRequest -Uri \$downloadUrl -OutFile \$vlcPath -TimeoutSec 300; if ((Get-Item \$vlcPath).Length -lt 1MB) { throw 'Downloaded file too small' }; Write-Host 'Installing VLC...'; \$proc = Start-Process msiexec.exe -ArgumentList \"/i `\"\$vlcPath`\" /qn /norestart\" -Wait -NoNewWindow -PassThru; if (Test-Path \$vlcExe) { Write-Host 'VLC installed successfully' } else { throw 'VLC binary not found after installation' } }"
    else
        echo -e "  ${YELLOW}Skipping VLC installation (disabled)${NC}"
    fi

    # Step 6: Install Visual C++ Redistributables (if enabled, skip if already installed)
    if [ "$INSTALL_VCREDIST" = "1" ]; then
        run_azure_cmd "Installing Visual C++ Redistributables" \
            "\$vcInstalled = Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\VisualStudio\\14.0\\VC\\Runtimes\\X64' -ErrorAction SilentlyContinue; if (\$vcInstalled) { Write-Host 'Visual C++ Redistributables already installed (custom image)' } else { Write-Host 'Installing Visual C++ Redistributables...'; New-Item -ItemType Directory -Path 'C:\\Temp' -Force | Out-Null; Write-Host 'Downloading VC++ 2013 x64...'; Invoke-WebRequest -Uri 'https://aka.ms/highdpimfc2013x64enu' -OutFile 'C:\\Temp\\vcredist_2013_x64.exe' -TimeoutSec 120; Start-Process 'C:\\Temp\\vcredist_2013_x64.exe' -ArgumentList '/quiet /norestart' -Wait; Write-Host 'VC++ 2013 x64 installed'; Write-Host 'Downloading VC++ 2013 x86...'; Invoke-WebRequest -Uri 'https://aka.ms/highdpimfc2013x86enu' -OutFile 'C:\\Temp\\vcredist_2013_x86.exe' -TimeoutSec 120; Start-Process 'C:\\Temp\\vcredist_2013_x86.exe' -ArgumentList '/quiet /norestart' -Wait; Write-Host 'VC++ 2013 x86 installed'; Write-Host 'Downloading VC++ 2015-2022 x86...'; Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x86.exe' -OutFile 'C:\\Temp\\vcredist_2022_x86.exe' -TimeoutSec 120; Start-Process 'C:\\Temp\\vcredist_2022_x86.exe' -ArgumentList '/quiet /norestart' -Wait; Write-Host 'VC++ 2015-2022 x86 installed'; Write-Host 'Downloading VC++ 2015-2022 x64...'; Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile 'C:\\Temp\\vcredist_2022_x64.exe' -TimeoutSec 120; Start-Process 'C:\\Temp\\vcredist_2022_x64.exe' -ArgumentList '/quiet /norestart' -Wait; Write-Host 'VC++ 2015-2022 x64 installed'; Write-Host 'All Visual C++ Redistributables installed successfully' }"
    else
        echo -e "  ${YELLOW}Skipping Visual C++ Redistributables (disabled)${NC}"
    fi

    # Step 7: Install 7-Zip (if enabled)
    if [ "$INSTALL_7ZIP" = "1" ]; then
        run_azure_cmd "Installing 7-Zip" \
            "\$zipExe = 'C:\\Program Files\\7-Zip\\7z.exe'; if (Test-Path \$zipExe) { Write-Host '7-Zip already installed (custom image)' } else { Write-Host 'Downloading 7-Zip...'; New-Item -ItemType Directory -Path 'C:\\Temp' -Force | Out-Null; Invoke-WebRequest -Uri 'https://www.7-zip.org/a/7z2301-x64.msi' -OutFile 'C:\\Temp\\7zip.msi' -TimeoutSec 300; Write-Host 'Installing 7-Zip...'; Start-Process msiexec.exe -ArgumentList '/i \"C:\\Temp\\7zip.msi\" /qn /norestart' -Wait -NoNewWindow; Write-Host '7-Zip installed successfully' }"
    fi

    # Step 8: Install Notepad++ (if enabled)
    if [ "$INSTALL_NOTEPAD_PP" = "1" ]; then
        run_azure_cmd "Installing Notepad++" \
            "\$nppExe = 'C:\\Program Files\\Notepad++\\notepad++.exe'; if (Test-Path \$nppExe) { Write-Host 'Notepad++ already installed (custom image)' } else { Write-Host 'Downloading Notepad++...'; New-Item -ItemType Directory -Path 'C:\\Temp' -Force | Out-Null; Invoke-WebRequest -Uri 'https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.6.2/npp.8.6.2.Installer.x64.exe' -OutFile 'C:\\Temp\\npp-installer.exe' -TimeoutSec 300; Write-Host 'Installing Notepad++...'; Start-Process 'C:\\Temp\\npp-installer.exe' -ArgumentList '/S' -Wait; Write-Host 'Notepad++ installed successfully' }"
    fi

    # Step 9: Download Adobe Creative Cloud installer (if enabled)
    if [ "$INSTALL_ADOBE_CC" = "1" ]; then
        run_azure_cmd "Downloading Adobe Creative Cloud installer" \
            "Write-Host 'Downloading Adobe Creative Cloud installer...'; \$desktopPath = 'C:\\Users\\Public\\Desktop'; New-Item -ItemType Directory -Path \$desktopPath -Force | Out-Null; \$installerPath = Join-Path \$desktopPath 'Adobe_Creative_Cloud_Installer.exe'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://lucidlink-se-tools.s3.us-east-1.amazonaws.com/adobe-cc-win/Creative_Cloud_Set-Up.exe' -OutFile \$installerPath -TimeoutSec 300 -UseBasicParsing; \$fileSize = (Get-Item \$installerPath).Length / 1MB; Write-Host \"Downloaded Adobe CC installer: \$([math]::Round(\$fileSize, 2)) MB\"; Write-Host 'NOTE: Adobe CC requires manual installation with Adobe account credentials'"
    else
        echo -e "  ${YELLOW}Skipping Adobe Creative Cloud download (disabled)${NC}"
    fi

    # Step 10: Download TC Benchmark client and install uv (if enabled)
    if [ "$INSTALL_TC_BENCHMARK" = "1" ]; then
        run_azure_cmd "Installing uv (Python package manager)" \
            "Write-Host 'Installing uv...'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1' | Invoke-Expression; \$uvSrc = \"\$env:USERPROFILE\\.local\\bin\"; \$uvDest = 'C:\\Program Files\\uv'; New-Item -ItemType Directory -Path \$uvDest -Force | Out-Null; Copy-Item \"\$uvSrc\\uv.exe\" \$uvDest -Force; Copy-Item \"\$uvSrc\\uvx.exe\" \$uvDest -Force; \$currentPath = [Environment]::GetEnvironmentVariable('Path', 'Machine'); if (\$currentPath -notlike \"*\$uvDest*\") { [Environment]::SetEnvironmentVariable('Path', \"\$currentPath;\$uvDest\", 'Machine'); Write-Host \"Added \$uvDest to system PATH\" }; & \"\$uvDest\\uv.exe\" --version; Write-Host 'uv installed system-wide'"

        # Encode tfbench.py, pyproject.toml, README.md as base64 to push via run-command
        # (Bitbucket zip download fails for private repos)
        _find_tc_file() { local f="$1"; for d in "$(dirname "${BASH_SOURCE[0]}")/../tc-benchmark-files" "$HOME/Cursor_projects/tc-benchmark-bitbucket/tc-benchmark"; do [ -f "$d/$f" ] && echo "$d/$f" && return; done; find "$HOME" -maxdepth 5 -path "*/tc-benchmark/$f" -type f 2>/dev/null | head -1; }
        TFBENCH_B64=$(base64 < "$(_find_tc_file tfbench.py)" 2>/dev/null || echo "")
        PYPROJECT_B64=$(base64 < "$(_find_tc_file pyproject.toml)" 2>/dev/null || echo "")
        README_B64=$(base64 < "$(_find_tc_file README.md)" 2>/dev/null || echo "")

        run_azure_cmd "Downloading TC Benchmark and tframetest" \
            "\$destPath = 'C:\\Users\\Public\\Desktop\\tc-benchmark'; if (Test-Path \$destPath) { Remove-Item -Path \$destPath -Recurse -Force }; New-Item -ItemType Directory -Path \$destPath -Force | Out-Null; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Write-Host 'Downloading tframetest from GitHub...'; New-Item -ItemType Directory -Path 'C:\\Temp' -Force | Out-Null; \$tframetestZip = 'C:\\Temp\\tframetest-win64.zip'; Invoke-WebRequest -Uri 'https://github.com/tuxera/tframetest/releases/download/3025.12.0/tframetest-win-x86_64-w64-mingw32-3025.12.0.zip' -OutFile \$tframetestZip -TimeoutSec 300 -UseBasicParsing; Expand-Archive -Path \$tframetestZip -DestinationPath 'C:\\Temp\\tframetest-extract' -Force; Copy-Item -Path 'C:\\Temp\\tframetest-extract\\tframetest-win-x86_64-w64-mingw32-3025.12.0\\tframetest.exe' -Destination \$destPath; Copy-Item -Path 'C:\\Temp\\tframetest-extract\\tframetest-win-x86_64-w64-mingw32-3025.12.0\\*.dll' -Destination \$destPath -ErrorAction SilentlyContinue; Write-Host 'tframetest.exe installed'; Remove-Item -Path \$tframetestZip, 'C:\\Temp\\tframetest-extract' -Recurse -Force -ErrorAction SilentlyContinue; Write-Host 'Downloading tfbench.py from Bitbucket...'; \$bbBase = 'https://bitbucket.org/lucidlink/tc-benchmark/raw/master'; try { Invoke-WebRequest -Uri \"\$bbBase/tfbench.py\" -OutFile (Join-Path \$destPath 'tfbench.py') -UseBasicParsing -TimeoutSec 60; Invoke-WebRequest -Uri \"\$bbBase/pyproject.toml\" -OutFile (Join-Path \$destPath 'pyproject.toml') -UseBasicParsing -TimeoutSec 60; Invoke-WebRequest -Uri \"\$bbBase/README.md\" -OutFile (Join-Path \$destPath 'README.md') -UseBasicParsing -TimeoutSec 60; \$tfSize = (Get-Item (Join-Path \$destPath 'tfbench.py')).Length; if (\$tfSize -lt 1000) { throw 'Downloaded file too small' }; Write-Host 'Downloaded from Bitbucket' } catch { Write-Host \"Bitbucket download failed (\$_), using embedded files...\"; \$tfB64 = '${TFBENCH_B64}'; \$pyB64 = '${PYPROJECT_B64}'; \$rdB64 = '${README_B64}'; if (\$tfB64) { [IO.File]::WriteAllBytes((Join-Path \$destPath 'tfbench.py'), [Convert]::FromBase64String(\$tfB64)); [IO.File]::WriteAllBytes((Join-Path \$destPath 'pyproject.toml'), [Convert]::FromBase64String(\$pyB64)); if (\$rdB64) { [IO.File]::WriteAllBytes((Join-Path \$destPath 'README.md'), [Convert]::FromBase64String(\$rdB64)) } else { [IO.File]::WriteAllText((Join-Path \$destPath 'README.md'), '# TC Benchmark') }; Write-Host 'Installed from embedded files' } else { Write-Host 'WARNING: No embedded files available - tfbench.py not installed' } }; Write-Host \"TC Benchmark installed to \$destPath\"; Get-ChildItem \$destPath | ForEach-Object { Write-Host \"  \$(\$_.Name) (\$([math]::Round(\$_.Length/1KB, 1)) KB)\" }"
    else
        echo -e "  ${YELLOW}Skipping TC Benchmark download (disabled)${NC}"
    fi

    # ==================================================================
    # CORE SOFTWARE (Always Installed)
    # ==================================================================

    # Step 11: Install LucidLink (skip if already installed)
    run_azure_cmd "Installing LucidLink" \
        "\$lucidPath = 'C:\\Program Files\\LucidLink\\bin\\lucid.exe'; if (Test-Path \$lucidPath) { Write-Host 'LucidLink already installed (custom image)'; \$lucidBinPath = 'C:\\Program Files\\LucidLink\\bin'; \$currentPath = [Environment]::GetEnvironmentVariable('Path', 'Machine'); if (\$currentPath -notlike \"*\$lucidBinPath*\") { Write-Host 'Adding LucidLink to system PATH...'; [Environment]::SetEnvironmentVariable('Path', \"\$currentPath;\$lucidBinPath\", 'Machine') } } else { Write-Host 'Downloading LucidLink MSI...'; New-Item -ItemType Directory -Path 'C:\\Temp' -Force | Out-Null; \$installerUrl = 'https://www.lucidlink.com/download/new-ll-latest/win/stable/'; \$lucidlinkInstaller = 'C:\\Temp\\LucidLink-Setup.msi'; & curl.exe -L -o \$lucidlinkInstaller \$installerUrl; \$fileSize = (Get-Item \$lucidlinkInstaller).Length; Write-Host \"Downloaded: \$([math]::Round(\$fileSize/1MB, 2)) MB\"; Write-Host 'Installing LucidLink MSI...'; \$installLog = 'C:\\Temp\\lucidlink-install.log'; \$msiArgs = @('/i', \"\`\"\$lucidlinkInstaller\`\"\", '/quiet', '/norestart', '/log', \"\`\"\$installLog\`\"\"); \$process = Start-Process msiexec -Args \$msiArgs -Wait -NoNewWindow -PassThru; Write-Host \"MSI exit code: \$(\$process.ExitCode)\"; Start-Sleep -Seconds 10; if (Test-Path \$lucidPath) { Write-Host 'LucidLink installed successfully'; \$lucidBinPath = 'C:\\Program Files\\LucidLink\\bin'; \$currentPath = [Environment]::GetEnvironmentVariable('Path', 'Machine'); if (\$currentPath -notlike \"*\$lucidBinPath*\") { Write-Host 'Adding LucidLink to system PATH...'; [Environment]::SetEnvironmentVariable('Path', \"\$currentPath;\$lucidBinPath\", 'Machine') } } else { Write-Host 'WARNING: Installation may have failed' } }"

    # Step 12: Enable Windows dark mode
    run_azure_cmd "Enabling Windows dark mode" \
        "\$themePath = 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize'; if (-not (Test-Path \$themePath)) { New-Item -Path \$themePath -Force | Out-Null }; Set-ItemProperty -Path \$themePath -Name 'AppsUseLightTheme' -Value 0 -Type DWord; Set-ItemProperty -Path \$themePath -Name 'SystemUsesLightTheme' -Value 0 -Type DWord; Write-Host 'Dark mode enabled'"

    # Step 13: Reboot VM to activate NVIDIA GPU drivers
    # The NVIDIA GPU Driver Extension (installed by Terraform) requires a reboot
    # to load the driver. We reboot after all software is installed, then wait
    # for the VM to come back up.
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} Rebooting VM to activate NVIDIA GPU drivers..."
    az vm restart \
        --resource-group "$RESOURCE_GROUP" \
        --name "$VM_NAME" \
        --no-wait 2>/dev/null

    echo -e "  ${YELLOW}Waiting for VM to restart...${NC}"
    sleep 30

    # Wait for VM to be running again (up to 5 minutes)
    local retries=0
    local max_retries=10
    while [ $retries -lt $max_retries ]; do
        local vm_state
        vm_state=$(az vm get-instance-view \
            --resource-group "$RESOURCE_GROUP" \
            --name "$VM_NAME" \
            --query "instanceView.statuses[?code=='PowerState/running'] | [0].code" \
            --output tsv 2>/dev/null)
        if [ "$vm_state" = "PowerState/running" ]; then
            break
        fi
        retries=$((retries + 1))
        sleep 30
    done

    if [ $retries -ge $max_retries ]; then
        echo -e "  ${YELLOW}⚠ VM may still be restarting — check Azure portal${NC}"
    else
        echo -e "  ${GREEN}✓ VM restarted successfully${NC}"
        # Verify NVIDIA driver is loaded
        run_azure_cmd "Verifying NVIDIA GPU driver" \
            "if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { nvidia-smi --query-gpu=name,driver_version --format=csv,noheader } else { Write-Host 'nvidia-smi not found — driver may still be installing' }"
    fi

    # Get public IP
    PUBLIC_IP=$(az vm show \
        --resource-group "$RESOURCE_GROUP" \
        --name "$VM_NAME" \
        --show-details \
        --query "publicIps" \
        --output tsv 2>/dev/null)

    echo
    echo "=================================================="
    echo -e "  ${GREEN}Deployment Complete!${NC}"
    echo "=================================================="
    echo -e "VM Name:  ${BLUE}${VM_NAME}${NC}"
    echo -e "RDP:      ${BLUE}${PUBLIC_IP}:3389${NC}"
    echo -e "Password: ${BLUE}${ADMIN_PASSWORD}${NC}"
    echo "=================================================="
    echo
    echo "Installed Software:"
    echo "  ✓ NVIDIA GPU drivers (activated after reboot)"
    echo "  ✓ D: drive (data disk)"
    echo "  ✓ Google Chrome"
    echo "  ✓ LucidLink"
    [ "$INSTALL_VLC" = "1" ] && echo "  ✓ VLC Media Player"
    [ "$INSTALL_VCREDIST" = "1" ] && echo "  ✓ Visual C++ Redistributables (2013, 2015-2022)"
    [ "$INSTALL_7ZIP" = "1" ] && echo "  ✓ 7-Zip"
    [ "$INSTALL_NOTEPAD_PP" = "1" ] && echo "  ✓ Notepad++"
    [ "$INSTALL_ADOBE_CC" = "1" ] && echo "  📦 Adobe Creative Cloud installer (on Desktop - requires manual install)"
    [ "$INSTALL_TC_BENCHMARK" = "1" ] && echo "  ✓ uv (Python package manager)"
    [ "$INSTALL_TC_BENCHMARK" = "1" ] && echo "  ✓ TC Benchmark + tframetest (on Desktop)"
    echo
    echo "Next steps:"
    echo "  1. Connect via RDP client"
    echo "  2. Configure LucidLink filespace connection"
    [ "$INSTALL_ADOBE_CC" = "1" ] && echo "  3. Double-click Adobe_Creative_Cloud_Installer.exe on Desktop to install"
    [ "$INSTALL_TC_BENCHMARK" = "1" ] && echo "  3. Open tc-benchmark folder on Desktop and run: uv run tfbench.py -h"
}

# Run main function
main "$@"
