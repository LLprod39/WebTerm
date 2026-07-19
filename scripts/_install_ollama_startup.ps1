$startup = [Environment]::GetFolderPath("Startup")
$bat = Join-Path $startup "WebTerm-EnsureOllamaWSL.bat"
$script = "C:\WebTrerm\scripts\ensure-ollama-wsl.ps1"
@(
  "@echo off"
  "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" -Quiet"
) | Set-Content -Path $bat -Encoding ASCII
Write-Host "Wrote $bat"
Get-Content $bat
