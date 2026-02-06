#!/usr/bin/env python3
"""
Import JSON export into PostgreSQL database.

This script imports sites and pages data from the JSON export file
into the PostgreSQL database using SQLAlchemy async ORM.

Usage:
    python scripts/import_to_postgres.py [--input PATH] [--dry-run]
"""

import asyncio
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

# Add app to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import Base, Site, Page
from app.config import get_settings


async def import_json_to_postgres(
    input_path: str = "./data/migration_export.json",
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Import JSON export data into PostgreSQL.
    
    Args:
        input_path: Path to JSON export file
        dry_run: If True, don't actually commit changes
        
    Returns:
        Dictionary containing import statistics
    """
    # Check if JSON file exists
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Export file not found: {input_path}")
    
    # Load JSON data
    print(f"Loading data from {input_path}...")
    with open(input_path, 'r', encoding='utf-8') as f:
        export_data = json.load(f)
    
    print(f"  Export version: {export_data.get('version')}")
    print(f"  Exported at: {export_data.get('exported_at')}")
    print(f"  Sites: {len(export_data['sites'])}")
    print(f"  Pages: {len(export_data['pages'])}")
    
    if dry_run:
        print("\n⚠ DRY RUN MODE - No changes will be committed")
    
    # Get database settings
    settings = get_settings()
    database_url = settings.database_url
    
    # Convert to async URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
    
    print(f"\nConnecting to PostgreSQL...")
    
    # Create async engine
    engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True
    )
    
    # Create async session factory
    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    stats = {
        "sites_imported": 0,
        "pages_imported": 0,
        "sites_skipped": 0,
        "pages_skipped": 0,
        "errors": []
    }
    
    async with async_session_factory() as session:
        try:
            # Import sites
            print("\nImporting sites...")
            site_id_mapping = {}  # Maps old IDs to new IDs
            
            for site_data in export_data["sites"]:
                try:
                    # Check if site already exists
                    result = await session.execute(
                        select(Site).where(Site.domain == site_data["domain"])
                    )
                    existing_site = result.scalars().first()
                    
                    if existing_site:
                        print(f"  Skipping site {site_data['domain']} (already exists)")
                        site_id_mapping[site_data["id"]] = existing_site.id
                        stats["sites_skipped"] += 1
                        continue
                    
                    # Parse timestamp
                    last_scraped = None
                    if site_data.get("last_scraped"):
                        try:
                            last_scraped = datetime.fromisoformat(
                                site_data["last_scraped"].replace("Z", "+00:00")
                            )
                        except (ValueError, AttributeError):
                            pass
                    
                    # Create new site
                    site = Site(
                        url=site_data["url"],
                        domain=site_data["domain"],
                        status=site_data["status"],
                        page_count=site_data["page_count"],
                        last_scraped=last_scraped,
                        config={}  # Initialize with empty config
                    )
                    session.add(site)
                    await session.flush()  # Get the new ID
                    
                    site_id_mapping[site_data["id"]] = site.id
                    stats["sites_imported"] += 1
                    print(f"  ✓ Imported site {site.domain} (ID: {site_data['id']} → {site.id})")
                    
                except Exception as e:
                    error_msg = f"Error importing site {site_data.get('domain')}: {e}"
                    print(f"  ✗ {error_msg}")
                    stats["errors"].append(error_msg)
            
            # Import pages
            print(f"\nImporting pages...")
            batch_size = 100
            pages_batch = []
            
            for i, page_data in enumerate(export_data["pages"]):
                try:
                    # Map old site_id to new site_id
                    old_site_id = page_data["site_id"]
                    if old_site_id not in site_id_mapping:
                        print(f"  ✗ Skipping page {page_data['url']} (site_id {old_site_id} not found)")
                        stats["pages_skipped"] += 1
                        continue
                    
                    new_site_id = site_id_mapping[old_site_id]
                    
                    # Create new page
                    page = Page(
                        site_id=new_site_id,
                        url=page_data["url"],
                        title=page_data.get("title"),
                        content=page_data.get("content"),
                        page_metadata={}  # Initialize with empty metadata
                    )
                    pages_batch.append(page)
                    
                    # Commit in batches
                    if len(pages_batch) >= batch_size:
                        session.add_all(pages_batch)
                        await session.flush()
                        stats["pages_imported"] += len(pages_batch)
                        print(f"  ✓ Imported batch of {len(pages_batch)} pages ({stats['pages_imported']} total)")
                        pages_batch = []
                    
                except Exception as e:
                    error_msg = f"Error importing page {page_data.get('url')}: {e}"
                    print(f"  ✗ {error_msg}")
                    stats["errors"].append(error_msg)
            
            # Import remaining pages
            if pages_batch:
                session.add_all(pages_batch)
                await session.flush()
                stats["pages_imported"] += len(pages_batch)
                print(f"  ✓ Imported final batch of {len(pages_batch)} pages ({stats['pages_imported']} total)")
            
            # Commit or rollback
            if dry_run:
                print("\n⚠ Rolling back (dry run mode)")
                await session.rollback()
            else:
                print("\nCommitting changes...")
                await session.commit()
                print("  ✓ Changes committed")
        
        except Exception as e:
            print(f"\n✗ Import failed: {e}")
            await session.rollback()
            raise
    
    await engine.dispose()
    
    # Print summary
    print(f"\n{'=' * 60}")
    print("IMPORT SUMMARY")
    print(f"{'=' * 60}")
    print(f"Sites imported: {stats['sites_imported']}")
    print(f"Sites skipped: {stats['sites_skipped']}")
    print(f"Pages imported: {stats['pages_imported']}")
    print(f"Pages skipped: {stats['pages_skipped']}")
    print(f"Errors: {len(stats['errors'])}")
    
    if stats["errors"]:
        print(f"\nErrors encountered:")
        for error in stats["errors"][:10]:  # Show first 10 errors
            print(f"  - {error}")
        if len(stats["errors"]) > 10:
            print(f"  ... and {len(stats['errors']) - 10} more errors")
    
    if dry_run:
        print(f"\n⚠ DRY RUN - No changes were committed to the database")
    else:
        print(f"\n✓ Import complete!")
    
    return stats


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Import JSON export into PostgreSQL database"
    )
    parser.add_argument(
        "--input",
        default="./data/migration_export.json",
        help="Path to JSON export file (default: ./data/migration_export.json)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run import without committing changes"
    )
    
    args = parser.parse_args()
    
    try:
        stats = asyncio.run(import_json_to_postgres(args.input, args.dry_run))
        
        # Return non-zero exit code if there were errors
        if stats["errors"]:
            return 1
        return 0
        
    except Exception as e:
        print(f"\n✗ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
