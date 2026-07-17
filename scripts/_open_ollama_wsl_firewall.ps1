# Requires Administrator. Opens TCP 11434 for WSL -> Windows Ollama.
$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
  [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdmin) {
  Write-Host "Re-launching elevated..."
  $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
  Start-Process powershell -Verb RunAs -ArgumentList $arg -Wait
  exit $LASTEXITCODE
}

Write-Host "Running as Administrator"

# Host firewall
$name = "Ollama WSL 11434"
Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Allow -Protocol TCP -LocalPort 11434 -Profile Any | Out-Null
Write-Host "Host firewall rule OK: $name"

# Hyper-V / WSL firewall (Windows 11)
try {
  Get-NetFirewallHyperVRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallHyperVRule -ErrorAction SilentlyContinue
  New-NetFirewallHyperVRule -DisplayName $name -Direction Inbound -Action Allow -Protocol TCP -LocalPorts 11434 -Enabled True | Out-Null
  Write-Host "Hyper-V firewall rule OK: $name"
} catch {
  Write-Warning "Hyper-V rule skipped: $($_.Exception.Message)"
}

Write-Host "Done. From WSL: curl http://`$(ip route | awk '/default/{print `$3}'):11434/api/tags"
Start-Sleep -Seconds 2
