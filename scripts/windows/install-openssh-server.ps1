# Install and configure Windows OpenSSH Server for WebTerm.
# Run on the target machine in an elevated PowerShell session. WebTerm does not invoke this script.
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\windows\install-openssh-server.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\windows\install-openssh-server.ps1 -Shell powershell
#
# -Shell auto     Use pwsh.exe when it is on PATH, otherwise Windows PowerShell 5.1.
# -Shell pwsh     Require PowerShell 7+.
# -Shell powershell  Always use Windows PowerShell 5.1.
#
# Authorized keys:
#   Standard users:     %USERPROFILE%\.ssh\authorized_keys
#   Administrators:     %PROGRAMDATA%\ssh\administrators_authorized_keys
# OpenSSH's default sshd_config Match Group administrators already points admins at the
# ProgramData file. This script does not rewrite sshd_config.

#Requires -RunAsAdministrator

param(
    [ValidateSet("auto", "powershell", "pwsh")]
    [string]$Shell = "auto"
)

$ErrorActionPreference = "Stop"
$Utf8Marker = "# webterm-openssh-utf8"
$script:ListenPort = 22

function Resolve-OpenSshDefaultShell {
    param([string]$Choice)
    $windowsPowerShell = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
    $pwsh = Get-Command pwsh.exe -ErrorAction SilentlyContinue
    if ($Choice -eq "powershell") {
        return $windowsPowerShell
    }
    if ($Choice -eq "pwsh") {
        if (-not $pwsh) {
            throw "pwsh.exe was not found. Install PowerShell 7+ or pass -Shell powershell."
        }
        return $pwsh.Source
    }
    if ($pwsh) {
        return $pwsh.Source
    }
    return $windowsPowerShell
}

function Get-OpenSshServerCapability {
    $capability = Get-WindowsCapability -Online -Name "OpenSSH.Server~~~~0.0.1.0" -ErrorAction SilentlyContinue
    if (-not $capability -or -not $capability.Name) {
        $capability = Get-WindowsCapability -Online | Where-Object { $_.Name -like "OpenSSH.Server*" } | Select-Object -First 1
    }
    if (-not $capability) {
        throw "Windows capability OpenSSH.Server is not available on this image."
    }
    return $capability
}

function Test-SshdReady {
    $exe = Join-Path $env:WINDIR "System32\OpenSSH\sshd.exe"
    $service = Get-Service -Name sshd -ErrorAction SilentlyContinue
    return (Test-Path $exe) -and ($null -ne $service)
}

function Wait-SshdReady {
    param([int]$Seconds = 15)
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        if (Test-SshdReady) {
            return $true
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    return (Test-SshdReady)
}

function Repair-OpenSshServerFromComponentStore {
    $component = Get-ChildItem -Path (Join-Path $env:WINDIR "WinSxS") -Directory -Filter "*_openssh-server-components-onecore*" |
        Sort-Object Name |
        Select-Object -Last 1
    if (-not $component) {
        throw "sshd.exe is missing, and Windows has no OpenSSH server files in WinSxS."
    }

    $dest = Join-Path $env:WINDIR "System32\OpenSSH"
    if (-not (Test-Path $dest)) {
        New-Item -ItemType Directory -Path $dest -Force | Out-Null
    }
    foreach ($fileName in @("sshd.exe", "sftp-server.exe", "ssh-shellhost.exe", "moduli")) {
        $source = Join-Path $component.FullName $fileName
        $target = Join-Path $dest $fileName
        if ((Test-Path $source) -and -not (Test-Path $target)) {
            Copy-Item -Path $source -Destination $target
        } elseif ((Test-Path $source) -and $fileName -ne "moduli") {
            Copy-Item -Path $source -Destination $target -Force
        }
    }

    $configDir = Join-Path $env:ProgramData "ssh"
    if (-not (Test-Path $configDir)) {
        New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    }
    $config = Join-Path $configDir "sshd_config"
    $defaultConfig = Join-Path $component.FullName "sshd_config_default"
    if (-not (Test-Path $config) -and (Test-Path $defaultConfig)) {
        Copy-Item -Path $defaultConfig -Destination $config
    }

    if (-not (Get-Service -Name sshd -ErrorAction SilentlyContinue)) {
        New-Service -Name sshd -BinaryPathName (Join-Path $dest "sshd.exe") -DisplayName "OpenSSH SSH Server" -StartupType Automatic -Description "OpenSSH SSH Server" | Out-Null
    }
    Write-Host "Restored sshd from the Windows component store because the capability install did not register the service."
}

function Install-OpenSshServerCapability {
    $capability = Get-OpenSshServerCapability
    if ($capability.State -eq "Installed" -and (Test-SshdReady)) {
        Write-Host "OpenSSH Server capability is already installed."
        return
    }
    if ($capability.State -eq "Installed") {
        Write-Host "OpenSSH Server is marked installed, but the sshd service is missing. Reinstalling $($capability.Name)..."
        Remove-WindowsCapability -Online -Name $capability.Name | Out-Null
    } else {
        Write-Host "Installing $($capability.Name)..."
    }
    $result = Add-WindowsCapability -Online -Name $capability.Name
    if ($result.RestartNeeded) {
        Write-Warning "Windows requested a reboot before OpenSSH Server can finish installing."
    }
    if (-not (Wait-SshdReady)) {
        Repair-OpenSshServerFromComponentStore
    }
}

function Set-OpenSshAcl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [switch]$Directory
    )
    $acl = Get-Acl -LiteralPath $Path
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($rule in @($acl.Access)) {
        [void]$acl.RemoveAccessRule($rule)
    }
    $rights = [System.Security.AccessControl.FileSystemRights]::FullControl
    $allow = [System.Security.AccessControl.AccessControlType]::Allow
    foreach ($sidText in @("S-1-5-18", "S-1-5-32-544")) {
        $sid = New-Object System.Security.Principal.SecurityIdentifier($sidText)
        if ($Directory) {
            $inherit = [System.Security.AccessControl.InheritanceFlags]"ContainerInherit,ObjectInherit"
            $propagation = [System.Security.AccessControl.PropagationFlags]::None
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, $rights, $inherit, $propagation, $allow)
        } else {
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, $rights, $allow)
        }
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Repair-SshdConfig {
    $configDir = Join-Path $env:ProgramData "ssh"
    $config = Join-Path $configDir "sshd_config"
    if (-not (Test-Path $config)) {
        return
    }
    $raw = [System.IO.File]::ReadAllText($config)
    if ($raw.Contains("__PROGRAMDATA__")) {
        $programData = $env:ProgramData.TrimEnd("\")
        $updated = $raw.Replace("__PROGRAMDATA__", $programData)
        [System.IO.File]::WriteAllText($config, $updated, [System.Text.Encoding]::ASCII)
    }
    # sshd exits immediately when anyone besides SYSTEM and Administrators can read these files.
    Set-OpenSshAcl -Path $configDir -Directory
    Set-OpenSshAcl -Path $config
    Get-ChildItem -LiteralPath $configDir -Force -File | Where-Object {
        $_.Name -like "ssh_host_*_key" -or $_.Name -eq "administrators_authorized_keys"
    } | ForEach-Object {
        Set-OpenSshAcl -Path $_.FullName
    }
}

function Set-SshdServicePrivileges {
    & sc.exe privs sshd "SeAssignPrimaryTokenPrivilege/SeTcbPrivilege/SeBackupPrivilege/SeRestorePrivilege/SeImpersonatePrivilege" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "sc.exe failed to grant the privileges sshd needs to start (exit $LASTEXITCODE)"
    }
}

function Set-SshdListenPort {
    param([int]$Port)
    $config = Join-Path $env:ProgramData "ssh\sshd_config"
    $raw = [System.IO.File]::ReadAllText($config)
    if ($raw -match '(?m)^#?\s*Port\s+\d+\s*$') {
        $raw = [regex]::Replace($raw, '(?m)^#?\s*Port\s+\d+\s*$', "Port $Port", 1)
    } else {
        $raw = "Port $Port`r`n$raw"
    }
    [System.IO.File]::WriteAllText($config, $raw, [System.Text.Encoding]::ASCII)
    Set-OpenSshAcl -Path $config
    $script:ListenPort = $Port
}

function Get-SshdDebugLog {
    $sshd = Join-Path $env:WINDIR "System32\OpenSSH\sshd.exe"
    $log = Join-Path $env:TEMP "webterm-sshd-debug.txt"
    foreach ($path in @($log, "$log.out")) {
        if (Test-Path $path) {
            Remove-Item $path -Force
        }
    }
    $debug = Start-Process -FilePath $sshd -ArgumentList "-d" -PassThru -WindowStyle Hidden -RedirectStandardError $log -RedirectStandardOutput "$log.out"
    if (-not $debug.WaitForExit(4000)) {
        Stop-Process -Id $debug.Id -Force
    }
    Get-Process sshd -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    $detail = ""
    foreach ($path in @($log, "$log.out")) {
        if (Test-Path $path) {
            $detail += [System.IO.File]::ReadAllText($path)
        }
    }
    return $detail
}

function Enable-SshdService {
    if (-not (Get-Service -Name sshd -ErrorAction SilentlyContinue)) {
        throw "The sshd service is still missing after installing OpenSSH Server."
    }
    Repair-SshdConfig
    Set-SshdServicePrivileges
    Set-Service -Name sshd -StartupType Automatic
    $service = Get-Service -Name sshd
    if ($service.Status -eq "Running") {
        Write-Host "sshd is set to start automatically."
        return
    }
    try {
        Start-Service -Name sshd -ErrorAction Stop
    } catch {
        $detail = Get-SshdDebugLog
        if ($detail -match "Cannot bind any address|Permission denied" -and $script:ListenPort -eq 22) {
            Write-Host "Port 22 is blocked for sshd. Switching to TCP 2222."
            Set-SshdListenPort -Port 2222
            try {
                Start-Service -Name sshd -ErrorAction Stop
            } catch {
                $detail = Get-SshdDebugLog
                throw "sshd did not start on port $($script:ListenPort). $detail"
            }
        } else {
            throw "sshd did not start. $detail"
        }
    }
    Write-Host "sshd is set to start automatically on TCP port $($script:ListenPort)."
}

function Ensure-SshFirewallRule {
    param([int]$Port = $script:ListenPort)
    $name = "OpenSSH-Server-In-TCP"
    $existing = Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue
    if ($existing) {
        Set-NetFirewallRule -Name $name -Enabled True -Action Allow -Direction Inbound | Out-Null
        Set-NetFirewallPortFilter -AssociatedNetFirewallRule (Get-NetFirewallRule -Name $name) -Protocol TCP -LocalPort $Port | Out-Null
        Write-Host "Firewall rule $name allows TCP port $Port."
        return
    }
    New-NetFirewallRule -Name $name -DisplayName "OpenSSH Server (sshd)" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort $Port | Out-Null
    Write-Host "Opened TCP port $Port in the firewall."
}

function Set-OpenSshDefaultShell {
    param([string]$ShellPath)
    $regPath = "HKLM:\SOFTWARE\OpenSSH"
    if (-not (Test-Path $regPath)) {
        New-Item -Path $regPath -Force | Out-Null
    }
    New-ItemProperty -Path $regPath -Name DefaultShell -Value $ShellPath -PropertyType String -Force | Out-Null
    Write-Host "DefaultShell = $ShellPath"
}

function Get-AllUsersProfilePath {
    param([string]$ShellPath)
    $shellDir = Split-Path -Parent $ShellPath
    return Join-Path $shellDir "profile.ps1"
}

function Install-Utf8ProfileBlock {
    param([string]$ProfilePath)
    $block = @"
$Utf8Marker
if (-not (Get-Variable -Name WebTermUtf8Applied -Scope Global -ErrorAction SilentlyContinue)) {
    `$global:WebTermUtf8Applied = `$true
    chcp 65001 > `$null
    `$webTermUtf8 = New-Object System.Text.UTF8Encoding `$false
    [Console]::InputEncoding = `$webTermUtf8
    [Console]::OutputEncoding = `$webTermUtf8
}
"@
    $directory = Split-Path -Parent $ProfilePath
    if (-not (Test-Path $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    if (Test-Path $ProfilePath) {
        $existing = Get-Content -Path $ProfilePath -Raw -ErrorAction SilentlyContinue
        if ($existing -and $existing.Contains($Utf8Marker)) {
            Write-Host "UTF-8 profile block already present in $ProfilePath"
            return
        }
        Add-Content -Path $ProfilePath -Value "`r`n$block" -Encoding utf8
    } else {
        Set-Content -Path $ProfilePath -Value $block -Encoding utf8
    }
    Write-Host "Wrote UTF-8 profile block to $ProfilePath"
}

function Protect-AuthorizedKeysFile {
    param(
        [string]$Path,
        [string[]]$Grant
    )
    $directory = Split-Path -Parent $Path
    if (-not (Test-Path $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    if (-not (Test-Path $Path)) {
        New-Item -ItemType File -Path $Path -Force | Out-Null
    }
    & icacls.exe $Path /inheritance:r | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "icacls failed to remove inheritance on $Path (exit $LASTEXITCODE)"
    }
    foreach ($ace in $Grant) {
        & icacls.exe $Path /grant:r $ace | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "icacls failed for $Path ($ace, exit $LASTEXITCODE)"
        }
    }
    Write-Host "Restricted ACL on $Path"
}

Install-OpenSshServerCapability
Enable-SshdService
Ensure-SshFirewallRule

$defaultShell = Resolve-OpenSshDefaultShell -Choice $Shell
Set-OpenSshDefaultShell -ShellPath $defaultShell
Install-Utf8ProfileBlock -ProfilePath (Get-AllUsersProfilePath -ShellPath $defaultShell)

$adminKeys = Join-Path $env:ProgramData "ssh\administrators_authorized_keys"
Protect-AuthorizedKeysFile -Path $adminKeys -Grant @("*S-1-5-32-544:F", "*S-1-5-18:F")

$userKeys = Join-Path $env:USERPROFILE ".ssh\authorized_keys"
if (Test-Path $userKeys) {
    $userSshDir = Split-Path -Parent $userKeys
    & icacls.exe $userSshDir /grant:r "$($env:USERNAME):(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" | Out-Null
    & icacls.exe $userSshDir /inheritance:r | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "icacls failed to restrict $userSshDir (exit $LASTEXITCODE)"
    }
    Protect-AuthorizedKeysFile -Path $userKeys -Grant @("$($env:USERNAME):F", "*S-1-5-18:F")
    # Administrators are matched to ProgramData keys, not the user file.
    $publicKeys = @(Get-Content -Path $userKeys | Where-Object { $_ -match '^\s*ssh-' })
    $installed = @()
    if (Test-Path $adminKeys) {
        $installed = @(Get-Content -Path $adminKeys | Where-Object { $_ -match '^\s*ssh-' })
    }
    foreach ($publicKey in $publicKeys) {
        if ($installed -notcontains $publicKey.Trim()) {
            Add-Content -Path $adminKeys -Value $publicKey.Trim() -Encoding ascii
            $installed += $publicKey.Trim()
        }
    }
    Protect-AuthorizedKeysFile -Path $adminKeys -Grant @("*S-1-5-32-544:F", "*S-1-5-18:F")
} else {
    Write-Host "No user authorized_keys at $userKeys. Standard (non-admin) accounts keep keys in %USERPROFILE%\.ssh\authorized_keys with access limited to that user and SYSTEM."
}

Restart-Service -Name sshd
Write-Host "OpenSSH Server is ready on TCP port $($script:ListenPort)."
