# VajraNet foundation smoke test (PowerShell)
# Avoids reserved automatic variables such as $HOME / $Host / $PID.
$ErrorActionPreference = "Stop"
$projectRoot = "C:\Users\Aryan\Documents\vajranet"
Set-Location $projectRoot

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  throw "Virtualenv python not found at $python"
}

Write-Host "=== manage.py check ==="
& $python manage.py check
if ($LASTEXITCODE -ne 0) { throw "check failed" }

Write-Host "=== smoke_audit (Django-configured) ==="
& $python manage.py smoke_audit
if ($LASTEXITCODE -ne 0) { throw "smoke_audit failed" }

Write-Host "=== HTTP via runserver ==="
$server = Start-Process -FilePath $python -ArgumentList @("manage.py","runserver","127.0.0.1:8000","--noreload") -PassThru -WindowStyle Hidden
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 1
  try {
    $healthResponse = Invoke-RestMethod "http://127.0.0.1:8000/health/"
    if ($healthResponse.status -eq "ok") { $ready = $true; break }
  } catch {
    # server still starting
  }
}
if (-not $ready) { throw "runserver did not become healthy in time" }

try {
  Write-Host "HEALTH OK"

  $weatherResponse = Invoke-RestMethod "http://127.0.0.1:8000/api/weather/current/?city=Mumbai"
  Write-Host ("MUMBAI {0}C {1} {2}" -f $weatherResponse.temperature_c, $weatherResponse.weather_description, $weatherResponse.source)

  $homeResponse = Invoke-WebRequest "http://127.0.0.1:8000/" -UseBasicParsing
  Write-Host ("HOME_PAGE status={0} bytes={1}" -f $homeResponse.StatusCode, $homeResponse.RawContentLength)

  $lightningResponse = Invoke-RestMethod "http://127.0.0.1:8000/api/lightning/recent/"
  if ($lightningResponse.available) { throw "lightning should be unavailable" }
  Write-Host "LIGHTNING unavailable OK"
}
finally {
  if ($server -and -not $server.HasExited) {
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
  }
  Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

Write-Host "SMOKE TEST PASSED"
