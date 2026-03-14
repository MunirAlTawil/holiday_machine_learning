-- Migration: Add additional POI fields and ETL run tracking table
-- Migration ID: 002_add_poi_fields_and_etl_run
-- Description: Adds city, department_code to poi table and creates etl_run table for pipeline tracking

-- Add type column if it doesn't exist (for backward compatibility)
ALTER TABLE poi ADD COLUMN IF NOT EXISTS type TEXT;

-- Add city column if it doesn't exist
ALTER TABLE poi ADD COLUMN IF NOT EXISTS city TEXT;

-- Add department_code column if it doesn't exist
ALTER TABLE poi ADD COLUMN IF NOT EXISTS department_code TEXT;

-- Create indexes if they don't exist
CREATE INDEX IF NOT EXISTS idx_poi_type ON poi(type);
CREATE INDEX IF NOT EXISTS idx_poi_city ON poi(city);
CREATE INDEX IF NOT EXISTS idx_poi_department_code ON poi(department_code);

-- Create etl_run table for tracking pipeline runs
CREATE TABLE IF NOT EXISTS etl_run (
    id SERIAL PRIMARY KEY,
    run_type TEXT NOT NULL,
    status TEXT NOT NULL,
    rows_processed INT DEFAULT 0,
    rows_inserted INT DEFAULT 0,
    rows_skipped INT DEFAULT 0,
    started_at TIMESTAMP DEFAULT NOW(),
    finished_at TIMESTAMP NULL,
    message TEXT NULL
);

-- Create index on etl_run for querying by run_type and status
CREATE INDEX IF NOT EXISTS idx_etl_run_type ON etl_run(run_type);
CREATE INDEX IF NOT EXISTS idx_etl_run_status ON etl_run(status);
CREATE INDEX IF NOT EXISTS idx_etl_run_started_at ON etl_run(started_at);

