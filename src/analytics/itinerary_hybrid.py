"""
Hybrid Itinerary Generation Algorithm (PostgreSQL + Neo4j)
==========================================================

Uses PostgreSQL for geospatial queries and Neo4j for type diversity optimization.
"""
import math
import os
from typing import List, Dict, Any, Optional, Tuple, Set
from sqlalchemy.orm import Session
from sqlalchemy import text
from neo4j import GraphDatabase, Driver
from dotenv import load_dotenv

load_dotenv()

# Neo4j configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j_password")

# PostgreSQL configuration (for reference, but we use db session passed as parameter)
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "holiday")
POSTGRES_USER = os.getenv("POSTGRES_USER", "holiday")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "holiday")


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points on Earth (in kilometers)."""
    R = 6371.0
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c


def get_neo4j_driver() -> Optional[Driver]:
    """Create and return Neo4j driver instance."""
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        return driver
    except Exception:
        return None


def get_poi_types_from_neo4j(driver: Driver, poi_ids: List[str]) -> Dict[str, str]:
    """
    Get POI types from Neo4j using HAS_TYPE relationships.
    
    Returns:
        Dictionary mapping POI ID to type name
    """
    if not poi_ids:
        return {}
    
    try:
        with driver.session() as session:
            # Query to get POI types
            query = """
                MATCH (p:POI)-[:HAS_TYPE]->(t:Type)
                WHERE p.id IN $poi_ids
                RETURN p.id AS poi_id, t.name AS type_name
            """
            result = session.run(query, poi_ids=poi_ids)
            
            poi_types = {}
            for record in result:
                poi_types[record["poi_id"]] = record["type_name"]
            
            return poi_types
    except Exception:
        return {}


def get_type_diversity_scores(
    driver: Driver,
    candidate_poi_ids: List[str],
    used_types: Set[str],
    day_types: Set[str]
) -> Dict[str, float]:
    """
    Use Neo4j to calculate type diversity scores for candidate POIs.
    
    Higher score = better diversity (less repetition of types).
    
    Returns:
        Dictionary mapping POI ID to diversity score
    """
    if not driver or not candidate_poi_ids:
        return {poi_id: 0.0 for poi_id in candidate_poi_ids}
    
    try:
        # Get types for all candidate POIs
        poi_types = get_poi_types_from_neo4j(driver, candidate_poi_ids)
        
        diversity_scores = {}
        for poi_id in candidate_poi_ids:
            poi_type = poi_types.get(poi_id)
            
            if not poi_type:
                # No type info - neutral score
                diversity_scores[poi_id] = 0.0
            elif poi_type not in used_types:
                # New type never used - highest diversity bonus
                diversity_scores[poi_id] = 10.0
            elif poi_type not in day_types:
                # New type for this day - good diversity bonus
                diversity_scores[poi_id] = 5.0
            else:
                # Type already used today - penalty
                diversity_scores[poi_id] = -2.0
        
        return diversity_scores
    except Exception:
        # If Neo4j fails, return neutral scores
        return {poi_id: 0.0 for poi_id in candidate_poi_ids}


def find_nearby_pois(
    db: Session,
    center_lat: float,
    center_lon: float,
    radius_km: float = 50.0,
    types: Optional[List[str]] = None,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """Find POIs within radius_km of center coordinates using PostgreSQL."""
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


def generate_itinerary_hybrid(
    db: Session,
    start_lat: float,
    start_lon: float,
    days: int,
    daily_limit: int,
    radius_km: float = 50.0,
    types: Optional[List[str]] = None,
    diversity: bool = True
) -> Dict[str, Any]:
    """
    Generate itinerary using HYBRID approach (PostgreSQL + Neo4j).
    
    Algorithm:
    1. PostgreSQL: Find candidate POIs within radius (geospatial query)
    2. Neo4j (if diversity=True): Use graph to optimize type diversity
    3. Greedy selection: Minimize distance + maximize diversity
    
    Args:
        db: PostgreSQL database session
        start_lat: Starting latitude
        start_lon: Starting longitude
        days: Number of days
        daily_limit: Maximum POIs per day
        radius_km: Search radius in kilometers
        types: Optional list of POI types to filter
        diversity: If True, use Neo4j to maximize type diversity
    
    Returns:
        Dictionary with day-by-day itinerary
    """
    # Step 1: Find candidate POIs from PostgreSQL
    all_pois = find_nearby_pois(db, start_lat, start_lon, radius_km, types, limit=1000)
    
    if not all_pois:
        return {
            "start_location": {"latitude": start_lat, "longitude": start_lon},
            "days": days,
            "daily_limit": daily_limit,
            "total_pois_found": 0,
            "itinerary": [],
            "meta": {
                "diversity_mode": diversity,
                "neo4j_used": False
            }
        }
    
    # Step 2: Connect to Neo4j if diversity mode is enabled
    neo4j_driver = None
    neo4j_used = False
    if diversity:
        neo4j_driver = get_neo4j_driver()
        if neo4j_driver:
            neo4j_used = True
    
    # Step 3: Generate itinerary
    used_poi_ids = set()
    used_types = set()  # Types used across all days
    itinerary = []
    current_lat = start_lat
    current_lon = start_lon
    
    for day in range(1, days + 1):
        day_pois = []
        day_types = set()  # Types used in this day
        
        # Try to select daily_limit POIs for this day
        for _ in range(daily_limit):
            best_poi = None
            best_score = float('inf')
            
            # Get diversity scores from Neo4j if available
            candidate_ids = [p["id"] for p in all_pois if p["id"] not in used_poi_ids]
            diversity_scores = {}
            if neo4j_driver and diversity:
                diversity_scores = get_type_diversity_scores(
                    neo4j_driver, candidate_ids, used_types, day_types
                )
            
            for poi in all_pois:
                # Skip if already used
                if poi["id"] in used_poi_ids:
                    continue
                
                # Calculate distance from current location
                distance = haversine_distance(
                    current_lat, current_lon,
                    poi["latitude"], poi["longitude"]
                )
                
                # Base score: distance (lower is better)
                score = distance
                
                # Apply diversity bonus/penalty if Neo4j is available
                if diversity and neo4j_driver:
                    diversity_bonus = diversity_scores.get(poi["id"], 0.0)
                    # Convert diversity bonus to distance penalty (negative = better)
                    score = score - (diversity_bonus * 2)  # Multiply by 2 to weight diversity
                elif diversity:
                    # Fallback: simple type diversity without Neo4j
                    poi_type = poi.get("type")
                    if poi_type and poi_type not in day_types:
                        score = score - 5  # Prefer new types
                    elif poi_type and poi_type in day_types:
                        score = score + 2  # Penalize repeated types
                
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
            poi_type = best_poi.get("type")
            if poi_type:
                used_types.add(poi_type)
                day_types.add(poi_type)
            
            # Update current location to this POI
            current_lat = best_poi["latitude"]
            current_lon = best_poi["longitude"]
        
        if day_pois:
            itinerary.append({
                "day": day,
                "items": day_pois,
                "total_pois": len(day_pois),
                "types_visited": list(day_types)
            })
    
    # Close Neo4j driver if opened
    if neo4j_driver:
        neo4j_driver.close()
    
    return {
        "start_location": {"latitude": start_lat, "longitude": start_lon},
        "days": days,
        "daily_limit": daily_limit,
        "radius_km": radius_km,
        "types_filter": types,
        "total_pois_found": len(all_pois),
        "total_pois_selected": len(used_poi_ids),
        "itinerary": itinerary,
        "meta": {
            "diversity_mode": diversity,
            "neo4j_used": neo4j_used
        }
    }

