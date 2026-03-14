"""
Streamlit dashboard for POI data visualization.
Multi-page dashboard with Overview, Charts, Data Quality, POI Explorer, and Map Explorer.
"""
import streamlit as st
import requests
import pandas as pd
import os
import logging
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from typing import Optional, Dict, Any, List
from functools import lru_cache

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API base URL - use environment variable or default
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
# In Docker, use service name
if os.getenv("DOCKER_ENV"):
    API_BASE_URL = "http://api:8000"


def fetch_stats() -> Optional[Dict[str, Any]]:
    """Fetch general statistics from /stats endpoint."""
    try:
        response = requests.get(f"{API_BASE_URL}/stats", timeout=10)
        response.raise_for_status()
        data = response.json()
        logger.info(f"Stats fetched successfully: {data}")
        return data
    except requests.exceptions.ConnectionError as e:
        st.error(f"❌ Cannot connect to API at {API_BASE_URL}. Please ensure the API server is running.")
        logger.error(f"Connection error: {str(e)}")
        return None
    except requests.exceptions.Timeout as e:
        st.error(f"⏱️ Request timeout. API at {API_BASE_URL} took too long to respond.")
        logger.error(f"Timeout error: {str(e)}")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"❌ HTTP Error {e.response.status_code}: {e.response.text}")
        logger.error(f"HTTP error: {str(e)}")
        return None
    except Exception as e:
        st.error(f"❌ Error fetching stats: {str(e)}")
        logger.error(f"Unexpected error: {str(e)}")
        return None


def fetch_types_chart(limit: int = 15) -> Optional[List[Dict[str, Any]]]:
    """Fetch type counts from /charts/types endpoint."""
    try:
        response = requests.get(f"{API_BASE_URL}/charts/types", params={"limit": limit}, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching types chart: {str(e)}")
        return None


def fetch_updates_chart(days: int = 30) -> Optional[List[Dict[str, Any]]]:
    """Fetch day counts from /charts/updates endpoint."""
    try:
        response = requests.get(f"{API_BASE_URL}/charts/updates", params={"days": days}, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching updates chart: {str(e)}")
        return None


def fetch_quality() -> Optional[Dict[str, Any]]:
    """Fetch data quality metrics from /quality endpoint."""
    try:
        response = requests.get(f"{API_BASE_URL}/quality", timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching quality metrics: {str(e)}")
        return None


def fetch_pois(limit: int = 100, offset: int = 0, type_filter: Optional[str] = None, 
               search: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetch POIs from /pois endpoint with filters."""
    try:
        params = {"limit": limit, "offset": offset}
        if type_filter:
            params["type"] = type_filter
        if search:
            params["search"] = search
        
        response = requests.get(f"{API_BASE_URL}/pois", params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching POIs: {str(e)}")
        return None


def check_api_health() -> Dict[str, Any]:
    """Check API health and database connectivity."""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            return response.json()
        return {"status": "unhealthy", "api": "error", "database": {"status": "unknown"}}
    except requests.exceptions.ConnectionError as e:
        logger.error(f"API connection error: {str(e)}")
        return {"status": "unreachable", "api": "error", "database": {"status": "unknown"}, "error": f"Cannot connect to {API_BASE_URL}"}
    except Exception as e:
        logger.error(f"API health check error: {str(e)}")
        return {"status": "unreachable", "api": "error", "database": {"status": "unknown"}, "error": str(e)}


def check_api_available() -> bool:
    """Simple check if API is reachable."""
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=5)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"API availability check failed: {str(e)}")
        return False


@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_geojson(
    limit: int = 1000,
    offset: int = 0,
    type_filter: Optional[str] = None,
    search: Optional[str] = None,
    bbox: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Fetch GeoJSON data from /pois/geojson endpoint."""
    try:
        params = {"limit": limit, "offset": offset}
        if type_filter:
            params["type"] = type_filter
        if search:
            params["search"] = search
        if bbox:
            params["bbox"] = bbox
        
        response = requests.get(f"{API_BASE_URL}/pois/geojson", params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching GeoJSON: {str(e)}")
        return None


@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_categories() -> Optional[List[Dict[str, Any]]]:
    """Fetch distinct POI types from /stats/categories endpoint."""
    try:
        response = requests.get(f"{API_BASE_URL}/stats/categories", timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching categories: {str(e)}")
        return None


def fetch_graph_summary() -> Optional[Dict[str, Any]]:
    """Fetch graph summary from /graph/summary endpoint."""
    try:
        response = requests.get(f"{API_BASE_URL}/graph/summary", timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 503:
            return None  # Neo4j unavailable
        st.error(f"Error fetching graph summary: {str(e)}")
        return None
    except Exception as e:
        st.error(f"Error fetching graph summary: {str(e)}")
        return None


# Page configuration
st.set_page_config(
    page_title="POI Analytics Dashboard",
    page_icon="📍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Sidebar navigation
st.sidebar.title("📍 POI Dashboard")
page = st.sidebar.selectbox(
    "Navigate",
    ["Overview", "Types Chart", "Updates Chart", "Data Quality", "POI Explorer", "Map Explorer", "Itinerary Builder", "Graph"]
)

# Check API connection and database status
health_status = check_api_health()

# Display health status in sidebar
st.sidebar.header("System Status")
if health_status.get("status") == "healthy":
    st.sidebar.success("✅ API: Healthy")
    db_status = health_status.get("database", {}).get("status", "unknown")
    if db_status == "connected":
        st.sidebar.success("✅ Database: Connected")
    else:
        st.sidebar.error(f"❌ Database: {db_status}")
        if health_status.get("database", {}).get("error"):
            st.sidebar.caption(health_status["database"]["error"])
elif health_status.get("status") == "unreachable":
    st.sidebar.error("❌ API: Unreachable")
    st.error(f"⚠️ Cannot connect to API at {API_BASE_URL}")
    st.info("Please ensure the FastAPI server is running.")
    if not os.getenv("DOCKER_ENV"):
        st.code("py -m uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000", language="bash")
        st.code("Or use: .\\scripts\\run_api.ps1", language="bash")
    st.stop()
else:
    st.sidebar.warning("⚠️ API: Unhealthy")
    db_status = health_status.get("database", {}).get("status", "unknown")
    st.sidebar.error(f"❌ Database: {db_status}")
    if health_status.get("database", {}).get("error"):
        st.sidebar.caption(health_status["database"]["error"])
    st.warning("API is responding but database connection failed. Some features may not work.")

# Overview Page
if page == "Overview":
    st.title("📊 Overview - Key Performance Indicators")
    
    # Debug info
    with st.expander("🔧 Debug Info", expanded=False):
        st.write(f"**API Base URL:** {API_BASE_URL}")
        st.write(f"**Docker Environment:** {os.getenv('DOCKER_ENV', 'Not set')}")
        
        # Test API connection
        try:
            test_response = requests.get(f"{API_BASE_URL}/", timeout=2)
            st.success(f"✅ API is reachable (Status: {test_response.status_code})")
        except Exception as e:
            st.error(f"❌ API connection test failed: {str(e)}")
    
    with st.spinner("Loading statistics..."):
        stats = fetch_stats()
    
    # Check if stats is None (error) vs empty dict (no data)
    if stats is None:
        st.warning("⚠️ No statistics data available.")
        st.info(f"""
        **Troubleshooting Steps:**
        1. Check if API is running: Visit {API_BASE_URL}/docs
        2. Check API health: Visit {API_BASE_URL}/health
        3. Check browser console for CORS errors (F12 → Console)
        4. Verify API_BASE_URL is correct: {API_BASE_URL}
        5. Try manually calling: {API_BASE_URL}/stats in your browser
        """)
        
        # Try to fetch raw response for debugging
        try:
            raw_response = requests.get(f"{API_BASE_URL}/stats", timeout=10)
            with st.expander("🔍 Raw API Response"):
                st.code(f"Status Code: {raw_response.status_code}")
                st.json(raw_response.json() if raw_response.status_code == 200 else raw_response.text)
        except Exception as e:
            st.error(f"Failed to fetch raw response: {str(e)}")
        
        st.stop()
    
    # Display KPIs
    st.header("Key Metrics")
    col1, col2, col3, col4 = st.columns(4)
    
    total_pois = stats.get("total_pois", 0)
    pois_with_coords = stats.get("pois_with_coordinates", 0)
    distinct_types = stats.get("distinct_types", 0)
    
    with col1:
        st.metric("Total POIs", total_pois)
    
    with col2:
        st.metric("With Coordinates", pois_with_coords)
    
    with col3:
        st.metric("Distinct Types", distinct_types)
    
    with col4:
        last_update = stats.get("last_update_max")
        if last_update:
            st.metric("Latest Update", pd.to_datetime(last_update).strftime("%Y-%m-%d"))
        else:
            st.metric("Latest Update", "N/A")
    
    # Show warning if all metrics are zero
    if total_pois == 0 and pois_with_coords == 0 and distinct_types == 0:
        st.warning("⚠️ All metrics are zero. The database may be empty. Run the ETL pipeline to load data.")
    
    # Additional info
    st.header("Update Range")
    col1, col2 = st.columns(2)
    
    with col1:
        min_update = stats.get("last_update_min")
        if min_update:
            st.info(f"**Earliest:** {pd.to_datetime(min_update).strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            st.info("**Earliest:** N/A")
    
    with col2:
        max_update = stats.get("last_update_max")
        if max_update:
            st.info(f"**Latest:** {pd.to_datetime(max_update).strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            st.info("**Latest:** N/A")

# Types Chart Page
elif page == "Types Chart":
    st.title("📈 POI Counts by Type")
    
    limit = st.sidebar.slider("Number of types to show", 5, 50, 15)
    
    with st.spinner("Loading type counts..."):
        type_data = fetch_types_chart(limit=limit)
    
    if type_data:
        df = pd.DataFrame(type_data)
        if not df.empty:
            st.bar_chart(df.set_index("type"))
            
            st.header("Data Table")
            st.dataframe(df, width='stretch', hide_index=True)
        else:
            st.info("No type data available.")
    else:
        st.warning("Failed to load type data.")

# Updates Chart Page
elif page == "Updates Chart":
    st.title("📅 POI Updates Over Time")
    
    days = st.sidebar.slider("Number of days", 7, 90, 30)
    
    with st.spinner("Loading update counts..."):
        update_data = fetch_updates_chart(days=days)
    
    if update_data:
        df = pd.DataFrame(update_data)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date")
            
            st.line_chart(df.set_index("date"))
            
            st.header("Data Table")
            st.dataframe(df, width='stretch', hide_index=True)
        else:
            st.info("No update data available.")
    else:
        st.warning("Failed to load update data.")

# Data Quality Page
elif page == "Data Quality":
    st.title("🔍 Data Quality Metrics")
    st.markdown("Missing/null fields analysis")
    
    with st.spinner("Loading quality metrics..."):
        quality = fetch_quality()
    
    if quality:
        # Quality endpoint returns a dict of {column_name: null_count}
        # Dynamically create DataFrame from whatever columns are returned
        if isinstance(quality, dict) and quality:
            # Convert to list of dicts for DataFrame
            quality_list = [
                {"Field": field_name.replace("_", " ").title(), "Missing Count": count}
                for field_name, count in quality.items()
            ]
            df = pd.DataFrame(quality_list)
            
            if not df.empty:
                st.header("Missing Fields Summary")
                st.bar_chart(df.set_index("Field"))
                
                st.header("Data Table")
                st.dataframe(df, width='stretch', hide_index=True)
                
                # Calculate total POIs for percentage
                stats = fetch_stats()
                total = stats.get("total_pois", 1) if stats else 1
                
                if total > 0:
                    st.header("Completeness Percentage")
                    df_pct = df.copy()
                    df_pct["Completeness %"] = ((total - df_pct["Missing Count"]) / total * 100).round(2)
                    st.dataframe(df_pct[["Field", "Completeness %"]], width='stretch', hide_index=True)
            else:
                st.info("No quality data available.")
        else:
            st.warning("Invalid quality data format received.")
    else:
        st.warning("Failed to load quality metrics.")

# POI Explorer Page
elif page == "POI Explorer":
    st.title("🔎 POI Explorer")
    st.markdown("Browse and search POIs with filters and pagination")
    
    # Filters in sidebar
    st.sidebar.header("Filters")
    search_term = st.sidebar.text_input("Search (label/description)", "")
    type_filter = st.sidebar.text_input("Filter by type", "")
    
    # Pagination
    st.sidebar.header("Pagination")
    page_size = st.sidebar.selectbox("Items per page", [25, 50, 100, 200], index=1)
    
    # Get current page from session state
    if "poi_page" not in st.session_state:
        st.session_state.poi_page = 0
    
    col1, col2, col3 = st.sidebar.columns(3)
    with col1:
        if st.button("◀ Prev"):
            if st.session_state.poi_page > 0:
                st.session_state.poi_page -= 1
    with col2:
        st.write(f"Page {st.session_state.poi_page + 1}")
    with col3:
        if st.button("Next ▶"):
            st.session_state.poi_page += 1
    
    offset = st.session_state.poi_page * page_size
    
    # Fetch POIs
    with st.spinner("Loading POIs..."):
        poi_data = fetch_pois(
            limit=page_size,
            offset=offset,
            type_filter=type_filter if type_filter else None,
            search=search_term if search_term else None
        )
    
    if poi_data:
        items = poi_data.get("items", [])
        total = poi_data.get("total", 0)
        
        st.info(f"Showing {len(items)} of {total} POIs")
        
        if items:
            df = pd.DataFrame(items)
            
            # Format datetime columns
            for col in ["last_update", "created_at"]:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime("%Y-%m-%d %H:%M:%S")
            
            # Select display columns
            display_cols = ["id", "label", "type", "city", "latitude", "longitude", "last_update"]
            available_cols = [col for col in display_cols if col in df.columns]
            
            st.dataframe(df[available_cols], width='stretch', hide_index=True)
            
            # Reset page if needed
            max_pages = (total + page_size - 1) // page_size
            if st.session_state.poi_page >= max_pages:
                st.session_state.poi_page = max(0, max_pages - 1)
        else:
            st.info("No POIs found matching the criteria.")
    else:
        st.warning("Failed to load POIs.")

# Map Explorer Page
elif page == "Map Explorer":
    st.title("🗺️ Map Explorer")
    st.markdown("Interactive map visualization of POIs")
    
    # Sidebar filters
    st.sidebar.header("Map Filters")
    
    # Fetch categories for type dropdown
    categories_data = fetch_categories()
    type_options = ["All"] + ([cat["category"] for cat in categories_data] if categories_data else [])
    selected_type = st.sidebar.selectbox("Filter by Type", type_options, index=0)
    
    search_input = st.sidebar.text_input("Search (label/description)", "")
    
    limit_slider = st.sidebar.slider("Max Items", 100, 5000, 1000, step=100)
    
    cluster_markers = st.sidebar.toggle("Cluster Markers", value=True)
    
    # Map bounds filter button
    st.sidebar.header("Map Bounds Filter")
    filter_by_bounds = st.sidebar.button("Filter by visible map")
    
    # Initialize session state for map bounds
    if "current_bbox" not in st.session_state:
        st.session_state.current_bbox = None
    
    # Prepare filters
    type_filter = None if selected_type == "All" else selected_type
    search_filter = search_input if search_input else None
    bbox_filter = st.session_state.current_bbox if filter_by_bounds and st.session_state.current_bbox else None
    
    # Fetch GeoJSON data
    with st.spinner("Loading POIs on map..."):
        geojson_data = fetch_geojson(
            limit=limit_slider,
            offset=0,
            type_filter=type_filter,
            search=search_filter,
            bbox=bbox_filter
        )
    
    if geojson_data:
        features = geojson_data.get("features", [])
        
        if features:
            # Calculate KPI metrics
            total_items = len(features)
            distinct_types = len(set(
                f.get("properties", {}).get("type") 
                for f in features 
                if f.get("properties", {}).get("type")
            ))
            
            # Display KPIs
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Items Shown", total_items)
            with col2:
                st.metric("Distinct Types", distinct_types)
            
            # Calculate map center and bounds from data
            lats = [f["geometry"]["coordinates"][1] for f in features]
            lons = [f["geometry"]["coordinates"][0] for f in features]
            
            if lats and lons:
                center_lat = sum(lats) / len(lats)
                center_lon = sum(lons) / len(lons)
                
                # Create map
                m = folium.Map(
                    location=[center_lat, center_lon],
                    zoom_start=6,
                    tiles="OpenStreetMap"
                )
                
                # Add markers
                if cluster_markers:
                    marker_cluster = MarkerCluster().add_to(m)
                    marker_group = marker_cluster
                else:
                    marker_group = m
                
                for feature in features:
                    coords = feature["geometry"]["coordinates"]
                    lon, lat = coords[0], coords[1]
                    props = feature.get("properties", {})
                    
                    # Safe text field extraction with null handling
                    safe_label = (props.get("label") or "").strip()
                    safe_desc = (props.get("description") or "").strip()
                    safe_type = (props.get("type") or "N/A").strip()
                    safe_uri = (props.get("uri") or "").strip()
                    safe_last_update = props.get("last_update") or "N/A"
                    
                    # Fallback if both label and description are empty
                    if not safe_label and not safe_desc:
                        safe_label = "No description available"
                    
                    # Truncate description safely
                    desc_truncated = (safe_desc[:200] + "…") if len(safe_desc) > 200 else safe_desc
                    
                    # Format popup HTML with safe variables
                    popup_html = f"""
                    <div style="width: 250px;">
                        <h4 style="margin: 0 0 10px 0; font-weight: bold;">{safe_label}</h4>
                        <p style="margin: 5px 0;"><strong>Type:</strong> {safe_type}</p>
                        <p style="margin: 5px 0;"><strong>Updated:</strong> {safe_last_update}</p>
                        {f'<p style="margin: 5px 0;"><strong>Description:</strong> {desc_truncated}</p>' if safe_desc else ''}
                        {f'<p style="margin: 5px 0;"><a href="{safe_uri}" target="_blank">View Details</a></p>' if safe_uri else ''}
                    </div>
                    """
                    
                    popup = folium.Popup(popup_html, max_width=300)
                    folium.Marker(
                        location=[lat, lon],
                        popup=popup,
                        tooltip=safe_label or "POI"
                    ).add_to(marker_group)
                
                # Display map and get bounds
                map_data = st_folium(m, width='stretch', height=600, returned_objects=["bounds"])
                
                # Store current map bounds in session state
                if map_data.get("bounds"):
                    bounds = map_data["bounds"]
                    if bounds:
                        south_west = bounds.get("_southWest", {})
                        north_east = bounds.get("_northEast", {})
                        
                        if south_west and north_east:
                            min_lon = south_west.get("lng")
                            min_lat = south_west.get("lat")
                            max_lon = north_east.get("lng")
                            max_lat = north_east.get("lat")
                            
                            if all(x is not None for x in [min_lon, min_lat, max_lon, max_lat]):
                                st.session_state.current_bbox = f"{min_lon},{min_lat},{max_lon},{max_lat}"
                
                # Handle map bounds filter button click
                if filter_by_bounds and st.session_state.current_bbox:
                    bbox_str = st.session_state.current_bbox
                    
                    # Fetch filtered data
                    with st.spinner("Filtering by map bounds..."):
                        filtered_geojson = fetch_geojson(
                            limit=limit_slider,
                            offset=0,
                            type_filter=type_filter,
                            search=search_filter,
                            bbox=bbox_str
                        )
                    
                    if filtered_geojson:
                        filtered_features = filtered_geojson.get("features", [])
                        st.success(f"✅ Showing {len(filtered_features)} POIs within visible map area")
                        
                        # Recalculate center for filtered data
                        if filtered_features:
                            filtered_lats = [f["geometry"]["coordinates"][1] for f in filtered_features]
                            filtered_lons = [f["geometry"]["coordinates"][0] for f in filtered_features]
                            filtered_center_lat = sum(filtered_lats) / len(filtered_lats)
                            filtered_center_lon = sum(filtered_lons) / len(filtered_lons)
                        else:
                            filtered_center_lat = center_lat
                            filtered_center_lon = center_lon
                        
                        # Update map with filtered data
                        m_filtered = folium.Map(
                            location=[filtered_center_lat, filtered_center_lon],
                            zoom_start=8,
                            tiles="OpenStreetMap"
                        )
                        
                        if cluster_markers:
                            marker_cluster_filtered = MarkerCluster().add_to(m_filtered)
                            marker_group_filtered = marker_cluster_filtered
                        else:
                            marker_group_filtered = m_filtered
                        
                        for feature in filtered_features:
                            coords = feature["geometry"]["coordinates"]
                            lon, lat = coords[0], coords[1]
                            props = feature.get("properties", {})
                            
                            # Safe text field extraction with null handling
                            safe_label = (props.get("label") or "").strip()
                            safe_desc = (props.get("description") or "").strip()
                            safe_type = (props.get("type") or "N/A").strip()
                            safe_uri = (props.get("uri") or "").strip()
                            safe_last_update = props.get("last_update") or "N/A"
                            
                            # Fallback if both label and description are empty
                            if not safe_label and not safe_desc:
                                safe_label = "No description available"
                            
                            # Truncate description safely
                            desc_truncated = (safe_desc[:200] + "…") if len(safe_desc) > 200 else safe_desc
                            
                            # Format popup HTML with safe variables
                            popup_html = f"""
                            <div style="width: 250px;">
                                <h4 style="margin: 0 0 10px 0; font-weight: bold;">{safe_label}</h4>
                                <p style="margin: 5px 0;"><strong>Type:</strong> {safe_type}</p>
                                <p style="margin: 5px 0;"><strong>Updated:</strong> {safe_last_update}</p>
                                {f'<p style="margin: 5px 0;"><strong>Description:</strong> {desc_truncated}</p>' if safe_desc else ''}
                                {f'<p style="margin: 5px 0;"><a href="{safe_uri}" target="_blank">View Details</a></p>' if safe_uri else ''}
                            </div>
                            """
                            
                            popup = folium.Popup(popup_html, max_width=300)
                            folium.Marker(
                                location=[lat, lon],
                                popup=popup,
                                tooltip=safe_label or "POI"
                            ).add_to(marker_group_filtered)
                        
                        st_folium(m_filtered, width='stretch', height=600)
            else:
                st.warning("No valid coordinates found in GeoJSON data.")
        else:
            st.info("No POIs found matching the criteria.")
    else:
        st.error("⚠️ Failed to load GeoJSON data from API. Please check:")
        st.markdown("""
        - API server is running
        - Database connection is healthy
        - GeoJSON endpoint `/pois/geojson` is accessible
        
        The dashboard will continue to function, but the map cannot be displayed.
        """)

# Itinerary Builder Page
elif page == "Itinerary Builder":
    st.title("🗺️ Itinerary Builder")
    st.markdown("Generate a personalized day-by-day itinerary using **HYBRID approach** (PostgreSQL + Neo4j).")
    
    # Health check
    try:
        health_response = requests.get(f"{API_BASE_URL}/itinerary/health", timeout=5)
        if health_response.status_code == 200:
            health_data = health_response.json()
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("PostgreSQL POIs", health_data.get("postgres_pois", 0))
            with col2:
                st.metric("Neo4j POIs", health_data.get("neo4j_pois", 0))
            with col3:
                neo4j_status = "✅ Available" if health_data.get("neo4j_available") else "⚠️ Unavailable"
                st.metric("Neo4j Status", neo4j_status)
    except Exception:
        pass
    
    # Form inputs
    st.header("📍 Starting Location")
    col1, col2 = st.columns(2)
    with col1:
        start_lat = st.number_input(
            "Latitude",
            min_value=-90.0,
            max_value=90.0,
            value=48.8566,  # Paris default
            step=0.0001,
            format="%.4f",
            help="Starting latitude (e.g., 48.8566 for Paris)"
        )
    with col2:
        start_lon = st.number_input(
            "Longitude",
            min_value=-180.0,
            max_value=180.0,
            value=2.3522,  # Paris default
            step=0.0001,
            format="%.4f",
            help="Starting longitude (e.g., 2.3522 for Paris)"
        )
    
    st.header("📅 Trip Details")
    col1, col2, col3 = st.columns(3)
    with col1:
        days = st.number_input(
            "Number of Days",
            min_value=1,
            max_value=14,
            value=3,
            help="How many days is your trip? (1-14)"
        )
    with col2:
        radius_km = st.number_input(
            "Search Radius (km)",
            min_value=1.0,
            max_value=50.0,
            value=30.0,
            step=1.0,
            help="Maximum distance from starting point (1-50 km)"
        )
    with col3:
        max_pois_per_day = st.number_input(
            "Max POIs per Day",
            min_value=1,
            max_value=10,
            value=5,
            help="Maximum number of POIs per day (default: 5)"
        )
    
    st.header("🎯 Preferences")
    
    # Multi-select POI types
    try:
        categories = fetch_categories()
        if categories:
            type_options = [cat.get("category", "") for cat in categories if cat.get("category")]
            selected_types = st.multiselect(
                "POI Types (optional)",
                options=type_options,
                help="Select POI types to filter. Leave empty to include all types."
            )
        else:
            # Fallback to text input
            types_input = st.text_input(
                "POI Types (optional)",
                placeholder="Museum, Restaurant, Hotel (comma-separated)",
                help="Filter by specific POI types. Leave empty to include all types."
            )
            selected_types = [t.strip() for t in types_input.split(",") if t.strip()] if types_input else []
    except Exception:
        types_input = st.text_input(
            "POI Types (optional)",
            placeholder="Museum, Restaurant, Hotel (comma-separated)",
            help="Filter by specific POI types. Leave empty to include all types."
        )
        selected_types = [t.strip() for t in types_input.split(",") if t.strip()] if types_input else []
    
    # Explanation text
    st.info("""
    **Selection Logic:** The hybrid approach uses:
    - **PostgreSQL**: Finds POIs within radius using Haversine distance calculation
    - **Neo4j**: Optimizes type diversity across days using graph relationships (POI)-[:HAS_TYPE]->(Type)
    - **Scoring**: `score = distance_weight * (1 / (1 + distance_km)) + type_diversity_bonus`
    """)
    
    # Initialize session state for itinerary results
    if "itinerary_result" not in st.session_state:
        st.session_state.itinerary_result = None
    if "itinerary_error" not in st.session_state:
        st.session_state.itinerary_error = None
    
    # Use form to prevent automatic rerun
    with st.form("itinerary_form", clear_on_submit=False):
        # Generate button inside form
        col1, col2 = st.columns([1, 4])
        with col1:
            submitted = st.form_submit_button("🚀 Generate Itinerary", type="primary", use_container_width=True)
        with col2:
            if st.session_state.itinerary_result:
                clear_clicked = st.form_submit_button("🗑️ Clear Results", use_container_width=True)
                if clear_clicked:
                    st.session_state.itinerary_result = None
                    st.session_state.itinerary_error = None
                    st.rerun()
    
    # Generate itinerary when form is submitted
    if submitted:
        st.session_state.itinerary_error = None
        
        with st.spinner("⏳ Generating itinerary using HYBRID approach... Please wait."):
            try:
                # Prepare request payload (matching exact specification)
                payload = {
                    "lat": start_lat,
                    "lon": start_lon,
                    "days": days,
                    "radius_km": radius_km,
                    "max_pois_per_day": max_pois_per_day
                }
                if selected_types:
                    payload["types"] = selected_types
                
                logger.info(f"Calling API: {API_BASE_URL}/itinerary/build with payload: {payload}")
                
                # Call POST endpoint
                response = requests.post(
                    f"{API_BASE_URL}/itinerary/build",
                    json=payload,
                    timeout=30
                )
                logger.info(f"API Response Status: {response.status_code}")
                
                response.raise_for_status()
                result = response.json()
                logger.info(f"API Response: {result}")
                
                # Save result to session state
                st.session_state.itinerary_result = result
                st.session_state.itinerary_error = None
                
                # Force rerun to show results
                st.rerun()
            
            except requests.exceptions.HTTPError as e:
                error_detail = ""
                try:
                    error_detail = e.response.json().get("detail", str(e))
                    logger.error(f"HTTP Error: {error_detail}")
                except:
                    error_detail = str(e)
                    logger.error(f"HTTP Error (no JSON): {error_detail}")
                
                st.session_state.itinerary_error = {
                    "message": f"Error generating itinerary: {error_detail}",
                    "status_code": e.response.status_code if hasattr(e, 'response') else None
                }
                st.rerun()
            except Exception as e:
                logger.error(f"Exception: {str(e)}")
                st.session_state.itinerary_error = {
                    "message": f"Error: {str(e)}",
                    "status_code": None
                }
                st.rerun()
    
    # Display error if any (persists across reruns)
    if st.session_state.itinerary_error:
        error = st.session_state.itinerary_error
        st.error(error["message"])
        if error.get("status_code") == 400:
            st.info("Please check your input parameters (days: 1-14, daily_limit: 3-10, radius_km: 1-50).")
        elif error.get("status_code") == 500:
            st.error("Server error. Please check the API logs.")
        else:
            st.info("Make sure the API is running and accessible.")
    
    # Display results if available (persists across reruns)
    if st.session_state.itinerary_result:
        result = st.session_state.itinerary_result
        
        # Extract data from new format
        summary = result.get("summary", {})
        days_data = result.get("days", [])
        data_sources = result.get("data_sources", {})
        
        # Display results
        total_pois = sum(len(day.get("pois", [])) for day in days_data)
        st.success(f"✅ Generated itinerary with {total_pois} POIs across {len(days_data)} days!")
        
        # Show data sources
        st.info(f"""
        **Data Sources Used:**
        - PostgreSQL: {'✅' if data_sources.get('postgres') else '❌'}
        - Neo4j: {'✅' if data_sources.get('neo4j') else '❌'}
        """)
        
        # Summary metrics
        st.header("📊 Itinerary Summary")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Days", summary.get("days", days))
        with col2:
            st.metric("Total POIs Selected", summary.get("total_pois_selected", total_pois))
        with col3:
            st.metric("POIs Found", summary.get("total_pois_found", 0))
        with col4:
            st.metric("Query Time", f"{summary.get('query_time_seconds', 0):.2f}s")
        
        # Map
        st.header("🗺️ Itinerary Map")
        if days_data:
            # Create map centered on start location
            start_loc = summary.get("start_location", {})
            map_lat = start_loc.get("lat", start_lat)
            map_lon = start_loc.get("lon", start_lon)
            
            m = folium.Map(
                location=[map_lat, map_lon],
                zoom_start=12,
                tiles='OpenStreetMap'
            )
            
            # Add start marker
            folium.Marker(
                [map_lat, map_lon],
                popup="Start Location",
                icon=folium.Icon(color='green', icon='home', prefix='fa')
            ).add_to(m)
            
            # Add POIs for each day with different colors
            colors = ['red', 'blue', 'purple', 'orange', 'darkred', 'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue']
            
            for day_info in days_data:
                day_num = day_info.get("day", 1)
                color = colors[(day_num - 1) % len(colors)]
                
                pois = day_info.get("pois", [])
                for poi in pois:
                    folium.Marker(
                        [poi['lat'], poi['lon']],
                        popup=f"Day {day_num}: {poi.get('label', 'POI')}",
                        tooltip=f"Day {day_num}: {poi.get('label', poi['id'])}",
                        icon=folium.Icon(color=color, icon='map-marker', prefix='fa')
                    ).add_to(m)
            
            # Display map
            st_folium(m, width=1200, height=600)
        
        # Day-by-day itinerary table
        st.header("📅 Day-by-Day Itinerary")
        if days_data:
            # Create table data
            table_data = []
            for day_info in days_data:
                day_num = day_info.get("day", 1)
                pois = day_info.get("pois", [])
                route_hint = day_info.get("route_hint", "")
                
                for idx, poi in enumerate(pois, 1):
                    table_data.append({
                        "Day": day_num,
                        "POI #": idx,
                        "Label": poi.get("label", poi.get("id", "N/A")),
                        "Type": poi.get("type", "N/A"),
                        "Latitude": f"{poi.get('lat', 0):.4f}",
                        "Longitude": f"{poi.get('lon', 0):.4f}",
                        "Route Hint": route_hint if idx == 1 else ""
                    })
            
            if table_data:
                df = pd.DataFrame(table_data)
                st.dataframe(df, width='stretch', hide_index=True)
            
            # Detailed view with day selector
            st.subheader("Detailed View")
            selected_day = st.selectbox(
                "Select Day to View Details",
                options=[f"Day {d.get('day', 1)}" for d in days_data],
                index=0
            )
            selected_day_num = int(selected_day.split()[1])
            
            for day_info in days_data:
                if day_info.get("day") == selected_day_num:
                    st.markdown(f"### Day {day_info['day']}")
                    st.caption(day_info.get("route_hint", ""))
                    
                    pois = day_info.get("pois", [])
                    for idx, poi in enumerate(pois, 1):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.markdown(f"**{idx}. {poi.get('label', poi.get('id', 'POI'))}**")
                            if poi.get("type"):
                                st.badge(poi["type"])
                            st.caption(f"📍 Coordinates: {poi.get('lat', 0):.4f}, {poi.get('lon', 0):.4f}")
                        with col2:
                            if poi.get("uri"):
                                st.link_button("🔗 View", poi["uri"])
        else:
            st.info("No itinerary generated. Try adjusting your search parameters (larger radius, more days, or different location).")

# Graph Page
elif page == "Graph":
    st.title("🕸️ Graph Database (Neo4j)")
    st.markdown("Neo4j graph database statistics and model information")
    
    with st.spinner("Loading graph summary..."):
        graph_summary = fetch_graph_summary()
    
    if graph_summary:
        st.header("Graph Statistics")
        
        # Display metrics in columns
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("POI Nodes", graph_summary.get("poi_nodes", 0))
        
        with col2:
            st.metric("Type Nodes", graph_summary.get("type_nodes", 0))
        
        with col3:
            st.metric("City Nodes", graph_summary.get("city_nodes", 0))
        
        with col4:
            st.metric("Department Nodes", graph_summary.get("department_nodes", 0))
        
        # Relationship metrics
        st.header("Relationships")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("HAS_TYPE", graph_summary.get("has_type_relationships", 0))
        
        with col2:
            st.metric("IN_CITY", graph_summary.get("in_city_relationships", 0))
        
        with col3:
            st.metric("IN_DEPARTMENT", graph_summary.get("in_department_relationships", 0))
        
        # Totals
        st.header("Totals")
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Total Nodes", graph_summary.get("total_nodes", 0))
        
        with col2:
            st.metric("Total Relationships", graph_summary.get("total_relationships", 0))
        
        # Graph Model Explanation
        st.header("Graph Model")
        st.info("""
        The Neo4j graph database models POI data with the following structure:
        
        **Nodes:**
        - `POI`: Points of Interest with properties (id, label, type, latitude, longitude, uri, last_update)
        - `Type`: POI types (e.g., Museum, Restaurant, Hotel)
        - `City`: Cities where POIs are located (optional)
        - `Department`: French departments where POIs are located (optional)
        
        **Relationships:**
        - `(:POI)-[:HAS_TYPE]->(:Type)`: Links POIs to their types
        - `(:POI)-[:IN_CITY]->(:City)`: Links POIs to cities (if city data available)
        - `(:POI)-[:IN_DEPARTMENT]->(:Department)`: Links POIs to departments (if department_code available)
        
        **Why Graph Database?**
        Graph databases excel at relationship queries and enable powerful graph analytics:
        - Find all POIs of a specific type in a city
        - Discover POI clusters by geographic relationships
        - Analyze type distribution across departments
        - Perform graph traversals for recommendation systems
        
        For detailed documentation, see: [Graph Model Documentation](docs/GRAPH_MODEL.md)
        """)
        
        # Data table
        st.header("Detailed Statistics")
        summary_df = pd.DataFrame([
            {"Metric": "POI Nodes", "Count": graph_summary.get("poi_nodes", 0)},
            {"Metric": "Type Nodes", "Count": graph_summary.get("type_nodes", 0)},
            {"Metric": "City Nodes", "Count": graph_summary.get("city_nodes", 0)},
            {"Metric": "Department Nodes", "Count": graph_summary.get("department_nodes", 0)},
            {"Metric": "HAS_TYPE Relationships", "Count": graph_summary.get("has_type_relationships", 0)},
            {"Metric": "IN_CITY Relationships", "Count": graph_summary.get("in_city_relationships", 0)},
            {"Metric": "IN_DEPARTMENT Relationships", "Count": graph_summary.get("in_department_relationships", 0)},
            {"Metric": "Total Nodes", "Count": graph_summary.get("total_nodes", 0)},
            {"Metric": "Total Relationships", "Count": graph_summary.get("total_relationships", 0)},
        ])
        st.dataframe(summary_df, width='stretch', hide_index=True)
    
    else:
        st.warning("⚠️ Neo4j graph database is unavailable.")
        st.info("""
        The graph database may not be running or may not have been loaded yet.
        
        **To load data into Neo4j:**
        1. Ensure Neo4j service is running: `docker compose ps neo4j`
        2. Run the graph loader: `docker compose exec holiday_scheduler python -m src.pipelines.run_graph_load`
        3. Or wait for the scheduled hourly ETL to complete (it automatically loads to Neo4j)
        
        **Access Neo4j Browser:**
        - URL: http://localhost:7474
        - Username: neo4j
        - Password: (check your .env file or docker-compose.yml)
        """)
