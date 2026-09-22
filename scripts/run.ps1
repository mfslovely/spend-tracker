$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

& (Join-Path $PSScriptRoot "build.ps1")
Write-Host "Starting Spend Tracker at http://127.0.0.1:5000"
Set-Location -LiteralPath $projectRoot
& $venvPython run.py
