"""
Integration tests for transformation logic.
Tests coordinate extraction, last_update parsing, and invalid POI skipping.
"""
import pytest
from datetime import datetime
from src.pipelines.batch_etl import (
    extract_coordinates,
    extract_city,
    extract_department_code,
    extract_label,
    extract_description,
    extract_type,
    extract_theme_from_uri,
    parse_timestamp,
    transform_poi,
    transform_pois
)


class TestCoordinateExtraction:
    """Test coordinate extraction from various POI formats."""
    
    def test_extract_coordinates_from_schema_geo(self):
        """Test extraction from schema:geo with schema:latitude/longitude."""
        poi = {
            "isLocatedAt": [{
                "schema:geo": {
                    "schema:latitude": 48.8606,
                    "schema:longitude": 2.3376
                }
            }]
        }
        lat, lon = extract_coordinates(poi)
        assert lat == 48.8606
        assert lon == 2.3376
    
    def test_extract_coordinates_from_geo(self):
        """Test extraction from geo with latitude/longitude."""
        poi = {
            "isLocatedAt": [{
                "geo": {
                    "latitude": 48.8606,
                    "longitude": 2.3376
                }
            }]
        }
        lat, lon = extract_coordinates(poi)
        assert lat == 48.8606
        assert lon == 2.3376
    
    def test_extract_coordinates_from_coordinates_array(self):
        """Test extraction from coordinates array (GeoJSON format: [lon, lat])."""
        poi = {
            "isLocatedAt": [{
                "schema:geo": {
                    "schema:coordinates": [2.3376, 48.8606]  # [lon, lat]
                }
            }]
        }
        lat, lon = extract_coordinates(poi)
        assert lat == 48.8606
        assert lon == 2.3376
    
    def test_extract_coordinates_missing_location(self):
        """Test that missing isLocatedAt returns None."""
        poi = {}
        lat, lon = extract_coordinates(poi)
        assert lat is None
        assert lon is None
    
    def test_extract_coordinates_empty_location(self):
        """Test that empty isLocatedAt array returns None."""
        poi = {"isLocatedAt": []}
        lat, lon = extract_coordinates(poi)
        assert lat is None
        assert lon is None
    
    def test_extract_coordinates_invalid_format(self):
        """Test that invalid coordinate format returns None."""
        poi = {
            "isLocatedAt": [{
                "schema:geo": {
                    "schema:latitude": "invalid",
                    "schema:longitude": "invalid"
                }
            }]
        }
        lat, lon = extract_coordinates(poi)
        assert lat is None
        assert lon is None


class TestCityAndDepartmentExtraction:
    """Test city and department code extraction."""
    
    def test_extract_city_from_address(self):
        """Test city extraction from schema:address."""
        poi = {
            "isLocatedAt": [{
                "schema:address": {
                    "schema:addressLocality": "Paris"
                }
            }]
        }
        city = extract_city(poi)
        assert city == "Paris"
    
    def test_extract_department_code_from_postal_code(self):
        """Test department code extraction from postal code."""
        poi = {
            "isLocatedAt": [{
                "schema:address": {
                    "schema:postalCode": "75001"
                }
            }]
        }
        dept = extract_department_code(poi)
        assert dept == "75"
    
    def test_extract_department_code_invalid_postal_code(self):
        """Test that invalid postal code returns None."""
        poi = {
            "isLocatedAt": [{
                "schema:address": {
                    "schema:postalCode": "ABC"
                }
            }]
        }
        dept = extract_department_code(poi)
        assert dept is None


class TestLabelAndDescriptionExtraction:
    """Test label and description extraction."""
    
    def test_extract_label_from_dict_fr(self):
        """Test label extraction from dict with French."""
        poi = {"label": {"fr": "Musée du Louvre"}}
        label = extract_label(poi)
        assert label == "Musée du Louvre"
    
    def test_extract_label_from_dict_en(self):
        """Test label extraction from dict with English."""
        poi = {"label": {"en": "Louvre Museum"}}
        label = extract_label(poi)
        assert label == "Louvre Museum"
    
    def test_extract_label_from_string(self):
        """Test label extraction from string."""
        poi = {"label": "Louvre Museum"}
        label = extract_label(poi)
        assert label == "Louvre Museum"
    
    def test_extract_description_from_hasDescription(self):
        """Test description extraction from hasDescription."""
        poi = {
            "hasDescription": [{
                "shortDescription": {
                    "fr": "Un musée d'art"
                }
            }]
        }
        desc = extract_description(poi)
        assert desc == "Un musée d'art"


class TestTimestampParsing:
    """Test last_update timestamp parsing."""
    
    def test_parse_iso_timestamp(self):
        """Test parsing ISO format timestamp."""
        timestamp = parse_timestamp("2024-01-15T10:30:00Z")
        assert isinstance(timestamp, datetime)
        assert timestamp.year == 2024
        assert timestamp.month == 1
        assert timestamp.day == 15
    
    def test_parse_iso_timestamp_with_timezone(self):
        """Test parsing ISO format with timezone."""
        timestamp = parse_timestamp("2024-01-15T10:30:00+01:00")
        assert isinstance(timestamp, datetime)
    
    def test_parse_date_only(self):
        """Test parsing date-only format."""
        timestamp = parse_timestamp("2024-01-15")
        assert isinstance(timestamp, datetime)
        assert timestamp.year == 2024
        assert timestamp.month == 1
        assert timestamp.day == 15
    
    def test_parse_datetime_object(self):
        """Test parsing datetime object (should return as-is)."""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        timestamp = parse_timestamp(dt)
        assert timestamp == dt
    
    def test_parse_invalid_timestamp(self):
        """Test parsing invalid timestamp returns None."""
        timestamp = parse_timestamp("invalid-date")
        assert timestamp is None
    
    def test_parse_none_timestamp(self):
        """Test parsing None returns None."""
        timestamp = parse_timestamp(None)
        assert timestamp is None


class TestThemeExtraction:
    """Test theme extraction from URI."""
    
    def test_extract_theme_from_uri_with_restaurant(self):
        """Test extraction of 'restaurant' theme from URI."""
        uri = "https://data.datatourisme.fr/restaurant/123"
        theme = extract_theme_from_uri(uri)
        assert theme == "restaurant"
    
    def test_extract_theme_from_uri_with_museum(self):
        """Test extraction of 'museum' theme from URI."""
        uri = "https://data.datatourisme.fr/13/museum-abc"
        theme = extract_theme_from_uri(uri)
        assert theme == "museum"
    
    def test_extract_theme_from_uri_with_heritage(self):
        """Test extraction of 'heritage' theme from URI."""
        uri = "https://data.datatourisme.fr/heritage/site-123"
        theme = extract_theme_from_uri(uri)
        assert theme == "heritage"
    
    def test_extract_theme_from_uri_with_hotel(self):
        """Test extraction of 'hotel' theme from URI."""
        uri = "https://data.datatourisme.fr/23/hotel-paris-123"
        theme = extract_theme_from_uri(uri)
        assert theme == "hotel"
    
    def test_extract_theme_from_uri_no_theme(self):
        """Test URI with no theme segment returns None."""
        uri = "https://data.datatourisme.fr/13/2c29c0aa-bb2f-3dac-9f93-76f39f06bbc5"
        theme = extract_theme_from_uri(uri)
        assert theme is None
    
    def test_extract_theme_from_uri_empty(self):
        """Test empty URI returns None."""
        theme = extract_theme_from_uri("")
        assert theme is None
    
    def test_extract_theme_from_uri_none(self):
        """Test None URI returns None."""
        theme = extract_theme_from_uri(None)
        assert theme is None
    
    def test_extract_theme_from_uri_invalid(self):
        """Test invalid URI format returns None."""
        theme = extract_theme_from_uri("not-a-valid-uri")
        # Should handle gracefully and return None or a fallback
        assert theme is None or isinstance(theme, str)
    
    def test_extract_theme_from_uri_case_insensitive(self):
        """Test theme extraction is case-insensitive."""
        uri = "https://data.datatourisme.fr/RESTAURANT/123"
        theme = extract_theme_from_uri(uri)
        assert theme == "restaurant"  # Should be normalized to lowercase
    
    def test_extract_theme_from_uri_with_multiple_segments(self):
        """Test theme extraction when multiple segments exist."""
        uri = "https://data.datatourisme.fr/13/museum/cultural-site"
        theme = extract_theme_from_uri(uri)
        assert theme == "museum"  # Should find first matching theme


class TestPOITransformation:
    """Test complete POI transformation."""
    
    def test_transform_valid_poi(self):
        """Test transformation of valid POI."""
        poi = {
            "uuid": "test-poi-1",
            "label": {"fr": "Musée du Louvre"},
            "type": "Museum",
            "uri": "https://data.datatourisme.fr/museum/louvre",
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
                    "fr": "Un musée d'art"
                }
            }],
            "lastUpdate": "2024-01-15T10:30:00Z"
        }
        
        result = transform_poi(poi)
        
        assert result is not None
        assert result["id"] == "test-poi-1"
        assert result["label"] == "Musée du Louvre"
        assert result["type"] == "Museum"
        assert result["latitude"] == 48.8606
        assert result["longitude"] == 2.3376
        assert result["city"] == "Paris"
        assert result["department_code"] == "75"
        assert result["uri"] == "https://data.datatourisme.fr/museum/louvre"
        assert result["theme"] == "museum"  # Theme extracted from URI
        assert isinstance(result["last_update"], datetime)
        assert result["raw_json"] is not None
    
    def test_transform_poi_missing_coordinates(self):
        """Test that POI without coordinates is skipped."""
        poi = {
            "uuid": "test-poi-1",
            "label": "Test POI",
            "isLocatedAt": []  # No coordinates
        }
        
        result = transform_poi(poi)
        assert result is None
    
    def test_transform_poi_missing_uuid(self):
        """Test that POI without UUID is skipped."""
        poi = {
            "label": "Test POI",
            "isLocatedAt": [{
                "schema:geo": {
                    "schema:latitude": 48.8606,
                    "schema:longitude": 2.3376
                }
            }]
        }
        
        result = transform_poi(poi)
        assert result is None
    
    def test_transform_poi_invalid_coordinates(self):
        """Test that POI with invalid coordinates is skipped."""
        poi = {
            "uuid": "test-poi-1",
            "label": "Test POI",
            "isLocatedAt": [{
                "schema:geo": {
                    "schema:latitude": 100.0,  # Invalid (> 90)
                    "schema:longitude": 2.3376
                }
            }]
        }
        
        result = transform_poi(poi)
        assert result is None
    
    def test_transform_poi_invalid_longitude(self):
        """Test that POI with invalid longitude is skipped."""
        poi = {
            "uuid": "test-poi-1",
            "label": "Test POI",
            "isLocatedAt": [{
                "schema:geo": {
                    "schema:latitude": 48.8606,
                    "schema:longitude": 200.0  # Invalid (> 180)
                }
            }]
        }
        
        result = transform_poi(poi)
        assert result is None


class TestBatchTransformation:
    """Test batch transformation of multiple POIs."""
    
    def test_transform_pois_mixed_valid_invalid(self):
        """Test transformation of mixed valid and invalid POIs."""
        pois = [
            {
                "uuid": "valid-1",
                "label": "Valid POI 1",
                "isLocatedAt": [{
                    "schema:geo": {
                        "schema:latitude": 48.8606,
                        "schema:longitude": 2.3376
                    }
                }]
            },
            {
                "uuid": "invalid-1",
                "label": "Invalid POI",
                # Missing coordinates
            },
            {
                "uuid": "valid-2",
                "label": "Valid POI 2",
                "isLocatedAt": [{
                    "schema:geo": {
                        "schema:latitude": 48.8566,
                        "schema:longitude": 2.3522
                    }
                }]
            }
        ]
        
        transformed = transform_pois(pois)
        
        assert len(transformed) == 2
        assert transformed[0]["id"] == "valid-1"
        assert transformed[1]["id"] == "valid-2"
    
    def test_transform_pois_all_invalid(self):
        """Test transformation when all POIs are invalid."""
        pois = [
            {
                "uuid": "invalid-1",
                # Missing coordinates
            },
            {
                "uuid": "invalid-2",
                # Missing coordinates
            }
        ]
        
        transformed = transform_pois(pois)
        assert len(transformed) == 0

