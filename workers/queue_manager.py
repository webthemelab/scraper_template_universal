# workers/queue_manager.py
# ─────────────────────────────────────────────────────────────
# Redis-backed task queue for distributed scraping.
#
# WHY A QUEUE?
#   With a queue you can:
#   • Run multiple worker processes (even on different machines)
#   • Resume after a crash — unfinished tasks stay in the queue
#   • Deduplicate — never enqueue the same URL twice
#   • Prioritise — high-value URLs go to the front
#
# DESIGN:
#   • pending_urls  — Redis SET of URLs waiting to be scraped
#   • in_progress   — Redis SET of URLs currently being worked on
#   • completed     — Redis SET for deduplication (already done)
#   • failed_queue  — Redis LIST of serialised FailedURL records
# ─────────────────────────────────────────────────────────────

import json
import asyncio
from typing import Optional, List

import redis.asyncio as aioredis

from config.settings import settings
from utils.logger import get_logger

log = get_logger("queue")

_PENDING    = "scraper:queue:pending"
_PROGRESS   = "scraper:queue:in_progress"
_COMPLETED  = "scraper:queue:completed"
_FAILED     = "scraper:queue:failed"


class QueueManager:
    """
    Async Redis task queue.

    Basic flow:
        1. Producer calls enqueue_urls([...])
        2. Workers call dequeue() to get the next URL
        3. Worker calls complete(url) on success or fail(url) on error
        4. Crashed workers: in_progress URLs can be requeued via requeue_stale()
    """

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(
                settings.redis.url,
                encoding="utf-8",
                decode_responses=True,
            )
            log.info("Redis connection established")
        return self._redis

    # ── Producer ──────────────────────────────────────────────

    async def enqueue_urls(self, urls: List[str], skip_seen: bool = True):
        """
        Add URLs to the pending queue.

        Args:
            urls:       List of URLs to scrape
            skip_seen:  If True, skip URLs already completed or pending
        """
        r = await self._get_redis()
        added = 0
        for url in urls:
            if skip_seen:
                already_done    = await r.sismember(_COMPLETED, url)
                already_pending = await r.sismember(_PENDING,   url)
                if already_done or already_pending:
                    continue
            await r.sadd(_PENDING, url)
            added += 1
        log.info(f"Enqueued {added}/{len(urls)} URLs (skipped {len(urls)-added} seen)")
        return added

    # ── Worker ────────────────────────────────────────────────

    async def dequeue(self) -> Optional[str]:
        """
        Pop one URL from the pending queue and move it to in_progress.
        Returns None if the queue is empty.
        """
        r = await self._get_redis()
        url = await r.spop(_PENDING)
        if url:
            await r.sadd(_PROGRESS, url)
        return url

    async def complete(self, url: str):
        """Mark a URL as successfully scraped."""
        r = await self._get_redis()
        await r.srem(_PROGRESS, url)
        await r.sadd(_COMPLETED, url)

    async def fail(self, url: str, error: dict):
        """Move a URL from in_progress to the failed list."""
        r = await self._get_redis()
        await r.srem(_PROGRESS, url)
        await r.lpush(_FAILED, json.dumps({"url": url, **error}))

    async def requeue_stale(self):
        """
        Move all in_progress URLs back to pending.
        Call on startup to recover from a previous crash.
        """
        r = await self._get_redis()
        stale = await r.smembers(_PROGRESS)
        if stale:
            log.warning(f"Requeuing {len(stale)} stale in-progress URLs")
            for url in stale:
                await r.srem(_PROGRESS, url)
                await r.sadd(_PENDING,  url)

    # ── Stats ─────────────────────────────────────────────────

    async def stats(self) -> dict:
        """Return current queue depth for monitoring."""
        r = await self._get_redis()
        return {
            "pending":     await r.scard(_PENDING),
            "in_progress": await r.scard(_PROGRESS),
            "completed":   await r.scard(_COMPLETED),
            "failed":      await r.llen(_FAILED),
        }

    async def close(self):
        if self._redis:
            await self._redis.aclose()
            self._redis = None


# Module-level singleton
queue_manager = QueueManager()
