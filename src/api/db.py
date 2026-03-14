"""
Database configuration module.
Creates SQLAlchemy engine and session factory using environment variables.
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Load environment variables from .env file
load_dotenv()

# Get database connection parameters from environment variables with defaults
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "holiday")
POSTGRES_USER = os.getenv("POSTGRES_USER", "holiday")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "holiday")

# Construct database URL
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Print safe connection info (without password)
print(f"DB host={POSTGRES_HOST} db={POSTGRES_DB} user={POSTGRES_USER} port={POSTGRES_PORT}")

# Create SQLAlchemy engine with pool_pre_ping for connection health checks
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for declarative models
Base = declarative_base()


def get_db():
    """
    Dependency function for FastAPI to get database session.
    Yields a database session and ensures it's closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

