"""
Main pipeline runner for ETL operations.
Orchestrates fetch, transform, and load steps.
"""
import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pipelines.fetch_pois import fetch_pois
from pipelines.transform_pois import transform_pois
from pipelines.load_pois import load_pois, health_check


def run_pipeline(
    source: str = "fastapi",
    limit: int = 5000,
    offset: int = 0,
    page_size: int = 250,
    max_pages: int = None,
    source_id: int = None,
    batch_size: int = 100,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Run the complete ETL pipeline.
    
    Args:
        source: Source to fetch from - "fastapi" or "datatourisme" (default: "fastapi")
        limit: Maximum number of POIs to fetch (for fastapi)
        offset: Offset for pagination (for fastapi)
        page_size: Page size for DataTourisme API
        max_pages: Maximum number of pages to fetch (for datatourisme)
        source_id: Data source ID (None = auto-detect)
        batch_size: Batch size for database commits (default: 100)
        dry_run: If True, only fetch and transform without loading (default: False)
        
    Returns:
        Dictionary with pipeline execution results
    """
    start_time = datetime.now()
    results = {
        "start_time": start_time.isoformat(),
        "source": source,
        "fetch_count": 0,
        "transform_count": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "status": "unknown",
        "error": None
    }
    
    try:
        # Step 1: Health check
        print("=" * 60)
        print("POI ETL Pipeline")
        print("=" * 60)
        print(f"Source: {source}")
        print(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        if not dry_run:
            print("Step 1: Database health check...")
            if not health_check():
                raise Exception("Database connection failed. Please check your database configuration.")
            print("[OK] Database connection healthy")
            print()
        
        # Step 2: Fetch
        print("Step 2: Fetching POIs...")
        if source == "fastapi":
            raw_data = fetch_pois(limit=limit, offset=offset, endpoint="geojson")
            # Extract count from raw_data
            if raw_data.get("type") == "FeatureCollection":
                fetch_count = len(raw_data.get("features", []))
            else:
                fetch_count = len(raw_data.get("items", []))
        else:
            # For datatourisme, use legacy function
            from pipelines.fetch_pois import fetch_pois_from_source
            raw_pois = fetch_pois_from_source(source="datatourisme", page_size=page_size, max_pages=max_pages)
            # Convert to raw_data format for transform
            raw_data = {"items": raw_pois}
            fetch_count = len(raw_pois)
        
        results["fetch_count"] = fetch_count
        print(f"[OK] Fetched {fetch_count} POIs from {source}")
        print()
        
        if fetch_count == 0:
            print("[WARNING] No POIs fetched. Pipeline ending.")
            results["status"] = "completed"
            return results
        
        # Step 3: Transform
        print("Step 3: Transforming and normalizing POIs...")
        clean_data = transform_pois(raw_data)
        results["transform_count"] = len(clean_data)
        print(f"[OK] Transformed {len(clean_data)} POIs")
        print(f"[INFO] Skipped {fetch_count - len(clean_data)} invalid POIs")
        print()
        
        if not clean_data:
            print("[WARNING] No valid POIs after transformation. Pipeline ending.")
            results["status"] = "completed"
            return results
        
        # Step 4: Load (if not dry run)
        if dry_run:
            print("Step 4: Load (DRY RUN - skipping)")
            print(f"[INFO] Would load {len(clean_data)} POIs")
            results["status"] = "dry_run_completed"
        else:
            print("Step 4: Loading POIs into database...")
            inserted, updated, skipped = load_pois(
                clean_data,
                batch_size=batch_size
            )
            results["inserted_count"] = inserted
            results["updated_count"] = updated
            results["skipped_count"] = skipped
            print(f"[OK] Load complete:")
            print(f"  - Inserted: {inserted}")
            print(f"  - Updated: {updated}")
            print(f"  - Skipped: {skipped}")
            results["status"] = "completed"
        
        # Calculate duration
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results["end_time"] = end_time.isoformat()
        results["duration_seconds"] = duration
        
        print()
        print("=" * 60)
        print("Pipeline Summary")
        print("=" * 60)
        print(f"Status: {results['status']}")
        print(f"Fetched: {results['fetch_count']}")
        print(f"Transformed: {results['transform_count']}")
        if not dry_run:
            print(f"Inserted: {results['inserted_count']}")
            print(f"Updated: {results['updated_count']}")
            print(f"Skipped: {results['skipped_count']}")
        print(f"Duration: {duration:.2f} seconds")
        print("=" * 60)
        
        return results
        
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        results["end_time"] = end_time.isoformat()
        results["duration_seconds"] = duration
        results["status"] = "failed"
        results["error"] = str(e)
        
        print()
        print("=" * 60)
        print("Pipeline Failed")
        print("=" * 60)
        print(f"Error: {e}")
        print(f"Duration: {duration:.2f} seconds")
        print("=" * 60)
        
        return results


def main():
    """
    Main function that orchestrates the ETL pipeline.
    Calls fetch_pois, transform_pois, and load_pois in sequence.
    Prints execution summary.
    """
    parser = argparse.ArgumentParser(
        description="Run POI ETL pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch from FastAPI and load
  python pipelines/run_pipeline.py --limit 1000
  
  # Dry run (fetch and transform only)
  python pipelines/run_pipeline.py --limit 500 --dry-run
  
  # Fetch with custom batch size
  python pipelines/run_pipeline.py --limit 5000 --batch-size 200
        """
    )
    
    parser.add_argument("--source", choices=["fastapi", "datatourisme"], default="fastapi",
                       help="Source to fetch from (default: fastapi)")
    parser.add_argument("--limit", type=int, default=1000,
                       help="Maximum number of POIs to fetch (for fastapi, default: 1000)")
    parser.add_argument("--offset", type=int, default=0,
                       help="Offset for pagination (for fastapi, default: 0)")
    parser.add_argument("--page-size", type=int, default=250,
                       help="Page size for DataTourisme API (default: 250)")
    parser.add_argument("--max-pages", type=int, default=None,
                       help="Maximum number of pages to fetch (for datatourisme)")
    parser.add_argument("--batch-size", type=int, default=100,
                       help="Batch size for database commits (default: 100)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Fetch and transform only, do not load to database")
    
    args = parser.parse_args()
    
    # Run pipeline
    results = run_pipeline(
        source=args.source,
        limit=args.limit,
        offset=args.offset,
        page_size=args.page_size,
        max_pages=args.max_pages,
        source_id=None,  # Removed from new load_pois signature
        batch_size=args.batch_size,
        dry_run=args.dry_run
    )
    
    # Exit with appropriate code
    if results["status"] == "failed":
        sys.exit(1)
    elif results["status"] in ["completed", "dry_run_completed"]:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

