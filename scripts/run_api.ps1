# PowerShell script to run FastAPI server
# Usage: .\scripts\run_api.ps1

Write-Host "Starting FastAPI server..." -ForegroundColor Green
py -m uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000

