-- Migration: Add type column to poi table
-- Migration ID: 001_add_poi_type
-- Description: Adds a type column to the poi table for storing POI type/category from DataTourisme

-- Add type column if it doesn't exist
ALTER TABLE poi ADD COLUMN IF NOT EXISTS type TEXT;

-- Create index on type column if it doesn't exist
CREATE INDEX IF NOT EXISTS idx_poi_type ON poi(type);

