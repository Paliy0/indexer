"""
Database operations for SQLite with FTS5
"""

import sqlite3
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pathlib import Path


def get_db_connection(db_path: str = "./data/sites.db") -> sqlite3.Connection:
    """Create a database connection with row factory"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = "./data/sites.db") -> None:
    """Initialize database schema with tables and indexes"""
    # Ensure data directory exists
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Create sites table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            domain TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'pending',
            page_count INTEGER DEFAULT 0,
            last_scraped TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create pages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (site_id) REFERENCES sites(id)
        )
    """)
    
    # Create FTS5 virtual table for full-text search
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
            title,
            content,
            content='pages',
            content_rowid='id'
        )
    """)
    
    # Create triggers to keep FTS index in sync
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
            INSERT INTO pages_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END
    """)
    
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
            INSERT INTO pages_fts(pages_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
        END
    """)
    
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
            INSERT INTO pages_fts(pages_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
            INSERT INTO pages_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END
    """)
    
    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pages_site_id ON pages(site_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sites_domain ON sites(domain)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sites_status ON sites(status)")
    
    conn.commit()
    conn.close()


def create_site(url: str, domain: str, db_path: str = "./data/sites.db") -> int:
    """Create a new site entry"""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sites (url, domain, status) VALUES (?, ?, 'pending')",
        (url, domain)
    )
    site_id = cursor.lastrowid
    conn.commit()
    conn.close()
    if site_id is None:
        raise RuntimeError("Failed to create site: lastrowid is None")
    return site_id


def get_site(site_id: int, db_path: str = "./data/sites.db") -> Optional[Dict[str, Any]]:
    """Get site by ID"""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sites WHERE id = ?", (site_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_site_by_domain(domain: str, db_path: str = "./data/sites.db") -> Optional[Dict[str, Any]]:
    """Get site by domain"""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sites WHERE domain = ?", (domain,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_page(
    site_id: int, 
    url: str, 
    title: str, 
    content: str, 
    db_path: str = "./data/sites.db"
) -> int:
    """Create a new page entry (FTS index updated via triggers)"""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Insert page - triggers will update FTS index automatically
    cursor.execute(
        "INSERT INTO pages (site_id, url, title, content) VALUES (?, ?, ?, ?)",
        (site_id, url, title, content)
    )
    page_id = cursor.lastrowid
    
    conn.commit()
    conn.close()
    if page_id is None:
        raise RuntimeError("Failed to create page: lastrowid is None")
    return page_id


def get_pages_for_site(site_id: int, db_path: str = "./data/sites.db") -> List[Dict[str, Any]]:
    """Get all pages for a site"""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pages WHERE site_id = ?", (site_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_site_status(
    site_id: int, 
    status: str, 
    page_count: Optional[int] = None,
    db_path: str = "./data/sites.db"
) -> None:
    """Update site status and optionally page count"""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    if page_count is not None:
        cursor.execute(
            "UPDATE sites SET status = ?, page_count = ?, last_scraped = ? WHERE id = ?",
            (status, page_count, datetime.now(timezone.utc).isoformat(), site_id)
        )
    else:
        cursor.execute(
            "UPDATE sites SET status = ? WHERE id = ?",
            (status, site_id)
        )
    
    conn.commit()
    conn.close()


def get_all_sites(db_path: str = "./data/sites.db") -> List[Dict[str, Any]]:
    """Get all sites"""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sites ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
