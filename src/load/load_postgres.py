"""
PostgreSQL loader for DataTourisme POI data.
Loads CSV data into PostgreSQL with UPSERT functionality.
"""
import sys
import csv
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
import psycopg2
from dotenv import load_dotenv
import os

from src.config import PROCESSED_DATA_DIR, PROJECT_ROOT

# Load environment variables
load_dotenv()

# Database connection parameters
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "holiday")
POSTGRES_USER = os.getenv("POSTGRES_USER", "holiday")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "holiday")


def get_db_connection():
    """
    Create and return a PostgreSQL database connection.
    
    Returns:
        psycopg2.connection: Database connection object
    
    Raises:
        psycopg2.Error: If connection fails
    """
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        return conn
    except psycopg2.Error as e:
        raise ConnectionError(
            f"Failed to connect to PostgreSQL database.\n"
            f"Host: {POSTGRES_HOST}:{POSTGRES_PORT}, Database: {POSTGRES_DB}, User: {POSTGRES_USER}\n"
            f"Error: {e}\n"
            f"Make sure PostgreSQL is running (docker compose up -d) and connection parameters are correct."
        )


def health_check() -> bool:
    """
    Perform a health check on the database connection.
    
    Returns:
        bool: True if connection is healthy, False otherwise
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            result = cur.fetchone()
        conn.close()
        return result[0] == 1
    except Exception as e:
        print(f"[ERROR] Database health check failed: {e}")
        return False


def ensure_data_source(conn) -> int:
    """
    Ensure the 'datatourisme' data source exists and return its ID.
    
    Args:
        conn: Database connection
    
    Returns:
        int: Data source ID
    """
    with conn.cursor() as cur:
        # Try to get existing data source
        cur.execute(
            "SELECT id FROM data_source WHERE name = %s",
            ('datatourisme',)
        )
        result = cur.fetchone()
        
        if result:
            return result[0]
        
        # Insert if it doesn't exist
        cur.execute(
            "INSERT INTO data_source (name, description) VALUES (%s, %s) RETURNING id",
            ('datatourisme', 'DataTourisme API - French tourism data platform')
        )
        source_id = cur.fetchone()[0]
        conn.commit()
        return source_id


def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
    """
    Parse a timestamp string to datetime object.
    
    Args:
        timestamp_str: Timestamp string (e.g., '2026-02-03' or '2026-02-03T10:30:00Z')
    
    Returns:
        Optional[datetime]: Parsed datetime or None if invalid/empty
    """
    if not timestamp_str or timestamp_str.strip() == '':
        return None
    
    timestamp_str = timestamp_str.strip()
    
    # Try common formats
    formats = [
        '%Y-%m-%d',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M:%S%z',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue
    
    # If all formats fail, return None
    return None


def parse_float(value: str) -> Optional[float]:
    """
    Safely parse a string to float.
    
    Args:
        value: String value to parse
    
    Returns:
        Optional[float]: Parsed float or None if invalid
    """
    if not value or value.strip() == '':
        return None
    
    try:
        return float(value.strip())
    except (ValueError, TypeError):
        return None


def create_etl_run(conn, run_type: str, status: str, rows_processed: int, 
                   rows_inserted: int, rows_skipped: int, message: Optional[str] = None) -> int:
    """
    Create an ETL run record in the etl_run table.
    
    Args:
        conn: Database connection
        run_type: Type of run ('extract' or 'load')
        status: Status ('success' or 'fail')
        rows_processed: Total rows processed
        rows_inserted: Rows inserted
        rows_skipped: Rows skipped
        message: Optional message
        
    Returns:
        int: ETL run ID
    """
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO etl_run (run_type, status, rows_processed, rows_inserted, rows_skipped, finished_at, message)
            VALUES (%s, %s, %s, %s, %s, NOW(), %s)
            RETURNING id
        """, (run_type, status, rows_processed, rows_inserted, rows_skipped, message))
        run_id = cur.fetchone()[0]
        conn.commit()
        return run_id


def load_pois_from_csv(csv_path: Path, source_id: int, conn) -> Tuple[int, int, int]:
    """
    Load POIs from CSV file into PostgreSQL with UPSERT.
    
    Supports both naming conventions:
    - uuid OR id
    - lat OR latitude
    - lon OR longitude
    - lastUpdate OR last_update
    
    Args:
        csv_path: Path to CSV file
        source_id: Data source ID
        conn: Database connection
    
    Returns:
        Tuple[int, int, int]: (inserted_count, updated_count, skipped_count)
    """
    inserted_count = 0
    updated_count = 0
    skipped_count = 0
    missing_coords_count = 0
    missing_coords_samples = []
    
    upsert_query = """
        INSERT INTO poi (id, label, description, latitude, longitude, uri, type, city, department_code, last_update, raw_json, source_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            label = EXCLUDED.label,
            description = EXCLUDED.description,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            uri = EXCLUDED.uri,
            type = EXCLUDED.type,
            city = EXCLUDED.city,
            department_code = EXCLUDED.department_code,
            last_update = EXCLUDED.last_update,
            source_id = EXCLUDED.source_id
    """
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        with conn.cursor() as cur:
            for row in reader:
                # Extract ID - support both 'uuid' and 'id' field names
                poi_id = (row.get('uuid') or row.get('id', '')).strip()
                if not poi_id:
                    skipped_count += 1
                    continue
                
                # Parse coordinates - support both 'lat'/'lon' and 'latitude'/'longitude' field names
                lat_value = row.get('lat') or row.get('latitude', '')
                lon_value = row.get('lon') or row.get('longitude', '')
                latitude = parse_float(lat_value)
                longitude = parse_float(lon_value)
                
                # Validate coordinates
                if latitude is None or longitude is None:
                    missing_coords_count += 1
                    # Collect sample of 3 UUIDs with missing coordinates
                    if len(missing_coords_samples) < 3:
                        missing_coords_samples.append(poi_id)
                    skipped_count += 1
                    continue
                
                if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
                    skipped_count += 1
                    continue
                
                # Extract other fields - accept empty strings as None
                label = row.get('label', '').strip() or None
                description = row.get('description', '').strip() or None
                uri = row.get('uri', '').strip() or None
                type_value = row.get('type', '').strip() or None
                city = row.get('city', '').strip() or None
                department_code = row.get('department_code', '').strip() or None
                
                # Support both 'lastUpdate' and 'last_update' field names
                # If missing, set to NULL
                last_update_str = row.get('lastUpdate') or row.get('last_update', '')
                last_update = parse_timestamp(last_update_str) if last_update_str else None
                
                # raw_json is NULL for now (unless CSV has a raw_json column)
                raw_json = None
                if 'raw_json' in row and row.get('raw_json', '').strip():
                    try:
                        import json
                        raw_json = json.dumps(json.loads(row['raw_json']))
                    except (json.JSONDecodeError, ValueError):
                        raw_json = None
                
                # Check if POI already exists to count inserts vs updates
                cur.execute("SELECT id FROM poi WHERE id = %s", (poi_id,))
                exists = cur.fetchone() is not None
                
                # Execute UPSERT
                try:
                    cur.execute(upsert_query, (
                        poi_id,
                        label,
                        description,
                        latitude,
                        longitude,
                        uri,
                        type_value,
                        city,
                        department_code,
                        last_update,
                        raw_json,
                        source_id
                    ))
                    
                    if exists:
                        updated_count += 1
                    else:
                        inserted_count += 1
                    
                    # Commit every 100 rows for better performance
                    if (inserted_count + updated_count) % 100 == 0:
                        conn.commit()
                        
                except psycopg2.Error as e:
                    conn.rollback()
                    print(f"[WARNING] Error inserting POI {poi_id}: {e}")
                    skipped_count += 1
            
            # Final commit
            conn.commit()
    
    # Log missing coordinates information
    if missing_coords_count > 0:
        print(f"[WARNING] {missing_coords_count} rows skipped due to missing coordinates")
        if missing_coords_samples:
            print(f"[INFO] Sample UUIDs with missing coordinates: {', '.join(missing_coords_samples)}")
    
    return (inserted_count, updated_count, skipped_count)


def main():
    """Main function for running the loader as a script."""
    print("PostgreSQL POI Loader")
    print("=" * 50)
    
    # Health check
    print("Performing database health check...")
    if not health_check():
        print("[ERROR] Database connection failed. Please check:")
        print(f"  1. PostgreSQL is running: docker compose up -d")
        print(f"  2. Connection parameters in .env or environment variables")
        print(f"     POSTGRES_HOST={POSTGRES_HOST}")
        print(f"     POSTGRES_PORT={POSTGRES_PORT}")
        print(f"     POSTGRES_DB={POSTGRES_DB}")
        print(f"     POSTGRES_USER={POSTGRES_USER}")
        sys.exit(1)
    
    print("[OK] Database connection successful")
    
    # Get CSV file path
    csv_path = PROCESSED_DATA_DIR / "datatourisme_pois.csv"
    
    if not csv_path.exists():
        print(f"[ERROR] CSV file not found: {csv_path}")
        print("Please run the extraction first:")
        print("  py -m src.extract.fetch_datatourisme --page-size 50 --page 1")
        sys.exit(1)
    
    print(f"[OK] Found CSV file: {csv_path}")
    
    # Connect to database
    try:
        conn = get_db_connection()
        print("[OK] Connected to PostgreSQL database")
    except ConnectionError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    
    try:
        # Ensure data source exists
        print("Ensuring data source exists...")
        source_id = ensure_data_source(conn)
        print(f"[OK] Data source ID: {source_id}")
        
        # Load POIs from CSV
        print(f"Loading POIs from {csv_path}...")
        inserted, updated, skipped = load_pois_from_csv(csv_path, source_id, conn)
        
        total_processed = inserted + updated + skipped
        
        # Create ETL run record
        try:
            run_id = create_etl_run(
                conn=conn,
                run_type='load',
                status='success',
                rows_processed=total_processed,
                rows_inserted=inserted,
                rows_skipped=skipped,
                message=f"Loaded {inserted} new, updated {updated} existing, skipped {skipped} invalid"
            )
            print(f"[OK] ETL run recorded (ID: {run_id})")
        except Exception as e:
            print(f"[WARNING] Failed to record ETL run: {e}")
        
        # Print summary
        print("\n" + "=" * 50)
        print("Load Summary:")
        print(f"  Total rows processed: {total_processed}")
        print(f"  Inserted: {inserted}")
        print(f"  Updated: {updated}")
        print(f"  Skipped (invalid data): {skipped}")
        print("=" * 50)
        
        if skipped > 0:
            print(f"[WARNING] {skipped} rows were skipped due to invalid data (missing coordinates, etc.)")
        
        print("[OK] Data loading completed successfully!")
        
    except Exception as e:
        # Record failed ETL run
        try:
            create_etl_run(
                conn=conn,
                run_type='load',
                status='fail',
                rows_processed=0,
                rows_inserted=0,
                rows_skipped=0,
                message=f"Error: {str(e)}"
            )
        except:
            pass
        
        print(f"[ERROR] Error during data loading: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

