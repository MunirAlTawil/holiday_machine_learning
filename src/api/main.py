"""
FastAPI application for exposing POI data from PostgreSQL.
"""
import logging
import os
import traceback
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, text, or_, and_
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
from src.api.db import get_db, Base
from src.api.models import POI
from sqlalchemy import Column, String, Integer, DateTime, Text
from src.analytics.analytics import (
    get_poi_counts_by_category,
    get_recent_pois,
    get_coordinates_list,
    get_counts_by_type,
    get_counts_by_day,
    get_bbox_count,
    text_search_pois
)

# Configure logging
logger = logging.getLogger(__name__)

app = FastAPI(title="POI API", description="API for accessing Point of Interest data")

# Add CORS middleware to allow requests from Streamlit dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models for request/response
class POIResponse(BaseModel):
    """Response model for POI data."""
    id: str
    label: Optional[str] = None
    description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    uri: Optional[str] = None
    type: Optional[str] = None
    city: Optional[str] = None
    department_code: Optional[str] = None
    theme: Optional[str] = None
    last_update: Optional[datetime] = None
    source_id: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class POIListResponse(BaseModel):
    """Paginated response model for POI list."""
    items: List[POIResponse]
    total: int
    limit: int
    offset: int

    class Config:
        from_attributes = True


class StatsResponse(BaseModel):
    """Response model for statistics."""
    total_pois: int
    pois_with_coordinates: int
    distinct_types: int
    last_update_min: Optional[datetime] = None
    last_update_max: Optional[datetime] = None


class TypeCountResponse(BaseModel):
    """Response model for type counts."""
    type: str
    count: int


class DayCountResponse(BaseModel):
    """Response model for day counts."""
    date: str
    count: int


class QualityResponse(BaseModel):
    """Response model for data quality metrics."""
    # Dynamic response - only includes columns that exist in the database
    # Example: {"label": 5, "description": 10, "latitude": 0, ...}


class CategoryStatsResponse(BaseModel):
    """Response model for category statistics."""
    category: str
    count: int


class CoordinateResponse(BaseModel):
    """Response model for coordinates."""
    latitude: float
    longitude: float


class PipelineRunResponse(BaseModel):
    """Response model for pipeline run status."""
    run_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    fetched_count: int
    processed_count: int
    inserted_count: int
    updated_count: int
    skipped_count: int
    error_message: Optional[str] = None


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "POI API", "version": "1.0.0"}


@app.get("/health")
async def health(db: Session = Depends(get_db)):
    """
    Health check endpoint with database connectivity check.
    
    Returns:
        Health status with database connection status
    """
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        db_status = "connected"
        db_error = None
    except Exception as e:
        db_status = "disconnected"
        db_error = str(e)
        logger.error(f"Database health check failed: {traceback.format_exc()}")
    
    health_status = {
        "status": "healthy" if db_status == "connected" else "unhealthy",
        "api": "operational",
        "database": {
            "status": db_status,
            "error": db_error
        }
    }
    
    status_code = 200 if db_status == "connected" else 503
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=health_status)
    return health_status


@app.get("/pois", response_model=POIListResponse)
async def get_pois(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get POIs with pagination, filtering, and search.
    
    Args:
        limit: Maximum number of results (default: 50)
        offset: Number of results to skip (default: 0)
        search: Search term for label/description (case-insensitive ILIKE)
        type: Filter by POI type (uses POI.type column)
        
    Returns:
        Paginated response with items, total count, limit, and offset
    """
    try:
        # Build base queries for both count and data
        total_query = db.query(func.count(POI.id))
        query = db.query(POI)
        
        # Apply search filter to both queries
        if search:
            search_pattern = f"%{search}%"
            filter_condition = or_(
                POI.label.ilike(search_pattern),
                POI.description.ilike(search_pattern)
            )
            query = query.filter(filter_condition)
            total_query = total_query.filter(filter_condition)
        
        # Apply type filter to both queries
        if type:
            query = query.filter(POI.type == type)
            total_query = total_query.filter(POI.type == type)
        
        # Get total count (with filters applied)
        total = total_query.scalar() or 0
        
        # Apply pagination and get items
        items = query.offset(offset).limit(limit).all()
        
        # Convert ORM objects to Pydantic models
        items_response = [POIResponse.model_validate(p) for p in items]
        
        return POIListResponse(
            items=items_response,
            total=total,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


def parse_bbox(bbox_str: str) -> Tuple[float, float, float, float]:
    """
    Parse bbox string in format "minLon,minLat,maxLon,maxLat".
    
    Args:
        bbox_str: Bounding box string
        
    Returns:
        Tuple of (min_lon, min_lat, max_lon, max_lat)
        
    Raises:
        HTTPException: If bbox format is invalid
    """
    try:
        parts = bbox_str.split(",")
        if len(parts) != 4:
            raise ValueError("bbox must have exactly 4 values")
        min_lon, min_lat, max_lon, max_lat = map(float, parts)
        
        # Validate bbox bounds
        if min_lon >= max_lon or min_lat >= max_lat:
            raise ValueError("Invalid bbox: min values must be less than max values")
        if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
            raise ValueError("Longitude must be between -180 and 180")
        if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
            raise ValueError("Latitude must be between -90 and 90")
            
        return min_lon, min_lat, max_lon, max_lat
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid bbox format: {str(e)}. Expected format: 'minLon,minLat,maxLon,maxLat'")


@app.get("/pois/geojson")
async def get_pois_geojson(
    limit: int = Query(1000, ge=1, le=5000, description="Maximum number of results (1-5000)"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    type: Optional[str] = Query(None, description="Filter by POI type"),
    search: Optional[str] = Query(None, description="Case-insensitive search on label or description"),
    bbox: Optional[str] = Query(None, description="Bounding box filter: 'minLon,minLat,maxLon,maxLat'"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get POIs as GeoJSON FeatureCollection.
    
    Only returns POIs with non-null latitude and longitude.
    
    Query Parameters:
        limit: Maximum number of results (default: 1000, max: 5000)
        offset: Number of results to skip (default: 0)
        type: Filter by POI type (optional)
        search: Case-insensitive search on label or description (optional)
        bbox: Bounding box filter in format "minLon,minLat,maxLon,maxLat" (optional)
        
    Returns:
        GeoJSON FeatureCollection with POI features. Each feature has:
        - geometry: Point with coordinates [longitude, latitude]
        - properties: id, label, description, type, uri, last_update, source_id, created_at
    """
    try:
        # Start with base query filtering for non-null coordinates
        query = db.query(POI).filter(
            POI.latitude.isnot(None),
            POI.longitude.isnot(None)
        )
        
        # Apply search filter
        if search:
            search_pattern = f"%{search}%"
            filter_condition = or_(
                POI.label.ilike(search_pattern),
                POI.description.ilike(search_pattern)
            )
            query = query.filter(filter_condition)
        
        # Apply type filter
        if type:
            query = query.filter(POI.type == type)
        
        # Apply bbox filter
        if bbox:
            min_lon, min_lat, max_lon, max_lat = parse_bbox(bbox)
            query = query.filter(
                and_(
                    POI.longitude >= min_lon,
                    POI.longitude <= max_lon,
                    POI.latitude >= min_lat,
                    POI.latitude <= max_lat
                )
            )
        
        # Get total count (before pagination)
        total = query.count()
        
        # Apply pagination
        pois = query.offset(offset).limit(limit).all()
        
        # Build GeoJSON FeatureCollection
        features = []
        for poi in pois:
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [poi.longitude, poi.latitude]
                },
                "properties": {
                    "id": poi.id,
                    "label": poi.label,
                    "description": poi.description,
                    "type": poi.type,
                    "uri": poi.uri,
                    "last_update": poi.last_update.isoformat() if poi.last_update else None,
                    "source_id": poi.source_id,
                    "created_at": poi.created_at.isoformat() if poi.created_at else None
                }
            }
            features.append(feature)
        
        geojson = {
            "type": "FeatureCollection",
            "features": features
        }
        
        return geojson
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in /pois/geojson: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/pois/{poi_id}", response_model=POIResponse)
async def get_poi(poi_id: str, db: Session = Depends(get_db)):
    """
    Get a single POI by ID.
    
    Args:
        poi_id: The unique identifier of the POI
        
    Returns:
        POI data if found
        
    Raises:
        404: If POI with given ID is not found
    """
    poi = db.query(POI).filter(POI.id == poi_id).first()
    if poi is None:
        raise HTTPException(status_code=404, detail=f"POI with id '{poi_id}' not found")
    return poi


@app.get("/stats", response_model=StatsResponse)
async def get_stats(db: Session = Depends(get_db)):
    """
    Get comprehensive statistics about POIs.
    
    Returns:
        - total_pois: Total number of POIs
        - pois_with_coordinates: Number of POIs with coordinates
        - distinct_types: Number of distinct POI types
        - last_update_min: Earliest last_update timestamp
        - last_update_max: Latest last_update timestamp
    """
    try:
        total_pois = db.query(func.count(POI.id)).scalar() or 0
        
        pois_with_coordinates = db.query(func.count(POI.id)).filter(
            POI.latitude.isnot(None),
            POI.longitude.isnot(None)
        ).scalar() or 0
        
        # Count distinct types from POI.type column
        try:
            distinct_types = db.query(func.count(func.distinct(POI.type))).filter(
                POI.type.isnot(None)
            ).scalar() or 0
        except Exception as e:
            logger.warning(f"Error counting distinct types: {traceback.format_exc()}")
            distinct_types = 0
        
        last_update_min = db.query(func.min(POI.last_update)).scalar()
        last_update_max = db.query(func.max(POI.last_update)).scalar()
        
        return StatsResponse(
            total_pois=total_pois,
            pois_with_coordinates=pois_with_coordinates,
            distinct_types=distinct_types,
            last_update_min=last_update_min,
            last_update_max=last_update_max
        )
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats/categories", response_model=List[CategoryStatsResponse])
async def get_stats_categories(db: Session = Depends(get_db)):
    """
    Get count of POIs grouped by category.
    
    Returns a list of categories with their POI counts.
    """
    try:
        category_counts = get_poi_counts_by_category(db)
        return [CategoryStatsResponse(**item) for item in category_counts]
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/pois/recent", response_model=List[POIResponse])
async def get_pois_recent(limit: int = 20, db: Session = Depends(get_db)):
    """
    Get recent POIs ordered by last_update descending.
    
    Args:
        limit: Maximum number of POIs to return (default: 20)
        
    Returns:
        List of recent POI records ordered by last_update DESC
    """
    try:
        pois = get_recent_pois(db, limit=limit)
        return [POIResponse.model_validate(p) for p in pois]
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats/coordinates", response_model=List[CoordinateResponse])
async def get_stats_coordinates(limit: int = 1000, db: Session = Depends(get_db)):
    """
    Get list of latitude, longitude pairs for map visualization.
    
    Args:
        limit: Maximum number of coordinates to return (default: 1000)
        
    Returns:
        List of coordinate pairs for all POIs with valid coordinates.
    """
    try:
        coordinates = get_coordinates_list(db, limit=limit)
        return [CoordinateResponse(**coord) for coord in coordinates]
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/charts/types", response_model=List[TypeCountResponse])
async def get_charts_types(limit: int = 15, db: Session = Depends(get_db)):
    """
    Get POI counts by type for chart visualization.
    
    Args:
        limit: Maximum number of types to return (default: 15)
        
    Returns:
        List of type counts ordered by count descending
    """
    try:
        type_counts = get_counts_by_type(db, limit=limit)
        return [TypeCountResponse(**item) for item in type_counts]
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/charts/updates", response_model=List[DayCountResponse])
async def get_charts_updates(days: int = 30, db: Session = Depends(get_db)):
    """
    Get POI counts by day based on last_update for chart visualization.
    
    Args:
        days: Number of days to look back (default: 30)
        
    Returns:
        List of day counts ordered by date descending
    """
    try:
        day_counts = get_counts_by_day(db, days=days)
        return [DayCountResponse(**item) for item in day_counts]
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/quality")
async def get_quality(db: Session = Depends(get_db)):
    """
    Get data quality metrics showing NULL counts for existing POI columns.
    
    Dynamically inspects the POI model to detect existing columns and calculates
    NULL counts only for columns that actually exist in the database.
    
    Returns:
        JSON dictionary with NULL counts per column.
        Example: {"label": 5, "description": 10, "latitude": 0, ...}
        Safely returns empty dict if any SQL error occurs.
    """
    null_counts: Dict[str, int] = {}
    
    try:
        # Use SQLAlchemy inspection to get column metadata from the table
        # Get the table object from the model
        table = POI.__table__
        
        # Define allowed columns that should exist in the database
        # This list matches the actual database schema (after migration)
        allowed_columns = {
            "label", "description", "latitude", "longitude", 
            "uri", "type", "city", "department_code",
            "last_update", "raw_json", "source_id", "created_at"
        }
        
        # Get all columns from the table, excluding the primary key
        columns_to_check = []
        for column in table.columns:
            # Skip primary key (id) - it's always required
            if column.primary_key:
                logger.debug(f"Skipping primary key column: {column.name}")
                continue
            
            # Only include columns that are in the allowed list
            if column.name in allowed_columns:
                columns_to_check.append(column)
                logger.debug(f"Will check NULL counts for column: {column.name}")
            else:
                logger.debug(f"Skipping column not in allowed list: {column.name}")
        
        logger.info(f"Calculating NULL counts for {len(columns_to_check)} columns")
        
        # Dynamically build queries for each column using SQLAlchemy
        for column in columns_to_check:
            column_name = column.name
            try:
                # Get the column attribute from the POI model dynamically
                column_attr = getattr(POI, column_name, None)
                
                if column_attr is None:
                    logger.warning(f"Column '{column_name}' attribute not found in POI model")
                    null_counts[column_name] = 0
                    continue
                
                # Build SQLAlchemy query to count NULL values
                # This uses pure SQLAlchemy, not raw SQL
                null_count = db.query(func.count(POI.id)).filter(
                    column_attr.is_(None)
                ).scalar() or 0
                
                null_counts[column_name] = null_count
                logger.debug(f"Column '{column_name}': {null_count} NULL values")
                
            except AttributeError as e:
                logger.warning(f"Column '{column_name}' not found in POI model: {e}")
                null_counts[column_name] = 0
            except Exception as e:
                # Rollback transaction to prevent "current transaction is aborted" errors
                try:
                    db.rollback()
                except Exception as rollback_error:
                    logger.error(f"Error during rollback for column '{column_name}': {rollback_error}")
                logger.error(f"Error counting NULL values for column '{column_name}': {traceback.format_exc()}")
                null_counts[column_name] = 0
        
        logger.info(f"Successfully calculated NULL counts for {len(null_counts)} columns")
        return null_counts
        
    except Exception as e:
        # Final safety net - rollback and return empty dict if anything unexpected happens
        try:
            db.rollback()
        except Exception as rollback_error:
            logger.error(f"Error during final rollback in /quality endpoint: {rollback_error}")
        logger.error(f"Unexpected error in /quality endpoint: {traceback.format_exc()}")
        # Always return valid JSON (empty dict) to prevent 500 errors
        return {}


@app.get("/etl/status", response_model=PipelineRunResponse)
async def get_etl_status(db: Session = Depends(get_db)):
    """
    Get the current ETL pipeline status (latest run).
    
    Alias for /pipeline/last-run for consistency with requirements.
    
    Returns:
        PipelineRunResponse with the latest run information
    """
    return await get_pipeline_last_run(db)


@app.get("/pipeline/last-run", response_model=PipelineRunResponse)
async def get_pipeline_last_run(db: Session = Depends(get_db)):
    """
    Get the latest pipeline run status and statistics.
    
    Reads the most recent row from pipeline_runs table and returns:
    - Run metadata (run_id, started_at, finished_at, status)
    - Execution statistics (fetched_count, processed_count, inserted_count, updated_count, skipped_count)
    - Error message if the run failed
    
    Returns:
        PipelineRunResponse with the latest run information
    """
    try:
        # Query the pipeline_runs table for the most recent run
        result = db.execute(text("""
            SELECT run_id, started_at, finished_at, status, 
                   fetched_count, processed_count, inserted_count, 
                   updated_count, skipped_count, error_message
            FROM pipeline_runs
            ORDER BY started_at DESC
            LIMIT 1
        """))
        
        row = result.fetchone()
        
        if not row:
            raise HTTPException(
                status_code=404,
                detail="No pipeline runs found. Run the batch ETL pipeline first."
            )
        
        return PipelineRunResponse(
            run_id=row[0],
            started_at=row[1],
            finished_at=row[2],
            status=row[3],
            fetched_count=row[4] or 0,
            processed_count=row[5] or 0,
            inserted_count=row[6] or 0,
            updated_count=row[7] or 0,
            skipped_count=row[8] or 0,
            error_message=row[9]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching pipeline last run: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error fetching pipeline status: {str(e)}")


class GraphSummaryResponse(BaseModel):
    """Response model for graph summary statistics."""
    poi_nodes: int
    type_nodes: int
    city_nodes: int
    department_nodes: int
    has_type_relationships: int
    in_city_relationships: int
    in_department_relationships: int
    total_nodes: int
    total_relationships: int


@app.get("/graph/summary", response_model=GraphSummaryResponse)
async def get_graph_summary():
    """
    Get summary statistics from Neo4j graph database.
    
    Returns counts of nodes and relationships:
    - POI nodes, Type nodes, City nodes, Department nodes
    - HAS_TYPE, IN_CITY, IN_DEPARTMENT relationships
    
    Returns:
        GraphSummaryResponse with node and relationship counts
        
    Raises:
        503: If Neo4j is unavailable
    """
    try:
        from src.pipelines.graph_loader import get_graph_summary as get_neo4j_summary
        summary = get_neo4j_summary()
        return GraphSummaryResponse(**summary)
    except ConnectionError as e:
        logger.error(f"Neo4j connection error: {e}")
        raise HTTPException(
            status_code=503,
            detail="Neo4j graph database is unavailable. Please ensure Neo4j service is running."
        )
    except Exception as e:
        logger.error(f"Error fetching graph summary: {traceback.format_exc()}")
        raise HTTPException(
            status_code=503,
            detail=f"Error fetching graph summary: {str(e)}. Neo4j may be unavailable."
        )


class GraphSyncResponse(BaseModel):
    """Response model for graph sync operation."""
    success: bool
    pois_loaded: int
    types_created: int
    cities_created: int
    departments_created: int
    message: str
    error: Optional[str] = None


@app.post("/graph/sync", response_model=GraphSyncResponse)
async def sync_graph(
    batch_size: int = Query(default=100, ge=1, le=1000, description="Number of POIs to process per batch"),
    sync_token: Optional[str] = Query(default=None, description="Optional sync token for authentication")
):
    """
    Manually trigger synchronization of POI data from PostgreSQL to Neo4j.
    
    This endpoint loads all POIs from PostgreSQL into Neo4j, creating nodes and relationships.
    The operation is idempotent (safe to run multiple times).
    
    Args:
        batch_size: Number of POIs to process in each batch (1-1000, default: 100)
        sync_token: Optional authentication token (set via GRAPH_SYNC_TOKEN env var)
    
    Returns:
        GraphSyncResponse with sync results
        
    Raises:
        401: If sync_token is required but not provided or invalid
        503: If Neo4j or PostgreSQL is unavailable
        500: If sync operation fails
    """
    # Optional token-based authentication (disabled by default)
    required_token = os.getenv("GRAPH_SYNC_TOKEN")
    if required_token:
        if not sync_token or sync_token != required_token:
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing sync token. Set GRAPH_SYNC_TOKEN environment variable."
            )
    
    try:
        from src.pipelines.graph_loader import load_pois_to_neo4j
        
        logger.info(f"Starting graph sync with batch_size={batch_size}")
        pois_loaded, types_created, cities_created, depts_created = load_pois_to_neo4j(
            batch_size=batch_size
        )
        
        return GraphSyncResponse(
            success=True,
            pois_loaded=pois_loaded,
            types_created=types_created,
            cities_created=cities_created,
            departments_created=depts_created,
            message=f"Successfully synced {pois_loaded} POIs to Neo4j graph database."
        )
    
    except ConnectionError as e:
        logger.error(f"Neo4j connection error during sync: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Neo4j graph database is unavailable: {str(e)}. Please ensure Neo4j service is running."
        )
    except Exception as e:
        logger.error(f"Error during graph sync: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Graph sync failed: {str(e)}"
        )


class ETLRunNowResponse(BaseModel):
    """Response model for ETL run-now operation."""
    success: bool
    run_id: Optional[str] = None
    message: str
    error: Optional[str] = None


class ItineraryPOI(BaseModel):
    """POI in itinerary."""
    id: str
    label: Optional[str] = None
    description: Optional[str] = None
    latitude: float
    longitude: float
    type: Optional[str] = None
    uri: Optional[str] = None
    city: Optional[str] = None
    distance_from_previous_km: Optional[float] = None


class ItineraryDay(BaseModel):
    """Day in itinerary."""
    day: int
    pois: List[ItineraryPOI]
    total_pois: int
    types_visited: List[str]


class ItineraryResponse(BaseModel):
    """Response model for itinerary generation."""
    start_location: Dict[str, float]
    days: int
    radius_km: float
    types_filter: Optional[List[str]] = None
    limit_per_day: int
    total_pois_found: int
    total_pois_selected: int
    itinerary: List[ItineraryDay]


class ItineraryBuildRequest(BaseModel):
    """Request model for itinerary build."""
    lat: float = Field(..., ge=-90, le=90, description="Starting latitude")
    lon: float = Field(..., ge=-180, le=180, description="Starting longitude")
    days: int = Field(..., ge=1, le=14, description="Number of days (1-14)")
    radius_km: float = Field(..., ge=1, le=50, description="Search radius in kilometers")
    types: Optional[List[str]] = Field(default=None, description="Optional POI types filter")
    max_pois_per_day: int = Field(default=5, ge=1, le=10, description="Maximum POIs per day (default: 5)")


class ItineraryPOIItem(BaseModel):
    """POI item in itinerary day."""
    id: str
    label: Optional[str] = None
    type: Optional[str] = None
    lat: float
    lon: float
    uri: Optional[str] = None


class ItineraryDay(BaseModel):
    """Day in itinerary."""
    day: int
    pois: List[ItineraryPOIItem]
    route_hint: str


class ItineraryBuildResponse(BaseModel):
    """Response model for itinerary build - matches professor's specification."""
    summary: Dict[str, Any]
    days: List[ItineraryDay]
    data_sources: Dict[str, bool]


class ItineraryHealthResponse(BaseModel):
    """Response model for itinerary health check."""
    postgres_pois: int
    postgres_types: int
    neo4j_pois: int
    neo4j_types: int
    neo4j_available: bool


@app.post("/etl/run-now", response_model=ETLRunNowResponse)
async def run_etl_now(
    limit_per_run: int = Query(default=500, ge=1, le=5000, description="Maximum POIs to fetch"),
    max_pages: int = Query(default=5, ge=1, le=50, description="Maximum pages to fetch"),
    run_token: Optional[str] = Query(default=None, description="Optional authentication token")
):
    """
    Manually trigger ETL pipeline execution.
    
    This endpoint runs the batch ETL pipeline asynchronously in the background.
    Check /etl/status to monitor progress.
    
    Args:
        limit_per_run: Maximum POIs to fetch in this run (1-5000, default: 500)
        max_pages: Maximum pages to fetch (1-50, default: 5)
        run_token: Optional authentication token (set via ETL_RUN_TOKEN env var)
    
    Returns:
        ETLRunNowResponse with status message
        
    Raises:
        401: If run_token is required but not provided or invalid
        500: If ETL execution fails
    """
    # Optional token-based authentication (disabled by default)
    required_token = os.getenv("ETL_RUN_TOKEN")
    if required_token:
        if not run_token or run_token != required_token:
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing run token. Set ETL_RUN_TOKEN environment variable."
            )
    
    try:
        import asyncio
        import subprocess
        import sys
        from pathlib import Path
        
        # Run ETL pipeline in background using asyncio
        async def run_etl_background():
            project_root = Path(__file__).parent.parent.parent
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "src.pipelines.batch_etl",
                "--limit-per-run", str(limit_per_run),
                "--max-pages", str(max_pages),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(project_root)
            )
            # Don't wait for completion - return immediately
            return process
        
        # Start background task
        process = await run_etl_background()
        
        return ETLRunNowResponse(
            success=True,
            run_id=None,  # Will be created by ETL process
            message=f"ETL pipeline started in background. Check /etl/status for progress. PID: {process.pid}"
        )
    
    except Exception as e:
        logger.error(f"Error starting ETL pipeline: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start ETL pipeline: {str(e)}"
        )


@app.get("/itinerary", response_model=ItineraryResponse)
async def generate_itinerary(
    lat: float = Query(..., description="Starting latitude", ge=-90, le=90),
    lon: float = Query(..., description="Starting longitude", ge=-180, le=180),
    days: int = Query(..., description="Number of days", ge=1, le=30),
    radius_km: float = Query(default=50.0, description="Search radius in kilometers", ge=1, le=500),
    types: Optional[str] = Query(default=None, description="Comma-separated list of POI types to filter"),
    limit_per_day: int = Query(default=5, description="Maximum POIs per day", ge=1, le=20),
    db: Session = Depends(get_db)
):
    """
    Generate a day-by-day itinerary based on location, duration, and preferences.
    
    Uses a greedy distance-based algorithm that:
    - Minimizes travel distance between POIs
    - Maximizes type diversity (prefers different POI types)
    - Limits POIs per day
    
    Args:
        lat: Starting latitude (required)
        lon: Starting longitude (required)
        days: Number of days for the itinerary (1-30, required)
        radius_km: Search radius in kilometers (1-500, default: 50)
        types: Optional comma-separated list of POI types (e.g., "Museum,Restaurant")
        limit_per_day: Maximum POIs per day (1-20, default: 5)
    
    Returns:
        ItineraryResponse with day-by-day POI lists
        
    Example:
        GET /itinerary?lat=48.8566&lon=2.3522&days=3&radius_km=30&types=Museum,Restaurant&limit_per_day=4
    """
    try:
        from src.analytics.itinerary import generate_itinerary as generate_itinerary_algorithm
        
        # Parse types if provided
        type_list = None
        if types:
            type_list = [t.strip() for t in types.split(",") if t.strip()]
        
        # Generate itinerary
        itinerary = generate_itinerary_algorithm(
            db=db,
            start_lat=lat,
            start_lon=lon,
            days=days,
            radius_km=radius_km,
            types=type_list,
            limit_per_day=limit_per_day
        )
        
        return ItineraryResponse(**itinerary)
    
    except Exception as e:
        logger.error(f"Error generating itinerary: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate itinerary: {str(e)}"
        )


@app.post("/itinerary/build", response_model=ItineraryBuildResponse)
async def build_itinerary(
    request: ItineraryBuildRequest,
    db: Session = Depends(get_db)
):
    """
    Build a day-by-day itinerary using HYBRID approach (PostgreSQL + Neo4j).
    
    Uses PostgreSQL for geospatial queries and Neo4j for type diversity optimization.
    
    Args:
        request: ItineraryBuildRequest with trip parameters
        
    Returns:
        ItineraryBuildResponse with summary, days array, and data_sources
        
    Example:
        POST /itinerary/build
        {
            "lat": 48.8566,
            "lon": 2.3522,
            "days": 3,
            "radius_km": 30,
            "types": ["Museum", "Restaurant"],
            "max_pois_per_day": 5
        }
    """
    import time
    start_time = time.time()
    
    try:
        from src.analytics.itinerary_hybrid import generate_itinerary_hybrid
        
        # Validate inputs
        if not (-90 <= request.lat <= 90):
            raise HTTPException(
                status_code=400,
                detail="lat must be between -90 and 90"
            )
        
        if not (-180 <= request.lon <= 180):
            raise HTTPException(
                status_code=400,
                detail="lon must be between -180 and 180"
            )
        
        if request.days < 1 or request.days > 14:
            raise HTTPException(
                status_code=400,
                detail="days must be between 1 and 14"
            )
        
        if request.radius_km < 1 or request.radius_km > 50:
            raise HTTPException(
                status_code=400,
                detail="radius_km must be between 1 and 50"
            )
        
        if request.max_pois_per_day < 1 or request.max_pois_per_day > 10:
            raise HTTPException(
                status_code=400,
                detail="max_pois_per_day must be between 1 and 10"
            )
        
        logger.info(
            f"Itinerary build request: lat={request.lat}, lon={request.lon}, "
            f"days={request.days}, radius_km={request.radius_km}, "
            f"types={request.types}, max_pois_per_day={request.max_pois_per_day}"
        )
        
        # Generate itinerary using hybrid approach
        db_query_start = time.time()
        result = generate_itinerary_hybrid(
            db=db,
            start_lat=request.lat,
            start_lon=request.lon,
            days=request.days,
            daily_limit=request.max_pois_per_day,
            radius_km=request.radius_km,
            types=request.types,
            diversity=True  # Always use diversity mode for hybrid approach
        )
        db_query_time = time.time() - db_query_start
        
        logger.info(
            f"Itinerary generated: {result.get('total_pois_selected', 0)} POIs selected "
            f"from {result.get('total_pois_found', 0)} candidates in {db_query_time:.2f}s"
        )
        
        # Transform result to match exact specification
        days_response = []
        for day_data in result.get("itinerary", []):
            day_num = day_data.get("day", 1)
            items = day_data.get("items", [])
            
            # Convert items to specification format
            pois = []
            for item in items:
                pois.append(ItineraryPOIItem(
                    id=item.get("id", ""),
                    label=item.get("label"),
                    type=item.get("type"),
                    lat=item.get("latitude", 0.0),
                    lon=item.get("longitude", 0.0),
                    uri=item.get("uri")
                ))
            
            # Generate route hint
            types_visited = day_data.get("types_visited", [])
            route_hint = f"Visit {len(pois)} POI(s)"
            if types_visited:
                route_hint += f" including {', '.join(types_visited[:3])}"
            if len(types_visited) > 3:
                route_hint += f" and {len(types_visited) - 3} more type(s)"
            
            days_response.append(ItineraryDay(
                day=day_num,
                pois=pois,
                route_hint=route_hint
            ))
        
        # Build summary
        summary = {
            "start_location": {"lat": request.lat, "lon": request.lon},
            "days": request.days,
            "radius_km": request.radius_km,
            "types_filter": request.types,
            "max_pois_per_day": request.max_pois_per_day,
            "total_pois_found": result.get("total_pois_found", 0),
            "total_pois_selected": result.get("total_pois_selected", 0),
            "query_time_seconds": round(db_query_time, 3)
        }
        
        # Build data_sources
        meta = result.get("meta", {})
        data_sources = {
            "postgres": True,  # Always used for geospatial queries
            "neo4j": meta.get("neo4j_used", False)
        }
        
        total_time = time.time() - start_time
        logger.info(f"Itinerary build completed in {total_time:.2f}s (DB query: {db_query_time:.2f}s)")
        
        return ItineraryBuildResponse(
            summary=summary,
            days=days_response,
            data_sources=data_sources
        )
    
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error in itinerary build: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid input: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error building itinerary: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to build itinerary: {str(e)}"
        )


@app.get("/itinerary/health", response_model=ItineraryHealthResponse)
async def itinerary_health(db: Session = Depends(get_db)):
    """
    Health check endpoint for itinerary generation.
    
    Returns counts from PostgreSQL and Neo4j relevant to itinerary generation.
    
    Returns:
        ItineraryHealthResponse with POI and type counts from both databases
    """
    try:
        # PostgreSQL counts
        postgres_result = db.execute(text("""
            SELECT 
                COUNT(DISTINCT id) as pois,
                COUNT(DISTINCT type) as types
            FROM poi
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """))
        postgres_row = postgres_result.fetchone()
        postgres_pois = postgres_row[0] if postgres_row else 0
        postgres_types = postgres_row[1] if postgres_row else 0
        
        # Neo4j counts
        neo4j_available = False
        neo4j_pois = 0
        neo4j_types = 0
        
        try:
            from src.pipelines.graph_loader import get_neo4j_driver
            driver = get_neo4j_driver()
            if driver:
                neo4j_available = True
                with driver.session() as session:
                    try:
                        poi_result = session.run("MATCH (p:POI) RETURN count(p) as count")
                        poi_record = poi_result.single()
                        neo4j_pois = poi_record["count"] if poi_record else 0
                    except Exception as e:
                        logger.warning(f"Error counting POI nodes: {e}")
                        neo4j_pois = 0
                    
                    try:
                        type_result = session.run("MATCH (t:Type) RETURN count(t) as count")
                        type_record = type_result.single()
                        neo4j_types = type_record["count"] if type_record else 0
                    except Exception as e:
                        logger.warning(f"Error counting Type nodes: {e}")
                        neo4j_types = 0
                
                driver.close()
        except Exception as e:
            logger.warning(f"Neo4j health check failed: {e}")
        
        return ItineraryHealthResponse(
            postgres_pois=postgres_pois,
            postgres_types=postgres_types,
            neo4j_pois=neo4j_pois,
            neo4j_types=neo4j_types,
            neo4j_available=neo4j_available
        )
    
    except Exception as e:
        logger.error(f"Error in itinerary health check: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Health check failed: {str(e)}"
        )

