param([switch]$Lan, [int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.env')) { throw 'Run Setup-Windows.ps1 first.' }
if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'Python environment is missing. Run setup first.' }
$BindAddress = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host $BindAddress --port $Port
if ($LASTEXITCODE -ne 0) { throw 'Attendance server stopped with an error.' }
