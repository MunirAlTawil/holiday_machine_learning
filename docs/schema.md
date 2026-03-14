# Database Schema Documentation

## Overview

This document describes the normalized PostgreSQL schema designed to store DataTourisme Point of Interest (POI) data. The schema follows database normalization principles to eliminate data redundancy and support efficient querying.

## Schema Design Principles

- **Normalization**: Third normal form (3NF) to minimize data redundancy
- **Referential Integrity**: Foreign key constraints ensure data consistency
- **Performance**: Strategic indexes on frequently queried columns
- **Extensibility**: Schema supports multiple data sources and categories
- **Audit Trail**: Timestamps track when records are created

## Tables

### 1. data_source

Stores metadata about data sources (e.g., DataTourisme API, other future sources).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-incrementing unique identifier |
| `name` | TEXT | UNIQUE, NOT NULL | Name of the data source (e.g., "datatourisme") |
| `description` | TEXT | | Optional description of the data source |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Timestamp when the record was created |

**Primary Key**: `id`

**Unique Constraints**: `name`

**Indexes**: None (small table, PK index is sufficient)

**Example Data**:
```
id | name          | description                                    | created_at
---|---------------|------------------------------------------------|-------------------
1  | datatourisme  | DataTourisme API - French tourism data platform | 2024-01-15 10:00:00
```

### 2. poi (Point of Interest)

Stores the main POI data including location, description, and metadata.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Unique identifier from source system (e.g., UUID) |
| `label` | TEXT | | Name or title of the POI |
| `description` | TEXT | | Textual description of the POI |
| `latitude` | DOUBLE PRECISION | NOT NULL, CHECK (-90 to 90) | Latitude coordinate (WGS84, decimal degrees) |
| `longitude` | DOUBLE PRECISION | NOT NULL, CHECK (-180 to 180) | Longitude coordinate (WGS84, decimal degrees) |
| `uri` | TEXT | | Uniform Resource Identifier (URL) of the POI |
| `last_update` | TIMESTAMP | | Timestamp of last update from source system |
| `raw_json` | JSONB | | Original JSON payload from API for traceability and debugging |
| `source_id` | INTEGER | FOREIGN KEY → data_source(id) | Reference to the data source |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Timestamp when the record was inserted |

**Primary Key**: `id`

**Foreign Keys**:
- `source_id` → `data_source(id)` ON DELETE SET NULL

**Check Constraints**:
- `chk_latitude_range`: Ensures latitude is between -90 and 90 degrees
- `chk_longitude_range`: Ensures longitude is between -180 and 180 degrees

**Indexes**:
- `idx_poi_location` on `(latitude, longitude)` - Composite index for location-based queries and geospatial operations
- `idx_poi_source_id` on `source_id` - For filtering by data source
- `idx_poi_last_update` on `last_update` - For time-based queries and data freshness checks
- `idx_poi_text_search` - GIN index using `to_tsvector('simple', ...)` for full-text search on `label` and `description` combined (supports multi-language text)
- `idx_poi_raw_json` - **OPTIONAL** GIN index on `raw_json` (commented out by default for performance; enable only if needed for JSON path queries)

**Example Data**:
```
id                                   | label              | latitude  | longitude | source_id
-------------------------------------|--------------------|-----------|-----------|----------
123e4567-e89b-12d3-a456-426614174000| Musée du Louvre    | 48.8606   | 2.3376    | 1
987fcdeb-51a2-43b1-9c8d-123456789abc| Eiffel Tower       | 48.8584   | 2.2945    | 1
```

### 3. category

Stores POI categories/types (e.g., Museum, Restaurant, Hotel, Event).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Auto-incrementing unique identifier |
| `name` | TEXT | UNIQUE, NOT NULL | Category name (e.g., "Museum", "Restaurant") |
| `description` | TEXT | | Optional description of the category |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Timestamp when the record was created |

**Primary Key**: `id`

**Unique Constraints**: `name`

**Indexes**: None (small table, PK index is sufficient)

**Example Data**:
```
id | name       | description                    | created_at
---|------------|--------------------------------|-------------------
1  | Museum     | Museums and cultural sites     | 2024-01-15 10:00:00
2  | Restaurant | Restaurants and dining         | 2024-01-15 10:00:00
3  | Hotel      | Accommodations                | 2024-01-15 10:00:00
4  | Event      | Events and festivals          | 2024-01-15 10:00:00
```

### 4. poi_category (Junction Table)

Implements the many-to-many relationship between POIs and categories. A POI can belong to multiple categories, and a category can contain multiple POIs.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `poi_id` | TEXT | PRIMARY KEY, FOREIGN KEY → poi(id) | Reference to the POI |
| `category_id` | INTEGER | PRIMARY KEY, FOREIGN KEY → category(id) | Reference to the category |

**Primary Key**: `(poi_id, category_id)` - Composite primary key ensures uniqueness

**Foreign Keys**:
- `poi_id` → `poi(id)` ON DELETE CASCADE
- `category_id` → `category(id)` ON DELETE CASCADE

**Indexes**:
- `idx_poi_category_poi_id` on `poi_id` - For efficient lookups by POI
- `idx_poi_category_category_id` on `category_id` - For efficient lookups by category

**Example Data**:
```
poi_id                              | category_id
------------------------------------|------------
123e4567-e89b-12d3-a456-426614174000| 1          (Louvre is a Museum)
123e4567-e89b-12d3-a456-426614174000| 4          (Louvre also hosts Events)
987fcdeb-51a2-43b1-9c8d-123456789abc| 4          (Eiffel Tower hosts Events)
```

## Relationships

### One-to-Many: data_source → poi

- One data source can have many POIs
- A POI belongs to one data source (or NULL if source is deleted)
- Foreign key: `poi.source_id` → `data_source.id`
- Deletion behavior: SET NULL (if data source is deleted, POIs remain but source_id becomes NULL)

### Many-to-Many: poi ↔ category

- One POI can belong to multiple categories
- One category can contain multiple POIs
- Implemented via junction table: `poi_category`
- Foreign keys:
  - `poi_category.poi_id` → `poi.id`
  - `poi_category.category_id` → `category.id`
- Deletion behavior: CASCADE (if POI or category is deleted, related junction records are deleted)

## Entity Relationship Diagram (ERD) - Textual Description

```
┌─────────────────┐
│  data_source    │
├─────────────────┤
│ PK id (SERIAL)   │
│    name (TEXT)   │◄──────┐
│    description   │       │
│    created_at    │       │
└─────────────────┘       │
                           │
                           │ 1:N
                           │
┌─────────────────┐       │
│      poi        │       │
├─────────────────┤       │
│ PK id (TEXT)    │       │
│    label        │       │
│    description  │       │
│    latitude     │       │
│    longitude    │       │
│    uri          │       │
│    last_update  │       │
│ FK source_id    │───────┘
│    created_at   │
└────────┬────────┘
         │
         │ N:M
         │
         │    ┌──────────────────┐
         │    │   poi_category   │
         │    ├──────────────────┤
         │    │ PK,FK poi_id      │
         │    │ PK,FK category_id │
         └────┤                    │────┐
              └──────────────────┘    │
                                      │
                                      │ N:M
                                      │
              ┌─────────────────┐     │
              │    category    │     │
              ├─────────────────┤     │
              │ PK id (SERIAL)  │     │
              │    name (TEXT)  │     │
              │    description  │     │
              │    created_at   │     │
              └─────────────────┘     │
                                      │
                                      ┘
```

### UML Class Diagram Representation

```
[data_source]
+ id: SERIAL (PK)
+ name: TEXT (UNIQUE)
+ description: TEXT
+ created_at: TIMESTAMP

[poi]
+ id: TEXT (PK)
+ label: TEXT
+ description: TEXT
+ latitude: DOUBLE PRECISION (NOT NULL, CHECK -90 to 90)
+ longitude: DOUBLE PRECISION (NOT NULL, CHECK -180 to 180)
+ uri: TEXT
+ last_update: TIMESTAMP
+ raw_json: JSONB
+ source_id: INTEGER (FK → data_source.id)
+ created_at: TIMESTAMP

[category]
+ id: SERIAL (PK)
+ name: TEXT (UNIQUE)
+ description: TEXT
+ created_at: TIMESTAMP

[poi_category]
+ poi_id: TEXT (PK, FK → poi.id)
+ category_id: INTEGER (PK, FK → category.id)

Relationships:
data_source ||--o{ poi : "has"
poi }o--o{ category : "belongs to" (via poi_category)
```

## Index Strategy

### Geospatial Indexes

- **`idx_poi_latitude`** and **`idx_poi_longitude`**: Single-column indexes for range queries on latitude/longitude
- **`idx_poi_location`**: Composite index on `(latitude, longitude)` for:
  - Distance calculations
  - Bounding box queries
  - Spatial joins

### Foreign Key Indexes

- **`idx_poi_source_id`**: Enables efficient filtering by data source
- **`idx_poi_category_poi_id`**: Fast lookup of categories for a POI
- **`idx_poi_category_category_id`**: Fast lookup of POIs in a category

### Temporal Indexes

- **`idx_poi_last_update`**: Supports queries for:
  - Recently updated POIs
  - Data freshness checks
  - Incremental data loading

### Full-Text Search Indexes

- **`idx_poi_text_search`**: GIN index using PostgreSQL's `to_tsvector` function for full-text search
  - Combines `label` and `description` into a searchable text vector
  - Uses `'simple'` language configuration to support multi-language text (French, English, etc.)
  - The 'simple' configuration doesn't use stemming or stop words, making it language-agnostic
  - Supports advanced text search queries using `@@` operator
  - Example query: `WHERE to_tsvector('simple', COALESCE(label, '') || ' ' || COALESCE(description, '')) @@ to_tsquery('simple', 'museum & paris')`

### JSONB Indexes

- **`idx_poi_raw_json`**: **OPTIONAL** - GIN index on `raw_json` column (commented out by default)
  - Can be resource-intensive for large datasets; enable only if you need frequent JSON path queries
  - When enabled, supports efficient JSON path queries using `@>`, `?`, `?&`, `?|` operators
  - Supports queries on nested JSON structures
  - Enables traceability and debugging by preserving original API payload
  - To enable: uncomment the index creation line in `sql/schema.sql`

## Usage Examples

### Insert a POI with Categories

```sql
-- Insert POI
INSERT INTO poi (id, label, description, latitude, longitude, uri, last_update, source_id)
VALUES (
    '123e4567-e89b-12d3-a456-426614174000',
    'Musée du Louvre',
    'The world''s largest art museum',
    48.8606,
    2.3376,
    'https://data.datatourisme.fr/poi/123e4567-e89b-12d3-a456-426614174000',
    '2024-01-15 10:00:00',
    1
);

-- Link POI to categories
INSERT INTO poi_category (poi_id, category_id)
VALUES 
    ('123e4567-e89b-12d3-a456-426614174000', 1),  -- Museum
    ('123e4567-e89b-12d3-a456-426614174000', 4);  -- Event
```

### Query POIs by Category

```sql
SELECT p.id, p.label, p.latitude, p.longitude
FROM poi p
JOIN poi_category pc ON p.id = pc.poi_id
JOIN category c ON pc.category_id = c.id
WHERE c.name = 'Museum';
```

### Query POIs within a Bounding Box

```sql
SELECT id, label, latitude, longitude
FROM poi
WHERE latitude BETWEEN 48.8 AND 48.9
  AND longitude BETWEEN 2.2 AND 2.4;
```

### Full-Text Search on POIs

```sql
-- Search for POIs containing "museum" and "paris" in label or description
-- Uses 'simple' language configuration for multi-language support
SELECT id, label, description
FROM poi
WHERE to_tsvector('simple', COALESCE(label, '') || ' ' || COALESCE(description, ''))
      @@ to_tsquery('simple', 'museum & paris');
```

### Query Original JSON Payload

```sql
-- Extract specific field from raw_json
SELECT id, label, raw_json->>'type' as poi_type
FROM poi
WHERE raw_json ? 'type';

-- Query using JSON path
SELECT id, label
FROM poi
WHERE raw_json @> '{"type": "Museum"}'::jsonb;
```

### Query POIs by Data Source

```sql
SELECT p.id, p.label, ds.name as source_name
FROM poi p
JOIN data_source ds ON p.source_id = ds.id
WHERE ds.name = 'datatourisme';
```

## Data Quality Constraints

### Coordinate Validation

The schema enforces data quality through CHECK constraints:

- **Latitude**: Must be between -90 and 90 degrees (valid WGS84 range)
- **Longitude**: Must be between -180 and 180 degrees (valid WGS84 range)
- **NOT NULL**: Both latitude and longitude are required, ensuring all POIs have valid coordinates

These constraints prevent invalid geographic data from being inserted and ensure data integrity for geospatial queries.

### Traceability

The `raw_json` column stores the original JSON payload from the API, providing:

- **Audit Trail**: Complete record of what was received from the source
- **Debugging**: Ability to investigate data transformation issues
- **Reprocessing**: Option to reprocess data if transformation logic changes
- **Schema Evolution**: Flexibility to extract additional fields as API evolves

## Future Enhancements

Consider the following additions for production use:

1. **PostGIS Extension**: For advanced geospatial queries, consider using PostGIS with geometry columns and spatial indexes
2. **Partitioning**: Partition `poi` table by `source_id` or date if table grows very large
3. **Materialized Views**: Create materialized views for common query patterns
4. **Audit Tables**: Add audit tables to track changes to POI data
5. **Soft Deletes**: Add `deleted_at` column for soft delete functionality
6. **Multi-language Full-Text Search**: Consider language-specific tsvector columns for better multilingual search
7. **JSON Schema Validation**: Add CHECK constraints using `jsonb_typeof` or JSON schema validation for `raw_json`

