-- PostgreSQL Schema for DataTourisme POIs
-- Normalized schema to store POIs, categories, and their relationships

-- Table: data_source
-- Stores information about data sources (e.g., DataTourisme API)
CREATE TABLE IF NOT EXISTS data_source (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Table: poi (Point of Interest)
-- Stores the main POI data
CREATE TABLE IF NOT EXISTS poi (
    id TEXT PRIMARY KEY,
    label TEXT,
    description TEXT,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    uri TEXT,
    type TEXT,
    last_update TIMESTAMP,
    raw_json JSONB,
    source_id INTEGER REFERENCES data_source(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    -- Check constraints for valid coordinate ranges
    CONSTRAINT chk_latitude_range CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT chk_longitude_range CHECK (longitude BETWEEN -180 AND 180)
);

-- Table: category
-- Stores POI categories (e.g., Museum, Restaurant, Hotel, etc.)
CREATE TABLE IF NOT EXISTS category (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Table: poi_category (Junction Table)
-- Many-to-many relationship between POIs and categories
CREATE TABLE IF NOT EXISTS poi_category (
    poi_id TEXT REFERENCES poi(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES category(id) ON DELETE CASCADE,
    PRIMARY KEY (poi_id, category_id)
);

-- Indexes for performance optimization

-- Composite index for geospatial queries (latitude, longitude)
CREATE INDEX IF NOT EXISTS idx_poi_location ON poi(latitude, longitude);

-- Index on source_id for filtering by data source
CREATE INDEX IF NOT EXISTS idx_poi_source_id ON poi(source_id);

-- Index on last_update for time-based queries
CREATE INDEX IF NOT EXISTS idx_poi_last_update ON poi(last_update);

-- Index on type for filtering by POI type
CREATE INDEX IF NOT EXISTS idx_poi_type ON poi(type);

-- GIN index for full-text search on label and description
-- Uses 'simple' language configuration to support multi-language text (French, English, etc.)
CREATE INDEX IF NOT EXISTS idx_poi_text_search ON poi
USING GIN (to_tsvector('simple', COALESCE(label, '') || ' ' || COALESCE(description, '')));

-- OPTIONAL: JSONB GIN index can be heavy; enable only if you need JSON path queries.
-- CREATE INDEX IF NOT EXISTS idx_poi_raw_json ON poi USING GIN (raw_json);

-- Index on poi_category for efficient lookups
CREATE INDEX IF NOT EXISTS idx_poi_category_poi_id ON poi_category(poi_id);
CREATE INDEX IF NOT EXISTS idx_poi_category_category_id ON poi_category(category_id);

-- Insert default data source
INSERT INTO data_source (name, description)
VALUES ('datatourisme', 'DataTourisme API - French tourism data platform')
ON CONFLICT (name) DO NOTHING;

