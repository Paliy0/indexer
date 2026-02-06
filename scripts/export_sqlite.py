#!/usr/bin/env python3
"""
Export SQLite database to JSON format for migration to PostgreSQL.

This script exports sites and pages data from the Phase 1 SQLite database
to a JSON file that can be imported into PostgreSQL.

Usage:
    python scripts/export_sqlite.py [--db-path PATH] [--output PATH]
"""

import sqlite3
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any


def export_sqlite_to_json(
    db_path: str = "./data/sites.db",
    output_path: str = "./data/migration_export.json"
) -> Dict[str, Any]:
    """
    Export all data from SQLite to JSON format.
    
    Args:
        db_path: Path to SQLite database
        output_path: Path to output JSON file
        
    Returns:
        Dictionary containing export statistics
    """
    # Check if database exists
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    
    # Connect to SQLite database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Export sites
    print(f"Exporting sites from {db_path}...")
    cursor.execute("SELECT * FROM sites ORDER BY id")
    sites_rows = cursor.fetchall()
    
    sites = []
    for row in sites_rows:
        site = {
            "id": row["id"],
            "url": row["url"],
            "domain": row["domain"],
            "status": row["status"],
            "page_count": row["page_count"],
            "last_scraped": row["last_scraped"],
            "created_at": row["created_at"]
        }
        sites.append(site)
    
    print(f"  Found {len(sites)} sites")
    
    # Export pages
    print("Exporting pages...")
    cursor.execute("SELECT * FROM pages ORDER BY id")
    pages_rows = cursor.fetchall()
    
    pages = []
    for row in pages_rows:
        page = {
            "id": row["id"],
            "site_id": row["site_id"],
            "url": row["url"],
            "title": row["title"],
            "content": row["content"],
            "created_at": row["created_at"]
        }
        pages.append(page)
    
    print(f"  Found {len(pages)} pages")
    
    conn.close()
    
    # Prepare export data
    export_data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_db": db_path,
        "version": "1.0",
        "sites": sites,
        "pages": pages,
        "statistics": {
            "total_sites": len(sites),
            "total_pages": len(pages),
            "sites_by_status": {}
        }
    }
    
    # Calculate statistics
    for site in sites:
        status = site["status"]
        export_data["statistics"]["sites_by_status"][status] = \
            export_data["statistics"]["sites_by_status"].get(status, 0) + 1
    
    # Write to JSON file
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"\nWriting to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    file_size = output_file.stat().st_size
    file_size_mb = file_size / (1024 * 1024)
    
    print(f"\n✓ Export complete!")
    print(f"  Output file: {output_path}")
    print(f"  File size: {file_size_mb:.2f} MB")
    print(f"  Sites exported: {len(sites)}")
    print(f"  Pages exported: {len(pages)}")
    print(f"  Sites by status: {export_data['statistics']['sites_by_status']}")
    
    return export_data["statistics"]


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Export SQLite database to JSON for PostgreSQL migration"
    )
    parser.add_argument(
        "--db-path",
        default="./data/sites.db",
        help="Path to SQLite database (default: ./data/sites.db)"
    )
    parser.add_argument(
        "--output",
        default="./data/migration_export.json",
        help="Path to output JSON file (default: ./data/migration_export.json)"
    )
    
    args = parser.parse_args()
    
    try:
        export_sqlite_to_json(args.db_path, args.output)
    except Exception as e:
        print(f"\n✗ Export failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
