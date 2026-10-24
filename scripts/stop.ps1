[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $appRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) { throw 'AI HQ virtual environment is missing; no process will be terminated.' }
Push-Location -LiteralPath $appRoot
try {
    & $venvPython -m ai_hq.manage stop
    if ($LASTEXITCODE -ne 0) { throw 'AI HQ could not verify or stop its managed server. No unrelated process should be terminated.' }
} finally { Pop-Location }
