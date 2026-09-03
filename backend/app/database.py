"""OpsPilot — PostgreSQL async connection pool and query helpers.

Uses asyncpg for async database access as specified in the architecture.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import asyncpg

from backend.app.config import settings

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Pool
# ----------------------------------------------------------------------
_pool: Optional[asyncpg.Pool] = None


async def init_pool() -> None:
    """Create the connection pool. Called from the FastAPI lifespan.

    If the database is unreachable the pool is left as None and the app
    runs in *demo mode* — API endpoints that need the DB will return 503
    but the rest of the interface still loads.
    """
    global _pool
    if _pool is not None:
        return
    try:
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=settings.database_pool_min,
            max_size=settings.database_pool_max,
        )
        logger.info(
            "Database pool created (min=%d, max=%d)",
            settings.database_pool_min,
            settings.database_pool_max,
        )
    except Exception:
        logger.warning(
            "Database unreachable — running in DEMO mode (no persistent storage)"
        )
        _pool = None


async def close_pool() -> None:
    """Close every connection in the pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


def is_connected() -> bool:
    """Return True if the database pool is active."""
    return _pool is not None


@asynccontextmanager
async def get_connection():
    """Yield a connection from the pool and return it when done."""
    if _pool is None:
        raise RuntimeError("DATABASE_UNAVAILABLE")
    async with _pool.acquire() as conn:
        async with conn.transaction():
            yield conn


# ----------------------------------------------------------------------
# Query helpers
# ----------------------------------------------------------------------
async def execute(
    query: str,
    params: Optional[tuple] = None,
) -> int:
    """Run a write query. Returns the rowcount."""
    async with get_connection() as conn:
        result = await conn.execute(query, *(params or ()))
        # asyncpg returns e.g. 'INSERT 0 1' — parse the count
        parts = result.split()
        if len(parts) >= 2:
            try:
                return int(parts[-1])
            except ValueError:
                pass
        return 0


async def fetch_one(
    query: str,
    params: Optional[tuple] = None,
) -> Optional[Dict[str, Any]]:
    """Run a read query and return the first row as a dict (or None)."""
    async with get_connection() as conn:
        row = await conn.fetchrow(query, *(params or ()))
        return dict(row) if row else None


async def fetch_many(
    query: str,
    params: Optional[tuple] = None,
) -> List[Dict[str, Any]]:
    """Run a read query and return all rows as a list of dicts."""
    async with get_connection() as conn:
        rows = await conn.fetch(query, *(params or ()))
        return [dict(r) for r in rows]
