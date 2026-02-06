#!/usr/bin/env python3
"""
Index existing PostgreSQL pages into Meilisearch.

This script reads pages from PostgreSQL and indexes them into Meilisearch
for fast, typo-tolerant search. Supports incremental indexing by tracking
the last indexed timestamp.

Usage:
    python scripts/index_meilisearch.py [--batch-size SIZE] [--full] [--dry-run]
"""

import asyncio
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func

# Add app to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import Site, Page
from app.config import get_settings
from app.meilisearch_engine import MeiliSearchEngine


async def index_pages_to_meilisearch(
    batch_size: int = 100,
    full_reindex: bool = False,
    dry_run: bool = False,
    site_id: int = None
) -> Dict[str, Any]:
    """
    Index pages from PostgreSQL into Meilisearch.
    
    Args:
        batch_size: Number of pages to index per batch
        full_reindex: If True, reindex all pages. If False, only index new/updated pages
        dry_run: If True, don't actually index pages
        site_id: If provided, only index pages for this site
        
    Returns:
        Dictionary containing indexing statistics
    """
    # Get database settings
    settings = get_settings()
    database_url = settings.database_url
    
    # Convert to async URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
    elif database_url.startswith("sqlite"):
        database_url = database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
    
    print(f"{'=' * 60}")
    print("MEILISEARCH INDEXING")
    print(f"{'=' * 60}")
    print(f"Mode: {'Full reindex' if full_reindex else 'Incremental'}")
    print(f"Batch size: {batch_size}")
    if site_id:
        print(f"Site filter: {site_id}")
    if dry_run:
        print("⚠ DRY RUN MODE - No changes will be made")
    print()
    
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
    
    # Initialize Meilisearch
    print("Connecting to Meilisearch...")
    try:
        search_engine = MeiliSearchEngine()
        if not search_engine.health_check():
            raise Exception("Meilisearch is not accessible. Make sure it's running.")
        print("  ✓ Connected to Meilisearch")
    except Exception as e:
        print(f"  ✗ Failed to connect to Meilisearch: {e}")
        print("\nMake sure Meilisearch is running:")
        print("  ./scripts/start-meilisearch.sh")
        await engine.dispose()
        return {"error": str(e)}
    
    # Get current index stats
    index_stats = await search_engine.get_stats()
    print(f"  Current index: {index_stats.get('total_documents', 0)} documents")
    print()
    
    stats = {
        "pages_indexed": 0,
        "pages_skipped": 0,
        "batches_processed": 0,
        "errors": [],
        "start_time": datetime.now(timezone.utc),
        "sites_processed": set()
    }
    
    async with async_session_factory() as session:
        try:
            # Build query for pages
            query = select(Page)
            
            # Filter by site if specified
            if site_id:
                query = query.where(Page.site_id == site_id)
            
            # For incremental indexing, we would track last indexed time
            # Since we don't have a last_indexed_in_meilisearch field yet,
            # full_reindex determines if we process all pages or not
            if not full_reindex:
                # In incremental mode, we could filter by indexed_at timestamp
                # For now, we'll just process all pages since we don't have
                # a way to track which pages are already in Meilisearch
                # TODO: Add last_indexed_in_meilisearch field to Page model
                print("Note: Incremental mode will reindex all pages.")
                print("      (Add last_indexed_in_meilisearch field for true incremental)")
                print()
            
            # Order by ID for consistent processing
            query = query.order_by(Page.id)
            
            # Get total count
            count_query = select(func.count()).select_from(Page)
            if site_id:
                count_query = count_query.where(Page.site_id == site_id)
            
            result = await session.execute(count_query)
            total_pages = result.scalar()
            
            print(f"Found {total_pages} pages to process")
            
            if total_pages == 0:
                print("\nNo pages to index.")
                await engine.dispose()
                return stats
            
            # Process pages in batches
            offset = 0
            while True:
                # Fetch batch of pages
                batch_query = query.limit(batch_size).offset(offset)
                result = await session.execute(batch_query)
                pages_batch = result.scalars().all()
                
                if not pages_batch:
                    break
                
                # Prepare documents for indexing
                documents = []
                for page in pages_batch:
                    stats["sites_processed"].add(page.site_id)
                    
                    # Convert page to dictionary for Meilisearch
                    doc = {
                        "id": page.id,
                        "site_id": page.site_id,
                        "url": page.url,
                        "title": page.title or "",
                        "content": page.content or "",
                        "metadata": page.page_metadata or {},
                        "indexed_at": page.indexed_at.isoformat() if page.indexed_at else None
                    }
                    documents.append(doc)
                
                # Index batch in Meilisearch
                if not dry_run:
                    try:
                        result = await search_engine.index_pages(documents)
                        stats["pages_indexed"] += len(documents)
                        stats["batches_processed"] += 1
                        
                        print(f"  ✓ Indexed batch {stats['batches_processed']}: "
                              f"{len(documents)} pages "
                              f"({stats['pages_indexed']}/{total_pages})")
                    except Exception as e:
                        error_msg = f"Error indexing batch at offset {offset}: {e}"
                        print(f"  ✗ {error_msg}")
                        stats["errors"].append(error_msg)
                        stats["pages_skipped"] += len(documents)
                else:
                    # Dry run - just count
                    stats["pages_indexed"] += len(documents)
                    stats["batches_processed"] += 1
                    print(f"  [DRY RUN] Would index batch {stats['batches_processed']}: "
                          f"{len(documents)} pages "
                          f"({stats['pages_indexed']}/{total_pages})")
                
                # Move to next batch
                offset += batch_size
                
                # Small delay to avoid overwhelming Meilisearch
                if not dry_run:
                    await asyncio.sleep(0.1)
        
        except Exception as e:
            print(f"\n✗ Indexing failed: {e}")
            stats["errors"].append(str(e))
            raise
    
    await engine.dispose()
    
    # Calculate duration
    stats["end_time"] = datetime.now(timezone.utc)
    duration = (stats["end_time"] - stats["start_time"]).total_seconds()
    stats["duration_seconds"] = duration
    
    # Get final index stats
    if not dry_run:
        print("\nWaiting for indexing to complete...")
        await asyncio.sleep(2)  # Give Meilisearch time to process
        final_stats = await search_engine.get_stats()
        stats["final_document_count"] = final_stats.get('total_documents', 0)
    
    # Print summary
    print(f"\n{'=' * 60}")
    print("INDEXING SUMMARY")
    print(f"{'=' * 60}")
    print(f"Pages indexed: {stats['pages_indexed']}")
    print(f"Pages skipped: {stats['pages_skipped']}")
    print(f"Batches processed: {stats['batches_processed']}")
    print(f"Sites processed: {len(stats['sites_processed'])}")
    print(f"Duration: {duration:.2f} seconds")
    if not dry_run:
        print(f"Final index size: {stats.get('final_document_count', 0)} documents")
    print(f"Errors: {len(stats['errors'])}")
    
    if stats["errors"]:
        print(f"\nErrors encountered:")
        for error in stats["errors"][:10]:  # Show first 10 errors
            print(f"  - {error}")
        if len(stats["errors"]) > 10:
            print(f"  ... and {len(stats['errors']) - 10} more errors")
    
    if dry_run:
        print(f"\n⚠ DRY RUN - No changes were made to Meilisearch")
    else:
        print(f"\n✓ Indexing complete!")
        print(f"\nYou can now search at: {settings.meilisearch_host}")
    
    return stats


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Index PostgreSQL pages into Meilisearch for search"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of pages to index per batch (default: 100)"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Perform full reindex of all pages (default: incremental)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without actually indexing pages"
    )
    parser.add_argument(
        "--site-id",
        type=int,
        help="Only index pages for a specific site ID"
    )
    
    args = parser.parse_args()
    
    try:
        stats = asyncio.run(index_pages_to_meilisearch(
            batch_size=args.batch_size,
            full_reindex=args.full,
            dry_run=args.dry_run,
            site_id=args.site_id
        ))
        
        # Return non-zero exit code if there were errors
        if stats.get("errors"):
            return 1
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠ Indexing interrupted by user")
        return 130
    except Exception as e:
        print(f"\n✗ Indexing failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
