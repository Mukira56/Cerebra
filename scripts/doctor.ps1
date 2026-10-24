[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $appRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) { throw 'AI HQ virtual environment is missing. Run .\scripts\setup.ps1 first.' }
Push-Location -LiteralPath $appRoot
try {
    & $venvPython -m ai_hq.manage doctor
    if ($LASTEXITCODE -ne 0) { throw 'Doctor reported at least one required dependency failure.' }
} finally { Pop-Location }
