# Holiday Itinerary - System Architecture

## Overview

The Holiday Itinerary project is a Data Engineering platform for processing and serving tourism Point of Interest (POI) data. The system follows a modern microservices architecture with Docker containerization, automated batch processing, and dual-database storage (PostgreSQL + Neo4j).

## Architecture Diagram

See `docs/uml.puml` for PlantUML diagram, or `docs/ARCHITECTURE_DIAGRAM.md` for ASCII diagram.

## System Components

### 1. Data Sources

**DataTourisme API**
- Source: French tourism data platform (https://api.datatourisme.fr)
- Data Format: JSON (GeoJSON-compatible)
- Authentication: API Key required
- Rate Limiting: Implemented with retry logic

### 2. Extraction & Transformation Layer

**Batch ETL Pipeline** (`src/pipelines/batch_etl.py`)
- **Purpose**: Extract POI data from DataTourisme API, transform, and load into PostgreSQL
- **Schedule**: Hourly (via cron)
- **Features**:
  - Pagination support
  - Rate limiting and retry logic
  - Data normalization
  - UPSERT logic (idempotent)
  - Pipeline run tracking

**Graph Loader** (`src/pipelines/graph_loader.py`)
- **Purpose**: Load POI data from PostgreSQL into Neo4j graph database
- **Schedule**: Runs after batch ETL (hourly)
- **Features**:
  - Idempotent MERGE operations
  - Batch processing
  - Creates nodes and relationships
  - Constraint/index creation

### 3. Storage Layer

#### PostgreSQL (Primary Database)
- **Purpose**: Relational storage for POI data
- **Schema**: See `sql/schema.sql`
- **Key Tables**:
  - `poi`: Main POI data (id, label, type, city, department_code, coordinates, etc.)
  - `pipeline_runs`: ETL execution tracking
- **Indexes**: Location (lat/lng), type, last_update, full-text search (GIN)
- **Constraints**: Coordinate range validation

#### Neo4j (Graph Database)
- **Purpose**: Graph storage for relationship queries
- **Model**: See `docs/GRAPH_MODEL.md`
- **Nodes**:
  - `:POI` - Point of Interest entities
  - `:Type` - POI types (Museum, Restaurant, etc.)
  - `:City` - City locations
  - `:Department` - Department codes
- **Relationships**:
  - `(:POI)-[:HAS_TYPE]->(:Type)`
  - `(:POI)-[:IN_CITY]->(:City)`
  - `(:POI)-[:IN_DEPARTMENT]->(:Department)`
- **Constraints**: Unique constraints on POI.id, Type.name, City.name, Department.code

### 4. API Layer

**FastAPI Application** (`src/api/main.py`)
- **Framework**: FastAPI (Python)
- **Port**: 8000
- **Documentation**: Swagger UI at `/docs`
- **Endpoints**:
  - `GET /` - API info
  - `GET /health` - Health check with DB connectivity
  - `GET /pois` - List POIs (pagination, search, filtering)
  - `GET /pois/geojson` - GeoJSON format output
  - `GET /pois/{poi_id}` - Single POI by ID
  - `GET /stats` - Statistics (total POIs, coordinates, types)
  - `GET /stats/categories` - Category statistics
  - `GET /pois/recent` - Recent POIs
  - `GET /stats/coordinates` - Coordinate list
  - `GET /charts/types` - Type distribution
  - `GET /charts/updates` - Update timeline
  - `GET /quality` - Data quality metrics
  - `GET /pipeline/last-run` - Last ETL run status
  - `GET /graph/summary` - Neo4j graph statistics
  - `POST /graph/sync` - Manual graph synchronization

**Analytics Functions** (`src/analytics/analytics.py`)
- POI counts by category
- Recent POIs
- Coordinate lists
- Type distributions
- Update timelines
- Bounding box queries
- Text search

### 5. Frontend Layer

**Streamlit Dashboard** (`src/dashboard/app.py`)
- **Framework**: Streamlit (Python)
- **Port**: 8501
- **Features**:
  - Interactive map visualization (Folium)
  - POI statistics and charts
  - Search and filtering
  - Graph database statistics
  - System status indicators
- **Pages**: Home, Map, Statistics, Charts, Quality, Graph

### 6. Scheduler

**Cron-based Scheduler** (`Dockerfile.scheduler`)
- **Container**: `holiday_scheduler`
- **Schedule**: Hourly at minute 0 (`0 * * * *`)
- **Tasks**:
  1. Run batch ETL pipeline
  2. Run graph loader (after ETL)
- **Logging**: `/var/log/cron.log`

## Data Flow

```
1. DataTourisme API
   ↓
2. Batch ETL Pipeline (hourly)
   ↓
3. PostgreSQL (primary storage)
   ↓
4. Graph Loader (after ETL)
   ↓
5. Neo4j (graph storage)
   ↓
6. FastAPI (serves both databases)
   ↓
7. Streamlit Dashboard (consumes API)
```

## Docker Architecture

### Services

1. **postgres** - PostgreSQL 16 database
2. **neo4j** - Neo4j 5.15 graph database
3. **api** - FastAPI application
4. **dashboard** - Streamlit dashboard
5. **holiday_scheduler** - Cron-based ETL scheduler

### Network

All services run on the default Docker network (`holiday_network`), allowing service-to-service communication via service names.

### Volumes

- `postgres_data` - PostgreSQL data persistence
- `neo4j_data` - Neo4j data persistence
- `neo4j_logs` - Neo4j logs
- `scheduler_logs` - Scheduler logs

## Environment Variables

### PostgreSQL
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`

### Neo4j
- `NEO4J_URI` (for Python driver: `bolt://neo4j:7687`)
- `NEO4J_USER`, `NEO4J_PASSWORD`

### DataTourisme
- `DATATOURISME_API_KEY` (required)
- `DATATOURISME_BASE_URL` (default: https://api.datatourisme.fr)

### Graph Sync
- `GRAPH_SYNC_TOKEN` (optional, for POST /graph/sync authentication)

## Deployment

### Local Development
```bash
docker compose up -d --build
```

### Production
- Use `.github/workflows/release.yaml` for automated releases
- Tag releases with `v*.*.*` format
- Docker images are built and tagged

## Monitoring & Health Checks

- **API Health**: `GET /health` endpoint
- **PostgreSQL**: Health check via `pg_isready`
- **Neo4j**: Health check via HTTP endpoint
- **Scheduler**: Logs in `/var/log/cron.log`

## Security Considerations

- Environment variables for sensitive data (API keys, passwords)
- Optional token-based authentication for `/graph/sync`
- Database credentials not exposed in code
- `.env` file in `.gitignore`

## Scalability

- **Horizontal Scaling**: API and dashboard can be scaled independently
- **Database**: PostgreSQL supports read replicas
- **Graph Database**: Neo4j supports clustering (Enterprise edition)
- **Caching**: Can add Redis for API response caching

## Future Enhancements

1. **Streaming Pipeline**: Real-time data ingestion (Kafka, Spark Streaming)
2. **ML/Analytics**: Predictive models for POI recommendations
3. **Authentication**: JWT-based authentication for API
4. **Monitoring**: Prometheus + Grafana for metrics
5. **Logging**: Centralized logging (ELK stack)

---

*Last Updated: 2026-02-11*

