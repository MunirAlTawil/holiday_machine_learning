-- Migration: Add missing POI columns (type, city, department_code)
-- Migration ID: 003_add_missing_poi_columns
-- Description: Adds type, city, and department_code columns to poi table if they don't exist
--              Also ensures indexes exist for performance

-- Add type column if it doesn't exist
ALTER TABLE poi ADD COLUMN IF NOT EXISTS type TEXT;

-- Add city column if it doesn't exist
ALTER TABLE poi ADD COLUMN IF NOT EXISTS city TEXT;

-- Add department_code column if it doesn't exist
ALTER TABLE poi ADD COLUMN IF NOT EXISTS department_code TEXT;

-- Create indexes for performance (if they don't exist)
CREATE INDEX IF NOT EXISTS idx_poi_type ON poi(type);
CREATE INDEX IF NOT EXISTS idx_poi_last_update ON poi(last_update);

