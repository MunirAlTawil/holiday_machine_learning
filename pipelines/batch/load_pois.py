"""
Load transformed POI data into PostgreSQL using upsert logic.
Avoids duplicates and logs inserted vs updated rows.
"""
import logging
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# Import models
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.api.models import POI

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

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


def ensure_data_source(session, source_name: str = "DataTourisme API") -> Optional[int]:
    """
    Ensure data source exists in database, return its ID.
    
    Args:
        session: Database session
        source_name: Name of the data source
        
    Returns:
        Data source ID or None if table doesn't exist
    """
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
        logger.info(f"Created data source: {source_name} (ID: {source_id})")
        return source_id
        
    except SQLAlchemyError as e:
        session.rollback()
        logger.warning(f"Could not ensure data source (table may not exist): {e}")
        return None


def load_pois(clean_data: List[Dict[str, Any]], batch_size: int = 100) -> Tuple[int, int]:
    """
    Load clean POI data into PostgreSQL using upsert logic.
    
    Args:
        clean_data: List of clean POI dictionaries with fields:
                   id, label, latitude, longitude, uri, last_update, raw_json
        batch_size: Number of POIs to process before committing (default: 100)
        
    Returns:
        Tuple of (inserted_count, updated_count)
    """
    session = get_db_session()
    inserted_count = 0
    updated_count = 0
    skipped_count = 0
    
    try:
        # Ensure data source exists
        source_id = ensure_data_source(session)
        
        logger.info(f"Loading {len(clean_data)} POIs into database...")
        
        # Upsert query using ON CONFLICT
        upsert_query = text("""
            INSERT INTO poi (id, label, latitude, longitude, uri, last_update, raw_json, source_id)
            VALUES (:id, :label, :latitude, :longitude, :uri, :last_update, :raw_json::jsonb, :source_id)
            ON CONFLICT (id) DO UPDATE SET
                label = EXCLUDED.label,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                uri = EXCLUDED.uri,
                last_update = EXCLUDED.last_update,
                raw_json = EXCLUDED.raw_json,
                source_id = EXCLUDED.source_id
        """)
        
        for i, poi_data in enumerate(clean_data, 1):
            try:
                # Check if POI exists to determine insert vs update
                existing = session.query(POI).filter(POI.id == poi_data["id"]).first()
                
                # Prepare data for upsert
                params = {
                    "id": poi_data["id"],
                    "label": poi_data.get("label"),
                    "latitude": poi_data["latitude"],
                    "longitude": poi_data["longitude"],
                    "uri": poi_data.get("uri"),
                    "last_update": poi_data.get("last_update"),
                    "raw_json": poi_data.get("raw_json"),
                    "source_id": source_id
                }
                
                # Execute upsert
                session.execute(upsert_query, params)
                
                if existing:
                    updated_count += 1
                else:
                    inserted_count += 1
                
                # Commit in batches
                if (inserted_count + updated_count) % batch_size == 0:
                    session.commit()
                    logger.info(f"Processed {inserted_count + updated_count} POIs... "
                              f"({inserted_count} inserted, {updated_count} updated)")
                    
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
        logger.info(f"Load complete:")
        logger.info(f"  - Inserted: {inserted_count}")
        logger.info(f"  - Updated: {updated_count}")
        if skipped_count > 0:
            logger.info(f"  - Skipped: {skipped_count}")
        logger.info("=" * 60)
        
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to load POIs: {e}")
        raise
    finally:
        session.close()
    
    return (inserted_count, updated_count)


def health_check() -> bool:
    """
    Check database connection health.
    
    Returns:
        True if connection is healthy, False otherwise
    """
    try:
        session = get_db_session()
        session.execute(text("SELECT 1"))
        session.close()
        logger.info("Database health check: OK")
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Load POIs into PostgreSQL")
    parser.add_argument("input_file", type=Path,
                       help="Path to transformed JSON file (or use stdin)")
    parser.add_argument("--batch-size", type=int, default=100,
                       help="Batch size for commits (default: 100)")
    
    args = parser.parse_args()
    
    # Check database health
    if not health_check():
        logger.error("Database connection failed")
        sys.exit(1)
    
    # Load transformed data
    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            clean_data = json.load(f)
        
        if not isinstance(clean_data, list):
            raise ValueError("Expected list in JSON file")
        
        inserted, updated = load_pois(clean_data, batch_size=args.batch_size)
        print(f"\n[SUCCESS] Load complete: {inserted} inserted, {updated} updated")
        
    except Exception as e:
        logger.error(f"Load failed: {e}")
        sys.exit(1)

