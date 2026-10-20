# Starts the Agent2.py backend on http://127.0.0.1:8000 for the VS Code extension.
# Usage (from the repo root):  powershell -ExecutionPolicy Bypass -File .\start_backend.ps1

# Not using $ErrorActionPreference = "Stop": in Windows PowerShell 5.1 it turns any stderr
# from native tools (python, pip, docker) into a fatal error. Exit codes are checked instead.
$root = $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

# (Re)create the venv if it's missing or its base Python no longer exists.
$venvOk = $false
if (Test-Path $venvPython) {
    & $venvPython -c "import sys" 2>$null
    $venvOk = ($LASTEXITCODE -eq 0)
}
if (-not $venvOk) {
    Write-Host "Creating virtual environment in .venv ..."
    if (Test-Path (Join-Path $root ".venv")) { Remove-Item -Recurse -Force (Join-Path $root ".venv") -ErrorAction Stop }
    py -m venv (Join-Path $root ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Failed to create .venv - is Python installed (try 'py --version')?" }
}

# Install / update dependencies only when requirements.txt changed since the last install.
$req = Join-Path $root "requirements.txt"
$stamp = Join-Path $root ".venv\.requirements.stamp"
$reqHash = (Get-FileHash $req).Hash
if (-not (Test-Path $stamp) -or (Get-Content $stamp) -ne $reqHash) {
    Write-Host "Installing Python dependencies ..."
    & $venvPython -m pip install --upgrade pip -q
    & $venvPython -m pip install -r $req
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    Set-Content -Path $stamp -Value $reqHash -Encoding ascii
}

if (-not (Test-Path (Join-Path $root ".env"))) {
    Write-Warning "No .env file found at the repo root - see README for the keys it needs."
}

# test_node needs a running Docker daemon; warn early rather than failing mid-workflow.
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Docker is not running. Start Docker Desktop, or the sandbox test step will fail."
}

# Bind to localhost only: this server can read and write files anywhere on disk.
Write-Host "Starting backend on http://127.0.0.1:8000 (Ctrl+C to stop) ..."
& $venvPython -m uvicorn Agent2:app --app-dir (Join-Path $root "APP") --host 127.0.0.1 --port 8000
