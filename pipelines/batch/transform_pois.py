"""
Transform raw POI data from DataTourisme API.
Extracts useful fields and handles missing coordinates safely.
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def extract_coordinates(poi: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """
    Extract latitude and longitude from a POI object.
    Handles various DataTourisme JSON structures.
    
    Args:
        poi: POI dictionary from DataTourisme API
        
    Returns:
        Tuple of (latitude, longitude) or (None, None) if not found
    """
    location = poi.get("isLocatedAt")
    if not location:
        return None, None
    
    # Handle list format
    if isinstance(location, list) and len(location) > 0:
        location = location[0]
    
    if not isinstance(location, dict):
        return None, None
    
    # Try different geo structure formats
    geo = location.get("schema:geo") or location.get("geo")
    if not geo:
        return None, None
    
    # Try schema:latitude/schema:longitude
    latitude = geo.get("schema:latitude") or geo.get("latitude")
    longitude = geo.get("schema:longitude") or geo.get("longitude")
    
    # Try coordinate array format [lon, lat]
    if latitude is None or longitude is None:
        coords = geo.get("schema:coordinates") or geo.get("coordinates")
        if isinstance(coords, list) and len(coords) >= 2:
            longitude = coords[0]
            latitude = coords[1]
    
    # Convert to float if found
    try:
        if latitude is not None:
            latitude = float(latitude)
        if longitude is not None:
            longitude = float(longitude)
    except (ValueError, TypeError):
        return None, None
    
    return latitude, longitude


def extract_label(poi: Dict[str, Any]) -> Optional[str]:
    """
    Extract label from POI object.
    
    Args:
        poi: POI dictionary
        
    Returns:
        Label string or None
    """
    label_obj = poi.get("label") or poi.get("rdfs:label")
    
    if isinstance(label_obj, dict):
        # Try French first, then English
        label = label_obj.get("fr") or label_obj.get("@fr") or label_obj.get("en") or label_obj.get("@en")
        if label:
            return str(label).strip()
        # Try any string value
        for value in label_obj.values():
            if isinstance(value, str) and value.strip():
                return value.strip()
    elif isinstance(label_obj, str):
        return label_obj.strip()
    
    return None


def parse_timestamp(value: Any) -> Optional[datetime]:
    """
    Parse timestamp from various formats.
    
    Args:
        value: Timestamp value (string, datetime, or None)
        
    Returns:
        datetime object or None
    """
    if value is None:
        return None
    
    if isinstance(value, datetime):
        return value
    
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        
        # Try ISO format
        try:
            if 'T' in value:
                # Remove timezone if present
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


def transform_poi(poi: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Transform a single POI object, extracting only useful fields.
    
    Args:
        poi: Raw POI dictionary from DataTourisme API
        
    Returns:
        Transformed POI dictionary with fields:
        id, label, latitude, longitude, uri, last_update, raw_json
        Returns None if coordinates are missing
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
    
    # Extract other fields
    label = extract_label(poi)
    uri = poi.get("uri")
    if uri:
        uri = str(uri).strip() or None
    
    last_update_str = poi.get("lastUpdate") or poi.get("last_update")
    last_update = parse_timestamp(last_update_str)
    
    # Store raw JSON
    raw_json = json.dumps(poi) if poi else None
    
    return {
        "id": str(poi_id),
        "label": label,
        "latitude": latitude,
        "longitude": longitude,
        "uri": uri,
        "last_update": last_update,
        "raw_json": raw_json
    }


def transform_pois(raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Transform a list of raw POI objects.
    
    Args:
        raw_data: List of raw POI dictionaries from DataTourisme API
        
    Returns:
        List of transformed POI dictionaries
    """
    logger.info(f"Transforming {len(raw_data)} raw POI objects...")
    
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
    
    logger.info(f"Transformation complete: {len(transformed)} transformed, {skipped} skipped")
    
    if skipped > 0:
        logger.info(f"Skipped {skipped} POIs (missing coordinates or invalid data)")
    
    return transformed


def load_raw_json(file_path: Path) -> List[Dict[str, Any]]:
    """
    Load raw JSON data from file.
    
    Args:
        file_path: Path to JSON file
        
    Returns:
        List of POI dictionaries
    """
    logger.info(f"Loading raw JSON from {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            raise ValueError(f"Expected list in JSON file, got {type(data)}")
        
        logger.info(f"Loaded {len(data)} POI objects from {file_path}")
        return data
        
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in file {file_path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading JSON from {file_path}: {e}")
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Transform raw POI data")
    parser.add_argument("input_file", type=Path,
                       help="Path to raw JSON file")
    
    args = parser.parse_args()
    
    try:
        raw_data = load_raw_json(args.input_file)
        transformed = transform_pois(raw_data)
        
        print(f"\n[SUCCESS] Transformed {len(transformed)} POIs from {len(raw_data)} raw objects")
        if transformed:
            print(f"Sample POI ID: {transformed[0].get('id')}")
    except Exception as e:
        logger.error(f"Transformation failed: {e}")
        sys.exit(1)

