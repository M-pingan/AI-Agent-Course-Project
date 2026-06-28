$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
Set-Location backend

if (-not (Test-Path .venv\Scripts\python.exe)) {
    python -m venv .venv
}

& .venv\Scripts\python.exe -m uvicorn app.main:app --reload
