"""
Transform and normalize POI data.
Cleans fields, handles nulls, and trims strings.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import json


def normalize_string(value: Any) -> Optional[str]:
    """
    Normalize a string value: trim whitespace, convert None/empty to None.
    
    Args:
        value: Value to normalize
        
    Returns:
        Normalized string or None
    """
    if value is None:
        return None
    
    if isinstance(value, str):
        normalized = value.strip()
        return normalized if normalized else None
    
    # Convert other types to string
    return str(value).strip() if str(value).strip() else None


def normalize_float(value: Any) -> Optional[float]:
    """
    Normalize a float value.
    
    Args:
        value: Value to normalize
        
    Returns:
        Float value or None
    """
    if value is None:
        return None
    
    if isinstance(value, (int, float)):
        return float(value)
    
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
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
        
        # Try ISO format first
        try:
            # Handle ISO format with or without timezone
            if 'T' in value:
                # Remove timezone info if present
                if '+' in value or value.endswith('Z'):
                    value = value.split('+')[0].split('Z')[0]
                return datetime.fromisoformat(value)
            else:
                # Try date-only format
                return datetime.strptime(value, "%Y-%m-%d")
        except (ValueError, TypeError):
            # Try other common formats
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%d/%m/%Y",
                "%m/%d/%Y"
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(value, fmt)
                except (ValueError, TypeError):
                    continue
    
    return None


def validate_coordinates(latitude: Optional[float], longitude: Optional[float]) -> bool:
    """
    Validate that coordinates are within valid ranges.
    
    Args:
        latitude: Latitude value
        longitude: Longitude value
        
    Returns:
        True if coordinates are valid, False otherwise
    """
    if latitude is None or longitude is None:
        return False
    
    return (-90 <= latitude <= 90) and (-180 <= longitude <= 180)


def transform_poi(poi: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Transform and normalize a single POI.
    
    Args:
        poi: Raw POI dictionary
        
    Returns:
        Transformed POI dictionary or None if invalid
    """
    # Extract and normalize ID
    poi_id = normalize_string(poi.get("id"))
    if not poi_id:
        return None
    
    # Normalize string fields
    label = normalize_string(poi.get("label"))
    description = normalize_string(poi.get("description"))
    poi_type = normalize_string(poi.get("type"))
    uri = normalize_string(poi.get("uri"))
    
    # Normalize coordinates
    latitude = normalize_float(poi.get("latitude"))
    longitude = normalize_float(poi.get("longitude"))
    
    # Validate coordinates
    if not validate_coordinates(latitude, longitude):
        return None
    
    # Parse timestamp
    last_update = parse_timestamp(poi.get("last_update"))
    
    # Handle source_id (should be integer or None)
    source_id = poi.get("source_id")
    if source_id is not None:
        try:
            source_id = int(source_id)
        except (ValueError, TypeError):
            source_id = None
    
    # Handle raw_json
    raw_json = poi.get("raw_json")
    if raw_json is not None:
        if isinstance(raw_json, dict):
            try:
                raw_json = json.dumps(raw_json)
            except (TypeError, ValueError):
                raw_json = None
        elif isinstance(raw_json, str):
            # Validate it's valid JSON
            try:
                json.loads(raw_json)
            except (json.JSONDecodeError, ValueError):
                raw_json = None
        else:
            raw_json = None
    
    # Build transformed POI
    transformed = {
        "id": poi_id,
        "label": label,
        "description": description,
        "latitude": latitude,
        "longitude": longitude,
        "type": poi_type,
        "uri": uri,
        "last_update": last_update,
        "source_id": source_id,
        "raw_json": raw_json
    }
    
    return transformed


def transform_pois(raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Transform raw JSON data from FastAPI endpoints into clean POI dictionaries.
    Extracts only useful fields: id, label, description, type, lat, lon, updated_at.
    
    Supports both endpoint formats:
    - /pois: {"items": [...], "total": int, ...}
    - /pois/geojson: {"type": "FeatureCollection", "features": [...]}
    
    Args:
        raw_data: Raw JSON response dictionary from FastAPI endpoint
        
    Returns:
        List of clean POI dictionaries ready for database insertion
    """
    transformed = []
    skipped = 0
    
    # Determine response format and extract POI items
    pois_to_process = []
    
    # Check if it's a GeoJSON FeatureCollection
    if raw_data.get("type") == "FeatureCollection" and "features" in raw_data:
        features = raw_data.get("features", [])
        for feature in features:
            props = feature.get("properties", {})
            geometry = feature.get("geometry", {})
            coords = geometry.get("coordinates", [])
            
            # Extract from GeoJSON format
            poi = {
                "id": props.get("id"),
                "label": props.get("label"),
                "description": props.get("description"),
                "type": props.get("type"),
                "latitude": coords[1] if len(coords) >= 2 else None,
                "longitude": coords[0] if len(coords) >= 1 else None,
                "last_update": props.get("last_update")
            }
            pois_to_process.append(poi)
    
    # Check if it's a regular /pois response
    elif "items" in raw_data:
        items = raw_data.get("items", [])
        for item in items:
            # Extract from regular POI format
            poi = {
                "id": item.get("id"),
                "label": item.get("label"),
                "description": item.get("description"),
                "type": item.get("type"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "last_update": item.get("last_update")
            }
            pois_to_process.append(poi)
    
    # Transform each POI
    for poi in pois_to_process:
        # Extract and normalize ID (required)
        poi_id = normalize_string(poi.get("id"))
        if not poi_id:
            skipped += 1
            continue
        
        # Extract and normalize coordinates (required)
        latitude = normalize_float(poi.get("latitude"))
        longitude = normalize_float(poi.get("longitude"))
        
        # Validate coordinates
        if not validate_coordinates(latitude, longitude):
            skipped += 1
            continue
        
        # Extract and normalize other fields (optional)
        label = normalize_string(poi.get("label"))
        description = normalize_string(poi.get("description"))
        poi_type = normalize_string(poi.get("type"))
        updated_at = parse_timestamp(poi.get("last_update"))
        
        # Build clean dictionary with only useful fields
        clean_poi = {
            "id": poi_id,
            "label": label,
            "description": description,
            "type": poi_type,
            "lat": latitude,  # Using 'lat' as requested
            "lon": longitude,  # Using 'lon' as requested
            "updated_at": updated_at  # Using 'updated_at' as requested
        }
        
        transformed.append(clean_poi)
    
    if skipped > 0:
        print(f"[INFO] Skipped {skipped} invalid POIs during transformation")
    
    return transformed


def transform_pois_legacy(pois: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Transform and normalize a list of POIs (legacy function for backward compatibility).
    
    Args:
        pois: List of raw POI dictionaries
        
    Returns:
        List of transformed POI dictionaries (invalid POIs are filtered out)
    """
    transformed = []
    skipped = 0
    
    for poi in pois:
        transformed_poi = transform_poi(poi)
        if transformed_poi:
            transformed.append(transformed_poi)
        else:
            skipped += 1
    
    if skipped > 0:
        print(f"[INFO] Skipped {skipped} invalid POIs during transformation")
    
    return transformed


if __name__ == "__main__":
    import sys
    
    # Test with GeoJSON format
    print("Testing GeoJSON format...")
    geojson_sample = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [2.3522, 48.8566]
                },
                "properties": {
                    "id": "test-123",
                    "label": "  Test POI  ",
                    "description": "  Test description  ",
                    "type": "Museum",
                    "last_update": "2024-01-15T10:30:00Z"
                }
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [None, None]
                },
                "properties": {
                    "id": "invalid"
                }
            }
        ]
    }
    
    transformed = transform_pois(geojson_sample)
    print(f"Transformed {len(transformed)} out of {len(geojson_sample['features'])} POIs")
    if transformed:
        print(f"Sample transformed POI: {transformed[0]}")
    
    print("\nTesting /pois format...")
    pois_sample = {
        "items": [
            {
                "id": "test-456",
                "label": "Another POI",
                "description": "Another description",
                "type": "Restaurant",
                "latitude": 48.8606,
                "longitude": 2.3376,
                "last_update": "2024-01-16T12:00:00Z"
            }
        ],
        "total": 1,
        "limit": 50,
        "offset": 0
    }
    
    transformed2 = transform_pois(pois_sample)
    print(f"Transformed {len(transformed2)} out of {len(pois_sample['items'])} POIs")
    if transformed2:
        print(f"Sample transformed POI: {transformed2[0]}")

