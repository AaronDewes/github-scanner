"""
Database utilities for the API
"""

import os
from contextlib import contextmanager
import psycopg2
from psycopg2.extras import RealDictCursor


def get_database_url():
    """Get database URL from environment."""
    return os.getenv('DATABASE_URL', 'postgresql://scanner:password@localhost:5432/github_scanner')


@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    conn = psycopg2.connect(get_database_url())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_db_cursor(conn=None):
    """Context manager for database cursors."""
    should_close = False
    if conn is None:
        conn = psycopg2.connect(get_database_url())
        should_close = True
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        yield cursor
        if should_close:
            conn.commit()
    except Exception:
        if should_close:
            conn.rollback()
        raise
    finally:
        cursor.close()
        if should_close:
            conn.close()
