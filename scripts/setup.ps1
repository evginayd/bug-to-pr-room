# Sets up the demo app on Windows (PowerShell) and runs its tests.
# Usage, from the repository root:  .\scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\demo-app")

if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
& .\.venv\Scripts\python.exe -m pytest -q

Write-Host ""
Write-Host "Demo app is ready. To run it:"
Write-Host "  cd demo-app; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload"
Write-Host "Then open http://127.0.0.1:8000/docs"
