"""
Data extraction module for fetching DataTourisme data.
"""
import json
import argparse
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests
import pandas as pd
from src.config import RAW_DATA_DIR, PROCESSED_DATA_DIR, DATATOURISME_API_KEY, BASE_URL

API_URL = f"{BASE_URL}/v1/catalog"


def fetch_catalog(
    page_size: int = 50,
    page: int = 1,
    lang: str = "fr,en",
    fields: Optional[str] = None,
    filters: Optional[str] = None
) -> dict:
    """
    Fetch catalog data from DataTourisme API.
    
    Args:
        page_size: Number of items per page (default: 50, max: 250)
        page: Page number (default: 1)
        lang: Language codes, comma-separated (default: "fr,en")
        fields: Comma-separated list of fields to request (optional)
        filters: Filter parameters (optional)
    
    Returns:
        Dictionary containing the API response
    
    Raises:
        ValueError: If API key is missing, page_size exceeds max, or response is invalid
        requests.HTTPError: If the API request fails
    """
    # Validate page_size
    if page_size > 250:
        raise ValueError("page_size cannot exceed 250")
    if page_size < 1:
        raise ValueError("page_size must be at least 1")
    
    # Check API key - this should be checked before making request
    if not DATATOURISME_API_KEY:
        raise ValueError("DATATOURISME_API_KEY not found. Please set it in your .env file.")
    
    # Set default fields if not provided
    if fields is None:
        fields = "uuid,label,type,uri,isLocatedAt,hasDescription,lastUpdate"
    
    # Build query parameters
    params = {
        "page_size": page_size,
        "page": page,
        "lang": lang,
        "fields": fields
    }
    
    # Add filters if provided
    if filters:
        params["filters"] = filters
    
    # Set headers with API key
    headers = {
        "X-API-Key": DATATOURISME_API_KEY
    }
    
    try:
        # Add rate limiting safety
        time.sleep(0.2)
        
        response = requests.get(API_URL, params=params, headers=headers, timeout=30)
        
        # Handle specific HTTP errors with clear messages
        if response.status_code == 401 or response.status_code == 403:
            raise requests.HTTPError("Invalid API key or unauthorized")
        elif response.status_code != 200:
            # For non-200 status codes, include status and response text
            error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
            raise requests.HTTPError(error_msg)
        
        try:
            data = response.json()
            
            # Validate response structure - ensure "objects" is a list
            if "objects" not in data:
                raise ValueError("Response does not contain 'objects' field. Invalid API response structure.")
            
            if not isinstance(data.get("objects"), list):
                raise ValueError("Response 'objects' field is not a list. Invalid API response structure.")
            
            return data
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON response: {e}")
            
    except requests.exceptions.HTTPError:
        # Re-raise HTTP errors (we've already formatted them)
        raise
    except requests.exceptions.RequestException as e:
        raise requests.RequestException(f"Request failed: {e}")


def extract_field(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """
    Extract a field from nested dictionary using multiple possible keys.
    
    Args:
        data: Dictionary to search in
        keys: Possible keys to look for
        default: Default value if key not found
    
    Returns:
        Value found or default
    """
    for key in keys:
        if key in data:
            return data[key]
    return default


def get_best_label(poi: Dict[str, Any]) -> str:
    """
    Extract the best available label/name from a POI.
    Tries object["rdfs:label"]["fr"] then ["en"], else any available string.
    
    Args:
        poi: Point of Interest dictionary
    
    Returns:
        Best available label or empty string
    """
    # Priority 1: Try rdfs:label with language preference
    rdfs_label = poi.get("rdfs:label")
    if rdfs_label:
        if isinstance(rdfs_label, dict):
            # Try French first, then English, then any other language
            label = rdfs_label.get("@fr") or rdfs_label.get("fr") or rdfs_label.get("@en") or rdfs_label.get("en")
            if label:
                return str(label)
            # If no language-specific key, try to get any string value
            for key, value in rdfs_label.items():
                if isinstance(value, str) and value:
                    return value
        elif isinstance(rdfs_label, str):
            return rdfs_label
        elif isinstance(rdfs_label, list) and len(rdfs_label) > 0:
            # If it's a list, try the first item
            first_item = rdfs_label[0]
            if isinstance(first_item, dict):
                return first_item.get("@fr") or first_item.get("fr") or first_item.get("@en") or first_item.get("en") or ""
            return str(first_item) if first_item else ""
    
    # Priority 2: Try label field (may also be multilingual)
    label = poi.get("label")
    if label:
        if isinstance(label, dict):
            # Try French first, then English, then any other language
            label_str = label.get("@fr") or label.get("fr") or label.get("@en") or label.get("en")
            if label_str:
                return str(label_str)
            # If no language-specific key, try to get any string value
            for key, value in label.items():
                if isinstance(value, str) and value:
                    return value
        elif isinstance(label, str):
            return label
        elif isinstance(label, list) and len(label) > 0:
            first_item = label[0]
            if isinstance(first_item, dict):
                return first_item.get("@fr") or first_item.get("fr") or first_item.get("@en") or first_item.get("en") or ""
            return str(first_item) if first_item else ""
    
    # Fallback: Try other common fields
    for field_name in ["name", "nom", "title", "titre"]:
        value = poi.get(field_name)
        if value:
            if isinstance(value, str):
                return value
            elif isinstance(value, dict):
                return value.get("@fr") or value.get("fr") or value.get("@en") or value.get("en") or ""
    
    return ""


def get_coordinates(poi: Dict[str, Any]) -> tuple:
    """
    Extract latitude and longitude from a POI.
    Checks multiple possible DataTourisme JSON structures in priority order.
    
    Priority order:
    A) object["isLocatedAt"][0]["schema:geo"]["schema:latitude"] and ["schema:longitude"]
    B) object["isLocatedAt"][0]["schema:geo"]["latitude"] and ["longitude"]
    C) object["isLocatedAt"][0]["geo"]["latitude"] and ["longitude"]
    D) object["isLocatedAt"][0]["schema:geo"]["schema:coordinates"] (handle [lon, lat])
    E) object["isLocatedAt"][0]["schema:geo"]["coordinates"] (handle [lon, lat])
    F) Any nested "geometry" / "coordinates" fields (handle GeoJSON where coordinates=[lon, lat])
    
    Args:
        poi: Point of Interest dictionary
    
    Returns:
        Tuple of (latitude, longitude) or (None, None)
    """
    # Get isLocatedAt array
    is_located_at = extract_field(poi, "isLocatedAt", default=None)
    if not is_located_at:
        return (None, None)
    
    # Ensure it's a list/array
    if not isinstance(is_located_at, list) or len(is_located_at) == 0:
        return (None, None)
    
    location = is_located_at[0]
    if not isinstance(location, dict):
        return (None, None)
    
    # Priority A: schema:geo with schema:latitude and schema:longitude
    schema_geo = location.get("schema:geo")
    if schema_geo and isinstance(schema_geo, dict):
        lat = schema_geo.get("schema:latitude")
        lon = schema_geo.get("schema:longitude")
        if lat is not None and lon is not None:
            try:
                return (float(lat), float(lon))
            except (ValueError, TypeError):
                pass
    
    # Priority B: schema:geo with latitude and longitude
    if schema_geo and isinstance(schema_geo, dict):
        lat = schema_geo.get("latitude")
        lon = schema_geo.get("longitude")
        if lat is not None and lon is not None:
            try:
                return (float(lat), float(lon))
            except (ValueError, TypeError):
                pass
    
    # Priority C: geo with latitude and longitude
    geo = location.get("geo")
    if geo and isinstance(geo, dict):
        lat = geo.get("latitude")
        lon = geo.get("longitude")
        if lat is not None and lon is not None:
            try:
                return (float(lat), float(lon))
            except (ValueError, TypeError):
                pass
    
    # Priority D: schema:geo with schema:coordinates (GeoJSON format: [lon, lat])
    if schema_geo and isinstance(schema_geo, dict):
        coords = schema_geo.get("schema:coordinates")
        if coords and isinstance(coords, list) and len(coords) >= 2:
            try:
                # GeoJSON format: [longitude, latitude]
                return (float(coords[1]), float(coords[0]))
            except (ValueError, TypeError, IndexError):
                pass
    
    # Priority E: schema:geo with coordinates (GeoJSON format: [lon, lat])
    if schema_geo and isinstance(schema_geo, dict):
        coords = schema_geo.get("coordinates")
        if coords and isinstance(coords, list) and len(coords) >= 2:
            try:
                # GeoJSON format: [longitude, latitude]
                return (float(coords[1]), float(coords[0]))
            except (ValueError, TypeError, IndexError):
                pass
    
    # Priority F: Check for geometry/coordinates in any nested structure
    # Look for GeoJSON-like structures
    def find_geometry_coords(obj, depth=0):
        """Recursively search for geometry/coordinates structures."""
        if depth > 5:  # Limit recursion depth
            return None
        if not isinstance(obj, dict):
            return None
        
        # Check for geometry.coordinates (GeoJSON)
        if "geometry" in obj and isinstance(obj["geometry"], dict):
            coords = obj["geometry"].get("coordinates")
            if coords and isinstance(coords, list) and len(coords) >= 2:
                try:
                    # Handle both [lon, lat] and [[[lon, lat]]] (Polygon) formats
                    if isinstance(coords[0], list):
                        # Nested array, get first coordinate pair
                        if isinstance(coords[0][0], list):
                            coords = coords[0][0]
                        else:
                            coords = coords[0]
                    # GeoJSON format: [longitude, latitude]
                    return (float(coords[1]), float(coords[0]))
                except (ValueError, TypeError, IndexError):
                    pass
        
        # Check for direct coordinates field
        if "coordinates" in obj:
            coords = obj["coordinates"]
            if isinstance(coords, list) and len(coords) >= 2:
                try:
                    # Handle nested arrays
                    if isinstance(coords[0], list):
                        if isinstance(coords[0][0], list):
                            coords = coords[0][0]
                        else:
                            coords = coords[0]
                    # GeoJSON format: [longitude, latitude]
                    return (float(coords[1]), float(coords[0]))
                except (ValueError, TypeError, IndexError):
                    pass
        
        # Recursively search nested dictionaries
        for value in obj.values():
            if isinstance(value, dict):
                result = find_geometry_coords(value, depth + 1)
                if result:
                    return result
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        result = find_geometry_coords(item, depth + 1)
                        if result:
                            return result
        
        return None
    
    result = find_geometry_coords(location)
    if result:
        return result
    
    return (None, None)


def convert_to_csv(data: dict, output_path: Path) -> Path:
    """
    Convert API response objects to flat CSV format.
    
    Args:
        data: API response dictionary containing "objects" array
        output_path: Path to save CSV file
    
    Returns:
        Path to saved CSV file
    """
    rows = []
    
    # Extract objects from response
    objects = data.get("objects", [])
    
    if not isinstance(objects, list):
        raise ValueError("'objects' field is not a list in API response")
    
    for obj in objects:
        # Extract uuid
        uuid = extract_field(obj, "uuid", "id", "@id", default="")
        uuid = str(uuid) if uuid else ""
        
        # Extract uri
        uri = extract_field(obj, "uri", "url", "@id", default="")
        if isinstance(uri, dict):
            uri = uri.get("@id", uri.get("value", ""))
        uri = str(uri) if uri else ""
        
        # Extract label using improved function
        label = get_best_label(obj)
        
        # Extract type
        obj_type = extract_field(obj, "type", "@type", "rdf:type", default="")
        if isinstance(obj_type, list) and len(obj_type) > 0:
            obj_type = obj_type[0]
        if isinstance(obj_type, dict):
            obj_type = obj_type.get("@id", obj_type.get("value", ""))
        obj_type = str(obj_type) if obj_type else ""
        
        # Extract coordinates
        latitude, longitude = get_coordinates(obj)
        
        # Extract description - try hasDescription[0].shortDescription with @fr/@en
        description = ""
        has_description = obj.get("hasDescription")
        if has_description and isinstance(has_description, list) and len(has_description) > 0:
            desc_obj = has_description[0]
            if isinstance(desc_obj, dict):
                short_desc = desc_obj.get("shortDescription")
                if short_desc:
                    if isinstance(short_desc, dict):
                        # Try French first, then English, then any other language
                        description = short_desc.get("@fr") or short_desc.get("fr") or short_desc.get("@en") or short_desc.get("en")
                        if not description:
                            # If no language-specific key, try to get any string value
                            for key, value in short_desc.items():
                                if isinstance(value, str) and value:
                                    description = value
                                    break
                    elif isinstance(short_desc, str):
                        description = short_desc
        
        # Fallback: Try other description fields
        if not description:
            description = extract_field(obj, "description", "rdfs:comment", default="")
            if isinstance(description, dict):
                description = description.get("value", description.get("@value", description.get("text", "")))
            description = str(description) if description else ""
        
        # Extract lastUpdate
        last_update = extract_field(obj, "lastUpdate", "last_update", "updated", default="")
        last_update = str(last_update) if last_update else ""
        
        rows.append({
            "uuid": uuid,
            "uri": uri,
            "label": label,
            "type": obj_type,
            "lat": latitude,
            "lon": longitude,
            "description": description,
            "lastUpdate": last_update
        })
    
    # Calculate coordinate statistics
    rows_with_coords = sum(1 for row in rows if row["lat"] is not None and row["lon"] is not None)
    rows_missing_coords = len(rows) - rows_with_coords
    
    # Print statistics
    print(f"[INFO] Coordinate extraction statistics:")
    print(f"  Total rows: {len(rows)}")
    print(f"  Rows with coordinates: {rows_with_coords}")
    print(f"  Rows missing coordinates: {rows_missing_coords}")
    
    # Create DataFrame and save to CSV
    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False, encoding="utf-8")
    
    return output_path


def main():
    """Main function for running the extraction as a script."""
    parser = argparse.ArgumentParser(
        description="Fetch catalog data from DataTourisme API"
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=50,
        help="Number of items per page (default: 50, max: 250)"
    )
    parser.add_argument(
        "--page",
        type=int,
        default=1,
        help="Page number (default: 1)"
    )
    parser.add_argument(
        "--lang",
        type=str,
        default="fr,en",
        help="Language codes, comma-separated (default: fr,en)"
    )
    parser.add_argument(
        "--fields",
        type=str,
        default=None,
        help="Comma-separated list of fields to request (optional)"
    )
    parser.add_argument(
        "--filters",
        type=str,
        default=None,
        help="Filter parameters (optional)"
    )
    
    args = parser.parse_args()
    
    # Check API key first and exit with code 2 if missing
    if not DATATOURISME_API_KEY:
        print("[ERROR] DATATOURISME_API_KEY not found. Please set it in your .env file.")
        print("        Copy .env.example to .env and add your API key.")
        sys.exit(2)
    
    # Fetch data
    print(f"Fetching catalog data from DataTourisme API (page {args.page}, size {args.page_size})...")
    try:
        data = fetch_catalog(
            page_size=args.page_size,
            page=args.page,
            lang=args.lang,
            fields=args.fields,
            filters=args.filters
        )
        print("[OK] Successfully fetched data from API")
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Error fetching data: {e}")
        sys.exit(1)
    
    # Save raw JSON
    raw_output_path = RAW_DATA_DIR / f"datatourisme_catalog_page{args.page}.json"
    try:
        with open(raw_output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[OK] Saved raw data to {raw_output_path}")
    except Exception as e:
        print(f"[ERROR] Error saving raw data: {e}")
        sys.exit(1)
    
    # Convert to CSV
    csv_output_path = PROCESSED_DATA_DIR / "datatourisme_pois.csv"
    try:
        convert_to_csv(data, csv_output_path)
        print(f"[OK] Converted and saved CSV to {csv_output_path}")
    except Exception as e:
        print(f"[ERROR] Error converting to CSV: {e}")
        sys.exit(1)
    
    print("[OK] Data extraction completed successfully!")
    sys.exit(0)


if __name__ == "__main__":
    main()

