# Start Django backend on native Windows (no WSL).
# Expects Docker Desktop with postgres/redis from mini-prod compose.
# Usage (from repo root):
#   .\scripts\start-backend-windows.ps1
#   .\scripts\start-backend-windows.ps1 -Port 9000

param(
  [int]$Port = 9000,
  [switch]$SkipDocker,
  [switch]$Migrate
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  Write-Host "Windows venv not found at .venv\Scripts\python.exe" -ForegroundColor Red
  Write-Host "Create it with:" -ForegroundColor Yellow
  Write-Host '  py -3.12 -m venv .venv'
  Write-Host '  .\.venv\Scripts\python.exe -m pip install -r requirements-mini.txt'
  Write-Host "(On Windows, skip python-ldap if build fails — LDAP is optional for local login.)"
  exit 1
}

if (-not $SkipDocker) {
  Write-Host "Ensuring postgres + redis containers are up..." -ForegroundColor Cyan
  docker start mini-prod-postgres mini-prod-redis 2>$null | Out-Null
  $deadline = (Get-Date).AddSeconds(60)
  do {
    $pg = docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' mini-prod-postgres 2>$null
    $rd = docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' mini-prod-redis 2>$null
    if (($pg -eq "healthy" -or $pg -eq "running") -and ($rd -eq "healthy" -or $rd -eq "running")) { break }
    Start-Sleep -Seconds 2
  } while ((Get-Date) -lt $deadline)
  Write-Host "postgres=$pg redis=$rd"
}

if ($Migrate) {
  Write-Host "Running migrations..." -ForegroundColor Cyan
  & $Python manage.py migrate
}

Write-Host "Starting backend on http://127.0.0.1:$Port/ (native Windows, no WSL)" -ForegroundColor Green
& $Python manage.py runserver "127.0.0.1:$Port"
