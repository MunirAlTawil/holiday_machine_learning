# Architecture Diagram

## Holiday Itinerary Data Engineering Project

This document contains the architecture diagram in Mermaid format. You can render it in:
- GitHub/GitLab (native Mermaid support)
- VS Code with Mermaid extension
- Online: https://mermaid.live
- Convert to PNG using: `mmdc -i architecture.mmd -o architecture.png` (requires mermaid-cli)

## System Architecture

```mermaid
graph TB
    subgraph External["🌐 External Services"]
        API[DataTourisme API<br/>https://api.datatourisme.fr<br/>REST API with API Key]
    end

    subgraph ETL["🔄 ETL Pipeline"]
        direction TB
        Extract[Extract Step<br/>fetch_pois_from_api<br/>Rate Limiting: 10 req/s<br/>Pagination Support]
        Transform[Transform Step<br/>transform_poi<br/>Coordinate Extraction<br/>Data Normalization]
        Load[Load Step<br/>load_pois_to_database<br/>Smart UPSERT Logic<br/>Batch Processing]
    end

    subgraph Scheduler["⏰ Cron Scheduler"]
        Cron[Cron Daemon<br/>Schedule: 0 * * * *<br/>Hourly Execution]
        ETLScript[run_etl.sh<br/>Batch ETL Pipeline]
        GraphScript[Graph Loader<br/>run_graph_load]
    end

    subgraph Storage["💾 Data Storage"]
        PostgreSQL[(PostgreSQL 16<br/>Port: 5432<br/>Tables: poi, pipeline_runs<br/>data_source)]
        Neo4j[(Neo4j 5.15<br/>Ports: 7474 HTTP<br/>7687 Bolt<br/>Graph Database)]
    end

    subgraph Services["🚀 Application Services"]
        FastAPI[FastAPI Service<br/>Port: 8000<br/>REST API<br/>Auto-migration on startup]
        Dashboard[Streamlit Dashboard<br/>Port: 8501<br/>Interactive UI<br/>Multi-page App]
    end

    subgraph Users["👥 Users"]
        APIUser[API Consumers<br/>REST Clients]
        DashboardUser[Dashboard Users<br/>Web Browser]
    end

    %% External to ETL
    API -->|HTTPS<br/>X-API-Key Header<br/>JSON Response| Extract

    %% ETL Flow
    Extract -->|Raw POI Objects| Transform
    Transform -->|Cleaned POI Data| Load

    %% ETL to Storage
    Load -->|UPSERT<br/>Insert/Update| PostgreSQL
    Load -->|Pipeline Run Tracking| PostgreSQL

    %% Scheduler to ETL
    Cron -->|Hourly Trigger| ETLScript
    ETLScript -->|Executes| Extract
    ETLScript -->|After ETL| GraphScript

    %% Graph Loader
    PostgreSQL -->|Read POIs| GraphScript
    GraphScript -->|MERGE Nodes/Relationships| Neo4j

    %% Storage to Services
    PostgreSQL -->|SQL Queries<br/>Geospatial Queries| FastAPI
    Neo4j -->|Cypher Queries<br/>Graph Traversals| FastAPI

    %% Services to Users
    FastAPI -->|REST API<br/>JSON Responses| APIUser
    FastAPI -->|HTTP API<br/>CORS Enabled| Dashboard
    Dashboard -->|Interactive UI<br/>Charts & Maps| DashboardUser

    %% Styling
    classDef external fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef etl fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef storage fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef service fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef scheduler fill:#fff9c4,stroke:#f57f17,stroke-width:2px
    classDef user fill:#fce4ec,stroke:#880e4f,stroke-width:2px

    class API external
    class Extract,Transform,Load etl
    class PostgreSQL,Neo4j storage
    class FastAPI,Dashboard service
    class Cron,ETLScript,GraphScript scheduler
    class APIUser,DashboardUser user
```

## Data Flow

1. **Extraction**: Cron Scheduler triggers ETL pipeline hourly
2. **ETL Pipeline**: 
   - Extracts POI data from DataTourisme API
   - Transforms and normalizes data
   - Loads into PostgreSQL with UPSERT logic
3. **Graph Loading**: After ETL, loads POIs from PostgreSQL into Neo4j
4. **API Services**: FastAPI reads from both PostgreSQL and Neo4j
5. **Dashboard**: Streamlit dashboard consumes FastAPI endpoints
6. **Users**: Access via REST API or Web Dashboard

## Component Details

### External Services
- **DataTourisme API**: French tourism data platform
  - Rate Limits: 10 req/s sustained, ≤1000 req/hour
  - Authentication: API Key via X-API-Key header

### ETL Pipeline
- **Extract**: `src/pipelines/batch_etl.py::fetch_pois_from_api()`
- **Transform**: `src/pipelines/batch_etl.py::transform_poi()`
- **Load**: `src/pipelines/batch_etl.py::load_pois_to_database()`

### Cron Scheduler
- **Schedule**: Every hour at minute 0 (`0 * * * *`)
- **Script**: `docker/cron/crontab` → `/app/run_etl.sh`
- **Execution**: Batch ETL → Graph Loader

### Data Storage
- **PostgreSQL**: Relational database for POI data
- **Neo4j**: Graph database for relationship queries

### Application Services
- **FastAPI**: REST API with auto-migration
- **Streamlit**: Interactive dashboard with multiple pages

## Generating PNG from Mermaid

### Option 1: Using mermaid-cli
```bash
npm install -g @mermaid-js/mermaid-cli
mmdc -i docs/architecture/architecture.mmd -o docs/architecture/architecture.png
```

### Option 2: Using Online Tool
1. Visit https://mermaid.live
2. Paste contents of `architecture.mmd`
3. Click "Download PNG"

### Option 3: Using VS Code
1. Install "Markdown Preview Mermaid Support" extension
2. Open `architecture.md`
3. Right-click diagram → "Export as PNG"

