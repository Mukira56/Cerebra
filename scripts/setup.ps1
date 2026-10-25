[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $appRoot '.venv\Scripts\python.exe'
Push-Location -LiteralPath $appRoot
try {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCommand) { throw 'Python 3.13+ is required. Install it only after reviewing and approving the installation.' }
        & $pythonCommand.Source -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
    }
    $pipArguments = @('-m', 'pip', 'install', '--no-cache-dir', '-e', '.[dev]')
    $constraintsPath = Join-Path $appRoot 'requirements.lock'
    if (Test-Path -LiteralPath $constraintsPath) { $pipArguments += @('--constraint', $constraintsPath) }
    & $venvPython @pipArguments
    if ($LASTEXITCODE -ne 0) { throw 'Project dependency installation failed. Check available disk space and the pip output.' }
    Write-Host 'Project dependencies installed in the local .venv. Preparing and checking Cerebra...'
    & $venvPython -m ai_hq.manage doctor
    if ($LASTEXITCODE -ne 0) { throw 'Doctor reported a required dependency failure. Review the checks above.' }
    Write-Host 'Setup complete. Run .\scripts\start.ps1 to launch your private local dashboard.'
} finally { Pop-Location }
