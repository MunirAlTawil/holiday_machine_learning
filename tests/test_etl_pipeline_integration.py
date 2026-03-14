"""
Integration tests for ETL pipeline end-to-end.
Tests the complete ETL workflow: Extract -> Transform -> Load.
"""
import os
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from src.pipelines.batch_etl import (
    fetch_pois_from_api,
    transform_pois,
    load_pois_to_database,
    main as batch_etl_main,
    ensure_pipeline_runs_table,
    create_pipeline_run,
    update_pipeline_run
)
from src.api.models import POI, Base
from src.api.db import Base as DBBase


@pytest.fixture(scope="module")
def postgres_container():
    """Create a PostgreSQL test container."""
    with PostgresContainer("postgres:16") as postgres:
        yield postgres


@pytest.fixture
def test_db(postgres_container):
    """Create test database with schema."""
    # Get connection string from container
    connection_url = postgres_container.get_connection_url()
    # For SQLAlchemy, we need postgresql:// (testcontainers may return postgresql+psycopg2)
    if connection_url.startswith("postgresql+psycopg2"):
        connection_url = connection_url.replace("postgresql+psycopg2", "postgresql")
    elif connection_url.startswith("postgres://"):
        connection_url = connection_url.replace("postgres://", "postgresql://")
    
    # Create engine and schema
    engine = create_engine(connection_url, echo=False)
    
    # Create all tables
    Base.metadata.create_all(engine)
    DBBase.metadata.create_all(engine)
    
    # Create data_source table if it doesn't exist
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
    
    # Ensure pipeline_runs table exists
    ensure_pipeline_runs_table(engine)
    
    yield engine
    
    # Cleanup
    Base.metadata.drop_all(engine)
    DBBase.metadata.drop_all(engine)


@pytest.fixture
def mock_api_response():
    """Mock DataTourisme API response."""
    return {
        "objects": [
            {
                "uuid": "test-poi-1",
                "label": {"fr": "Musée du Louvre"},
                "type": "Museum",
                "uri": "https://example.com/louvre",
                "isLocatedAt": [{
                    "schema:geo": {
                        "schema:latitude": 48.8606,
                        "schema:longitude": 2.3376
                    },
                    "schema:address": {
                        "schema:addressLocality": "Paris",
                        "schema:postalCode": "75001"
                    }
                }],
                "hasDescription": [{
                    "shortDescription": {
                        "fr": "Le musée du Louvre est un musée d'art et d'antiquités"
                    }
                }],
                "lastUpdate": "2024-01-15T10:30:00Z"
            },
            {
                "uuid": "test-poi-2",
                "label": {"fr": "Restaurant Le Comptoir"},
                "type": "Restaurant",
                "uri": "https://example.com/comptoir",
                "isLocatedAt": [{
                    "schema:geo": {
                        "schema:latitude": 48.8566,
                        "schema:longitude": 2.3522
                    },
                    "schema:address": {
                        "schema:addressLocality": "Paris",
                        "schema:postalCode": "75002"
                    }
                }],
                "hasDescription": [{
                    "shortDescription": {
                        "fr": "Un restaurant français traditionnel"
                    }
                }],
                "lastUpdate": "2024-01-16T14:20:00Z"
            },
            {
                "uuid": "test-poi-3-invalid",
                "label": {"fr": "POI sans coordonnées"},
                "type": "Hotel",
                # Missing coordinates - should be skipped
                "isLocatedAt": [],
                "lastUpdate": "2024-01-17T08:00:00Z"
            }
        ]
    }


def test_etl_pipeline_end_to_end(test_db, mock_api_response):
    """Test complete ETL pipeline end-to-end."""
    # Mock the API call
    mock_response = Mock()
    mock_response.json.return_value = mock_api_response
    mock_response.status_code = 200
    mock_response.raise_for_status = Mock()
    
    # Set environment variable for API key
    os.environ["DATATOURISME_API_KEY"] = "test-api-key"
    
    # Patch DATABASE_URL to use test database
    import src.pipelines.batch_etl as batch_etl_module
    original_db_url = batch_etl_module.DATABASE_URL
    batch_etl_module.DATABASE_URL = str(test_db.url)
    
    try:
        with patch('src.pipelines.batch_etl.requests.get', return_value=mock_response):
            with patch('src.pipelines.batch_etl.fetch_with_retry', return_value=mock_response):
                # Step 1: Extract
                raw_pois = fetch_pois_from_api(
                    max_pages=1,
                    page_size=250,
                    limit_per_run=10,
                    rate_limiter=None
                )
                
                assert len(raw_pois) == 3
                assert raw_pois[0]["uuid"] == "test-poi-1"
                
                # Step 2: Transform
                transformed_pois = transform_pois(raw_pois)
                
                # Should have 2 valid POIs (one without coordinates is skipped)
                assert len(transformed_pois) == 2
                assert transformed_pois[0]["id"] == "test-poi-1"
                assert transformed_pois[0]["latitude"] == 48.8606
                assert transformed_pois[0]["longitude"] == 2.3376
                assert transformed_pois[0]["city"] == "Paris"
                assert transformed_pois[0]["department_code"] == "75"
                
                # Step 3: Load
                inserted, updated, skipped = load_pois_to_database(
                    transformed_pois,
                    batch_size=10,
                    engine=test_db
                )
                
                assert inserted == 2
                assert updated == 0
                assert skipped == 0
                
                # Verify data in database
                SessionLocal = sessionmaker(bind=test_db)
                session = SessionLocal()
                try:
                    pois = session.query(POI).all()
                    assert len(pois) == 2
                    
                    poi1 = session.query(POI).filter(POI.id == "test-poi-1").first()
                    assert poi1 is not None
                    assert poi1.label == "Musée du Louvre"
                    assert poi1.type == "Museum"
                    assert poi1.latitude == 48.8606
                    assert poi1.longitude == 2.3376
                    assert poi1.city == "Paris"
                    assert poi1.department_code == "75"
                    assert poi1.uri == "https://example.com/louvre"
                    
                    poi2 = session.query(POI).filter(POI.id == "test-poi-2").first()
                    assert poi2 is not None
                    assert poi2.type == "Restaurant"
                finally:
                    session.close()
    finally:
        batch_etl_module.DATABASE_URL = original_db_url
    finally:
        batch_etl_module.DATABASE_URL = original_db_url


def test_etl_pipeline_with_existing_data(test_db, mock_api_response):
    """Test ETL pipeline with existing POI data (update scenario)."""
    # First, insert a POI with older last_update
    SessionLocal = sessionmaker(bind=test_db)
    session = SessionLocal()
    try:
        # Insert existing POI with older timestamp
        old_poi = POI(
            id="test-poi-1",
            label="Old Label",
            type="Museum",
            latitude=48.8606,
            longitude=2.3376,
            last_update=datetime(2024, 1, 10, 10, 0, 0)  # Older than API response
        )
        session.add(old_poi)
        session.commit()
    finally:
        session.close()
    
    # Mock API response with newer last_update
    mock_response = Mock()
    mock_response.json.return_value = mock_api_response
    mock_response.status_code = 200
    mock_response.raise_for_status = Mock()
    
    os.environ["DATATOURISME_API_KEY"] = "test-api-key"
    
    import src.pipelines.batch_etl as batch_etl_module
    original_db_url = batch_etl_module.DATABASE_URL
    batch_etl_module.DATABASE_URL = str(test_db.url)
    
    try:
        with patch('src.pipelines.batch_etl.requests.get', return_value=mock_response):
            with patch('src.pipelines.batch_etl.fetch_with_retry', return_value=mock_response):
                # Run ETL
                raw_pois = fetch_pois_from_api(max_pages=1, page_size=250, limit_per_run=10)
                transformed_pois = transform_pois(raw_pois)
                inserted, updated, skipped = load_pois_to_database(
                    transformed_pois,
                    batch_size=10,
                    engine=test_db
                )
                
                # Should update existing POI
                assert inserted == 1  # Only new POI (test-poi-2)
                assert updated == 1   # Updated test-poi-1
                assert skipped == 0
                
                # Verify update
                session = SessionLocal()
                try:
                    poi = session.query(POI).filter(POI.id == "test-poi-1").first()
                    assert poi.label == "Musée du Louvre"  # Updated label
                    assert poi.last_update > datetime(2024, 1, 10, 10, 0, 0)  # Newer timestamp
                finally:
                    session.close()
    finally:
        batch_etl_module.DATABASE_URL = original_db_url


def test_etl_pipeline_skips_older_updates(test_db, mock_api_response):
    """Test that ETL pipeline skips POIs with older last_update."""
    # Insert POI with newer timestamp
    SessionLocal = sessionmaker(bind=test_db)
    session = SessionLocal()
    try:
        new_poi = POI(
            id="test-poi-1",
            label="Current Label",
            type="Museum",
            latitude=48.8606,
            longitude=2.3376,
            last_update=datetime(2024, 1, 20, 10, 0, 0)  # Newer than API response (2024-01-15)
        )
        session.add(new_poi)
        session.commit()
    finally:
        session.close()
    
    # Mock API response
    mock_response = Mock()
    mock_response.json.return_value = mock_api_response
    mock_response.status_code = 200
    mock_response.raise_for_status = Mock()
    
    os.environ["DATATOURISME_API_KEY"] = "test-api-key"
    
    import src.pipelines.batch_etl as batch_etl_module
    original_db_url = batch_etl_module.DATABASE_URL
    batch_etl_module.DATABASE_URL = str(test_db.url)
    
    try:
        with patch('src.pipelines.batch_etl.requests.get', return_value=mock_response):
            with patch('src.pipelines.batch_etl.fetch_with_retry', return_value=mock_response):
                raw_pois = fetch_pois_from_api(max_pages=1, page_size=250, limit_per_run=10)
                transformed_pois = transform_pois(raw_pois)
                inserted, updated, skipped = load_pois_to_database(
                    transformed_pois,
                    batch_size=10,
                    engine=test_db
                )
                
                # Should skip test-poi-1 (older update) and insert test-poi-2
                assert inserted == 1
                assert updated == 0
                assert skipped == 1  # Skipped because DB has newer timestamp
                
                # Verify POI was not updated
                session = SessionLocal()
                try:
                    poi = session.query(POI).filter(POI.id == "test-poi-1").first()
                    assert poi.label == "Current Label"  # Not updated
                finally:
                    session.close()
    finally:
        batch_etl_module.DATABASE_URL = original_db_url


def test_pipeline_runs_tracking(test_db):
    """Test that pipeline runs are tracked in pipeline_runs table."""
    ensure_pipeline_runs_table(test_db)
    
    # Create a pipeline run
    run_id = create_pipeline_run(test_db)
    assert run_id is not None
    
    # Update pipeline run
    update_pipeline_run(
        test_db,
        run_id,
        'success',
        fetched_count=10,
        processed_count=8,
        inserted_count=5,
        updated_count=2,
        skipped_count=1
    )
    
    # Verify run was recorded
    SessionLocal = sessionmaker(bind=test_db)
    session = SessionLocal()
    try:
        result = session.execute(
            text("SELECT * FROM pipeline_runs WHERE run_id = :run_id"),
            {"run_id": run_id}
        )
        row = result.fetchone()
        assert row is not None
        assert row[3] == 'success'  # status
        assert row[4] == 10  # fetched_count
        assert row[5] == 8  # processed_count
        assert row[6] == 5  # inserted_count
        assert row[7] == 2  # updated_count
        assert row[8] == 1  # skipped_count
    finally:
        session.close()

