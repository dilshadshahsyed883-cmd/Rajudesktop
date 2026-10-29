# Creates the private venv this skill's scripts run in: scripts\.venv
# Usage: powershell -ExecutionPolicy Bypass -File <skill>\scripts\setup.ps1
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$venv = Join-Path $here ".venv"
$py = Join-Path $venv "Scripts\python.exe"

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
    Write-Error "uv not found on PATH. Install it (https://docs.astral.sh/uv/) and re-run."
}

if (-not (Test-Path $py)) {
    & $uv venv $venv --python 3.12
    if ($LASTEXITCODE -ne 0) { throw "uv venv failed" }
}

& $uv pip install --python $py uiautomation comtypes mss pillow
if ($LASTEXITCODE -ne 0) { throw "package install failed" }

& $py -c "import uiautomation, mss, PIL; print('venv ok:', uiautomation.VERSION if hasattr(uiautomation,'VERSION') else 'uiautomation', mss.__version__, PIL.__version__)"
Write-Output "Python: $py"
