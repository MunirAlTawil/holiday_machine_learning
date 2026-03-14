"""
Unit tests for FastAPI endpoints.
Tests /health, /pois, /stats, and /graph/summary endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.main import app
from src.api.db import get_db, Base
from src.api.models import POI
from datetime import datetime

# Test database setup (in-memory SQLite for unit tests)
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    """Create a test database session."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    """Create a test client with database dependency override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    # Override the database dependency
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture
def sample_pois(db_session):
    """Create sample POI data for testing."""
    pois = [
        POI(
            id="poi-1",
            label="Test Museum",
            description="A test museum",
            latitude=48.8566,
            longitude=2.3522,
            type="Museum",
            city="Paris",
            department_code="75",
            uri="http://example.com/poi-1",
            last_update=datetime.now(),
            created_at=datetime.now()
        ),
        POI(
            id="poi-2",
            label="Test Restaurant",
            description="A test restaurant",
            latitude=48.8606,
            longitude=2.3376,
            type="Restaurant",
            city="Paris",
            department_code="75",
            uri="http://example.com/poi-2",
            last_update=datetime.now(),
            created_at=datetime.now()
        ),
    ]
    db_session.add_all(pois)
    db_session.commit()
    return pois


def test_root_endpoint(client):
    """Test root endpoint returns API info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "version" in data
    assert data["message"] == "POI API"


def test_health_endpoint_with_db(client, db_session):
    """Test /health endpoint with database connection."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "unhealthy"]
    assert "api" in data
    assert "database" in data


def test_get_pois_empty(client, db_session):
    """Test /pois endpoint with no data."""
    response = client.get("/pois")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["items"]) == 0
    assert data["limit"] == 50
    assert data["offset"] == 0


def test_get_pois_with_data(client, db_session, sample_pois):
    """Test /pois endpoint with sample data."""
    response = client.get("/pois")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2
    # Check first POI
    assert data["items"][0]["id"] in ["poi-1", "poi-2"]


def test_get_pois_pagination(client, db_session, sample_pois):
    """Test /pois endpoint pagination."""
    # First page
    response = client.get("/pois?limit=1&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["limit"] == 1
    assert data["offset"] == 0
    
    # Second page
    response = client.get("/pois?limit=1&offset=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["offset"] == 1


def test_get_pois_search(client, db_session, sample_pois):
    """Test /pois endpoint with search parameter."""
    response = client.get("/pois?search=Museum")
    assert response.status_code == 200
    data = response.json()
    # Should find at least one POI with "Museum" in label or description
    assert data["total"] >= 1
    assert any("Museum" in item.get("label", "") for item in data["items"])


def test_get_pois_filter_by_type(client, db_session, sample_pois):
    """Test /pois endpoint with type filter."""
    response = client.get("/pois?type=Museum")
    assert response.status_code == 200
    data = response.json()
    # All items should have type "Museum"
    for item in data["items"]:
        assert item.get("type") == "Museum"


def test_get_poi_by_id(client, db_session, sample_pois):
    """Test /pois/{poi_id} endpoint."""
    response = client.get("/pois/poi-1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "poi-1"
    assert data["label"] == "Test Museum"


def test_get_poi_by_id_not_found(client, db_session):
    """Test /pois/{poi_id} endpoint with non-existent ID."""
    response = client.get("/pois/non-existent")
    assert response.status_code == 404


def test_get_stats(client, db_session, sample_pois):
    """Test /stats endpoint."""
    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_pois" in data
    assert "pois_with_coordinates" in data
    assert "distinct_types" in data
    assert data["total_pois"] >= 2


def test_get_graph_summary_success(client):
    """Test /graph/summary endpoint with successful Neo4j connection."""
    mock_summary = {
        "poi_nodes": 10,
        "type_nodes": 5,
        "city_nodes": 3,
        "department_nodes": 2,
        "has_type_relationships": 10,
        "in_city_relationships": 8,
        "in_department_relationships": 7,
        "total_nodes": 20,
        "total_relationships": 25
    }
    
    with patch('src.pipelines.graph_loader.get_graph_summary', return_value=mock_summary):
        response = client.get("/graph/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["poi_nodes"] == 10
        assert data["total_nodes"] == 20
        assert data["total_relationships"] == 25


def test_get_graph_summary_connection_error(client):
    """Test /graph/summary endpoint when Neo4j is unavailable."""
    with patch('src.pipelines.graph_loader.get_graph_summary', side_effect=ConnectionError("Neo4j unavailable")):
        response = client.get("/graph/summary")
        assert response.status_code == 503
        data = response.json()
        assert "unavailable" in data["detail"].lower()


def test_post_graph_sync_success(client):
    """Test POST /graph/sync endpoint with successful sync."""
    mock_result = (100, 10, 5, 3)  # pois_loaded, types, cities, departments
    
    with patch('src.pipelines.graph_loader.load_pois_to_neo4j', return_value=mock_result):
        response = client.post("/graph/sync?batch_size=100")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["pois_loaded"] == 100
        assert data["types_created"] == 10


def test_post_graph_sync_connection_error(client):
    """Test POST /graph/sync endpoint when Neo4j is unavailable."""
    with patch('src.pipelines.graph_loader.load_pois_to_neo4j', side_effect=ConnectionError("Neo4j unavailable")):
        response = client.post("/graph/sync")
        assert response.status_code == 503
        data = response.json()
        assert "unavailable" in data["detail"].lower()


def test_post_graph_sync_with_token(client):
    """Test POST /graph/sync endpoint with authentication token."""
    import os
    os.environ["GRAPH_SYNC_TOKEN"] = "test-token-123"
    
    mock_result = (50, 5, 3, 2)
    
    try:
        with patch('src.pipelines.graph_loader.load_pois_to_neo4j', return_value=mock_result):
            # Without token - should fail
            response = client.post("/graph/sync")
            assert response.status_code == 401
            
            # With wrong token - should fail
            response = client.post("/graph/sync?sync_token=wrong-token")
            assert response.status_code == 401
            
            # With correct token - should succeed
            response = client.post("/graph/sync?sync_token=test-token-123")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
    finally:
        # Clean up
        if "GRAPH_SYNC_TOKEN" in os.environ:
            del os.environ["GRAPH_SYNC_TOKEN"]


def test_get_etl_status(client, db_session):
    """Test GET /etl/status endpoint."""
    response = client.get("/etl/status")
    # Should return 200 even if no runs exist (returns default values)
    assert response.status_code in [200, 404]


def test_get_itinerary_basic(client, db_session, sample_pois):
    """Test GET /itinerary endpoint with basic parameters."""
    response = client.get("/itinerary?lat=48.8566&lon=2.3522&days=2&radius_km=50")
    assert response.status_code == 200
    data = response.json()
    assert "start_location" in data
    assert "days" in data
    assert "itinerary" in data
    assert data["days"] == 2
    assert isinstance(data["itinerary"], list)


def test_get_itinerary_with_types(client, db_session, sample_pois):
    """Test GET /itinerary endpoint with type filter."""
    response = client.get("/itinerary?lat=48.8566&lon=2.3522&days=1&types=Museum,Restaurant")
    assert response.status_code == 200
    data = response.json()
    assert "types_filter" in data
    assert data["types_filter"] == ["Museum", "Restaurant"]


def test_get_itinerary_invalid_coordinates(client):
    """Test GET /itinerary endpoint with invalid coordinates."""
    # Invalid latitude
    response = client.get("/itinerary?lat=100&lon=2.3522&days=1")
    assert response.status_code == 422  # Validation error
    
    # Invalid longitude
    response = client.get("/itinerary?lat=48.8566&lon=200&days=1")
    assert response.status_code == 422


def test_get_itinerary_invalid_days(client):
    """Test GET /itinerary endpoint with invalid days."""
    # Days too high
    response = client.get("/itinerary?lat=48.8566&lon=2.3522&days=100")
    assert response.status_code == 422
    
    # Days too low
    response = client.get("/itinerary?lat=48.8566&lon=2.3522&days=0")
    assert response.status_code == 422

