"""
Analytics functions for POI data analysis.
These functions are designed to be reusable by FastAPI endpoints.
"""
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, text, func, and_, or_
from src.api.models import POI


def get_poi_counts_by_category(db: Session) -> List[Dict[str, Any]]:
    """
    Get count of POIs grouped by category.
    
    Joins poi -> poi_category -> category tables to count POIs per category.
    
    Args:
        db: SQLAlchemy database session
        
    Returns:
        List of dictionaries with 'category' and 'count' keys
        Example: [{"category": "Museum", "count": 15}, {"category": "Restaurant", "count": 8}]
    """
    # Use raw SQL for the join since we don't have Category/POICategory models
    # Join: poi -> poi_category -> category
    query = text("""
        SELECT c.name AS category, COUNT(DISTINCT p.id) AS count
        FROM poi p
        INNER JOIN poi_category pc ON p.id = pc.poi_id
        INNER JOIN category c ON pc.category_id = c.id
        GROUP BY c.id, c.name
        ORDER BY count DESC, c.name ASC
    """)
    
    result = db.execute(query)
    return [{"category": row.category, "count": row.count} for row in result]


def get_recent_pois(db: Session, limit: int = 20) -> List[POI]:
    """
    Get recent POIs ordered by last_update descending.
    
    Args:
        db: SQLAlchemy database session
        limit: Maximum number of POIs to return (default: 20)
        
    Returns:
        List of POI objects ordered by last_update DESC
    """
    return db.query(POI).order_by(desc(POI.last_update)).limit(limit).all()


def get_coordinates_list(db: Session, limit: int = 1000) -> List[Dict[str, float]]:
    """
    Get list of latitude, longitude pairs for map visualization.
    
    Args:
        db: SQLAlchemy database session
        limit: Maximum number of coordinates to return (default: 1000)
        
    Returns:
        List of dictionaries with 'latitude' and 'longitude' keys
        Example: [{"latitude": 48.8606, "longitude": 2.3376}, {"latitude": 48.8584, "longitude": 2.2945}]
    """
    pois = db.query(POI.latitude, POI.longitude).filter(
        POI.latitude.isnot(None),
        POI.longitude.isnot(None)
    ).limit(limit).all()
    
    return [{"latitude": poi.latitude, "longitude": poi.longitude} for poi in pois]


def get_counts_by_type(db: Session, limit: int = 15) -> List[Dict[str, Any]]:
    """
    Get POI counts grouped by type (top N).
    Uses POI.type column (after migration).
    
    Args:
        db: SQLAlchemy database session
        limit: Maximum number of types to return (default: 15)
        
    Returns:
        List of dictionaries with 'type' and 'count' keys
        Example: [{"type": "Restaurant", "count": 45}, {"type": "Museum", "count": 32}]
    """
    result = db.query(
        POI.type,
        func.count(POI.id).label('count')
    ).filter(
        POI.type.isnot(None)
    ).group_by(
        POI.type
    ).order_by(
        func.count(POI.id).desc()
    ).limit(limit).all()
    
    return [{"type": row.type, "count": row.count} for row in result]


def get_counts_by_day(db: Session, days: int = 30) -> List[Dict[str, Any]]:
    """
    Get POI counts grouped by day based on last_update date (last N days).
    
    Args:
        db: SQLAlchemy database session
        days: Number of days to look back (default: 30)
        
    Returns:
        List of dictionaries with 'date' and 'count' keys
        Example: [{"date": "2024-01-15", "count": 12}, {"date": "2024-01-16", "count": 8}]
    """
    query = text("""
        SELECT DATE(last_update) AS date, COUNT(*) AS count
        FROM poi
        WHERE last_update IS NOT NULL
          AND last_update >= CURRENT_DATE - INTERVAL ':days days'
        GROUP BY DATE(last_update)
        ORDER BY date DESC
    """)
    
    result = db.execute(query, {"days": days})
    return [{"date": str(row.date), "count": row.count} for row in result]


def get_missing_fields_summary(db: Session) -> Dict[str, int]:
    """
    Get summary of missing/null fields in POI data.
    Only checks columns that exist in the database.
    
    Args:
        db: SQLAlchemy database session
        
    Returns:
        Dictionary with field names and counts of NULL values
        Example: {"label": 5, "description": 12, "uri": 2, "last_update": 3}
    """
    # Check columns that exist in the database (after migration)
    allowed_columns = {
        "label", "description", "latitude", "longitude",
        "uri", "type", "city", "department_code",
        "last_update", "raw_json", "source_id", "created_at"
    }
    
    result_dict: Dict[str, int] = {}
    
    # Build query dynamically using SQLAlchemy for each existing column
    for column_name in allowed_columns:
        try:
            column_attr = getattr(POI, column_name, None)
            if column_attr is not None:
                null_count = db.query(func.count(POI.id)).filter(
                    column_attr.is_(None)
                ).scalar() or 0
                result_dict[column_name] = null_count
        except Exception as e:
            # Skip columns that don't exist or cause errors
            result_dict[column_name] = 0
    
    return result_dict


def get_bbox_count(db: Session, min_lat: float, max_lat: float, 
                   min_lon: float, max_lon: float) -> int:
    """
    Count POIs within a bounding box.
    
    Args:
        db: SQLAlchemy database session
        min_lat: Minimum latitude
        max_lat: Maximum latitude
        min_lon: Minimum longitude
        max_lon: Maximum longitude
        
    Returns:
        int: Count of POIs in bounding box
    """
    count = db.query(func.count(POI.id)).filter(
        and_(
            POI.latitude >= min_lat,
            POI.latitude <= max_lat,
            POI.longitude >= min_lon,
            POI.longitude <= max_lon
        )
    ).scalar()
    
    return count or 0


def text_search_pois(db: Session, search_term: str, limit: int = 100, 
                     offset: int = 0) -> Tuple[List[POI], int]:
    """
    Search POIs by text in label and description using ILIKE.
    
    Args:
        db: SQLAlchemy database session
        search_term: Search term to match
        limit: Maximum number of results (default: 100)
        offset: Number of results to skip (default: 0)
        
    Returns:
        Tuple of (list of POI objects, total count)
    """
    search_pattern = f"%{search_term}%"
    
    # Build query with ILIKE filters
    query = db.query(POI).filter(
        or_(
            POI.label.ilike(search_pattern),
            POI.description.ilike(search_pattern)
        )
    )
    
    # Get total count
    total_count = query.count()
    
    # Get paginated results
    pois = query.offset(offset).limit(limit).all()
    
    return pois, total_count

