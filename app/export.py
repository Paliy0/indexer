"""
Export functionality for Site Search Platform.

Provides Exporter class for exporting pages in various formats:
- JSON: Full metadata with ISO timestamps
- CSV: Spreadsheet format with truncated content preview
- Markdown: Structured documentation format

Supports large exports (up to 10,000 pages) using StreamingResponse.
"""

import csv
import json
import io
from typing import Dict, List, Any, AsyncIterator
from datetime import datetime, UTC, UTC
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import Page, Site


class Exporter:
    """Export pages in various formats with support for large datasets."""
    
    MAX_PAGES_FOR_MEMORY_EXPORT = 10000  # Maximum pages to export in memory
    
    @staticmethod
    async def get_pages_for_site(
        db: AsyncSession, 
        site_id: int, 
        limit: int = 10000
    ) -> List[Page]:
        """
        Get pages for a site with pagination for large exports.
        
        Args:
            db: Database session
            site_id: Site ID to export
            limit: Maximum number of pages to fetch
            
        Returns:
            List of Page objects
        """
        result = await db.execute(
            select(Page)
            .where(Page.site_id == site_id)
            .order_by(Page.created_at.desc())
            .limit(limit)
        )
        pages = result.scalars().all()
        return list(pages)  # Convert to list for type compatibility
    
    @classmethod
    def export_json(cls, pages: List[Page], site: Site) -> Dict[str, Any]:
        """
        Export pages to JSON format.
        
        Args:
            pages: List of Page objects
            site: Site object
            
        Returns:
            Dictionary ready for JSON serialization
        """
        pages_data = []
        for page in pages:
            # Get string values from page attributes
            page_url = str(page.url) if page.url else ""
            page_title = str(page.title) if page.title else ""
            page_content = str(page.content) if page.content else ""
            
            page_data = {
                "url": page_url,
                "title": page_title,
                "content": page_content,
                "content_preview": cls._truncate_content(page_content, 200),
                "metadata": page.page_metadata or {},
                "indexed_at": page.indexed_at.isoformat() if page.indexed_at else None,
                "created_at": page.created_at.isoformat() if page.created_at else None,
            }
            pages_data.append(page_data)
        
        return {
            "exported_at": datetime.now(UTC).isoformat(),
            "site": {
                "id": site.id,
                "url": site.url,
                "domain": site.domain,
                "status": site.status,
                "page_count": site.page_count,
                "last_scraped": site.last_scraped.isoformat() if site.last_scraped else None,
                "created_at": site.created_at.isoformat() if site.created_at else None,
            },
            "total_pages": len(pages_data),
            "pages": pages_data
        }
    
    @classmethod
    async def stream_json(
        cls, 
        db: AsyncSession, 
        site_id: int, 
        site: Site, 
        batch_size: int = 1000
    ) -> AsyncIterator[str]:
        """
        Stream JSON export for large datasets.
        
        Args:
            db: Database session
            site_id: Site ID to export
            site: Site object
            batch_size: Number of pages to fetch per batch
            
        Yields:
            JSON chunks
        """
        # Yield start of JSON
        yield '{"exported_at": "' + datetime.now(UTC).isoformat() + '",'
        yield '"site": {'
        yield f'"id": {site.id},'
        yield f'"url": "{site.url}",'
        yield f'"domain": "{site.domain}",'
        yield f'"status": "{site.status}",'
        yield f'"page_count": {site.page_count},'
        yield f'"last_scraped": ' + (f'"{site.last_scraped.isoformat()}"' if site.last_scraped else "null") + ','
        yield f'"created_at": "{site.created_at.isoformat()}"' + '},'
        yield '"total_pages": '  # Placeholder, will be updated
        
        total_pages = 0
        offset = 0
        first_page = True
        
        yield '"pages": ['
        
        while True:
            # Fetch batch of pages
            result = await db.execute(
                select(Page)
                .where(Page.site_id == site_id)
                .order_by(Page.created_at.desc())
                .offset(offset)
                .limit(batch_size)
            )
            batch = result.scalars().all()
            
            if not batch:
                break
            
            for page in batch:
                if not first_page:
                    yield ','
                else:
                    first_page = False
                
                # Get string values from page attributes
                page_url = str(page.url) if page.url else ""
                page_title = str(page.title) if page.title else ""
                page_content = str(page.content) if page.content else ""
                
                page_data = {
                    "url": page_url,
                    "title": page_title,
                    "content": page_content,
                    "content_preview": cls._truncate_content(page_content, 200),
                    "metadata": page.page_metadata or {},
                    "indexed_at": page.indexed_at.isoformat() if page.indexed_at else None,
                    "created_at": page.created_at.isoformat() if page.created_at else None,
                }
                
                yield json.dumps(page_data, ensure_ascii=False)
                total_pages += 1
            
            offset += batch_size
        
        yield ']}'
    
    @classmethod
    def export_csv(cls, pages: List[Page]) -> str:
        """
        Export pages to CSV format.
        
        Args:
            pages: List of Page objects
            
        Returns:
            CSV string
        """
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(["url", "title", "content_preview", "indexed_at"])
        
        # Write data
        for page in pages:
            page_url = str(page.url) if page.url else ""
            page_title = str(page.title) if page.title else ""
            page_content = str(page.content) if page.content else ""
            
            writer.writerow([
                page_url,
                page_title,
                cls._truncate_content(page_content, 200),
                page.indexed_at.isoformat() if page.indexed_at else None
            ])
        
        return output.getvalue()
    
    @classmethod
    async def stream_csv(
        cls, 
        db: AsyncSession, 
        site_id: int, 
        batch_size: int = 1000
    ) -> AsyncIterator[str]:
        """
        Stream CSV export for large datasets.
        
        Args:
            db: Database session
            site_id: Site ID to export
            batch_size: Number of pages to fetch per batch
            
        Yields:
            CSV chunks
        """
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(["url", "title", "content_preview", "indexed_at"])
        yield output.getvalue()
        output.truncate(0)
        output.seek(0)
        
        offset = 0
        
        while True:
            # Fetch batch of pages
            result = await db.execute(
                select(Page)
                .where(Page.site_id == site_id)
                .order_by(Page.created_at.desc())
                .offset(offset)
                .limit(batch_size)
            )
            batch = result.scalars().all()
            
            if not batch:
                break
            
            for page in batch:
                page_url = str(page.url) if page.url else ""
                page_title = str(page.title) if page.title else ""
                page_content = str(page.content) if page.content else ""
                
                writer.writerow([
                    page_url,
                    page_title,
                    cls._truncate_content(page_content, 200),
                    page.indexed_at.isoformat() if page.indexed_at else None
                ])
            
            yield output.getvalue()
            output.truncate(0)
            output.seek(0)
            offset += batch_size
    
    @classmethod
    def export_markdown(cls, pages: List[Page], site: Site, include_content: bool = True) -> str:
        """
        Export pages to Markdown format.
        
        Args:
            pages: List of Page objects
            site: Site object
            include_content: Whether to include full content or just preview
            
        Returns:
            Markdown string
        """
        lines = [
            f"# Export: {site.domain}",
            "",
            f"Exported: {datetime.now(UTC).isoformat()}",
            f"Total pages: {len(pages)}",
            f"Site URL: {site.url}",
            f"Status: {site.status}",
            "",
            "---",
            ""
        ]
        
        for i, page in enumerate(pages, 1):
            page_url = str(page.url) if page.url else ""
            page_title = str(page.title) if page.title else 'Untitled'
            page_content = str(page.content) if page.content else ""
            
            content = page_content if include_content else cls._truncate_content(page_content, 200)
            
            lines.extend([
                f"## {i}. {page_title}",
                "",
                f"**URL:** {page_url}",
                f"**Indexed:** {page.indexed_at.isoformat() if page.indexed_at else 'Unknown'}",
                "",
                content,
                "",
                "---",
                ""
            ])
        
        return "\n".join(lines)
    
    @classmethod
    async def stream_markdown(
        cls, 
        db: AsyncSession, 
        site_id: int, 
        site: Site, 
        include_content: bool = True,
        batch_size: int = 500
    ) -> AsyncIterator[str]:
        """
        Stream Markdown export for large datasets.
        
        Args:
            db: Database session
            site_id: Site ID to export
            site: Site object
            include_content: Whether to include full content
            batch_size: Number of pages to fetch per batch
            
        Yields:
            Markdown chunks
        """
        # Yield header
        yield f"# Export: {site.domain}\n\n"
        yield f"Exported: {datetime.now(UTC).isoformat()}\n"
        yield f"Total pages: "  # Placeholder
        yield f"Site URL: {site.url}\n"
        yield f"Status: {site.status}\n\n"
        yield "---\n\n"
        
        offset = 0
        page_count = 0
        
        while True:
            # Fetch batch of pages
            result = await db.execute(
                select(Page)
                .where(Page.site_id == site_id)
                .order_by(Page.created_at.desc())
                .offset(offset)
                .limit(batch_size)
            )
            batch = result.scalars().all()
            
            if not batch:
                break
            
            for page in batch:
                page_count += 1
                page_title = str(page.title) if page.title else 'Untitled'
                page_url = str(page.url) if page.url else ""
                page_content = str(page.content) if page.content else ""
                
                content = page_content if include_content else cls._truncate_content(page_content, 200)
                
                yield f"## {page_count}. {page_title}\n\n"
                yield f"**URL:** {page_url}\n"
                yield f"**Indexed:** {page.indexed_at.isoformat() if page.indexed_at else 'Unknown'}\n\n"
                yield content + "\n\n"
                yield "---\n\n"
            
            offset += batch_size
    
    @classmethod
    def _truncate_content(cls, content: str, max_length: int = 200) -> str:
        """
        Truncate content for preview.
        
        Args:
            content: Content to truncate
            max_length: Maximum length
            
        Returns:
            Truncated content with ellipsis if needed
        """
        if not content:
            return ""
        
        if len(content) <= max_length:
            return content
        
        # Truncate at word boundary if possible
        truncated = content[:max_length]
        if content[max_length:max_length+1] not in (' ', '\n', '\t', '\r'):
            # Find last space
            last_space = truncated.rfind(' ')
            if last_space > max_length * 0.8:  # Only if we have a reasonable space
                truncated = truncated[:last_space]
        
        return truncated + "..."
    
    @classmethod
    async def create_export_response(
        cls,
        db: AsyncSession,
        site_id: int,
        site: Site,
        format: str = "json",
        include_content: bool = True,
        stream_large: bool = True
    ) -> StreamingResponse:
        """
        Create appropriate export response based on format and size.
        
        Args:
            db: Database session
            site_id: Site ID to export
            site: Site object
            format: Export format (json, csv, md)
            include_content: Whether to include full content
            stream_large: Whether to stream large exports
            
        Returns:
            StreamingResponse for the export
        """
        # Get page count to decide streaming vs in-memory
        result = await db.execute(
            select(Page).where(Page.site_id == site_id)
        )
        pages = result.scalars().all()
        page_count = len(pages)
        
        if format == "json":
            if stream_large and page_count > 500:
                # Stream large JSON exports
                return StreamingResponse(
                    cls.stream_json(db, site_id, site),
                    media_type="application/json",
                    headers={
                        "Content-Disposition": f'attachment; filename="site-{site_id}-export.json"'
                    }
                )
            else:
                # Small export in memory
                pages = await cls.get_pages_for_site(db, site_id)
                export_data = cls.export_json(pages, site)
                content = json.dumps(export_data, indent=2, ensure_ascii=False)
                return StreamingResponse(
                    iter([content]),
                    media_type="application/json",
                    headers={
                        "Content-Disposition": f'attachment; filename="site-{site_id}-export.json"'
                    }
                )
        
        elif format == "csv":
            if stream_large and page_count > 1000:
                # Stream large CSV exports
                return StreamingResponse(
                    cls.stream_csv(db, site_id),
                    media_type="text/csv",
                    headers={
                        "Content-Disposition": f'attachment; filename="site-{site_id}-export.csv"'
                    }
                )
            else:
                # Small export in memory
                pages = await cls.get_pages_for_site(db, site_id)
                content = cls.export_csv(pages)
                return StreamingResponse(
                    iter([content]),
                    media_type="text/csv",
                    headers={
                        "Content-Disposition": f'attachment; filename="site-{site_id}-export.csv"'
                    }
                )
        
        else:  # markdown
            if stream_large and page_count > 500:
                # Stream large Markdown exports
                return StreamingResponse(
                    cls.stream_markdown(db, site_id, site, include_content),
                    media_type="text/markdown",
                    headers={
                        "Content-Disposition": f'attachment; filename="site-{site_id}-export.md"'
                    }
                )
            else:
                # Small export in memory
                pages = await cls.get_pages_for_site(db, site_id)
                content = cls.export_markdown(pages, site, include_content)
                return StreamingResponse(
                    iter([content]),
                    media_type="text/markdown",
                    headers={
                        "Content-Disposition": f'attachment; filename="site-{site_id}-export.md"'
                    }
                )