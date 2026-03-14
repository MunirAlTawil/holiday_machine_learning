# Holiday Itinerary Recommendation System

Author: Muhammed Munir Al Tawil\
GitHub: MunirAlTawil\
Program: Data and Cloud Engineer -- DataScientest

------------------------------------------------------------------------

## Project Summary

This project implements a **tourism itinerary recommendation platform**
that helps travelers explore Points of Interest (POIs) and generate
travel routes based on location, duration of stay, and available
attractions.

The system integrates **data engineering pipelines, relational and graph
databases, APIs, and an interactive dashboard** to deliver a complete
tourism data exploration platform.

------------------------------------------------------------------------

## Problem Statement

Planning a trip often requires searching through many tourism platforms
to identify places to visit. Travelers must manually evaluate locations,
distances, and available time.

The goal of this project is to build a system capable of:

• Collecting tourism data automatically\
• Structuring the data for efficient exploration\
• Modeling relationships between tourism locations\
• Generating itinerary suggestions for travelers

------------------------------------------------------------------------

## Data Source

The dataset used in this project comes from:

**DataTourisme API**

This open dataset provides structured tourism information about
thousands of Points of Interest across France.

Each POI contains:

• Name\
• Description\
• Geographic coordinates\
• City and department\
• Tourism category\
• Metadata related to tourism activities

------------------------------------------------------------------------

## Data Engineering Pipeline

The project implements a complete **ETL pipeline**.

### Extract

Tourism data is collected automatically from the DataTourisme API.

### Transform

The transformation stage performs:

• Data cleaning\
• Extraction of tourism themes\
• Normalization of geographic data\
• Structuring POI metadata

### Load

Processed data is stored in a PostgreSQL relational database.

Main pipeline module:

src/pipelines/batch_etl.py

------------------------------------------------------------------------

## Data Modeling

### Relational Database

A PostgreSQL database is used to store structured tourism data.

The relational schema includes:

• POI information\
• ETL tracking metadata\
• source data management

Database schema and migrations are located in:

sql/

------------------------------------------------------------------------

### Graph Database

A Neo4j graph database is used to model relationships between tourism
entities.

Graph nodes:

• POI\
• City\
• Type\
• Department

Relationships:

• POI → HAS_TYPE → Type\
• POI → IN_CITY → City\
• POI → IN_DEPARTMENT → Department

Graph database allows efficient exploration of tourism relationships.

Graph loading module:

src/pipelines/graph_loader.py

------------------------------------------------------------------------

## API Layer

A REST API built with **FastAPI** exposes tourism data to external
services.

Example endpoints:

/health\
/pois\
/pois/geojson\
/stats\
/quality\
/graph/summary\
/graph/sync\
/etl/status\
/itinerary\
/itinerary/build

API implementation:

src/api/

------------------------------------------------------------------------

## Interactive Dashboard

An interactive dashboard built with **Streamlit** allows visual
exploration of tourism data.

Features:

• interactive maps\
• POI explorer\
• dataset statistics\
• itinerary generation\
• data quality insights

Dashboard location:

src/dashboard/app.py

------------------------------------------------------------------------

## Automation

The system includes automated data workflows to keep tourism data
updated.

Automation includes:

• scheduled ETL processes\
• graph synchronization\
• containerized services

------------------------------------------------------------------------

## Containerized Architecture

The entire platform is containerized using **Docker**.

Services include:

• FastAPI backend\
• Streamlit dashboard\
• PostgreSQL database\
• Neo4j graph database\
• Scheduler service

Deployment configuration:

docker-compose.yml

------------------------------------------------------------------------

## Testing

Testing is implemented using **pytest**.

Coverage includes:

• API endpoints\
• ETL pipeline\
• data transformation logic\
• graph database loading

Test suite location:

tests/

------------------------------------------------------------------------

## Architecture

The platform architecture integrates:

• Data ingestion pipelines\
• PostgreSQL relational storage\
• Neo4j graph database\
• FastAPI backend services\
• Streamlit visualization dashboard

Architecture documentation:

docs/

------------------------------------------------------------------------

## Future Improvements

Potential improvements include:

• machine learning based itinerary optimization\
• clustering tourism locations\
• recommendation systems based on user behavior\
• integration with tourism rating platforms

------------------------------------------------------------------------

## Conclusion

This project demonstrates how **data engineering techniques and modern
data architectures** can be combined to build a tourism recommendation
platform.

The integration of ETL pipelines, relational and graph databases, APIs,
and interactive dashboards provides a scalable foundation for tourism
data exploration and itinerary generation.
