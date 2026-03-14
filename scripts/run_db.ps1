# PowerShell script to start PostgreSQL database
# Usage: .\scripts\run_db.ps1

Write-Host "Starting PostgreSQL database with Docker Compose..." -ForegroundColor Green
docker compose up -d

Write-Host "Waiting for database to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

Write-Host "Database is running!" -ForegroundColor Green
Write-Host "PostgreSQL is available at localhost:5432" -ForegroundColor Cyan

