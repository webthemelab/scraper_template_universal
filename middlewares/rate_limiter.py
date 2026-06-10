# middlewares/rate_limiter.py
# ─────────────────────────────────────────────────────────────
# Per-domain rate limiting using a token bucket algorithm.
#
# WHY THIS EXISTS:
#   Hammering a server with hundreds of requests per second is
#   both unethical and the fastest way to get your IP banned.
#   This middleware enforces a maximum request rate per domain,
#   regardless of how many concurrent workers you're running.
#
# HOW TOKEN BUCKET WORKS:
#   Each domain has a "bucket" that fills up at a fixed rate
#   (e.g. 20 tokens/minute). Each request consumes one token.
#   If the bucket is empty, the worker waits until it refills.
#   This naturally throttles bursts while allowing sustained
#   scraping at a controlled pace.
#
# BEST PRACTICE:
#   Always honour the Crawl-delay from robots.txt as a minimum.
#   Our limiter uses whichever is larger: your configured rate
#   or the site's requested delay.
# ─────────────────────────────────────────────────────────────

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlparse

from config.settings import settings
from utils.logger import get_logger
from utils.robots import get_crawl_delay

log = get_logger("rate_limiter")


@dataclass
class _TokenBucket:
    """
    Token bucket for one domain.
    rate: tokens added per second
    capacity: maximum tokens in bucket
    """
    rate:      float
    capacity:  float
    tokens:    float = field(init=False)
    last_fill: float = field(init=False)

    def __post_init__(self):
        self.tokens    = self.capacity
        self.last_fill = time.monotonic()

    def _refill(self):
        now    = time.monotonic()
        elapsed = now - self.last_fill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_fill = now

    def consume(self) -> float:
        """
        Try to consume one token.
        Returns 0 if a token was available, or the number of
        seconds to wait until one becomes available.
        """
        self._refill()
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return 0.0
        # Time until next token is available
        return (1.0 - self.tokens) / self.rate


class RateLimiter:
    """
    Async rate limiter keyed by domain.

    Usage:
        limiter = RateLimiter()
        await limiter.acquire("https://example.com/page")
    """

    def __init__(self):
        # requests-per-minute from settings → tokens-per-second
        self._default_rate = settings.scraper.rate_limit_rpm / 60.0
        self._buckets: dict[str, _TokenBucket] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _get_bucket(self, domain: str, crawl_delay: float = 0.0) -> _TokenBucket:
        if domain not in self._buckets:
            # Honour Crawl-delay: if robots.txt asks for ≥5s between requests,
            # cap our rate at 1 request per 5s regardless of settings.
            if crawl_delay > 0:
                rate = min(self._default_rate, 1.0 / crawl_delay)
            else:
                rate = self._default_rate
            self._buckets[domain] = _TokenBucket(rate=rate, capacity=max(1.0, rate * 2))
            log.debug(f"Rate bucket created for {domain}: {rate:.2f} req/s")
        return self._buckets[domain]

    async def acquire(self, url: str):
        """
        Wait until a request to this URL's domain is permitted.
        Must be awaited before every HTTP request.
        """
        domain = urlparse(url).netloc
        crawl_delay = get_crawl_delay(url)

        async with self._locks[domain]:
            bucket = self._get_bucket(domain, crawl_delay)
            wait = bucket.consume()
            if wait > 0:
                log.debug(f"Rate limit: sleeping {wait:.2f}s for {domain}")
                await asyncio.sleep(wait)

    def set_domain_rate(self, domain: str, rpm: int):
        """Override the rate for a specific domain (requests per minute)."""
        rate = rpm / 60.0
        self._buckets[domain] = _TokenBucket(rate=rate, capacity=max(1.0, rate * 2))
        log.info(f"Custom rate set for {domain}: {rpm} rpm")


# Module-level singleton
rate_limiter = RateLimiter()
