"""
Batch ETL Pipeline for Holiday Itinerary Project - Stage 3: Hourly Batch Pipeline
=================================================================================

This script performs a complete ETL (Extract, Transform, Load) workflow:
1. EXTRACTION: Fetches POI data from DataTourisme REST API with rate limiting and retries
2. TRANSFORMATION: Normalizes and cleans the data
3. LOAD: Inserts or updates records in PostgreSQL using smart UPSERT logic
4. STATE: Tracks pipeline runs in pipeline_runs table

Usage:
    python -m src.pipelines.batch_etl --limit-per-run 500 --max-pages 5 --since-hours 24

Environment Variables Required:
    - DATABASE_URL: PostgreSQL connection string (or use POSTGRES_* variables)
    - DATATOURISME_API_KEY: API key for DataTourisme API
    - DATATOURISME_BASE_URL: Base URL for DataTourisme API (default: https://api.datatourisme.fr)
"""
import argparse
import json
import logging
import os
import sys
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from uuid import uuid4

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base

# Add src to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.api.models import POI

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

# Database configuration - use DATABASE_URL if provided, otherwise construct from individual vars
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "holiday")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "holiday")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "holiday")
    DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# API configuration
DATATOURISME_API_KEY = os.getenv("DATATOURISME_API_KEY", "")
DATATOURISME_BASE_URL = os.getenv("DATATOURISME_BASE_URL", "https://api.datatourisme.fr")
API_URL = f"{DATATOURISME_BASE_URL}/v1/catalog"

# Rate limiting configuration
MAX_REQUESTS_PER_SECOND = 10  # Sustained rate limit
MAX_REQUESTS_PER_HOUR = 1000  # Hourly rate limit

# ============================================================================
# RATE LIMITING & RETRY LOGIC
# ============================================================================

class RateLimiter:
    """Rate limiter to respect API constraints: max 10 req/s sustained, <=1000 req/hour."""
    
    def __init__(self, max_per_second: int = 10, max_per_hour: int = 1000):
        self.max_per_second = max_per_second
        self.max_per_hour = max_per_hour
        self.request_times = deque()  # Track request timestamps
        self.hourly_requests = deque()  # Track requests in last hour
        
    def wait_if_needed(self):
        """Wait if we need to respect rate limits."""
        now = time.time()
        
        # Remove requests older than 1 second
        while self.request_times and now - self.request_times[0] >= 1.0:
            self.request_times.popleft()
        
        # Remove requests older than 1 hour
        while self.hourly_requests and now - self.hourly_requests[0] >= 3600.0:
            self.hourly_requests.popleft()
        
        # Check per-second limit
        if len(self.request_times) >= self.max_per_second:
            sleep_time = 1.0 - (now - self.request_times[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
                now = time.time()
        
        # Check per-hour limit
        if len(self.hourly_requests) >= self.max_per_hour:
            sleep_time = 3600.0 - (now - self.hourly_requests[0])
            if sleep_time > 0:
                logger.warning(f"Hourly rate limit reached. Waiting {sleep_time:.1f} seconds...")
                time.sleep(sleep_time)
                now = time.time()
        
        # Record this request
        self.request_times.append(now)
        self.hourly_requests.append(now)


def fetch_with_retry(url: str, params: Dict, headers: Dict, max_retries: int = 3) -> requests.Response:
    """
    Fetch with exponential backoff retry logic.
    
    Args:
        url: API URL
        params: Query parameters
        headers: Request headers
        max_retries: Maximum number of retry attempts
        
    Returns:
        Response object
        
    Raises:
        requests.RequestException: If all retries fail
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            if response.status_code in [401, 403]:
                raise ValueError("Invalid API key or unauthorized")
            if response.status_code == 429:  # Rate limit exceeded
                wait_time = (2 ** attempt) + (time.time() % 1)  # Exponential backoff + jitter
                logger.warning(f"Rate limit exceeded. Retrying in {wait_time:.2f} seconds...")
                time.sleep(wait_time)
                continue
            if attempt == max_retries - 1:
                raise
            wait_time = 2 ** attempt  # Exponential backoff
            logger.warning(f"HTTP error {response.status_code}. Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 2 ** attempt  # Exponential backoff
            logger.warning(f"Request failed: {e}. Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
    
    raise requests.RequestException(f"Failed after {max_retries} retries")


# ============================================================================
# PIPELINE STATE TRACKING
# ============================================================================

# Create base for pipeline_runs table
PipelineBase = declarative_base()

class PipelineRun(PipelineBase):
    """Model for pipeline_runs table."""
    __tablename__ = "pipeline_runs"
    
    run_id = Column(String, primary_key=True)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String, nullable=False)  # 'running', 'success', 'failed'
    fetched_count = Column(Integer, default=0)
    processed_count = Column(Integer, default=0)
    inserted_count = Column(Integer, default=0)
    updated_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)


def ensure_pipeline_runs_table(engine):
    """Create pipeline_runs table if it doesn't exist."""
    try:
        PipelineRun.__table__.create(engine, checkfirst=True)
        logger.info("Pipeline runs table ensured")
    except Exception as e:
        logger.warning(f"Could not ensure pipeline_runs table: {e}")


def create_pipeline_run(engine) -> str:
    """Create a new pipeline run record and return run_id."""
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        run_id = str(uuid4())
        run = PipelineRun(
            run_id=run_id,
            started_at=datetime.now(),
            status='running',
            fetched_count=0,
            processed_count=0,
            inserted_count=0,
            updated_count=0,
            skipped_count=0
        )
        session.add(run)
        session.commit()
        logger.info(f"Created pipeline run: {run_id}")
        return run_id
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating pipeline run: {e}")
        raise
    finally:
        session.close()


def update_pipeline_run(engine, run_id: str, status: str, **kwargs):
    """Update pipeline run with results."""
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        run = session.query(PipelineRun).filter(PipelineRun.run_id == run_id).first()
        if run:
            run.status = status
            run.finished_at = datetime.now()
            for key, value in kwargs.items():
                if hasattr(run, key):
                    setattr(run, key, value)
            session.commit()
            logger.info(f"Updated pipeline run {run_id}: status={status}")
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating pipeline run: {e}")
    finally:
        session.close()


# ============================================================================
# EXTRACTION STEP
# ============================================================================

def extract_coordinates(poi: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """Extract latitude and longitude from a POI object."""
    location = poi.get("isLocatedAt")
    if not location:
        return None, None
    
    if isinstance(location, list) and len(location) > 0:
        location = location[0]
    
    if not isinstance(location, dict):
        return None, None
    
    geo = location.get("schema:geo") or location.get("geo")
    if not geo:
        return None, None
    
    latitude = geo.get("schema:latitude") or geo.get("latitude")
    longitude = geo.get("schema:longitude") or geo.get("longitude")
    
    if latitude is None or longitude is None:
        coords = geo.get("schema:coordinates") or geo.get("coordinates")
        if isinstance(coords, list) and len(coords) >= 2:
            longitude = coords[0]
            latitude = coords[1]
    
    try:
        if latitude is not None:
            latitude = float(latitude)
        if longitude is not None:
            longitude = float(longitude)
    except (ValueError, TypeError):
        return None, None
    
    return latitude, longitude


def extract_city(poi: Dict[str, Any]) -> Optional[str]:
    """Extract city name from POI object (from isLocatedAt → schema:address → schema:addressLocality)."""
    location = poi.get("isLocatedAt")
    if not location:
        return None
    
    if isinstance(location, list) and len(location) > 0:
        location = location[0]
    
    if not isinstance(location, dict):
        return None
    
    address = location.get("schema:address") or location.get("address")
    if not address:
        return None
    
    if isinstance(address, list) and len(address) > 0:
        address = address[0]
    
    if not isinstance(address, dict):
        return None
    
    city = address.get("schema:addressLocality") or address.get("addressLocality") or address.get("locality")
    if city:
        return str(city).strip() if isinstance(city, str) else None
    
    return None


def extract_department_code(poi: Dict[str, Any]) -> Optional[str]:
    """Extract department code from POI object (from isLocatedAt → schema:address → schema:postalCode first 2 digits)."""
    location = poi.get("isLocatedAt")
    if not location:
        return None
    
    if isinstance(location, list) and len(location) > 0:
        location = location[0]
    
    if not isinstance(location, dict):
        return None
    
    address = location.get("schema:address") or location.get("address")
    if not address:
        return None
    
    if isinstance(address, list) and len(address) > 0:
        address = address[0]
    
    if not isinstance(address, dict):
        return None
    
    postal_code = address.get("schema:postalCode") or address.get("postalCode") or address.get("postal_code")
    if not postal_code:
        return None
    
    # Extract first 2 digits of postal code (French department code)
    postal_str = str(postal_code).strip()
    if len(postal_str) >= 2:
        try:
            # French postal codes: first 2 digits = department code
            dept_code = postal_str[:2]
            # Validate it's numeric
            int(dept_code)
            return dept_code
        except (ValueError, TypeError):
            return None
    
    return None


def extract_theme_from_uri(uri: str) -> Optional[str]:
    """
    Extract theme from POI URI string.
    
    Parses URI to extract main thematic segment (e.g., /restaurant/, /museum/, /heritage/).
    Returns normalized lowercase theme.
    
    Args:
        uri: URI string (e.g., "https://data.datatourisme.fr/13/2c29c0aa-bb2f-3dac-9f93-76f39f06bbc5")
        
    Returns:
        Normalized lowercase theme string, or None if no theme can be extracted
        
    Examples:
        >>> extract_theme_from_uri("https://data.datatourisme.fr/restaurant/123")
        "restaurant"
        >>> extract_theme_from_uri("https://data.datatourisme.fr/13/museum-abc")
        "museum"
        >>> extract_theme_from_uri("https://data.datatourisme.fr/13/2c29c0aa-bb2f-3dac-9f93-76f39f06bbc5")
        None  # No theme segment found
    """
    if not uri or not isinstance(uri, str):
        return None
    
    uri = uri.strip()
    if not uri:
        return None
    
    try:
        from urllib.parse import urlparse
        parsed = urlparse(uri)
        path = parsed.path.strip('/')
        
        if not path:
            return None
        
        # Split path into segments
        segments = [seg for seg in path.split('/') if seg]
        
        # Common theme keywords to look for in path segments
        theme_keywords = [
            'restaurant', 'museum', 'heritage', 'hotel', 'accommodation',
            'attraction', 'activity', 'event', 'festival', 'monument',
            'park', 'garden', 'beach', 'mountain', 'castle', 'church',
            'cathedral', 'theater', 'cinema', 'shopping', 'market',
            'sport', 'outdoor', 'indoor', 'cultural', 'natural', 'historic'
        ]
        
        # Check each segment for theme keywords
        for segment in segments:
            segment_lower = segment.lower()
            # Check if segment contains a theme keyword
            for keyword in theme_keywords:
                if keyword in segment_lower:
                    return keyword
        
        # If no keyword found, check if first non-numeric segment looks like a theme
        # (skip numeric segments like department codes)
        for segment in segments:
            segment_lower = segment.lower()
            # Skip if it's just a number (likely department code) or UUID-like
            if segment_lower.isdigit() or len(segment_lower) > 20:
                continue
            # If segment is a reasonable length and doesn't look like UUID, use it
            if 3 <= len(segment_lower) <= 20 and '-' not in segment_lower[:8]:
                return segment_lower
        
        return None
        
    except Exception as e:
        logger.debug(f"Error extracting theme from URI {uri}: {e}")
        return None


def extract_label(poi: Dict[str, Any]) -> Optional[str]:
    """Extract label from POI object."""
    label_obj = poi.get("label") or poi.get("rdfs:label")
    
    if isinstance(label_obj, dict):
        label = label_obj.get("fr") or label_obj.get("@fr") or label_obj.get("en") or label_obj.get("@en")
        if label:
            return str(label).strip()
        for value in label_obj.values():
            if isinstance(value, str) and value.strip():
                return value.strip()
    elif isinstance(label_obj, str):
        return label_obj.strip()
    
    return None


def extract_description(poi: Dict[str, Any]) -> Optional[str]:
    """Extract description from POI object."""
    desc_obj = poi.get("hasDescription") or poi.get("description")
    
    if isinstance(desc_obj, dict):
        desc = desc_obj.get("fr") or desc_obj.get("@fr") or desc_obj.get("en") or desc_obj.get("@en")
        if desc:
            return str(desc).strip()
        for value in desc_obj.values():
            if isinstance(value, str) and value.strip():
                return value.strip()
    elif isinstance(desc_obj, str):
        return desc_obj.strip()
    
    return None


def extract_type(poi: Dict[str, Any]) -> Optional[str]:
    """Extract type from POI object."""
    poi_type = poi.get("type") or poi.get("@type")
    if poi_type:
        if isinstance(poi_type, list) and len(poi_type) > 0:
            poi_type = poi_type[0]
        return str(poi_type).strip() if poi_type else None
    return None


def parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse timestamp from various formats."""
    if value is None:
        return None
    
    if isinstance(value, datetime):
        return value
    
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        
        try:
            if 'T' in value:
                if '+' in value:
                    value = value.split('+')[0]
                if value.endswith('Z'):
                    value = value[:-1]
                return datetime.fromisoformat(value)
            else:
                return datetime.strptime(value, "%Y-%m-%d")
        except (ValueError, TypeError):
            pass
    
    return None


def fetch_pois_from_api(
    max_pages: Optional[int] = None,
    page_size: int = 250,
    limit_per_run: int = 500,
    since_hours: Optional[int] = None,
    rate_limiter: Optional[RateLimiter] = None
) -> List[Dict[str, Any]]:
    """
    EXTRACTION STEP: Fetch POI data from DataTourisme REST API.
    
    Respects rate limits (max 10 req/s sustained, <=1000 req/hour) and uses retries
    with exponential backoff.
    
    Args:
        max_pages: Maximum number of pages to fetch
        page_size: Number of items per page (max: 250)
        limit_per_run: Maximum total POIs to fetch in this run
        since_hours: Filter POIs updated in last N hours (if API supports)
        rate_limiter: Rate limiter instance
        
    Returns:
        List of raw POI dictionaries from the API
    """
    logger.info("=" * 60)
    logger.info("EXTRACTION STEP: Fetching POIs from DataTourisme API")
    logger.info("=" * 60)
    
    if not DATATOURISME_API_KEY:
        raise ValueError("DATATOURISME_API_KEY not found. Please set it in your .env file.")
    
    if rate_limiter is None:
        rate_limiter = RateLimiter(MAX_REQUESTS_PER_SECOND, MAX_REQUESTS_PER_HOUR)
    
    all_objects = []
    current_page = 1
    
    headers = {
        "X-API-Key": DATATOURISME_API_KEY
    }
    
    logger.info(f"Starting fetch operation (max_pages={max_pages}, page_size={page_size}, limit={limit_per_run})")
    
    while True:
        if max_pages and current_page > max_pages:
            logger.info(f"Reached max_pages limit ({max_pages})")
            break
        
        if len(all_objects) >= limit_per_run:
            logger.info(f"Reached limit_per_run ({limit_per_run})")
            break
        
        params = {
            "page_size": min(page_size, 250),
            "page": current_page,
            "lang": "fr,en",
            "fields": "uuid,label,type,uri,isLocatedAt,hasDescription,lastUpdate"
        }
        
        # Note: DataTourisme API may not support since_hours filtering directly
        # If it does, we would add it here. For now, we just limit by pages/limit
        
        try:
            # Rate limiting
            rate_limiter.wait_if_needed()
            
            logger.info(f"Fetching page {current_page}...")
            response = fetch_with_retry(API_URL, params=params, headers=headers)
            
            data = response.json()
            
            if "objects" not in data:
                raise ValueError("Response does not contain 'objects' field")
            
            objects = data.get("objects", [])
            
            if not objects:
                logger.info(f"No objects in page {current_page}, stopping")
                break
            
            # Apply limit_per_run
            remaining = limit_per_run - len(all_objects)
            if remaining <= 0:
                break
            
            objects_to_add = objects[:remaining]
            all_objects.extend(objects_to_add)
            
            logger.info(f"Page {current_page}: Fetched {len(objects_to_add)} objects (total: {len(all_objects)})")
            
            if len(objects) < page_size:
                logger.info("Reached last page (fewer objects than page_size)")
                break
            
            current_page += 1
            
        except Exception as e:
            logger.error(f"Error fetching page {current_page}: {e}")
            raise
    
    logger.info(f"EXTRACTION COMPLETE: Fetched {len(all_objects)} total POI objects")
    logger.info("=" * 60)
    
    return all_objects


# ============================================================================
# TRANSFORMATION STEP
# ============================================================================

def transform_poi(poi: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    TRANSFORMATION STEP: Transform a single POI object.
    
    Extracts: id, uri, label, description, latitude, longitude, type, last_update, raw_json
    Normalizes strings (strip), ensures lat/lon valid ranges.
    Skips rows missing coordinates.
    """
    # Extract ID (required)
    poi_id = poi.get("uuid") or poi.get("id")
    if not poi_id:
        return None
    
    # Extract coordinates (required - skip if missing)
    latitude, longitude = extract_coordinates(poi)
    if latitude is None or longitude is None:
        return None
    
    # Validate coordinate ranges
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return None
    
    # Extract and normalize other fields
    label = extract_label(poi)
    if label:
        label = label.strip()
    
    description = extract_description(poi)
    if description:
        description = description.strip()
    
    uri = poi.get("uri")
    if uri:
        uri = str(uri).strip() or None
    
    poi_type = extract_type(poi)
    
    last_update_str = poi.get("lastUpdate") or poi.get("last_update")
    last_update = parse_timestamp(last_update_str)
    
    # Extract city and department_code
    city = extract_city(poi)
    department_code = extract_department_code(poi)
    
    # Extract theme from URI
    theme = None
    if uri:
        theme = extract_theme_from_uri(uri)
    
    # Store raw JSON for audit trail
    raw_json = json.dumps(poi) if poi else None
    
    return {
        "id": str(poi_id),
        "uri": uri,
        "label": label,
        "description": description,
        "latitude": latitude,
        "longitude": longitude,
        "type": poi_type,
        "city": city,
        "department_code": department_code,
        "theme": theme,
        "last_update": last_update,
        "raw_json": raw_json
    }


def transform_pois(raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """TRANSFORMATION STEP: Transform a list of raw POI objects."""
    logger.info("=" * 60)
    logger.info("TRANSFORMATION STEP: Normalizing and cleaning POI data")
    logger.info("=" * 60)
    logger.info(f"Processing {len(raw_data)} raw POI objects...")
    
    transformed = []
    skipped = 0
    
    for poi in raw_data:
        try:
            transformed_poi = transform_poi(poi)
            if transformed_poi:
                transformed.append(transformed_poi)
            else:
                skipped += 1
        except Exception as e:
            logger.warning(f"Error transforming POI {poi.get('uuid', 'unknown')}: {e}")
            skipped += 1
    
    logger.info(f"TRANSFORMATION COMPLETE: {len(transformed)} transformed, {skipped} skipped")
    if skipped > 0:
        logger.info(f"Skipped {skipped} POIs (missing coordinates or invalid data)")
    logger.info("=" * 60)
    
    return transformed


# ============================================================================
# LOAD STEP
# ============================================================================

def load_pois_to_database(
    clean_data: List[Dict[str, Any]],
    batch_size: int = 100,
    engine=None
) -> Tuple[int, int, int]:
    """
    LOAD STEP: Insert or update POIs in PostgreSQL using smart UPSERT logic.
    
    Only updates if incoming last_update is newer OR db last_update is null.
    
    Args:
        clean_data: List of transformed POI dictionaries
        batch_size: Number of POIs to process before committing
        engine: SQLAlchemy engine (creates new if None)
        
    Returns:
        Tuple of (inserted_count, updated_count, skipped_count)
    """
    logger.info("=" * 60)
    logger.info("LOAD STEP: Inserting/updating POIs in PostgreSQL")
    logger.info("=" * 60)
    
    if engine is None:
        engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    inserted_count = 0
    updated_count = 0
    skipped_count = 0
    
    try:
        # Ensure data source exists
        source_id = None
        try:
            result = session.execute(text("SELECT id FROM data_source WHERE name = :name"), {"name": "DataTourisme API"})
            row = result.fetchone()
            if row:
                source_id = row[0]
        except Exception:
            pass
        
        logger.info(f"Loading {len(clean_data)} POIs into database...")
        
        # Smart UPSERT: only update if incoming last_update is newer OR db last_update is null
        upsert_query = text("""
            INSERT INTO poi (id, label, description, latitude, longitude, uri, type, city, department_code, theme, last_update, raw_json, source_id)
            VALUES (:id, :label, :description, :latitude, :longitude, :uri, :type, :city, :department_code, :theme, :last_update, CAST(:raw_json AS jsonb), :source_id)
            ON CONFLICT (id) DO UPDATE SET
                label = CASE 
                    WHEN EXCLUDED.last_update > poi.last_update OR poi.last_update IS NULL 
                    THEN EXCLUDED.label 
                    ELSE poi.label 
                END,
                description = CASE 
                    WHEN EXCLUDED.last_update > poi.last_update OR poi.last_update IS NULL 
                    THEN EXCLUDED.description 
                    ELSE poi.description 
                END,
                latitude = CASE 
                    WHEN EXCLUDED.last_update > poi.last_update OR poi.last_update IS NULL 
                    THEN EXCLUDED.latitude 
                    ELSE poi.latitude 
                END,
                longitude = CASE 
                    WHEN EXCLUDED.last_update > poi.last_update OR poi.last_update IS NULL 
                    THEN EXCLUDED.longitude 
                    ELSE poi.longitude 
                END,
                uri = CASE 
                    WHEN EXCLUDED.last_update > poi.last_update OR poi.last_update IS NULL 
                    THEN EXCLUDED.uri 
                    ELSE poi.uri 
                END,
                type = CASE 
                    WHEN EXCLUDED.last_update > poi.last_update OR poi.last_update IS NULL 
                    THEN EXCLUDED.type 
                    ELSE poi.type 
                END,
                city = CASE 
                    WHEN EXCLUDED.last_update > poi.last_update OR poi.last_update IS NULL 
                    THEN EXCLUDED.city 
                    ELSE poi.city 
                END,
                department_code = CASE 
                    WHEN EXCLUDED.last_update > poi.last_update OR poi.last_update IS NULL 
                    THEN EXCLUDED.department_code 
                    ELSE poi.department_code 
                END,
                theme = CASE 
                    WHEN EXCLUDED.last_update > poi.last_update OR poi.last_update IS NULL 
                    THEN EXCLUDED.theme 
                    ELSE poi.theme 
                END,
                last_update = CASE 
                    WHEN EXCLUDED.last_update > poi.last_update OR poi.last_update IS NULL 
                    THEN EXCLUDED.last_update 
                    ELSE poi.last_update 
                END,
                raw_json = CASE 
                    WHEN EXCLUDED.last_update > poi.last_update OR poi.last_update IS NULL 
                    THEN EXCLUDED.raw_json 
                    ELSE poi.raw_json 
                END,
                source_id = CASE 
                    WHEN EXCLUDED.last_update > poi.last_update OR poi.last_update IS NULL 
                    THEN EXCLUDED.source_id 
                    ELSE poi.source_id 
                END
        """)
        
        for poi_data in clean_data:
            try:
                # Check if POI exists and get current last_update
                existing = session.query(POI).filter(POI.id == poi_data["id"]).first()
                
                # Determine if we should update
                should_update = True
                if existing and existing.last_update:
                    incoming_update = poi_data.get("last_update")
                    if incoming_update and incoming_update <= existing.last_update:
                        should_update = False
                        skipped_count += 1
                
                if should_update:
                    params = {
                        "id": poi_data["id"],
                        "label": poi_data.get("label"),
                        "description": poi_data.get("description"),
                        "latitude": poi_data["latitude"],
                        "longitude": poi_data["longitude"],
                        "uri": poi_data.get("uri"),
                        "type": poi_data.get("type"),
                        "city": poi_data.get("city"),
                        "department_code": poi_data.get("department_code"),
                        "theme": poi_data.get("theme"),
                        "last_update": poi_data.get("last_update"),
                        "raw_json": poi_data.get("raw_json"),
                        "source_id": source_id
                    }
                    
                    session.execute(upsert_query, params)
                    
                    if existing:
                        updated_count += 1
                    else:
                        inserted_count += 1
                
                # Commit in batches
                if (inserted_count + updated_count) % batch_size == 0:
                    session.commit()
                    logger.info(f"Processed {inserted_count + updated_count} POIs... "
                              f"({inserted_count} inserted, {updated_count} updated, {skipped_count} skipped)")
                    
            except SQLAlchemyError as e:
                session.rollback()
                logger.warning(f"Error processing POI {poi_data.get('id', 'unknown')}: {e}")
                skipped_count += 1
                continue
            except Exception as e:
                session.rollback()
                logger.warning(f"Unexpected error processing POI {poi_data.get('id', 'unknown')}: {e}")
                skipped_count += 1
                continue
        
        # Final commit
        session.commit()
        
        logger.info("=" * 60)
        logger.info(f"LOAD COMPLETE:")
        logger.info(f"  - Inserted: {inserted_count}")
        logger.info(f"  - Updated: {updated_count}")
        logger.info(f"  - Skipped: {skipped_count}")
        logger.info("=" * 60)
        
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to load POIs: {e}")
        raise
    finally:
        session.close()
    
    return (inserted_count, updated_count, skipped_count)


# ============================================================================
# MAIN ETL WORKFLOW
# ============================================================================

def main():
    """Main ETL workflow orchestrator."""
    parser = argparse.ArgumentParser(description="Batch ETL Pipeline for Holiday Itinerary Project")
    parser.add_argument("--limit-per-run", type=int, default=500,
                       help="Maximum POIs to fetch per run (default: 500)")
    parser.add_argument("--max-pages", type=int, default=5,
                       help="Maximum pages to fetch (default: 5)")
    parser.add_argument("--since-hours", type=int, default=24,
                       help="Filter POIs updated in last N hours (default: 24, note: API may not support)")
    
    args = parser.parse_args()
    
    start_time = datetime.now()
    run_id = None
    engine = None
    
    try:
        # Create database engine
        engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
        
        # Ensure pipeline_runs table exists
        ensure_pipeline_runs_table(engine)
        
        # Create pipeline run record
        run_id = create_pipeline_run(engine)
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("Batch ETL Pipeline - Holiday Itinerary Project")
        logger.info("=" * 60)
        logger.info(f"Run ID: {run_id}")
        logger.info(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Arguments: limit_per_run={args.limit_per_run}, max_pages={args.max_pages}, since_hours={args.since_hours}")
        logger.info("")
        
        # Initialize rate limiter
        rate_limiter = RateLimiter(MAX_REQUESTS_PER_SECOND, MAX_REQUESTS_PER_HOUR)
        
        # EXTRACTION: Fetch POIs from DataTourisme API
        raw_pois = fetch_pois_from_api(
            max_pages=args.max_pages,
            page_size=250,
            limit_per_run=args.limit_per_run,
            since_hours=args.since_hours,
            rate_limiter=rate_limiter
        )
        
        update_pipeline_run(engine, run_id, 'running', fetched_count=len(raw_pois))
        
        if not raw_pois:
            logger.warning("No POIs fetched from API. Pipeline ending.")
            update_pipeline_run(engine, run_id, 'success', processed_count=0, inserted_count=0, updated_count=0, skipped_count=0)
            return
        
        # TRANSFORMATION: Normalize and clean the data
        clean_pois = transform_pois(raw_pois)
        
        update_pipeline_run(engine, run_id, 'running', processed_count=len(clean_pois))
        
        if not clean_pois:
            logger.warning("No valid POIs after transformation. Pipeline ending.")
            update_pipeline_run(engine, run_id, 'success', inserted_count=0, updated_count=0, skipped_count=len(raw_pois))
            return
        
        # LOAD: Insert or update records in PostgreSQL
        inserted_count, updated_count, skipped_count = load_pois_to_database(clean_pois, batch_size=100, engine=engine)
        
        # Update pipeline run with final results
        update_pipeline_run(
            engine, run_id, 'success',
            processed_count=len(clean_pois),
            inserted_count=inserted_count,
            updated_count=updated_count,
            skipped_count=skipped_count
        )
        
        # Calculate duration
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Print execution summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("Pipeline Execution Summary")
        logger.info("=" * 60)
        logger.info(f"Run ID: {run_id}")
        logger.info(f"Status: SUCCESS")
        logger.info(f"Raw POIs fetched: {len(raw_pois)}")
        logger.info(f"Clean POIs transformed: {len(clean_pois)}")
        logger.info(f"Inserted: {inserted_count}")
        logger.info(f"Updated: {updated_count}")
        logger.info(f"Skipped: {skipped_count}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("=" * 60)
        
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        error_message = str(e)
        logger.error("")
        logger.error("=" * 60)
        logger.error("Pipeline Execution Failed")
        logger.error("=" * 60)
        logger.error(f"Run ID: {run_id}")
        logger.error(f"Error: {error_message}")
        logger.error(f"Duration: {duration:.2f} seconds")
        logger.error("=" * 60)
        
        if run_id and engine:
            update_pipeline_run(engine, run_id, 'failed', error_message=error_message)
        
        sys.exit(1)


if __name__ == "__main__":
    main()
