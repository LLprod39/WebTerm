# Start Ollama so WSL backends can reach it, without breaking `ollama run` CLI.
#
# Problem:
#   1) Default Ollama binds 127.0.0.1 only -> WSL cannot connect via host gateway.
#   2) Setting user OLLAMA_HOST=0.0.0.0:11434 makes CLI try 0.0.0.0 and fail.
#
# Fix: bind the serve process only to 0.0.0.0:11434; leave user OLLAMA_HOST empty.
# Also open host + Hyper-V firewall for TCP 11434 (requires one-time Admin).

$ErrorActionPreference = "Continue"
$ollamaBin = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
if (-not (Test-Path $ollamaBin)) {
  $cmd = Get-Command ollama -ErrorAction SilentlyContinue
  if ($cmd) { $ollamaBin = $cmd.Source }
  else { throw "ollama.exe not found" }
}

# Never keep 0.0.0.0 in user env (breaks CLI)
$userHost = [System.Environment]::GetEnvironmentVariable("OLLAMA_HOST", "User")
if ($userHost -and $userHost -match "0\.0\.0\.0") {
  [System.Environment]::SetEnvironmentVariable("OLLAMA_HOST", $null, "User")
  Write-Host "Cleared user OLLAMA_HOST=$userHost (was breaking ollama CLI)"
}

# Restart cleanly
Get-Process ollama* -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $ollamaBin
$psi.Arguments = "serve"
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
# ProcessStartInfo.EnvironmentVariables is case-insensitive and already populated
$psi.EnvironmentVariables["OLLAMA_HOST"] = "0.0.0.0:11434"
[void][System.Diagnostics.Process]::Start($psi)

$ok = $false
for ($i = 0; $i -lt 12; $i++) {
  Start-Sleep -Seconds 1
  $listen = netstat -ano | Select-String "0.0.0.0:11434" | Select-String "LISTENING"
  if ($listen) {
    $ok = $true
    break
  }
}

if ($ok) {
  Write-Host "Ollama listening on 0.0.0.0:11434 (WSL/LAN reachable)"
} else {
  Write-Warning "Ollama may not be listening on 0.0.0.0:11434 yet"
  netstat -ano | Select-String "11434"
}

# Firewall (best-effort; elevate helper if needed)
$ruleName = "Ollama WSL 11434"
$hostRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if (-not $hostRule) {
  Write-Host "Firewall rule missing — launching elevated helper (UAC)..."
  $helper = Join-Path $PSScriptRoot "_open_ollama_wsl_firewall.ps1"
  if (Test-Path $helper) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$helper`"" -Wait
  }
} else {
  Write-Host "Firewall rule present: $ruleName"
}

try {
  $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 3
  Write-Host "Local health OK ($($r.StatusCode))"
} catch {
  Write-Warning "Local health FAIL: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "CLI: open a NEW terminal and run: ollama list   (uses 127.0.0.1)"
Write-Host "WSL: curl http://`$(ip route show default | awk '{print `$3}'):11434/api/tags"
Write-Host "WebTerm .model_config.json ollama_base_url: http://192.168.0.16:11434 (LAN) or WSL gateway"
