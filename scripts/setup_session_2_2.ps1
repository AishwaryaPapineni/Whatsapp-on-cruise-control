# Session 2.2 Part 0.5 (Windows) -- install if missing, start chroma once, wait for heartbeat.
Set-Location (Join-Path $PSScriptRoot "..")
$Port = if ($env:CHROMA_PORT) { $env:CHROMA_PORT } else { 8000 }
foreach ($pkg in @("chromadb", "sentence-transformers")) {
  python -m pip show $pkg *> $null
  if ($LASTEXITCODE -eq 0) { Write-Host "OK $pkg already installed" } else { python -m pip install $pkg }
}
$used = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($used) {
  try { Invoke-RestMethod "http://localhost:$Port/api/v2/heartbeat" | Out-Null; Write-Host "OK Chroma already running on :$Port"; exit 0 }
  catch { Write-Host "Port $Port is used by another process. Free it or set CHROMA_PORT."; exit 1 }
}
New-Item -ItemType Directory -Force logs | Out-Null
$p = Start-Process chroma -ArgumentList "run --path ./chroma_data --port $Port" -RedirectStandardOutput logs/chroma.log -PassThru -WindowStyle Hidden
$p.Id | Out-File .chroma_server.pid
for ($i = 0; $i -lt 10; $i++) {
  try { Invoke-RestMethod "http://localhost:$Port/api/v2/heartbeat" | Out-Null; Write-Host "OK Chroma running on :$Port (pid $($p.Id))"; exit 0 } catch { Start-Sleep 2 }
}
Write-Host "Chroma did not answer the heartbeat -- see logs/chroma.log"; exit 1
