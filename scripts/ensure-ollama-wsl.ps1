# Keep Windows Ollama reachable from WSL (bind 0.0.0.0:11434).
# The tray app often reverts to 127.0.0.1-only; this rebinds and can install Startup.
param(
  [switch]$InstallStartup,
  [switch]$Quiet
)

$ErrorActionPreference = "Continue"
$ollamaBin = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
if (-not (Test-Path $ollamaBin)) {
  $cmd = Get-Command ollama -ErrorAction SilentlyContinue
  if ($cmd) { $ollamaBin = $cmd.Source } else { throw "ollama.exe not found" }
}

function Info([string]$m) { if (-not $Quiet) { Write-Host $m } }

function ListenLines {
  @(netstat -ano | Select-String "LISTENING" | Select-String ":11434")
}

function LocalOk {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 2
    return $r.StatusCode -eq 200
  } catch { return $false }
}

function OnAllInterfaces {
  $lines = ListenLines
  return [bool]($lines | Where-Object { $_.Line -match "0\.0\.0\.0:11434|\[::\]:11434" })
}

function StartServe {
  Info "Starting: $ollamaBin serve  (OLLAMA_HOST=0.0.0.0:11434)"
  # Do not set User OLLAMA_HOST=0.0.0.0 (breaks CLI). Only the serve process gets it.
  Get-Process ollama* -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 2

  # cmd start detaches better than ProcessStartInfo in some environments
  $cmd = "set OLLAMA_HOST=0.0.0.0:11434&& start `"`" /B `"$ollamaBin`" serve"
  cmd.exe /c $cmd | Out-Null

  for ($i = 1; $i -le 20; $i++) {
    Start-Sleep -Seconds 1
    if ((LocalOk) -and (OnAllInterfaces)) {
      Info "OK after ${i}s: 0.0.0.0:11434 + HTTP 200"
      return $true
    }
    if ((LocalOk) -and -not (OnAllInterfaces)) {
      Info "Bound only on 127.0.0.1 after ${i}s - tray app won; retry rebind"
      Get-Process ollama* -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
      Start-Sleep -Seconds 1
      cmd.exe /c $cmd | Out-Null
    }
  }
  Info "Listen state:"
  ListenLines | ForEach-Object { Info $_.Line }
  Get-Process ollama* -ErrorAction SilentlyContinue | Format-Table Id, ProcessName | Out-String | ForEach-Object { Info $_ }
  return (LocalOk)
}

# --- main ---
if ((LocalOk) -and (OnAllInterfaces)) {
  Info "Already healthy on 0.0.0.0:11434"
} else {
  [void](StartServe)
}

# Sticky URL for WebTerm (prefer LAN)
$sticky = "http://192.168.0.16:11434"
try {
  $lan = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -match "^192\.168\." } |
    Select-Object -First 1 -ExpandProperty IPAddress
  if ($lan) { $sticky = "http://${lan}:11434" }
} catch {}
Set-Content -Path "C:\WebTrerm\.ollama_wsl_url" -Value $sticky -Encoding ASCII -NoNewline
Info "Sticky: $sticky"

if ($InstallStartup) {
  $startup = [Environment]::GetFolderPath("Startup")
  $bat = Join-Path $startup "WebTerm-EnsureOllamaWSL.bat"
  $me = $PSCommandPath
  @(
    "@echo off"
    "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$me`" -Quiet"
  ) | Set-Content -Path $bat -Encoding ASCII
  Info "Startup: $bat"
}

if (-not (LocalOk)) {
  Write-Error "Ollama still down on 127.0.0.1:11434"
  exit 1
}
if (-not (OnAllInterfaces)) {
  Write-Warning "Ollama is up but ONLY on 127.0.0.1 - WSL will fail until rebind sticks"
  exit 2
}
Info "Ready for WSL"
exit 0
