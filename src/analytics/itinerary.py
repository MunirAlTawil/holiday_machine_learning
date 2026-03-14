"""
Itinerary Generation Algorithm
==============================

Simple greedy distance-based algorithm for generating day-by-day itineraries.
Maximizes type diversity while minimizing travel distance.
"""
import math
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth (in kilometers).
    
    Uses the Haversine formula.
    """
    # Earth radius in kilometers
    R = 6371.0
    
    # Convert to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    distance = R * c
    return distance


def find_nearby_pois(
    db: Session,
    center_lat: float,
    center_lon: float,
    radius_km: float = 50.0,
    types: Optional[List[str]] = None,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """
    Find POIs within radius_km of center coordinates.
    
    Uses PostgreSQL's point-to-point distance calculation.
    """
    # Build query with radius filter
    # Using approximate distance calculation (good enough for filtering)
    query = text("""
        SELECT 
            id, label, description, latitude, longitude, 
            uri, type, city, department_code,
            (
                6371 * acos(
                    cos(radians(:center_lat)) * 
                    cos(radians(latitude)) * 
                    cos(radians(longitude) - radians(:center_lon)) + 
                    sin(radians(:center_lat)) * 
                    sin(radians(latitude))
                )
            ) AS distance_km
        FROM poi
        WHERE 
            latitude IS NOT NULL 
            AND longitude IS NOT NULL
            AND (
                6371 * acos(
                    cos(radians(:center_lat)) * 
                    cos(radians(latitude)) * 
                    cos(radians(longitude) - radians(:center_lon)) + 
                    sin(radians(:center_lat)) * 
                    sin(radians(latitude))
                )
            ) <= :radius_km
    """)
    
    params = {
        "center_lat": center_lat,
        "center_lon": center_lon,
        "radius_km": radius_km
    }
    
    # Add type filter if provided
    if types and len(types) > 0:
        # Escape single quotes in type names
        type_list = "', '".join([t.replace("'", "''") for t in types])
        query = text(str(query).replace(
            "WHERE",
            f"WHERE type IN ('{type_list}') AND"
        ))
    
    query = text(str(query) + " ORDER BY distance_km ASC LIMIT :limit")
    params["limit"] = limit
    
    result = db.execute(query, params)
    pois = []
    for row in result:
        pois.append({
            "id": row[0],
            "label": row[1],
            "description": row[2],
            "latitude": float(row[3]),
            "longitude": float(row[4]),
            "uri": row[5],
            "type": row[6],
            "city": row[7],
            "department_code": row[8],
            "distance_km": float(row[9]) if row[9] is not None else 0.0
        })
    
    return pois


def generate_itinerary(
    db: Session,
    start_lat: float,
    start_lon: float,
    days: int,
    radius_km: float = 50.0,
    types: Optional[List[str]] = None,
    limit_per_day: int = 5
) -> Dict[str, Any]:
    """
    Generate a day-by-day itinerary using greedy distance-based algorithm.
    
    Algorithm:
    1. Find all POIs within radius_km
    2. For each day:
       a. Start from current location (or previous day's last POI)
       b. Select POIs greedily: minimize distance while maximizing type diversity
       c. Limit to limit_per_day POIs per day
    
    Args:
        db: Database session
        start_lat: Starting latitude
        start_lon: Starting longitude
        days: Number of days
        radius_km: Search radius in kilometers
        types: Optional list of POI types to filter
        limit_per_day: Maximum POIs per day
    
    Returns:
        Dictionary with day-by-day itinerary
    """
    # Find all nearby POIs
    all_pois = find_nearby_pois(db, start_lat, start_lon, radius_km, types, limit=1000)
    
    if not all_pois:
        return {
            "start_location": {"latitude": start_lat, "longitude": start_lon},
            "days": days,
            "total_pois_found": 0,
            "itinerary": []
        }
    
    # Track used POIs and types
    used_poi_ids = set()
    itinerary = []
    current_lat = start_lat
    current_lon = start_lon
    
    # Generate itinerary for each day
    for day in range(1, days + 1):
        day_pois = []
        day_types = set()
        
        # Try to select limit_per_day POIs for this day
        for _ in range(limit_per_day):
            best_poi = None
            best_score = float('inf')
            
            for poi in all_pois:
                # Skip if already used
                if poi["id"] in used_poi_ids:
                    continue
                
                # Calculate distance from current location
                distance = haversine_distance(
                    current_lat, current_lon,
                    poi["latitude"], poi["longitude"]
                )
                
                # Score: distance (lower is better) - bonus for new type
                type_bonus = 0
                if poi.get("type") and poi["type"] not in day_types:
                    type_bonus = -5  # Prefer new types (negative = better score)
                
                score = distance + type_bonus
                
                if score < best_score:
                    best_score = score
                    best_poi = poi
            
            # If no POI found, break
            if not best_poi:
                break
            
            # Add to day's itinerary
            day_pois.append({
                "id": best_poi["id"],
                "label": best_poi.get("label"),
                "description": best_poi.get("description"),
                "latitude": best_poi["latitude"],
                "longitude": best_poi["longitude"],
                "type": best_poi.get("type"),
                "uri": best_poi.get("uri"),
                "city": best_poi.get("city"),
                "distance_from_previous_km": round(
                    haversine_distance(
                        current_lat, current_lon,
                        best_poi["latitude"], best_poi["longitude"]
                    ), 2
                )
            })
            
            # Update tracking
            used_poi_ids.add(best_poi["id"])
            if best_poi.get("type"):
                day_types.add(best_poi["type"])
            
            # Update current location to this POI
            current_lat = best_poi["latitude"]
            current_lon = best_poi["longitude"]
        
        if day_pois:
            itinerary.append({
                "day": day,
                "pois": day_pois,
                "total_pois": len(day_pois),
                "types_visited": list(day_types)
            })
    
    return {
        "start_location": {"latitude": start_lat, "longitude": start_lon},
        "days": days,
        "radius_km": radius_km,
        "types_filter": types,
        "limit_per_day": limit_per_day,
        "total_pois_found": len(all_pois),
        "total_pois_selected": len(used_poi_ids),
        "itinerary": itinerary
    }

