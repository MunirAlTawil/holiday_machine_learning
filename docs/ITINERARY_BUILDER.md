# Itinerary Builder - Implementation Guide

## Overview

The Itinerary Builder is a core feature of the Holiday Itinerary project that generates personalized day-by-day trip itineraries using a **HYBRID approach** combining:

- **PostgreSQL**: Geospatial queries to find POIs within radius
- **Neo4j**: Type diversity optimization using graph relationships

## Architecture

### Hybrid Approach

1. **PostgreSQL (Primary)**: 
   - Finds candidate POIs within `radius_km` of starting location
   - Uses Haversine formula for distance calculation
   - Filters by POI types if specified

2. **Neo4j (Optimization)**:
   - When `diversity=true`: Uses `HAS_TYPE` relationships to maximize type diversity
   - Calculates diversity scores for each candidate POI
   - Penalizes repeated types, rewards new types

3. **Greedy Algorithm**:
   - Selects POIs that minimize distance + maximize diversity
   - Organizes into day-by-day schedule
   - Limits POIs per day

## API Endpoints

### POST /itinerary/build

**Request:**
```json
{
  "days": 3,
  "daily_limit": 5,
  "lat": 48.8566,
  "lon": 2.3522,
  "radius_km": 30,
  "types": ["Museum", "Restaurant"],
  "diversity": true
}
```

**Response:**
```json
{
  "itinerary": [
    {
      "day": 1,
      "items": [
        {
          "id": "poi-123",
          "label": "Louvre Museum",
          "description": "...",
          "latitude": 48.8606,
          "longitude": 2.3376,
          "type": "Museum",
          "uri": "http://...",
          "city": "Paris",
          "distance_from_previous_km": 0.5
        }
      ],
      "total_pois": 5,
      "types_visited": ["Museum", "Restaurant"]
    }
  ],
  "meta": {
    "diversity_mode": true,
    "neo4j_used": true
  }
}
```

### GET /itinerary/health

Returns health status for itinerary generation:
```json
{
  "postgres_pois": 500,
  "postgres_types": 81,
  "neo4j_pois": 500,
  "neo4j_types": 81,
  "neo4j_available": true
}
```

## Dashboard UI

### Location
- **File**: `src/dashboard/app.py`
- **Page**: "Itinerary Builder" (in sidebar navigation)

### Features
- Health check display (PostgreSQL + Neo4j counts)
- Form inputs:
  - Starting location (lat/lon)
  - Trip duration (1-14 days)
  - Daily POI limit (3-10)
  - Search radius (1-50 km)
  - POI types (multi-select)
  - Diversity mode (toggle)
- Interactive map visualization
- Day-by-day itinerary display
- Day selector for viewing specific days

## Algorithm Details

### Diversity Scoring (Neo4j)

When `diversity=true` and Neo4j is available:

1. Query Neo4j for POI types using `HAS_TYPE` relationships
2. Calculate diversity scores:
   - **+10.0**: Type never used (highest diversity)
   - **+5.0**: Type not used today (good diversity)
   - **-2.0**: Type already used today (penalty)

3. Combine with distance:
   ```
   score = distance_km - (diversity_bonus * 2)
   ```

### Fallback Mode

If Neo4j is unavailable but `diversity=true`:
- Uses simple type diversity from PostgreSQL data
- Still maximizes type diversity but without graph optimization

## Testing

### Manual Testing

```bash
# Test health endpoint
curl http://localhost:8000/itinerary/health

# Test itinerary build
curl -X POST "http://localhost:8000/itinerary/build" \
  -H "Content-Type: application/json" \
  -d '{
    "days": 3,
    "daily_limit": 5,
    "lat": 48.8566,
    "lon": 2.3522,
    "radius_km": 30,
    "diversity": true
  }'
```

### Automated Testing

```bash
python tools/test_itinerary.py
```

## Files

- **Algorithm**: `src/analytics/itinerary_hybrid.py`
- **API Endpoints**: `src/api/main.py` (POST /itinerary/build, GET /itinerary/health)
- **Dashboard UI**: `src/dashboard/app.py` (Itinerary Builder page)
- **Test Script**: `tools/test_itinerary.py`

## Usage Examples

### Example 1: 3-Day Paris Trip
```json
{
  "days": 3,
  "daily_limit": 5,
  "lat": 48.8566,
  "lon": 2.3522,
  "radius_km": 30,
  "diversity": true
}
```

### Example 2: Museums Only
```json
{
  "days": 2,
  "daily_limit": 4,
  "lat": 48.8566,
  "lon": 2.3522,
  "radius_km": 25,
  "types": ["Museum"],
  "diversity": false
}
```

## Error Handling

- **400 Bad Request**: Invalid parameters (days > 14, daily_limit > 10, etc.)
- **500 Internal Server Error**: Database connection issues or algorithm errors
- **Graceful Degradation**: Falls back to PostgreSQL-only if Neo4j unavailable

---

*End of Itinerary Builder Documentation*

