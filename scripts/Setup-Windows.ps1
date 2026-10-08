param([ValidateSet('Native','Docker')][string]$Database = 'Native')
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    & py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 with the Windows Python launcher first.' }
}
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (-not (Test-Path '.env')) {
    $JwtSecret = & .\.venv\Scripts\python.exe -c 'import secrets; print(secrets.token_urlsafe(48))'
    $DockerPassword = & .\.venv\Scripts\python.exe -c 'import secrets; print(secrets.token_hex(24))'
    if ($Database -eq 'Docker') {
        $DbUrl = "postgresql+psycopg://attendance:$DockerPassword@localhost:5432/attendance"
    } else {
        $DbHost = Read-Host 'PostgreSQL host (Enter for localhost)'
        if (-not $DbHost) { $DbHost = 'localhost' }
        $DbPort = Read-Host 'PostgreSQL port (Enter for 5432)'
        if (-not $DbPort) { $DbPort = '5432' }
        $DbName = Read-Host 'Database name (Enter for attendance)'
        if (-not $DbName) { $DbName = 'attendance' }
        $DbUser = Read-Host 'Database user (Enter for attendance)'
        if (-not $DbUser) { $DbUser = 'attendance' }
        $SecurePassword = Read-Host 'Database password' -AsSecureString
        $RawPassword = [System.Net.NetworkCredential]::new('', $SecurePassword).Password
        $EncodedPassword = [Uri]::EscapeDataString($RawPassword)
        $EncodedUser = [Uri]::EscapeDataString($DbUser)
        $EncodedDatabase = [Uri]::EscapeDataString($DbName)
        $DbUrl = "postgresql+psycopg://${EncodedUser}:${EncodedPassword}@${DbHost}:${DbPort}/${EncodedDatabase}"
        $RawPassword = $null
    }
    $Lines = @("DATABASE_URL=$DbUrl", "JWT_SECRET=$JwtSecret", 'COOKIE_SECURE=false', 'SESSION_HOURS=8', "DB_PASSWORD=$DockerPassword")
    [IO.File]::WriteAllLines((Join-Path $ProjectRoot '.env'), $Lines, [Text.UTF8Encoding]::new($false))
    $WindowsIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls .env /inheritance:r /grant:r "${WindowsIdentity}:(F)" 'SYSTEM:(F)' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict .env access. Set its Windows permissions before continuing.' }
    Write-Host 'Created local .env with generated keys. Existing files are never overwritten.'
}
if ($Database -eq 'Docker') {
    & docker compose up -d --wait db
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL startup failed. Check Docker Desktop and port 5432.' }
}
# --app-dir is a Uvicorn option; initialization uses Python's working directory instead.
Push-Location backend
try {
    # The root .env is selected explicitly through the process environment via dotenv.
    & ..\.venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv('../.env'); from app.cli import main; import sys; sys.argv=['app.cli','init']; main()"
    if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed. Check your PostgreSQL connection.' }
    & ..\.venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv('../.env'); from app.cli import main; import sys; sys.argv=['app.cli','create-admin','--if-missing']; main()"
    if ($LASTEXITCODE -ne 0) { throw 'Administrator creation did not complete. Existing accounts are preserved.' }
} finally { Pop-Location }
Write-Host 'Setup complete. Start with .\scripts\Start-Windows.ps1.'
