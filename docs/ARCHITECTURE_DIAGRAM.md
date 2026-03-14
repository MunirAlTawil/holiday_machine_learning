# System Architecture Diagram

## Holiday Itinerary Project - Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         DataTourisme API                                │
│                    (External Data Source)                                 │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               │ HTTPS (REST API)
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Batch ETL Pipeline                                   │
│              (src/pipelines/batch_etl.py)                                │
│                                                                          │
│  ┌──────────┐    ┌──────────────┐    ┌──────────┐                     │
│  │ Extract  │───▶│ Transform   │───▶│  Load    │                     │
│  │ (API)    │    │ (Normalize)  │    │ (Upsert) │                     │
│  └──────────┘    └──────────────┘    └────┬─────┘                     │
└───────────────────────────────────────────┼────────────────────────────┘
                                            │
                                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database                                   │
│                    (Relational DB)                                      │
│                                                                          │
│  ┌─────────────┐                                                        │
│  │    poi      │  (Primary table with POI data)                        │
│  │  data_source│                                                        │
│  │  category   │                                                        │
│  │ poi_category│                                                        │
│  │  etl_run    │                                                        │
│  └─────────────┘                                                        │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               │ SQL Query
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Graph Loader Pipeline                                 │
│              (src/pipelines/graph_loader.py)                             │
│                                                                          │
│  Reads from PostgreSQL → Creates Nodes & Relationships                  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               │ Cypher (MERGE)
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Neo4j Graph Database                                  │
│                    (Graph DB)                                            │
│                                                                          │
│  ┌─────────┐      ┌─────────┐      ┌─────────┐      ┌─────────┐        │
│  │  POI    │      │  Type   │      │  City   │      │Department│       │
│  │ (Node)  │      │ (Node)  │      │ (Node)  │      │ (Node)   │        │
│  └────┬────┘      └────┬────┘      └────┬────┘      └────┬─────┘        │
│       │               │                 │                │              │
│       │ HAS_TYPE      │                 │                │              │
│       ├───────────────┘                 │                │              │
│       │                                 │                │              │
│       │ IN_CITY                         │                │              │
│       ├─────────────────────────────────┘                │              │
│       │                                                  │              │
│       │ IN_DEPARTMENT                                    │              │
│       └──────────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────────────────┘
                               │
                               │ REST API
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    FastAPI Service                                       │
│                    (src/api/main.py)                                     │
│                                                                          │
│  Endpoints:                                                              │
│  - GET /pois          (PostgreSQL)                                      │
│  - GET /stats         (PostgreSQL)                                      │
│  - GET /charts/*      (PostgreSQL)                                      │
│  - GET /graph/summary (Neo4j)                                           │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               │ HTTP
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Streamlit Dashboard                                   │
│                    (src/dashboard/app.py)                                │
│                                                                          │
│  Pages:                                                                  │
│  - Overview                                                              │
│  - Types Chart                                                           │
│  - Updates Chart                                                         │
│  - Data Quality                                                          │
│  - POI Explorer                                                          │
│  - Map Explorer                                                          │
│  - Graph (Neo4j statistics)                                             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                    Scheduler (CRON)                                      │
│                    (holiday_scheduler container)                         │
│                                                                          │
│  Hourly Schedule:                                                        │
│  1. Run batch_etl.py (Extract → Transform → Load to PostgreSQL)        │
│  2. Run graph_loader.py (Load from PostgreSQL → Neo4j)                  │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### Data Sources
- **DataTourisme API**: External REST API providing French tourism POI data
- **Rate Limiting**: 10 req/s sustained, 1000 req/hour

### ETL Pipeline
- **Extract**: Fetches POI data from DataTourisme API with pagination
- **Transform**: Normalizes and cleans data (coordinates, types, metadata)
- **Load**: Smart UPSERT into PostgreSQL (updates only if newer)

### Databases

#### PostgreSQL (Primary)
- **Purpose**: Transactional data, complex queries, aggregations
- **Schema**: Normalized relational schema with foreign keys
- **Tables**: `poi`, `data_source`, `category`, `poi_category`, `etl_run`

#### Neo4j (Secondary)
- **Purpose**: Relationship queries, graph analytics
- **Model**: Graph with nodes and relationships
- **Nodes**: `POI`, `Type`, `City`, `Department`
- **Relationships**: `HAS_TYPE`, `IN_CITY`, `IN_DEPARTMENT`

### API Layer
- **FastAPI**: REST API exposing both PostgreSQL and Neo4j data
- **Endpoints**: 13 endpoints for POI queries, statistics, charts, and graph summary
- **Health Checks**: Monitors both PostgreSQL and Neo4j connectivity

### Frontend
- **Streamlit**: Multi-page dashboard with interactive visualizations
- **Features**: Charts, maps, data quality analysis, graph statistics

### Automation
- **Scheduler**: CRON-based hourly execution
- **Pipeline**: Batch ETL → Graph Loader (sequential execution)
- **Logging**: All execution logged to `/var/log/cron.log`

## Data Flow Sequence

1. **Hourly Trigger**: CRON scheduler fires at minute 0
2. **ETL Execution**: 
   - Fetch from DataTourisme API
   - Transform and validate data
   - Load into PostgreSQL (UPSERT)
3. **Graph Load**:
   - Read POIs from PostgreSQL
   - Create/update nodes in Neo4j (MERGE)
   - Create/update relationships (MERGE)
4. **API Serving**: FastAPI serves data from both databases
5. **Dashboard Display**: Streamlit visualizes data via API

## Technology Stack

- **Languages**: Python 3.11
- **Databases**: PostgreSQL 16, Neo4j 5.15
- **API Framework**: FastAPI
- **Frontend**: Streamlit
- **Containerization**: Docker, Docker Compose
- **Scheduling**: CRON
- **ORM**: SQLAlchemy (PostgreSQL)
- **Graph Driver**: Neo4j Python Driver

## Network Architecture

All services run in Docker containers on the same network (`holiday_network`):

- **postgres**: `holiday_postgres` (port 5432)
- **neo4j**: `holiday_neo4j` (ports 7474 HTTP, 7687 Bolt)
- **api**: `holiday_api` (port 8000)
- **dashboard**: `holiday_dashboard` (port 8501)
- **holiday_scheduler**: `holiday_scheduler` (no exposed ports)

Services communicate via Docker service names (e.g., `postgres`, `neo4j`, `api`).

---

*For detailed graph model, see: [GRAPH_MODEL.md](GRAPH_MODEL.md)*

