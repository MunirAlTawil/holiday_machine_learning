"""
Unit tests for the GeoJSON endpoint /pois/geojson.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from src.api.main import app, parse_bbox
from src.api.db import Base
from src.api.models import POI


# Create in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client with database dependency override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    # Override the database dependency
    from src.api.db import get_db
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture
def sample_pois(db_session):
    """Create sample POIs for testing."""
    pois = [
        POI(
            id="poi1",
            label="Eiffel Tower",
            description="Famous landmark in Paris",
            latitude=48.8584,
            longitude=2.2945,
            type="Monument",
            uri="https://example.com/eiffel",
            last_update=datetime(2024, 1, 1),
            source_id=1,
            created_at=datetime(2024, 1, 1)
        ),
        POI(
            id="poi2",
            label="Louvre Museum",
            description="Art museum in Paris",
            latitude=48.8606,
            longitude=2.3376,
            type="Museum",
            uri="https://example.com/louvre",
            last_update=datetime(2024, 1, 2),
            source_id=1,
            created_at=datetime(2024, 1, 2)
        ),
        POI(
            id="poi3",
            label="Notre-Dame",
            description="Cathedral in Paris",
            latitude=48.8530,
            longitude=2.3499,
            type="Monument",
            uri=None,
            last_update=datetime(2024, 1, 3),
            source_id=1,
            created_at=datetime(2024, 1, 3)
        ),
        POI(
            id="poi4",
            label="No Coordinates",
            description="POI without coordinates",
            latitude=None,
            longitude=None,
            type="Other",
            uri=None,
            last_update=None,
            source_id=1,
            created_at=datetime(2024, 1, 4)
        ),
    ]
    for poi in pois:
        db_session.add(poi)
    db_session.commit()
    return pois


def test_parse_bbox_valid():
    """Test parsing valid bbox string."""
    result = parse_bbox("2.0,48.0,3.0,49.0")
    assert result == (2.0, 48.0, 3.0, 49.0)


def test_parse_bbox_invalid_format():
    """Test parsing invalid bbox format."""
    with pytest.raises(Exception):  # HTTPException from FastAPI
        parse_bbox("2.0,48.0,3.0")  # Missing one value


def test_parse_bbox_invalid_bounds():
    """Test parsing bbox with invalid bounds."""
    with pytest.raises(Exception):
        parse_bbox("3.0,48.0,2.0,49.0")  # min_lon > max_lon


def test_parse_bbox_invalid_longitude():
    """Test parsing bbox with invalid longitude."""
    with pytest.raises(Exception):
        parse_bbox("200.0,48.0,201.0,49.0")  # Longitude > 180


def test_parse_bbox_invalid_latitude():
    """Test parsing bbox with invalid latitude."""
    with pytest.raises(Exception):
        parse_bbox("2.0,100.0,3.0,101.0")  # Latitude > 90


def test_geojson_endpoint_basic(client, sample_pois):
    """Test basic GeoJSON endpoint functionality."""
    response = client.get("/pois/geojson")
    assert response.status_code == 200
    
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert "features" in data
    # Should only return POIs with coordinates (3 out of 4)
    assert len(data["features"]) == 3


def test_geojson_endpoint_limit(client, sample_pois):
    """Test GeoJSON endpoint with limit parameter."""
    response = client.get("/pois/geojson?limit=2")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data["features"]) == 2


def test_geojson_endpoint_offset(client, sample_pois):
    """Test GeoJSON endpoint with offset parameter."""
    response = client.get("/pois/geojson?limit=1&offset=1")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data["features"]) == 1
    # Should get the second POI
    assert data["features"][0]["properties"]["id"] in ["poi2", "poi3"]


def test_geojson_endpoint_type_filter(client, sample_pois):
    """Test GeoJSON endpoint with type filter."""
    response = client.get("/pois/geojson?type=Monument")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data["features"]) == 2
    for feature in data["features"]:
        assert feature["properties"]["type"] == "Monument"


def test_geojson_endpoint_search_filter(client, sample_pois):
    """Test GeoJSON endpoint with search filter."""
    response = client.get("/pois/geojson?search=Paris")
    assert response.status_code == 200
    
    data = response.json()
    # Should find POIs with "Paris" in description
    assert len(data["features"]) >= 2
    for feature in data["features"]:
        assert "Paris" in feature["properties"]["description"] or "Paris" in feature["properties"]["label"]


def test_geojson_endpoint_bbox_filter(client, sample_pois):
    """Test GeoJSON endpoint with bbox filter."""
    # Bbox around Paris (roughly)
    response = client.get("/pois/geojson?bbox=2.2,48.8,2.4,48.9")
    assert response.status_code == 200
    
    data = response.json()
    # Should filter POIs within bbox
    assert len(data["features"]) >= 1
    for feature in data["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        assert 2.2 <= lon <= 2.4
        assert 48.8 <= lat <= 48.9


def test_geojson_endpoint_bbox_invalid(client, sample_pois):
    """Test GeoJSON endpoint with invalid bbox."""
    response = client.get("/pois/geojson?bbox=invalid")
    assert response.status_code == 400


def test_geojson_endpoint_limit_max(client, sample_pois):
    """Test GeoJSON endpoint with max limit."""
    response = client.get("/pois/geojson?limit=5000")
    assert response.status_code == 200


def test_geojson_endpoint_limit_exceeds_max(client, sample_pois):
    """Test GeoJSON endpoint with limit exceeding max."""
    response = client.get("/pois/geojson?limit=6000")
    assert response.status_code == 422  # Validation error


def test_geojson_feature_structure(client, sample_pois):
    """Test GeoJSON feature structure."""
    response = client.get("/pois/geojson?limit=1")
    assert response.status_code == 200
    
    data = response.json()
    feature = data["features"][0]
    
    # Check feature structure
    assert feature["type"] == "Feature"
    assert "geometry" in feature
    assert "properties" in feature
    
    # Check geometry
    assert feature["geometry"]["type"] == "Point"
    assert len(feature["geometry"]["coordinates"]) == 2
    assert isinstance(feature["geometry"]["coordinates"][0], float)  # longitude
    assert isinstance(feature["geometry"]["coordinates"][1], float)  # latitude
    
    # Check properties
    props = feature["properties"]
    assert "id" in props
    assert "label" in props
    assert "description" in props
    assert "type" in props
    assert "uri" in props
    assert "last_update" in props
    assert "source_id" in props
    assert "created_at" in props

