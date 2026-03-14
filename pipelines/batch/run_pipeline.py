"""
Main pipeline orchestrator for batch ETL operations.
Orchestrates fetch → transform → load steps.
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from pipelines.batch.fetch_pois import fetch_pois
from pipelines.batch.transform_pois import load_raw_json, transform_pois
from pipelines.batch.load_pois import load_pois, health_check

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def main():
    """
    Main function that orchestrates the batch ETL pipeline.
    Executes: fetch → transform → load
    """
    start_time = datetime.now()
    
    logger.info("=" * 60)
    logger.info("Batch ETL Pipeline - Holiday Itinerary Project")
    logger.info("=" * 60)
    logger.info(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")
    
    try:
        # Step 1: Database health check
        logger.info("Step 1: Database health check...")
        if not health_check():
            raise Exception("Database connection failed. Please check your database configuration.")
        logger.info("[OK] Database connection healthy")
        logger.info("")
        
        # Step 2: Fetch POIs from DataTourisme API
        logger.info("Step 2: Fetching POIs from DataTourisme API...")
        raw_json_path = fetch_pois(max_pages=None, page_size=250)
        logger.info("")
        
        # Step 3: Transform raw data
        logger.info("Step 3: Transforming raw POI data...")
        raw_data = load_raw_json(raw_json_path)
        clean_data = transform_pois(raw_data)
        logger.info("")
        
        if not clean_data:
            logger.warning("No valid POIs after transformation. Pipeline ending.")
            return
        
        # Step 4: Load into database
        logger.info("Step 4: Loading POIs into PostgreSQL...")
        inserted_count, updated_count = load_pois(clean_data, batch_size=100)
        logger.info("")
        
        # Calculate duration
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Print execution summary
        logger.info("=" * 60)
        logger.info("Pipeline Execution Summary")
        logger.info("=" * 60)
        logger.info(f"Status: SUCCESS")
        logger.info(f"Raw data file: {raw_json_path}")
        logger.info(f"Raw POIs fetched: {len(raw_data)}")
        logger.info(f"Clean POIs transformed: {len(clean_data)}")
        logger.info(f"Inserted: {inserted_count}")
        logger.info(f"Updated: {updated_count}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("=" * 60)
        
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.error("=" * 60)
        logger.error("Pipeline Execution Failed")
        logger.error("=" * 60)
        logger.error(f"Error: {e}")
        logger.error(f"Duration: {duration:.2f} seconds")
        logger.error("=" * 60)
        
        sys.exit(1)


if __name__ == "__main__":
    main()

