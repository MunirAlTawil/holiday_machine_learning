# Data Sources

This document describes the data sources used in this project.

## DataTourisme API

### Overview

DataTourisme is a French tourism data platform that provides structured information about Points of Interest (POIs), accommodations, events, and other tourism-related entities across France. The API provides access to a comprehensive catalog of tourism data following semantic web standards (JSON-LD).

### Documentation Links

- **Official Documentation**: [https://www.datatourisme.fr/](https://www.datatourisme.fr/)
- **API Documentation**: [https://www.datatourisme.fr/api/](https://www.datatourisme.fr/api/)
- **Swagger/OpenAPI**: [https://api.datatourisme.fr/swagger](https://api.datatourisme.fr/swagger)

### Endpoint

**Base URL**: `https://api.datatourisme.fr`

**Endpoint**: `GET /v1/catalog`

**Full URL**: `https://api.datatourisme.fr/v1/catalog`

### Authentication

**Method**: API Key via HTTP Header

**Header Name**: `X-API-Key`

**Header Value**: Your DataTourisme API key (obtained from [DataTourisme portal](https://www.datatourisme.fr/api/))

**Note**: The API key must be set in the `.env` file as `DATATOURISME_API_KEY` and is never committed to version control.

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page_size` | integer | No | 50 | Number of items per page (max: 250) |
| `page` | integer | No | 1 | Page number (1-indexed) |
| `lang` | string | No | "fr,en" | Comma-separated language codes (e.g., "fr,en", "en") |
| `fields` | string | No | See below | Comma-separated list of fields to retrieve |
| `filters` | string | No | - | Filter parameters (optional) |

**Default Fields**: `uuid,label,type,uri,isLocatedAt,hasDescription,lastUpdate`

### Example Requests

#### cURL

```bash
curl -X GET "https://api.datatourisme.fr/v1/catalog?page_size=50&page=1&lang=fr,en&fields=uuid,label,type,uri,isLocatedAt,hasDescription,lastUpdate" \
  -H "X-API-Key: YOUR_API_KEY_HERE"
```

#### Python

```python
import requests

url = "https://api.datatourisme.fr/v1/catalog"
headers = {
    "X-API-Key": "YOUR_API_KEY_HERE"
}
params = {
    "page_size": 50,
    "page": 1,
    "lang": "fr,en",
    "fields": "uuid,label,type,uri,isLocatedAt,hasDescription,lastUpdate"
}

response = requests.get(url, headers=headers, params=params)
data = response.json()
```

#### Using Project Module

```python
from src.extract.fetch_datatourisme import fetch_catalog

# Fetch 50 items from page 1
data = fetch_catalog(page_size=50, page=1)
```

### Example Response

```json
{
  "objects": [
    {
      "uuid": "123e4567-e89b-12d3-a456-426614174000",
      "label": {
        "fr": "Musée du Louvre",
        "en": "Louvre Museum"
      },
      "type": "Museum",
      "uri": "https://www.datatourisme.fr/poi/123e4567-e89b-12d3-a456-426614174000",
      "isLocatedAt": {
        "geo": {
          "latitude": 48.8606,
          "longitude": 2.3376
        }
      },
      "hasDescription": {
        "fr": "Le musée du Louvre est le plus grand musée du monde...",
        "en": "The Louvre Museum is the world's largest museum..."
      },
      "lastUpdate": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 15000,
  "page": 1,
  "page_size": 50
}
```

### Response Structure

The API returns a JSON object with the following structure:

- **`objects`** (array): List of tourism objects (POIs, accommodations, events, etc.)
- **`total`** (integer): Total number of objects available
- **`page`** (integer): Current page number
- **`page_size`** (integer): Number of items per page

### Data Processing

The raw API response is saved to `data/raw/datatourisme_catalog_page{page}.json` and then processed into a flat CSV format saved at `data/processed/datatourisme_pois.csv`.

### CSV Output Columns

The following table describes the columns in the processed CSV file:

| Column | Type | Description | Source Field |
|--------|------|-------------|--------------|
| `uuid` | string | Unique identifier for the tourism object | `uuid` |
| `uri` | string | Uniform Resource Identifier (URL) of the object | `uri` |
| `label` | string | Name or title of the object (best available language) | `label` (extracted from multilingual object) |
| `type` | string | Type or category of the tourism object (e.g., Museum, Restaurant, Hotel) | `type` |
| `lat` | float | Latitude coordinate of the object's location | `isLocatedAt.geo.latitude` |
| `lon` | float | Longitude coordinate of the object's location | `isLocatedAt.geo.longitude` |
| `description` | string | Textual description of the object (best available language) | `hasDescription` (extracted from multilingual object) |
| `lastUpdate` | string | ISO 8601 timestamp of the last update to the object | `lastUpdate` |

### Notes

- **Rate Limiting**: The extraction script includes a 0.2 second delay between requests to respect API rate limits.
- **Multilingual Support**: The API supports multiple languages. The CSV extraction selects the best available label and description based on the requested languages.
- **Coordinate System**: Coordinates use WGS84 (EPSG:4326) standard (latitude/longitude in decimal degrees).
- **Data Freshness**: The `lastUpdate` field indicates when the object data was last modified in the source system.
- **Missing Data**: Some fields may be empty (null) if not available for a particular object. The extraction process handles missing data gracefully.

### Error Handling

The extraction script handles the following error scenarios:

- **401/403**: Invalid or missing API key
- **404**: Incorrect endpoint URL
- **Non-200 status**: Includes status code and response text in error message
- **Missing "objects" field**: Validates response structure before processing

---

## Adding New Data Sources

When adding a new data source to this project, please document:

1. **Overview**: Brief description of the data source
2. **Documentation Links**: Official docs, API documentation, Swagger/OpenAPI
3. **Endpoint Details**: Base URL, endpoint path, HTTP method
4. **Authentication**: Method and requirements
5. **Query Parameters**: All available parameters with descriptions
6. **Example Requests**: cURL and Python examples
7. **Response Structure**: Example response and schema
8. **Data Processing**: How the data is transformed
9. **Output Format**: Description of processed output (CSV columns, etc.)
10. **Notes**: Any important considerations, limitations, or best practices
