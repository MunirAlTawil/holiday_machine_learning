-- Migration: Add missing POI columns (city, department_code)
-- Migration ID: 02_schema_migration
-- Description: Idempotent migration that adds city and department_code columns to poi table if they don't exist
-- Safe to run multiple times - will not drop data or cause errors if columns already exist

-- Add city column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'poi' 
        AND column_name = 'city'
    ) THEN
        ALTER TABLE poi ADD COLUMN city TEXT;
        RAISE NOTICE 'Added column: poi.city';
    ELSE
        RAISE NOTICE 'Column poi.city already exists, skipping';
    END IF;
END $$;

-- Add department_code column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'poi' 
        AND column_name = 'department_code'
    ) THEN
        ALTER TABLE poi ADD COLUMN department_code TEXT;
        RAISE NOTICE 'Added column: poi.department_code';
    ELSE
        RAISE NOTICE 'Column poi.department_code already exists, skipping';
    END IF;
END $$;

