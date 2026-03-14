# Script to run database migrations manually
# Note: The API automatically runs sql/02_schema_migration.sql on startup
# This script is for manual verification or if you need to run other migrations

Write-Host "Checking services status..." -ForegroundColor Cyan
docker compose ps

Write-Host "`nChecking POI table structure..." -ForegroundColor Cyan
docker compose exec postgres psql -U holiday -d holiday -c "\d poi"

Write-Host "`nRunning migrations..." -ForegroundColor Cyan

# Migration 001: Add type column
Write-Host "Running 001_add_poi_type.sql..." -ForegroundColor Yellow
Get-Content sql/migrations/001_add_poi_type.sql | docker compose exec -T postgres psql -U holiday -d holiday

# Migration 002: Add city, department_code and etl_run table
Write-Host "Running 002_add_poi_fields_and_etl_run.sql..." -ForegroundColor Yellow
Get-Content sql/migrations/002_add_poi_fields_and_etl_run.sql | docker compose exec -T postgres psql -U holiday -d holiday

# Migration 003: Add missing columns (idempotent)
Write-Host "Running 003_add_missing_poi_columns.sql..." -ForegroundColor Yellow
Get-Content sql/migrations/003_add_missing_poi_columns.sql | docker compose exec -T postgres psql -U holiday -d holiday

# Migration 02: Our new idempotent migration (also runs automatically on API startup)
Write-Host "Running 02_schema_migration.sql..." -ForegroundColor Yellow
Get-Content sql/02_schema_migration.sql | docker compose exec -T postgres psql -U holiday -d holiday

Write-Host "`nVerifying final table structure..." -ForegroundColor Cyan
docker compose exec postgres psql -U holiday -d holiday -c "\d poi"

Write-Host "`nRestarting API to ensure it picks up schema changes..." -ForegroundColor Cyan
docker compose restart api

Write-Host "`nDone! Check API logs to verify migration ran successfully:" -ForegroundColor Green
Write-Host "docker compose logs api | Select-String -Pattern 'migration'" -ForegroundColor Gray

