Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path .chroma_server.pid)) { Write-Host "Nothing to stop"; exit 0 }
$procId = Get-Content .chroma_server.pid
Stop-Process -Id $procId -ErrorAction SilentlyContinue; Remove-Item .chroma_server.pid; Write-Host "Stopped Chroma (pid $procId)"
