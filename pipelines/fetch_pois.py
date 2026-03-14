"""
Fetch POIs from FastAPI or external API.
"""
import os
import requests
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
DATATOURISME_API_KEY = os.getenv("DATATOURISME_API_KEY", "")
DATATOURISME_BASE_URL = os.getenv("BASE_URL", "https://api.datatourisme.fr")


def fetch_from_fastapi(limit: int = 5000, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Fetch POIs from FastAPI GeoJSON endpoint.
    
    Args:
        limit: Maximum number of POIs to fetch (default: 5000, max: 5000)
        offset: Number of POIs to skip (default: 0)
        
    Returns:
        List of POI dictionaries with properties
        
    Raises:
        requests.RequestException: If API request fails
    """
    try:
        url = f"{API_BASE_URL}/pois/geojson"
        params = {
            "limit": min(limit, 5000),
            "offset": offset
        }
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        geojson = response.json()
        features = geojson.get("features", [])
        
        # Convert GeoJSON features to POI dictionaries
        pois = []
        for feature in features:
            props = feature.get("properties", {})
            geometry = feature.get("geometry", {})
            coords = geometry.get("coordinates", [])
            
            poi = {
                "id": props.get("id"),
                "label": props.get("label"),
                "description": props.get("description"),
                "latitude": coords[1] if len(coords) >= 2 else None,
                "longitude": coords[0] if len(coords) >= 1 else None,
                "type": props.get("type"),
                "uri": props.get("uri"),
                "last_update": props.get("last_update"),
                "source_id": props.get("source_id"),
                "created_at": props.get("created_at")
            }
            pois.append(poi)
        
        return pois
        
    except requests.RequestException as e:
        raise requests.RequestException(f"Failed to fetch from FastAPI: {e}")


def fetch_from_datatourisme(page_size: int = 250, page: int = 1, max_pages: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Fetch POIs directly from DataTourisme external API.
    
    Args:
        page_size: Number of items per page (default: 250, max: 250)
        page: Starting page number (default: 1)
        max_pages: Maximum number of pages to fetch (None = fetch all)
        
    Returns:
        List of POI dictionaries
        
    Raises:
        ValueError: If API key is missing
        requests.RequestException: If API request fails
    """
    if not DATATOURISME_API_KEY:
        raise ValueError("DATATOURISME_API_KEY not found. Please set it in your .env file.")
    
    url = f"{DATATOURISME_BASE_URL}/v1/catalog"
    headers = {
        "X-API-Key": DATATOURISME_API_KEY
    }
    
    all_pois = []
    current_page = page
    total_pages = None
    
    while True:
        if max_pages and current_page > page + max_pages - 1:
            break
            
        params = {
            "page_size": min(page_size, 250),
            "page": current_page,
            "lang": "fr,en",
            "fields": "uuid,label,type,uri,isLocatedAt,hasDescription,lastUpdate"
        }
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            objects = data.get("objects", [])
            
            if not objects:
                break
            
            # Extract total pages from response if available
            if total_pages is None:
                total = data.get("total", 0)
                if total > 0:
                    total_pages = (total + page_size - 1) // page_size
            
            # Transform DataTourisme objects to POI format
            for obj in objects:
                poi = transform_datatourisme_object(obj)
                if poi:  # Only add if transformation succeeded
                    all_pois.append(poi)
            
            # Check if we've reached the last page
            if total_pages and current_page >= total_pages:
                break
                
            current_page += 1
            
        except requests.RequestException as e:
            raise requests.RequestException(f"Failed to fetch from DataTourisme API: {e}")
    
    return all_pois


def transform_datatourisme_object(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Transform a DataTourisme API object to POI format.
    
    Args:
        obj: DataTourisme API object dictionary
        
    Returns:
        POI dictionary or None if transformation fails
    """
    try:
        # Extract ID
        poi_id = obj.get("uuid") or obj.get("id")
        if not poi_id:
            return None
        
        # Extract label
        label_obj = obj.get("label", {})
        if isinstance(label_obj, dict):
            label = label_obj.get("fr") or label_obj.get("en") or label_obj.get("@fr") or label_obj.get("@en")
            if not label:
                # Try to get any string value
                for v in label_obj.values():
                    if isinstance(v, str) and v:
                        label = v
                        break
        else:
            label = str(label_obj) if label_obj else None
        
        # Extract description
        desc_obj = obj.get("hasDescription", {})
        if isinstance(desc_obj, dict):
            description = desc_obj.get("fr") or desc_obj.get("en") or desc_obj.get("@fr") or desc_obj.get("@en")
            if not description:
                for v in desc_obj.values():
                    if isinstance(v, str) and v:
                        description = v
                        break
        else:
            description = str(desc_obj) if desc_obj else None
        
        # Extract coordinates
        latitude = None
        longitude = None
        location = obj.get("isLocatedAt")
        if location:
            if isinstance(location, list) and len(location) > 0:
                location = location[0]
            
            if isinstance(location, dict):
                geo = location.get("schema:geo") or location.get("geo")
                if geo:
                    latitude = geo.get("schema:latitude") or geo.get("latitude")
                    longitude = geo.get("schema:longitude") or geo.get("longitude")
                    
                    # Handle coordinate array format [lon, lat]
                    if latitude is None and longitude is None:
                        coords = geo.get("schema:coordinates") or geo.get("coordinates")
                        if isinstance(coords, list) and len(coords) >= 2:
                            longitude = coords[0]
                            latitude = coords[1]
        
        # Skip if no coordinates
        if latitude is None or longitude is None:
            return None
        
        # Extract other fields
        poi_type = obj.get("type")
        uri = obj.get("uri")
        last_update = obj.get("lastUpdate") or obj.get("last_update")
        
        return {
            "id": str(poi_id),
            "label": label,
            "description": description,
            "latitude": float(latitude) if latitude is not None else None,
            "longitude": float(longitude) if longitude is not None else None,
            "type": str(poi_type) if poi_type else None,
            "uri": str(uri) if uri else None,
            "last_update": last_update,
            "source_id": None,  # Will be set during load
            "created_at": None,
            "raw_json": obj  # Store original object
        }
        
    except Exception as e:
        # Log error but continue processing
        print(f"[WARNING] Failed to transform object: {e}")
        return None


def fetch_pois(limit: int = 1000, offset: int = 0, endpoint: str = "geojson") -> Dict[str, Any]:
    """
    Fetch POIs from FastAPI endpoint and return raw JSON data.
    
    Args:
        limit: Maximum number of POIs to fetch (default: 1000, max: 5000)
        offset: Number of POIs to skip (default: 0)
        endpoint: Endpoint to use - "pois" or "geojson" (default: "geojson")
        
    Returns:
        Raw JSON response dictionary
        
    Raises:
        requests.RequestException: If API request fails
    """
    try:
        # Choose endpoint
        if endpoint == "geojson":
            url = f"{API_BASE_URL}/pois/geojson"
        elif endpoint == "pois":
            url = f"{API_BASE_URL}/pois"
        else:
            raise ValueError(f"Invalid endpoint: {endpoint}. Must be 'pois' or 'geojson'")
        
        params = {
            "limit": min(limit, 5000),
            "offset": offset
        }
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        raw_data = response.json()
        
        # Log number of records fetched
        if endpoint == "geojson":
            record_count = len(raw_data.get("features", []))
            print(f"[INFO] Fetched {record_count} POI records from /pois/geojson")
        else:
            record_count = len(raw_data.get("items", []))
            print(f"[INFO] Fetched {record_count} POI records from /pois")
        
        return raw_data
        
    except requests.RequestException as e:
        raise requests.RequestException(f"Failed to fetch from FastAPI: {e}")


def fetch_pois_from_source(source: str = "fastapi", **kwargs) -> List[Dict[str, Any]]:
    """
    Main function to fetch POIs from specified source (legacy function for backward compatibility).
    
    Args:
        source: Source to fetch from - "fastapi" or "datatourisme" (default: "fastapi")
        **kwargs: Additional arguments passed to fetch function
        
    Returns:
        List of POI dictionaries
        
    Raises:
        ValueError: If source is invalid
    """
    if source == "fastapi":
        return fetch_from_fastapi(**kwargs)
    elif source == "datatourisme":
        return fetch_from_datatourisme(**kwargs)
    else:
        raise ValueError(f"Invalid source: {source}. Must be 'fastapi' or 'datatourisme'")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch POIs from API")
    parser.add_argument("--source", choices=["fastapi", "datatourisme"], default="fastapi",
                       help="Source to fetch from (default: fastapi)")
    parser.add_argument("--limit", type=int, default=5000,
                       help="Maximum number of POIs to fetch (for fastapi)")
    parser.add_argument("--offset", type=int, default=0,
                       help="Offset for pagination (for fastapi)")
    parser.add_argument("--page-size", type=int, default=250,
                       help="Page size for DataTourisme API")
    parser.add_argument("--max-pages", type=int, default=None,
                       help="Maximum number of pages to fetch (for datatourisme)")
    
    args = parser.parse_args()
    
    try:
        if args.source == "fastapi":
            # Use new simple fetch_pois function
            raw_data = fetch_pois(limit=args.limit, offset=args.offset, endpoint="geojson")
            print(f"[OK] Fetched data from FastAPI")
            if raw_data.get("features"):
                print(f"[INFO] Sample POI ID: {raw_data['features'][0].get('properties', {}).get('id')}")
        else:
            # Use legacy function for datatourisme
            pois = fetch_pois_from_source(source="datatourisme", page_size=args.page_size, max_pages=args.max_pages)
            print(f"[OK] Fetched {len(pois)} POIs from {args.source}")
            if pois:
                print(f"[INFO] Sample POI ID: {pois[0].get('id')}")
    except Exception as e:
        print(f"[ERROR] {e}")
        exit(1)

