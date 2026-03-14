#!/usr/bin/env python3
"""
Test script for Itinerary Builder endpoints.
Tests POST /itinerary/build and GET /itinerary/health.
"""
import requests
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# API base URL
API_BASE_URL = "http://localhost:8000"


def test_itinerary_health():
    """Test GET /itinerary/health endpoint."""
    print("=" * 60)
    print("Testing GET /itinerary/health")
    print("=" * 60)
    
    try:
        response = requests.get(f"{API_BASE_URL}/itinerary/health", timeout=5)
        response.raise_for_status()
        data = response.json()
        
        print("✅ Health check passed!")
        print(f"   PostgreSQL POIs: {data.get('postgres_pois', 0)}")
        print(f"   PostgreSQL Types: {data.get('postgres_types', 0)}")
        print(f"   Neo4j POIs: {data.get('neo4j_pois', 0)}")
        print(f"   Neo4j Types: {data.get('neo4j_types', 0)}")
        print(f"   Neo4j Available: {data.get('neo4j_available', False)}")
        
        return True
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False


def test_itinerary_build_basic():
    """Test POST /itinerary/build with basic parameters."""
    print("\n" + "=" * 60)
    print("Testing POST /itinerary/build (Basic)")
    print("=" * 60)
    
    payload = {
        "days": 3,
        "daily_limit": 5,
        "lat": 48.8566,  # Paris
        "lon": 2.3522,
        "radius_km": 30,
        "diversity": True
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/itinerary/build",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        print("✅ Itinerary build successful!")
        print(f"   Days: {len(data.get('itinerary', []))}")
        print(f"   Total POIs: {sum(day.get('total_pois', 0) for day in data.get('itinerary', []))}")
        print(f"   Diversity Mode: {data.get('meta', {}).get('diversity_mode', False)}")
        print(f"   Neo4j Used: {data.get('meta', {}).get('neo4j_used', False)}")
        
        # Show first day
        if data.get('itinerary'):
            first_day = data['itinerary'][0]
            print(f"\n   Day {first_day.get('day')} Preview:")
            print(f"      POIs: {first_day.get('total_pois', 0)}")
            print(f"      Types: {', '.join(first_day.get('types_visited', []))}")
        
        return True
    except requests.exceptions.HTTPError as e:
        print(f"❌ Itinerary build failed: {e}")
        try:
            error_detail = e.response.json().get("detail", str(e))
            print(f"   Detail: {error_detail}")
        except:
            pass
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_itinerary_build_with_types():
    """Test POST /itinerary/build with type filter."""
    print("\n" + "=" * 60)
    print("Testing POST /itinerary/build (With Types Filter)")
    print("=" * 60)
    
    payload = {
        "days": 2,
        "daily_limit": 4,
        "lat": 48.8566,
        "lon": 2.3522,
        "radius_km": 25,
        "types": ["Museum", "Restaurant"],
        "diversity": True
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/itinerary/build",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        print("✅ Itinerary build with types successful!")
        print(f"   Days: {len(data.get('itinerary', []))}")
        print(f"   Types Filter: {payload['types']}")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_itinerary_build_validation():
    """Test POST /itinerary/build with invalid parameters."""
    print("\n" + "=" * 60)
    print("Testing POST /itinerary/build (Validation)")
    print("=" * 60)
    
    # Test invalid days
    payload = {
        "days": 20,  # Too high (max 14)
        "daily_limit": 5,
        "lat": 48.8566,
        "lon": 2.3522,
        "radius_km": 30
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/itinerary/build",
            json=payload,
            timeout=10
        )
        if response.status_code == 400:
            print("✅ Validation working correctly (rejected invalid days)")
            return True
        else:
            print(f"⚠️ Expected 400, got {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Run all tests."""
    print("Itinerary Builder API Tests")
    print("=" * 60)
    print(f"API Base URL: {API_BASE_URL}\n")
    
    results = []
    
    # Test health endpoint
    results.append(("Health Check", test_itinerary_health()))
    
    # Test basic build
    results.append(("Basic Build", test_itinerary_build_basic()))
    
    # Test with types
    results.append(("Build with Types", test_itinerary_build_with_types()))
    
    # Test validation
    results.append(("Validation", test_itinerary_build_validation()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

