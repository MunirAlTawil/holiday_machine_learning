"""
Graph Loader for Holiday Itinerary Project - Neo4j Integration
================================================================

Loads POI data from PostgreSQL into Neo4j graph database.
Creates nodes and relationships for POIs, Types, Cities, and Departments.

Usage:
    from src.pipelines.graph_loader import load_pois_to_neo4j
    load_pois_to_neo4j()

Environment Variables Required:
    - NEO4J_URI: Neo4j connection URI (default: bolt://neo4j:7687)
    - NEO4J_USER: Neo4j username (default: neo4j)
    - NEO4J_PASSWORD: Neo4j password (default: neo4j_password)
    - POSTGRES_*: PostgreSQL connection variables (for reading POI data)
"""
import logging
import os
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv
from neo4j import GraphDatabase, Driver, Session
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

# Neo4j configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j_password")

# PostgreSQL configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "holiday")
POSTGRES_USER = os.getenv("POSTGRES_USER", "holiday")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "holiday")

POSTGRES_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# ============================================================================
# NEO4J CONNECTION
# ============================================================================

def get_neo4j_driver() -> Optional[Driver]:
    """Create and return Neo4j driver instance."""
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        # Verify connection
        driver.verify_connectivity()
        logger.info(f"Connected to Neo4j at {NEO4J_URI}")
        return driver
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j: {e}")
        return None

# ============================================================================
# CONSTRAINTS & INDEXES
# ============================================================================

def create_constraints_and_indexes(driver: Driver) -> None:
    """Create constraints and indexes in Neo4j for optimal performance."""
    with driver.session() as session:
        # Create unique constraints (Neo4j 5.x syntax)
        constraints = [
            ("CREATE CONSTRAINT poi_id_unique IF NOT EXISTS FOR (p:POI) REQUIRE p.id IS UNIQUE", "POI.id IS UNIQUE"),
            ("CREATE CONSTRAINT type_name_unique IF NOT EXISTS FOR (t:Type) REQUIRE t.name IS UNIQUE", "Type.name IS UNIQUE"),
            ("CREATE CONSTRAINT department_code_unique IF NOT EXISTS FOR (d:Department) REQUIRE d.code IS UNIQUE", "Department.code IS UNIQUE"),
            ("CREATE CONSTRAINT city_name_unique IF NOT EXISTS FOR (c:City) REQUIRE c.name IS UNIQUE", "City.name IS UNIQUE"),
        ]
        
        for constraint_query, constraint_name in constraints:
            try:
                session.run(constraint_query)
                logger.info(f"Created constraint: {constraint_name}")
            except Exception as e:
                # Constraint may already exist, which is fine
                if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                    logger.debug(f"Constraint {constraint_name} already exists")
                else:
                    logger.warning(f"Error creating constraint {constraint_name}: {e}")
        
        # Create indexes for better query performance
        indexes = [
            ("CREATE INDEX poi_type_index IF NOT EXISTS FOR (p:POI) ON (p.type)", "POI.type"),
        ]
        
        for index_query, index_name in indexes:
            try:
                session.run(index_query)
                logger.info(f"Created index: {index_name}")
            except Exception as e:
                # Index may already exist, which is fine
                if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                    logger.debug(f"Index {index_name} already exists")
                else:
                    logger.warning(f"Error creating index {index_name}: {e}")

# ============================================================================
# DATA LOADING
# ============================================================================

def fetch_pois_from_postgres() -> List[Dict[str, Any]]:
    """Fetch all POIs from PostgreSQL database."""
    try:
        engine = create_engine(POSTGRES_URL)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        
        query = text("""
            SELECT 
                id, label, description, latitude, longitude, 
                uri, type, city, department_code, theme, last_update
            FROM poi
            ORDER BY id
        """)
        
        result = session.execute(query)
        pois = []
        for row in result:
            pois.append({
                "id": row[0],
                "label": row[1],
                "description": row[2],
                "latitude": float(row[3]) if row[3] is not None else None,
                "longitude": float(row[4]) if row[4] is not None else None,
                "uri": row[5],
                "type": row[6],
                "city": row[7],
                "department_code": row[8],
                "theme": row[9],
                "last_update": row[10].isoformat() if row[10] else None
            })
        
        session.close()
        logger.info(f"Fetched {len(pois)} POIs from PostgreSQL")
        return pois
    except Exception as e:
        logger.error(f"Failed to fetch POIs from PostgreSQL: {e}")
        raise

def load_pois_to_neo4j(batch_size: int = 100) -> Tuple[int, int, int, int]:
    """
    Load POIs from PostgreSQL into Neo4j graph database.
    
    Creates:
    - POI nodes with properties: id, label, type, latitude, longitude, uri, theme, last_update
    - Type nodes (if type exists)
    - City nodes (if city exists)
    - Department nodes (if department_code exists)
    - Relationships: HAS_TYPE, IN_CITY, IN_DEPARTMENT
    
    Args:
        batch_size: Number of POIs to process in each batch
        
    Returns:
        Tuple of (pois_loaded, types_created, cities_created, departments_created)
    """
    driver = get_neo4j_driver()
    if not driver:
        raise ConnectionError("Failed to connect to Neo4j")
    
    try:
        # Create constraints and indexes
        create_constraints_and_indexes(driver)
        
        # Fetch POIs from PostgreSQL
        pois = fetch_pois_from_postgres()
        
        if not pois:
            logger.warning("No POIs found in PostgreSQL")
            return (0, 0, 0, 0)
        
        logger.info(f"Loading {len(pois)} POIs into Neo4j...")
        
        pois_loaded = 0
        types_created = set()
        cities_created = set()
        departments_created = set()
        
        with driver.session() as session:
            # Process in batches
            for i in range(0, len(pois), batch_size):
                batch = pois[i:i + batch_size]
                
                for poi in batch:
                    try:
                        # Create or merge POI node
                        poi_query = """
                            MERGE (p:POI {id: $id})
                            SET p.label = $label,
                                p.type = $type,
                                p.latitude = $latitude,
                                p.longitude = $longitude,
                                p.uri = $uri,
                                p.theme = $theme,
                                p.last_update = $last_update
                        """
                        session.run(poi_query, {
                            "id": poi["id"],
                            "label": poi.get("label"),
                            "type": poi.get("type"),
                            "latitude": poi.get("latitude"),
                            "longitude": poi.get("longitude"),
                            "uri": poi.get("uri"),
                            "theme": poi.get("theme"),
                            "last_update": poi.get("last_update")
                        })
                        pois_loaded += 1
                        
                        # Create Type node and relationship (if type exists)
                        if poi.get("type"):
                            type_name = poi["type"]
                            types_created.add(type_name)
                            
                            # Create or merge Type node
                            session.run("""
                                MERGE (t:Type {name: $name})
                            """, {"name": type_name})
                            
                            # Create HAS_TYPE relationship
                            session.run("""
                                MATCH (p:POI {id: $poi_id})
                                MATCH (t:Type {name: $type_name})
                                MERGE (p)-[:HAS_TYPE]->(t)
                            """, {"poi_id": poi["id"], "type_name": type_name})
                        
                        # Create City node and relationship (if city exists)
                        if poi.get("city"):
                            city_name = poi["city"]
                            cities_created.add(city_name)
                            
                            # Create or merge City node
                            session.run("""
                                MERGE (c:City {name: $name})
                            """, {"name": city_name})
                            
                            # Create IN_CITY relationship
                            session.run("""
                                MATCH (p:POI {id: $poi_id})
                                MATCH (c:City {name: $city_name})
                                MERGE (p)-[:IN_CITY]->(c)
                            """, {"poi_id": poi["id"], "city_name": city_name})
                        
                        # Create Department node and relationship (if department_code exists)
                        if poi.get("department_code"):
                            dept_code = poi["department_code"]
                            departments_created.add(dept_code)
                            
                            # Create or merge Department node
                            session.run("""
                                MERGE (d:Department {code: $code})
                            """, {"code": dept_code})
                            
                            # Create IN_DEPARTMENT relationship
                            session.run("""
                                MATCH (p:POI {id: $poi_id})
                                MATCH (d:Department {code: $dept_code})
                                MERGE (p)-[:IN_DEPARTMENT]->(d)
                            """, {"poi_id": poi["id"], "dept_code": dept_code})
                    
                    except Exception as e:
                        logger.warning(f"Error processing POI {poi.get('id', 'unknown')}: {e}")
                        continue
                
                logger.info(f"Processed {min(i + batch_size, len(pois))}/{len(pois)} POIs...")
        
        logger.info("=" * 60)
        logger.info("Graph Load Complete:")
        logger.info(f"  - POIs loaded: {pois_loaded}")
        logger.info(f"  - Types created: {len(types_created)}")
        logger.info(f"  - Cities created: {len(cities_created)}")
        logger.info(f"  - Departments created: {len(departments_created)}")
        logger.info("=" * 60)
        
        return (pois_loaded, len(types_created), len(cities_created), len(departments_created))
    
    finally:
        driver.close()

def get_graph_summary() -> Dict[str, Any]:
    """
    Get summary statistics from Neo4j graph.
    
    Returns:
        Dictionary with counts of nodes and relationships
    """
    driver = get_neo4j_driver()
    if not driver:
        raise ConnectionError("Failed to connect to Neo4j")
    
    try:
        with driver.session() as session:
            # Count POI nodes
            poi_count = session.run("MATCH (p:POI) RETURN count(p) as count").single()["count"]
            
            # Count Type nodes
            type_count = session.run("MATCH (t:Type) RETURN count(t) as count").single()["count"]
            
            # Count City nodes
            city_count = session.run("MATCH (c:City) RETURN count(c) as count").single()["count"]
            
            # Count Department nodes
            dept_count = session.run("MATCH (d:Department) RETURN count(d) as count").single()["count"]
            
            # Count HAS_TYPE relationships
            has_type_count = session.run("MATCH ()-[r:HAS_TYPE]->() RETURN count(r) as count").single()["count"]
            
            # Count IN_CITY relationships
            in_city_count = session.run("MATCH ()-[r:IN_CITY]->() RETURN count(r) as count").single()["count"]
            
            # Count IN_DEPARTMENT relationships
            in_dept_count = session.run("MATCH ()-[r:IN_DEPARTMENT]->() RETURN count(r) as count").single()["count"]
            
            return {
                "poi_nodes": poi_count,
                "type_nodes": type_count,
                "city_nodes": city_count,
                "department_nodes": dept_count,
                "has_type_relationships": has_type_count,
                "in_city_relationships": in_city_count,
                "in_department_relationships": in_dept_count,
                "total_nodes": poi_count + type_count + city_count + dept_count,
                "total_relationships": has_type_count + in_city_count + in_dept_count
            }
    finally:
        driver.close()

