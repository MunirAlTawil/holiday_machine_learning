#!/usr/bin/env python3
"""
CLI Entry Point for Graph Loader
==================================

Command-line interface for loading POI data into Neo4j.

Usage:
    python -m src.pipelines.run_graph_load
    python -m src.pipelines.run_graph_load --batch-size 50
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.pipelines.graph_loader import load_pois_to_neo4j, get_graph_summary

def main():
    """Main entry point for graph loader CLI."""
    parser = argparse.ArgumentParser(
        description="Load POI data from PostgreSQL into Neo4j graph database"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of POIs to process in each batch (default: 100)"
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show graph summary statistics after loading"
    )
    
    args = parser.parse_args()
    
    try:
        # Load POIs into Neo4j
        pois_loaded, types_created, cities_created, depts_created = load_pois_to_neo4j(
            batch_size=args.batch_size
        )
        
        print(f"\n✅ Graph load completed successfully!")
        print(f"   POIs loaded: {pois_loaded}")
        print(f"   Types created: {types_created}")
        print(f"   Cities created: {cities_created}")
        print(f"   Departments created: {depts_created}")
        
        # Show summary if requested
        if args.summary:
            print("\n📊 Graph Summary:")
            summary = get_graph_summary()
            for key, value in summary.items():
                print(f"   {key}: {value}")
        
        return 0
    
    except ConnectionError as e:
        print(f"❌ Connection error: {e}", file=sys.stderr)
        print("   Make sure Neo4j is running and accessible.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

