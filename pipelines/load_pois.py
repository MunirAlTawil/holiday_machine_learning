"""
Load POIs into PostgreSQL using SQLAlchemy.
Supports insert and update operations.
"""
import os
from typing import List, Dict, Any, Tuple, Optional
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# Import models and database setup
import sys
from pathlib import Path

# Add src to path to import modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.api.db import Base, get_db
from src.api.models import POI

# Load environment variables
load_dotenv()

# Database connection parameters
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "holiday")
POSTGRES_USER = os.getenv("POSTGRES_USER", "holiday")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "holiday")

# Construct database URL
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"


def get_db_session():
    """
    Create and return a database session.
    
    Returns:
        SQLAlchemy session object
    """
    engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def ensure_data_source(session, source_name: str = "DataTourisme API") -> int:
    """
    Ensure data source exists in database, return its ID.
    
    Args:
        session: Database session
        source_name: Name of the data source
        
    Returns:
        Data source ID
    """
    from sqlalchemy import text
    
    # Check if data_source table exists
    try:
        result = session.execute(text("""
            SELECT id FROM data_source WHERE name = :name
        """), {"name": source_name})
        row = result.fetchone()
        
        if row:
            return row[0]
        
        # Create new data source
        result = session.execute(text("""
            INSERT INTO data_source (name, description)
            VALUES (:name, :description)
            RETURNING id
        """), {
            "name": source_name,
            "description": f"Data source: {source_name}"
        })
        source_id = result.fetchone()[0]
        session.commit()
        return source_id
        
    except SQLAlchemyError as e:
        session.rollback()
        # If table doesn't exist, return None (source_id can be NULL)
        print(f"[WARNING] Could not ensure data source: {e}")
        return None


def load_pois(clean_data: List[Dict[str, Any]], batch_size: int = 100) -> Tuple[int, int, int]:
    """
    Load clean POI data into PostgreSQL using SQLAlchemy models.
    Inserts new POIs and updates existing ones if last_update is newer.
    Commits in batches for performance.
    
    Args:
        clean_data: List of clean POI dictionaries with fields:
                   id, label, description, type, lat, lon, updated_at
        batch_size: Number of POIs to process before committing (default: 100)
        
    Returns:
        Tuple of (inserted_count, updated_count, skipped_count)
    """
    from datetime import datetime
    
    session = get_db_session()
    inserted_count = 0
    updated_count = 0
    skipped_count = 0
    
    try:
        for i, poi_data in enumerate(clean_data, 1):
            try:
                # Map clean_data fields to POI model fields
                poi_id = poi_data.get("id")
                if not poi_id:
                    skipped_count += 1
                    continue
                
                # Check if POI exists
                existing_poi = session.query(POI).filter(POI.id == poi_id).first()
                
                # Prepare data for POI model (map lat->latitude, lon->longitude, updated_at->last_update)
                latitude = poi_data.get("lat")
                longitude = poi_data.get("lon")
                
                # Validate coordinates
                if latitude is None or longitude is None:
                    skipped_count += 1
                    continue
                
                if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
                    skipped_count += 1
                    continue
                
                # Map fields
                poi_model_data = {
                    "id": poi_id,
                    "label": poi_data.get("label"),
                    "description": poi_data.get("description"),
                    "type": poi_data.get("type"),
                    "latitude": latitude,
                    "longitude": longitude,
                    "last_update": poi_data.get("updated_at"),  # Map updated_at to last_update
                    "uri": None,  # Not in clean_data
                    "city": None,  # Not in clean_data
                    "department_code": None,  # Not in clean_data
                    "raw_json": None,  # Not in clean_data
                    "source_id": None  # Not in clean_data
                }
                
                if existing_poi:
                    # Update only if new last_update is newer (or existing is None)
                    new_last_update = poi_model_data.get("last_update")
                    existing_last_update = existing_poi.last_update
                    
                    should_update = False
                    if new_last_update is None:
                        # If new data has no timestamp, don't update
                        should_update = False
                    elif existing_last_update is None:
                        # If existing has no timestamp, update
                        should_update = True
                    elif isinstance(new_last_update, datetime) and isinstance(existing_last_update, datetime):
                        # Compare timestamps
                        should_update = new_last_update > existing_last_update
                    else:
                        # Fallback: always update if timestamps can't be compared
                        should_update = True
                    
                    if should_update:
                        # Update existing POI
                        existing_poi.label = poi_model_data["label"]
                        existing_poi.description = poi_model_data["description"]
                        existing_poi.type = poi_model_data["type"]
                        existing_poi.latitude = poi_model_data["latitude"]
                        existing_poi.longitude = poi_model_data["longitude"]
                        existing_poi.last_update = poi_model_data["last_update"]
                        updated_count += 1
                    else:
                        # Skip update if existing is newer or equal
                        skipped_count += 1
                        continue
                else:
                    # Insert new POI
                    new_poi = POI(**poi_model_data)
                    session.add(new_poi)
                    inserted_count += 1
                
                # Commit in batches
                if (inserted_count + updated_count) % batch_size == 0:
                    session.commit()
                    print(f"[INFO] Processed {inserted_count + updated_count} POIs...")
                    
            except SQLAlchemyError as e:
                session.rollback()
                print(f"[WARNING] Error processing POI {poi_data.get('id', 'unknown')}: {e}")
                skipped_count += 1
                continue
            except Exception as e:
                session.rollback()
                print(f"[WARNING] Unexpected error processing POI {poi_data.get('id', 'unknown')}: {e}")
                skipped_count += 1
                continue
        
        # Final commit
        session.commit()
        
    except Exception as e:
        session.rollback()
        raise Exception(f"Failed to load POIs: {e}")
    finally:
        session.close()
    
    return (inserted_count, updated_count, skipped_count)


def load_pois_legacy(pois: List[Dict[str, Any]], source_id: Optional[int] = None, batch_size: int = 100) -> Tuple[int, int, int]:
    """
    Load POIs into PostgreSQL with UPSERT functionality.
    
    Args:
        pois: List of transformed POI dictionaries
        source_id: Data source ID (if None, will try to ensure default source)
        batch_size: Number of POIs to process before committing (default: 100)
        
    Returns:
        Tuple of (inserted_count, updated_count, skipped_count)
    """
    session = get_db_session()
    inserted_count = 0
    updated_count = 0
    skipped_count = 0
    
    try:
        # Ensure data source if source_id is None
        if source_id is None:
            source_id = ensure_data_source(session)
        
        for i, poi_data in enumerate(pois, 1):
            try:
                # Check if POI exists
                existing_poi = session.query(POI).filter(POI.id == poi_data["id"]).first()
                
                # Set source_id if not provided in POI data
                if poi_data.get("source_id") is None:
                    poi_data["source_id"] = source_id
                
                if existing_poi:
                    # Update existing POI
                    for key, value in poi_data.items():
                        if key != "id":  # Don't update the ID
                            setattr(existing_poi, key, value)
                    updated_count += 1
                else:
                    # Insert new POI
                    new_poi = POI(**poi_data)
                    session.add(new_poi)
                    inserted_count += 1
                
                # Commit in batches
                if (inserted_count + updated_count) % batch_size == 0:
                    session.commit()
                    
            except SQLAlchemyError as e:
                session.rollback()
                print(f"[WARNING] Error processing POI {poi_data.get('id', 'unknown')}: {e}")
                skipped_count += 1
                continue
            except Exception as e:
                session.rollback()
                print(f"[WARNING] Unexpected error processing POI {poi_data.get('id', 'unknown')}: {e}")
                skipped_count += 1
                continue
        
        # Final commit
        session.commit()
        
    except Exception as e:
        session.rollback()
        raise Exception(f"Failed to load POIs: {e}")
    finally:
        session.close()
    
    return (inserted_count, updated_count, skipped_count)


def health_check() -> bool:
    """
    Check database connection health.
    
    Returns:
        True if connection is healthy, False otherwise
    """
    try:
        session = get_db_session()
        from sqlalchemy import text
        session.execute(text("SELECT 1"))
        session.close()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="Load POIs into PostgreSQL")
    parser.add_argument("--source-id", type=int, default=None,
                       help="Data source ID (default: auto-detect)")
    parser.add_argument("--batch-size", type=int, default=100,
                       help="Batch size for commits (default: 100)")
    
    args = parser.parse_args()
    
    # Test with sample clean data
    from datetime import datetime
    
    sample_clean_data = [
        {
            "id": "test-poi-1",
            "label": "Test POI",
            "description": "Test description",
            "type": "Museum",
            "lat": 48.8566,
            "lon": 2.3522,
            "updated_at": datetime(2024, 1, 15, 10, 30)
        }
    ]
    
    print("Testing database connection...")
    if not health_check():
        print("[ERROR] Database connection failed")
        sys.exit(1)
    
    print("[OK] Database connection successful")
    print(f"Loading {len(sample_clean_data)} test POIs...")
    
    try:
        inserted, updated, skipped = load_pois(
            sample_clean_data,
            batch_size=args.batch_size
        )
        print(f"[OK] Load complete: {inserted} inserted, {updated} updated, {skipped} skipped")
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

