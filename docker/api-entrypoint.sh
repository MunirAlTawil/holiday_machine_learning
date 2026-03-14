#!/bin/bash
set -e

echo "Starting API container..."

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
until PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c '\q' 2>/dev/null; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 1
done

echo "PostgreSQL is ready!"

# Run migration
echo "Running database migration..."
if PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -f /app/sql/02_schema_migration.sql; then
  echo "Migration completed successfully"
else
  echo "ERROR: Migration failed!"
  exit 1
fi

# Start the API
echo "Starting FastAPI server..."
exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000

