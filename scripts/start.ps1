[CmdletBinding()]
param([ValidateRange(1024, 65535)][int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $appRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) { throw 'AI HQ virtual environment is missing. Run .\scripts\setup.ps1 first.' }
Push-Location -LiteralPath $appRoot
try {
    & $venvPython -m ai_hq.manage start --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'AI HQ could not start. Review the error and data\server.log.' }
} finally { Pop-Location }
