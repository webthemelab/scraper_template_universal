# db/connection.py
# ─────────────────────────────────────────────────────────────
# Async PostgreSQL connection pool using asyncpg.
# A pool keeps N connections open and reuses them across workers
# — far more efficient than opening a new connection per request.
# ─────────────────────────────────────────────────────────────

import asyncpg
from config.settings import settings
from utils.logger import get_logger

log = get_logger("db")

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, creating it on first call."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.db.dsn,
            min_size=settings.db.pool_min,
            max_size=settings.db.pool_max,
            command_timeout=30,
        )
        log.info(f"DB pool opened (min={settings.db.pool_min}, max={settings.db.pool_max})")
    return _pool


async def close_pool():
    """Close the pool gracefully on shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        log.info("DB pool closed")
