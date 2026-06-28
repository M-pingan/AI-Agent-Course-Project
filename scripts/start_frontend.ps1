$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
Set-Location frontend

if (-not $env:VITE_API_BASE_URL) {
    $env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
}

npm run dev
