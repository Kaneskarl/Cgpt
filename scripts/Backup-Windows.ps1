param([string]$OutputDirectory = 'backups')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& .\.venv\Scripts\python.exe scripts\database-backup.py backup --directory $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw 'Backup failed. Check PostgreSQL tools and disk space.' }
