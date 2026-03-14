-- Migration 004: Add theme column to poi table
-- Extracts theme from POI URI (e.g., restaurant, museum, heritage)

-- Add theme column if it doesn't exist
ALTER TABLE poi ADD COLUMN IF NOT EXISTS theme TEXT;

-- Add index on theme for filtering queries
CREATE INDEX IF NOT EXISTS idx_poi_theme ON poi(theme);

-- Comment on column
COMMENT ON COLUMN poi.theme IS 'Theme extracted from POI URI (e.g., restaurant, museum, heritage)';

