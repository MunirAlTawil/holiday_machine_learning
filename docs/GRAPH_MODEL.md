# Neo4j Graph Database Model

## Overview

The Holiday Itinerary project uses Neo4j as a graph database to complement the relational PostgreSQL database. This dual-database approach leverages the strengths of each database type:

- **PostgreSQL**: Excellent for structured queries, aggregations, and transactional data
- **Neo4j**: Optimal for relationship queries, graph traversals, and graph analytics

## Why Graph Database?

Graph databases are particularly well-suited for tourism data because:

1. **Relationship Queries**: Easily find all POIs of a specific type in a city, or all cities with a certain type of POI
2. **Graph Analytics**: Discover patterns, clusters, and relationships that are difficult to express in SQL
3. **Recommendation Systems**: Enable graph-based recommendations (e.g., "POIs similar to this one")
4. **Geographic Relationships**: Model spatial relationships and hierarchies (POI → City → Department → Region)
5. **Performance**: Graph queries for relationship-heavy operations are faster than SQL joins

## Graph Model

### Nodes

#### POI Node
- **Label**: `POI`
- **Properties**:
  - `id` (String, UNIQUE): Unique identifier from PostgreSQL
  - `label` (String): POI name/title
  - `type` (String): POI type/category
  - `latitude` (Float): Geographic latitude
  - `longitude` (Float): Geographic longitude
  - `uri` (String): DataTourisme URI
  - `last_update` (String): ISO 8601 timestamp

**Example:**
```cypher
(:POI {
  id: "123e4567-e89b-12d3-a456-426614174000",
  label: "Musée du Louvre",
  type: "Museum",
  latitude: 48.8606,
  longitude: 2.3376,
  uri: "https://data.datatourisme.fr/poi/...",
  last_update: "2024-01-15T10:30:00Z"
})
```

#### Type Node
- **Label**: `Type`
- **Properties**:
  - `name` (String, UNIQUE): Type name (e.g., "Museum", "Restaurant", "Hotel")

**Example:**
```cypher
(:Type {name: "Museum"})
```

#### City Node (Optional)
- **Label**: `City`
- **Properties**:
  - `name` (String, UNIQUE): City name

**Example:**
```cypher
(:City {name: "Paris"})
```

#### Department Node (Optional)
- **Label**: `Department`
- **Properties**:
  - `code` (String, UNIQUE): French department code (e.g., "75", "13", "69")

**Example:**
```cypher
(:Department {code: "75"})
```

### Relationships

#### HAS_TYPE
- **From**: `POI`
- **To**: `Type`
- **Direction**: `(:POI)-[:HAS_TYPE]->(:Type)`
- **Description**: Links a POI to its type/category

**Example:**
```cypher
(:POI {id: "123..."})-[:HAS_TYPE]->(:Type {name: "Museum"})
```

#### IN_CITY (Optional)
- **From**: `POI`
- **To**: `City`
- **Direction**: `(:POI)-[:IN_CITY]->(:City)`
- **Description**: Links a POI to the city where it's located
- **Note**: Only created if `city` property exists in PostgreSQL

**Example:**
```cypher
(:POI {id: "123..."})-[:IN_CITY]->(:City {name: "Paris"})
```

#### IN_DEPARTMENT (Optional)
- **From**: `POI`
- **To**: `Department`
- **Direction**: `(:POI)-[:IN_DEPARTMENT]->(:Department)`
- **Description**: Links a POI to the French department where it's located
- **Note**: Only created if `department_code` property exists in PostgreSQL

**Example:**
```cypher
(:POI {id: "123..."})-[:IN_DEPARTMENT]->(:Department {code: "75"})
```

## Constraints and Indexes

### Unique Constraints
```cypher
CREATE CONSTRAINT poi_id_unique FOR (p:POI) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT type_name_unique FOR (t:Type) REQUIRE t.name IS UNIQUE;
CREATE CONSTRAINT department_code_unique FOR (d:Department) REQUIRE d.code IS UNIQUE;
CREATE CONSTRAINT city_name_unique FOR (c:City) REQUIRE c.name IS UNIQUE;
```

### Indexes
```cypher
CREATE INDEX poi_type_index FOR (p:POI) ON (p.type);
```

## Example Queries

### Find all Museums in Paris
```cypher
MATCH (p:POI)-[:HAS_TYPE]->(t:Type {name: "Museum"})
MATCH (p)-[:IN_CITY]->(c:City {name: "Paris"})
RETURN p.label, p.latitude, p.longitude
LIMIT 10
```

### Count POIs by Type
```cypher
MATCH (p:POI)-[:HAS_TYPE]->(t:Type)
RETURN t.name AS type, count(p) AS count
ORDER BY count DESC
```

### Find all Cities with Museums
```cypher
MATCH (p:POI)-[:HAS_TYPE]->(t:Type {name: "Museum"})
MATCH (p)-[:IN_CITY]->(c:City)
RETURN DISTINCT c.name AS city, count(p) AS museum_count
ORDER BY museum_count DESC
```

### Find POIs in a Department
```cypher
MATCH (p:POI)-[:IN_DEPARTMENT]->(d:Department {code: "75"})
RETURN p.label, p.type
LIMIT 20
```

### Graph Statistics
```cypher
// Count nodes
MATCH (p:POI) RETURN count(p) AS poi_count
MATCH (t:Type) RETURN count(t) AS type_count

// Count relationships
MATCH ()-[r:HAS_TYPE]->() RETURN count(r) AS has_type_count
```

## Data Loading

The graph database is automatically populated from PostgreSQL after each ETL run:

1. **ETL Pipeline** (`src/pipelines/batch_etl.py`): Loads data into PostgreSQL
2. **Graph Loader** (`src/pipelines/graph_loader.py`): Reads from PostgreSQL and loads into Neo4j
3. **Scheduler**: Runs both pipelines hourly via CRON

The graph loader uses **MERGE** operations to ensure idempotency - it's safe to run multiple times without creating duplicates.

## Integration with PostgreSQL

The graph database is a **read replica** of the PostgreSQL database for relationship queries:

- **PostgreSQL**: Primary database for transactional operations, complex aggregations, and full-text search
- **Neo4j**: Secondary database for graph queries and relationship analytics

Data flows: `API → ETL → PostgreSQL → Graph Loader → Neo4j`

## Use Cases

1. **Type-Based Recommendations**: "Find all restaurants near museums"
2. **Geographic Analysis**: "Which departments have the most hotels?"
3. **Relationship Traversal**: "Find all POIs connected to a specific city through multiple relationships"
4. **Graph Analytics**: Community detection, centrality analysis, path finding

## Performance Considerations

- **Batch Loading**: POIs are loaded in batches (default: 100) for optimal performance
- **Indexes**: Type index on POI nodes speeds up type-based queries
- **Constraints**: Unique constraints ensure data integrity and improve query performance
- **MERGE Operations**: Idempotent loading allows safe re-runs without duplicates

---

*For architecture diagram, see: [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md)*

