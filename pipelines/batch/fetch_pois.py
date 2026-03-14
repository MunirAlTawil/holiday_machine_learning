"""
Fetch POIs from DataTourisme REST API with pagination.
Saves raw JSON data to /data/raw/pois_YYYYMMDD.json
"""
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import requests
from dotenv import load_dotenv

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

# Configuration
BASE_URL = os.getenv("BASE_URL", "https://api.datatourisme.fr")
DATATOURISME_API_KEY = os.getenv("DATATOURISME_API_KEY", "")
API_URL = f"{BASE_URL}/v1/catalog"

# Get project root and data directories
PROJECT_ROOT = Path(__file__).parent.parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)


def fetch_page(page: int, page_size: int = 250, lang: str = "fr,en") -> Dict[str, Any]:
    """
    Fetch a single page from DataTourisme API.
    
    Args:
        page: Page number to fetch
        page_size: Number of items per page (max: 250)
        lang: Language codes, comma-separated
        
    Returns:
        API response dictionary
        
    Raises:
        ValueError: If API key is missing or invalid parameters
        requests.RequestException: If API request fails
    """
    if not DATATOURISME_API_KEY:
        raise ValueError("DATATOURISME_API_KEY not found. Please set it in your .env file.")
    
    if page_size > 250:
        raise ValueError("page_size cannot exceed 250")
    
    params = {
        "page_size": min(page_size, 250),
        "page": page,
        "lang": lang,
        "fields": "uuid,label,type,uri,isLocatedAt,hasDescription,lastUpdate"
    }
    
    headers = {
        "X-API-Key": DATATOURISME_API_KEY
    }
    
    try:
        # Rate limiting
        time.sleep(0.2)
        
        logger.info(f"Fetching page {page} (page_size={page_size})...")
        response = requests.get(API_URL, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Validate response
        if "objects" not in data:
            raise ValueError("Response does not contain 'objects' field")
        
        if not isinstance(data.get("objects"), list):
            raise ValueError("Response 'objects' field is not a list")
        
        logger.info(f"Successfully fetched page {page}: {len(data.get('objects', []))} objects")
        return data
        
    except requests.exceptions.HTTPError as e:
        if response.status_code in [401, 403]:
            raise ValueError("Invalid API key or unauthorized")
        raise requests.RequestException(f"HTTP error fetching page {page}: {e}")
    except requests.exceptions.RequestException as e:
        raise requests.RequestException(f"Request failed for page {page}: {e}")


def fetch_all_pois(max_pages: Optional[int] = None, page_size: int = 250) -> List[Dict[str, Any]]:
    """
    Fetch all POIs from DataTourisme API using pagination.
    
    Args:
        max_pages: Maximum number of pages to fetch (None = fetch all)
        page_size: Number of items per page (default: 250, max: 250)
        
    Returns:
        List of all POI objects from all pages
    """
    all_objects = []
    current_page = 1
    total_pages = None
    
    logger.info(f"Starting fetch operation (max_pages={max_pages}, page_size={page_size})")
    
    while True:
        if max_pages and current_page > max_pages:
            logger.info(f"Reached max_pages limit ({max_pages})")
            break
        
        try:
            page_data = fetch_page(current_page, page_size=page_size)
            objects = page_data.get("objects", [])
            
            if not objects:
                logger.info(f"No objects in page {current_page}, stopping")
                break
            
            all_objects.extend(objects)
            
            # Extract total pages from first response
            if total_pages is None:
                total = page_data.get("total", 0)
                if total > 0:
                    total_pages = (total + page_size - 1) // page_size
                    logger.info(f"Total pages available: {total_pages}")
            
            # Check if we've reached the last page
            if total_pages and current_page >= total_pages:
                logger.info(f"Reached last page ({total_pages})")
                break
            
            current_page += 1
            
        except Exception as e:
            logger.error(f"Error fetching page {current_page}: {e}")
            raise
    
    logger.info(f"Fetch complete: {len(all_objects)} total objects fetched")
    return all_objects


def save_raw_json(data: List[Dict[str, Any]], output_path: Optional[Path] = None) -> Path:
    """
    Save raw JSON data to file with date-based naming.
    
    Args:
        data: List of POI objects to save
        output_path: Optional custom output path (default: auto-generate with date)
        
    Returns:
        Path to saved file
    """
    if output_path is None:
        date_str = datetime.now().strftime("%Y%m%d")
        output_path = RAW_DATA_DIR / f"pois_{date_str}.json"
    
    logger.info(f"Saving {len(data)} POIs to {output_path}")
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Successfully saved raw JSON to {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Error saving JSON to {output_path}: {e}")
        raise


def fetch_pois(max_pages: Optional[int] = None, page_size: int = 250) -> Path:
    """
    Main function to fetch POIs from DataTourisme API and save raw JSON.
    
    Args:
        max_pages: Maximum number of pages to fetch (None = fetch all)
        page_size: Number of items per page (default: 250)
        
    Returns:
        Path to saved raw JSON file
    """
    logger.info("=" * 60)
    logger.info("Starting POI fetch operation")
    logger.info("=" * 60)
    
    try:
        # Fetch all POIs
        all_pois = fetch_all_pois(max_pages=max_pages, page_size=page_size)
        
        if not all_pois:
            logger.warning("No POIs fetched from API")
            raise ValueError("No POIs fetched from API")
        
        # Save raw JSON
        output_path = save_raw_json(all_pois)
        
        logger.info("=" * 60)
        logger.info(f"Fetch operation complete: {len(all_pois)} records saved to {output_path}")
        logger.info("=" * 60)
        
        return output_path
        
    except Exception as e:
        logger.error(f"Fetch operation failed: {e}")
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch POIs from DataTourisme API")
    parser.add_argument("--max-pages", type=int, default=None,
                       help="Maximum number of pages to fetch (default: all)")
    parser.add_argument("--page-size", type=int, default=250,
                       help="Page size (default: 250, max: 250)")
    
    args = parser.parse_args()
    
    try:
        output_path = fetch_pois(max_pages=args.max_pages, page_size=args.page_size)
        print(f"\n[SUCCESS] Raw data saved to: {output_path}")
    except Exception as e:
        logger.error(f"Failed to fetch POIs: {e}")
        sys.exit(1)

