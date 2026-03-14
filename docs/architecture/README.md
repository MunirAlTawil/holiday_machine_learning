# Architecture Diagrams

This directory contains architecture diagrams for the Holiday Itinerary Data Engineering Project in multiple formats.

## Files

- **architecture.mmd** - Mermaid diagram source (for PNG generation)
- **architecture.md** - Mermaid diagram in Markdown (for GitHub rendering)
- **architecture.drawio** - Draw.io XML format (for editing in Draw.io)
- **architecture.png** - PNG image (generated)
- **generate_png.py** - Python script to regenerate PNG

## Generating PNG from Mermaid

### Option 1: Using mermaid-cli (Recommended)

```bash
# Install mermaid-cli globally
npm install -g @mermaid-js/mermaid-cli

# Generate PNG
mmdc -i docs/architecture/architecture.mmd -o docs/architecture/architecture.png -w 2400 -H 1800 -b transparent
```

### Option 2: Using Online Tool

1. Visit https://mermaid.live
2. Open `architecture.mmd` file
3. Click "Actions" → "Download PNG"

### Option 3: Using VS Code

1. Install "Markdown Preview Mermaid Support" extension
2. Open `architecture.md`
3. Right-click on the diagram → "Export as PNG"

### Option 4: Using Python (mermaid.ink API)

```python
import requests
from pathlib import Path

# Read Mermaid file
with open('docs/architecture/architecture.mmd', 'r') as f:
    mermaid_code = f.read()

# Convert to PNG via mermaid.ink API
response = requests.post(
    'https://mermaid.ink/img',
    json={'code': mermaid_code},
    params={'theme': 'default'}
)

# Save PNG
with open('docs/architecture/architecture.png', 'wb') as f:
    f.write(response.content)
```

## Opening Draw.io File

1. Visit https://app.diagrams.net (formerly draw.io)
2. File → Open from → Device
3. Select `architecture.drawio`
4. Edit and export as needed

## Architecture Overview

The diagram shows:

1. **External DataTourisme API** - Source of POI data
2. **ETL Batch Pipeline** - Extract, Transform, Load workflow
3. **Cron Scheduler** - Hourly automation (runs ETL + Graph Loader)
4. **PostgreSQL** - Relational database for POI storage
5. **Neo4j** - Graph database for relationship queries
6. **FastAPI** - REST API service
7. **Streamlit Dashboard** - Interactive web dashboard

## Data Flow

```
DataTourisme API
    ↓ (HTTPS, API Key)
ETL Pipeline (Extract → Transform → Load)
    ↓ (UPSERT)
PostgreSQL
    ↓ (Read POIs)
Graph Loader
    ↓ (MERGE)
Neo4j
    ↑ ↓ (Queries)
FastAPI ← → Streamlit Dashboard
    ↓         ↓
API Users  Dashboard Users
```

