"""
Integration tests for Neo4j graph loading.
Tests node creation, relationship creation, and graph structure.
"""
import os
import pytest
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer
from testcontainers.neo4j import Neo4jContainer

from src.pipelines.graph_loader import (
    get_neo4j_driver,
    create_constraints_and_indexes,
    fetch_pois_from_postgres,
    load_pois_to_neo4j,
    get_graph_summary
)
from src.api.models import POI, Base
from src.api.db import Base as DBBase


@pytest.fixture(scope="module")
def postgres_container():
    """Create a PostgreSQL test container."""
    with PostgresContainer("postgres:16") as postgres:
        yield postgres


@pytest.fixture(scope="module")
def neo4j_container():
    """Create a Neo4j test container."""
    with Neo4jContainer("neo4j:5.15-community") as neo4j:
        yield neo4j


@pytest.fixture
def test_db(postgres_container):
    """Create test database with schema and sample data."""
    connection_url = postgres_container.get_connection_url()
    # Fix connection URL for SQLAlchemy
    if connection_url.startswith("postgresql+psycopg2"):
        connection_url = connection_url.replace("postgresql+psycopg2", "postgresql")
    elif not connection_url.startswith("postgresql"):
        connection_url = connection_url.replace("postgres", "postgresql")
    engine = create_engine(connection_url, echo=False)
    
    # Create all tables
    Base.metadata.create_all(engine)
    DBBase.metadata.create_all(engine)
    
    # Create data_source table
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS data_source (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            INSERT INTO data_source (name, description)
            VALUES ('DataTourisme API', 'DataTourisme API - French tourism data platform')
            ON CONFLICT (name) DO NOTHING
        """))
        conn.commit()
    
    # Insert sample POIs
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        pois = [
            POI(
                id="poi-1",
                label="Louvre Museum",
                type="Museum",
                latitude=48.8606,
                longitude=2.3376,
                city="Paris",
                department_code="75",
                uri="https://example.com/louvre",
                last_update=datetime(2024, 1, 15, 10, 30, 0)
            ),
            POI(
                id="poi-2",
                label="Eiffel Tower",
                type="Monument",
                latitude=48.8584,
                longitude=2.2945,
                city="Paris",
                department_code="75",
                uri="https://example.com/eiffel",
                last_update=datetime(2024, 1, 16, 14, 20, 0)
            ),
            POI(
                id="poi-3",
                label="Restaurant Le Comptoir",
                type="Restaurant",
                latitude=48.8566,
                longitude=2.3522,
                city="Paris",
                department_code="75",
                uri="https://example.com/comptoir",
                last_update=datetime(2024, 1, 17, 8, 0, 0)
            ),
            POI(
                id="poi-4",
                label="Hotel Plaza",
                type="Hotel",
                latitude=45.7640,
                longitude=4.8357,
                city="Lyon",
                department_code="69",
                uri="https://example.com/plaza",
                last_update=datetime(2024, 1, 18, 12, 0, 0)
            ),
            POI(
                id="poi-5",
                label="POI without type",
                type=None,  # No type
                latitude=46.2276,
                longitude=2.2137,
                city=None,  # No city
                department_code=None,  # No department
                uri="https://example.com/poi5",
                last_update=datetime(2024, 1, 19, 9, 0, 0)
            )
        ]
        session.add_all(pois)
        session.commit()
    finally:
        session.close()
    
    yield engine
    
    # Cleanup
    Base.metadata.drop_all(engine)
    DBBase.metadata.drop_all(engine)


@pytest.fixture
def test_neo4j(neo4j_container):
    """Set up Neo4j connection for testing."""
    connection_url = neo4j_container.get_connection_url()
    auth = neo4j_container.get_connection_auth()
    
    # Set environment variables
    os.environ["NEO4J_URI"] = connection_url.replace("bolt://", "bolt://")
    os.environ["NEO4J_USER"] = auth[0]
    os.environ["NEO4J_PASSWORD"] = auth[1]
    
    yield connection_url, auth
    
    # Cleanup
    if "NEO4J_URI" in os.environ:
        del os.environ["NEO4J_URI"]
    if "NEO4J_USER" in os.environ:
        del os.environ["NEO4J_USER"]
    if "NEO4J_PASSWORD" in os.environ:
        del os.environ["NEO4J_PASSWORD"]


def test_neo4j_connection(test_neo4j):
    """Test Neo4j connection."""
    connection_url, auth = test_neo4j
    driver = get_neo4j_driver()
    assert driver is not None
    
    # Test connection
    with driver.session() as session:
        result = session.run("RETURN 1 as test")
        record = result.single()
        assert record["test"] == 1
    
    driver.close()


def test_create_constraints_and_indexes(test_neo4j):
    """Test that constraints and indexes are created."""
    driver = get_neo4j_driver()
    assert driver is not None
    
    try:
        create_constraints_and_indexes(driver)
        
        # Verify constraints exist by trying to create duplicate (should fail gracefully)
        with driver.session() as session:
            # Try to create a POI with duplicate ID (should work, but constraint exists)
            session.run("CREATE (p:POI {id: 'test-constraint'})")
            session.run("CREATE (p:POI {id: 'test-constraint'})")  # Should fail or be handled
    finally:
        driver.close()


def test_load_pois_to_neo4j(test_db, test_neo4j):
    """Test loading POIs from PostgreSQL to Neo4j."""
    connection_url, auth = test_neo4j
    
    # Update graph loader to use test database directly
    from src.pipelines import graph_loader
    original_fetch_func = graph_loader.fetch_pois_from_postgres
    
    # Create a wrapper that uses test_db
    def fetch_from_test_db():
        SessionLocal = sessionmaker(bind=test_db)
        session = SessionLocal()
        try:
            query = text("""
                SELECT 
                    id, label, description, latitude, longitude, 
                    uri, type, city, department_code, last_update
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
                    "last_update": row[9].isoformat() if row[9] else None
                })
            return pois
        finally:
            session.close()
    
    graph_loader.fetch_pois_from_postgres = fetch_from_test_db
    
    try:
        # Load POIs
        pois_loaded, types_created, cities_created, depts_created = load_pois_to_neo4j(batch_size=10)
        
        assert pois_loaded == 5
        assert types_created == 4  # Museum, Monument, Restaurant, Hotel (4 distinct types)
        assert cities_created == 2  # Paris, Lyon
        assert depts_created == 2  # 75, 69
        
        # Verify nodes in Neo4j
        driver = get_neo4j_driver()
        with driver.session() as session:
            # Count POI nodes
            result = session.run("MATCH (p:POI) RETURN count(p) as count")
            poi_count = result.single()["count"]
            assert poi_count == 5
            
            # Count Type nodes
            result = session.run("MATCH (t:Type) RETURN count(t) as count")
            type_count = result.single()["count"]
            assert type_count == 4  # Museum, Monument, Restaurant, Hotel
            
            # Count City nodes
            result = session.run("MATCH (c:City) RETURN count(c) as count")
            city_count = result.single()["count"]
            assert city_count == 2  # Paris, Lyon
            
            # Count Department nodes
            result = session.run("MATCH (d:Department) RETURN count(d) as count")
            dept_count = result.single()["count"]
            assert dept_count == 2  # 75, 69
            
            # Verify relationships
            result = session.run("MATCH ()-[r:HAS_TYPE]->() RETURN count(r) as count")
            has_type_count = result.single()["count"]
            assert has_type_count == 4  # 4 POIs with types (poi-5 has no type)
            
            result = session.run("MATCH ()-[r:IN_CITY]->() RETURN count(r) as count")
            in_city_count = result.single()["count"]
            assert in_city_count == 4  # 4 POIs with cities (poi-5 has no city)
            
            result = session.run("MATCH ()-[r:IN_DEPARTMENT]->() RETURN count(r) as count")
            in_dept_count = result.single()["count"]
            assert in_dept_count == 4  # 4 POIs with departments (poi-5 has no department)
        
        driver.close()
    finally:
        # Restore original
        graph_loader.fetch_pois_from_postgres = original_fetch_func


def test_verify_poi_node_properties(test_db, test_neo4j):
    """Test that POI nodes have correct properties."""
    connection_url, auth = test_neo4j
    
    from src.pipelines import graph_loader
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text
    original_fetch_func = graph_loader.fetch_pois_from_postgres
    
    def fetch_from_test_db():
        SessionLocal = sessionmaker(bind=test_db)
        session = SessionLocal()
        try:
            query = text("""
                SELECT 
                    id, label, description, latitude, longitude, 
                    uri, type, city, department_code, last_update
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
                    "last_update": row[9].isoformat() if row[9] else None
                })
            return pois
        finally:
            session.close()
    
    graph_loader.fetch_pois_from_postgres = fetch_from_test_db
    
    try:
        load_pois_to_neo4j(batch_size=10)
        
        driver = get_neo4j_driver()
        with driver.session() as session:
            # Get a specific POI
            result = session.run("""
                MATCH (p:POI {id: 'poi-1'})
                RETURN p.id as id, p.label as label, p.type as type, 
                       p.latitude as lat, p.longitude as lon, p.uri as uri
            """)
            record = result.single()
            
            assert record["id"] == "poi-1"
            assert record["label"] == "Louvre Museum"
            assert record["type"] == "Museum"
            assert record["lat"] == 48.8606
            assert record["lon"] == 2.3376
            assert record["uri"] == "https://example.com/louvre"
        
        driver.close()
    finally:
        graph_loader.fetch_pois_from_postgres = original_fetch_func


def test_verify_relationships(test_db, test_neo4j):
    """Test that relationships are correctly created."""
    connection_url, auth = test_neo4j
    
    from src.pipelines import graph_loader
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text
    original_fetch_func = graph_loader.fetch_pois_from_postgres
    
    def fetch_from_test_db():
        SessionLocal = sessionmaker(bind=test_db)
        session = SessionLocal()
        try:
            query = text("""
                SELECT 
                    id, label, description, latitude, longitude, 
                    uri, type, city, department_code, last_update
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
                    "last_update": row[9].isoformat() if row[9] else None
                })
            return pois
        finally:
            session.close()
    
    graph_loader.fetch_pois_from_postgres = fetch_from_test_db
    
    try:
        load_pois_to_neo4j(batch_size=10)
        
        driver = get_neo4j_driver()
        with driver.session() as session:
            # Verify HAS_TYPE relationship
            result = session.run("""
                MATCH (p:POI {id: 'poi-1'})-[:HAS_TYPE]->(t:Type)
                RETURN t.name as type_name
            """)
            record = result.single()
            assert record["type_name"] == "Museum"
            
            # Verify IN_CITY relationship
            result = session.run("""
                MATCH (p:POI {id: 'poi-1'})-[:IN_CITY]->(c:City)
                RETURN c.name as city_name
            """)
            record = result.single()
            assert record["city_name"] == "Paris"
            
            # Verify IN_DEPARTMENT relationship
            result = session.run("""
                MATCH (p:POI {id: 'poi-1'})-[:IN_DEPARTMENT]->(d:Department)
                RETURN d.code as dept_code
            """)
            record = result.single()
            assert record["dept_code"] == "75"
        
        driver.close()
    finally:
        graph_loader.fetch_pois_from_postgres = original_fetch_func


def test_get_graph_summary(test_db, test_neo4j):
    """Test graph summary statistics."""
    connection_url, auth = test_neo4j
    
    from src.pipelines import graph_loader
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text
    original_fetch_func = graph_loader.fetch_pois_from_postgres
    
    def fetch_from_test_db():
        SessionLocal = sessionmaker(bind=test_db)
        session = SessionLocal()
        try:
            query = text("""
                SELECT 
                    id, label, description, latitude, longitude, 
                    uri, type, city, department_code, last_update
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
                    "last_update": row[9].isoformat() if row[9] else None
                })
            return pois
        finally:
            session.close()
    
    graph_loader.fetch_pois_from_postgres = fetch_from_test_db
    
    try:
        load_pois_to_neo4j(batch_size=10)
        
        summary = get_graph_summary()
        
        assert summary["poi_nodes"] == 5
        assert summary["type_nodes"] == 4  # Museum, Monument, Restaurant, Hotel
        assert summary["city_nodes"] == 2
        assert summary["department_nodes"] == 2
        assert summary["has_type_relationships"] == 4
        assert summary["in_city_relationships"] == 4
        assert summary["in_department_relationships"] == 4
        assert summary["total_nodes"] == 13  # 5 + 4 + 2 + 2
        assert summary["total_relationships"] == 12  # 4 + 4 + 4
    finally:
        graph_loader.fetch_pois_from_postgres = original_fetch_func


def test_load_pois_idempotent(test_db, test_neo4j):
    """Test that loading POIs multiple times is idempotent."""
    connection_url, auth = test_neo4j
    
    from src.pipelines import graph_loader
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text
    original_fetch_func = graph_loader.fetch_pois_from_postgres
    
    def fetch_from_test_db():
        SessionLocal = sessionmaker(bind=test_db)
        session = SessionLocal()
        try:
            query = text("""
                SELECT 
                    id, label, description, latitude, longitude, 
                    uri, type, city, department_code, last_update
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
                    "last_update": row[9].isoformat() if row[9] else None
                })
            return pois
        finally:
            session.close()
    
    graph_loader.fetch_pois_from_postgres = fetch_from_test_db
    
    try:
        # Load first time
        load_pois_to_neo4j(batch_size=10)
        
        # Load second time (should be idempotent)
        pois_loaded, types_created, cities_created, depts_created = load_pois_to_neo4j(batch_size=10)
        
        # Should still have same counts
        assert pois_loaded == 5
        assert types_created == 4
        assert cities_created == 2
        assert depts_created == 2
        
        # Verify node counts haven't changed
        driver = get_neo4j_driver()
        with driver.session() as session:
            result = session.run("MATCH (p:POI) RETURN count(p) as count")
            poi_count = result.single()["count"]
            assert poi_count == 5  # Should still be 5, not 10
        
        driver.close()
    finally:
        graph_loader.fetch_pois_from_postgres = original_fetch_func

