param([int]$Port = 8091, [string]$PagesOrigin = 'https://currentjob.github.io')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$runtimeDir = Join-Path $projectRoot '.local'
New-Item -ItemType Directory -Force $runtimeDir | Out-Null
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use. Check the existing backend before starting another."
}
$env:CWP_HOST = '127.0.0.1'
$env:CWP_PORT = [string]$Port
$dbPath = Join-Path $runtimeDir 'city-walk-planner.db'
$legacyDb = Join-Path $runtimeDir 'harbor-lantern.db'
if (-not (Test-Path $dbPath) -and (Test-Path $legacyDb)) { $dbPath = $legacyDb }  # keep trips saved before the rename
$env:CWP_DB_PATH = $dbPath
$env:CWP_ALLOWED_ORIGINS = $PagesOrigin
$env:PYTHONUTF8 = '1'
$backend = Start-Process -FilePath (Join-Path $projectRoot '.venv\Scripts\python.exe') `
    -ArgumentList 'run.py' -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $runtimeDir 'backend.stdout.log') `
    -RedirectStandardError (Join-Path $runtimeDir 'backend.stderr.log')
$backend.Id | Set-Content (Join-Path $runtimeDir 'backend.pid')
Write-Output "Backend PID: $($backend.Id); http://127.0.0.1:$Port"
