"""
Configuration module for loading environment variables and managing paths.
Uses pathlib for OS-independent path handling.
"""
from pathlib import Path
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Project root directory (parent of src/)
PROJECT_ROOT = Path(__file__).parent.parent

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# Source directories
SRC_DIR = PROJECT_ROOT / "src"
EXTRACT_DIR = SRC_DIR / "extract"
TRANSFORM_DIR = SRC_DIR / "transform"
LOAD_DIR = SRC_DIR / "load"

# Other directories
NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"
DOCS_DIR = PROJECT_ROOT / "docs"
TESTS_DIR = PROJECT_ROOT / "tests"

# API Configuration
BASE_URL = os.getenv("BASE_URL", "https://api.datatourisme.fr")
DATATOURISME_API_KEY = os.getenv("DATATOURISME_API_KEY", "")

# Exported paths for external use
RAW_DIR = RAW_DATA_DIR
PROCESSED_DIR = PROCESSED_DATA_DIR

# Legacy environment variables (for backward compatibility)
API_KEY = os.getenv("API_KEY", "")
API_BASE_URL = os.getenv("API_BASE_URL", "")

# Create directories if they don't exist
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

