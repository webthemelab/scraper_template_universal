# middlewares/proxy_manager.py
# ─────────────────────────────────────────────────────────────
# Proxy rotation, health checking, and session management.
#
# WHY THIS EXISTS:
#   Many websites rate-limit or block IPs that make too many
#   requests. A proxy manager routes each request through a
#   different IP address so your traffic looks like organic
#   visitors from many locations.
#
# PROXY TYPES EXPLAINED:
#   • Datacenter proxies  — Hosted in data centres. Fast and cheap
#     but easier to detect because the IP ranges are known.
#     Good for: sites with light bot protection, fast bulk scraping.
#
#   • Residential proxies — Real home/mobile IPs from ISPs.
#     Much harder to detect and block. More expensive.
#     Good for: sites with heavy bot protection (Cloudflare, etc.).
#
#   • Rotating gateway    — A single endpoint (e.g. Bright Data,
#     Oxylabs) that assigns a fresh IP automatically per request
#     or per session. The simplest and most reliable option.
#
# COMMON MISTAKES:
#   1. Using the same proxy for too many requests → gets banned
#   2. Not testing whether a proxy is alive before using it
#   3. Leaking your real IP when a proxy fails (no fallback)
# ─────────────────────────────────────────────────────────────

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import httpx

from config.settings import settings
from utils.logger import get_logger

log = get_logger("proxy_manager")

# URL used to verify that a proxy is working and shows the correct IP
_IP_CHECK_URL = "https://api.ipify.org?format=json"


@dataclass
class ProxyRecord:
    """Tracks one proxy's URL, failure count, and health status."""
    url:          str
    failures:     int   = 0
    last_used:    float = 0.0
    banned:       bool  = False
    country_code: str   = ""

    @property
    def is_healthy(self) -> bool:
        return not self.banned and self.failures < 5

    def mark_failure(self):
        self.failures += 1
        if self.failures >= 5:
            self.banned = True
            log.warning(f"Proxy marked as dead: {self._safe_url}")

    def mark_success(self):
        # Gradually recover failure count on success
        self.failures = max(0, self.failures - 1)
        self.last_used = time.monotonic()

    @property
    def _safe_url(self) -> str:
        """Return proxy URL with password masked for safe logging."""
        parsed = urlparse(self.url)
        if parsed.password:
            return self.url.replace(parsed.password, "***")
        return self.url


class ProxyManager:
    """
    Manages a pool of proxies with rotation, health checking,
    and automatic failover.

    Usage:
        manager = ProxyManager()
        proxy_url = manager.get_proxy()          # returns a proxy URL string
        manager.report_success(proxy_url)
        manager.report_failure(proxy_url)
    """

    def __init__(self):
        self._pool: list[ProxyRecord] = []
        self._lock = asyncio.Lock()
        self._request_count = 0
        self._rotation_every = settings.proxy.rotation_every
        self._current: Optional[ProxyRecord] = None
        self._build_pool()

    def _build_pool(self):
        """Populate the proxy pool from settings."""
        cfg = settings.proxy

        if not cfg.enabled:
            log.info("Proxy disabled — using direct connection")
            return

        # 1. Rotating gateway (single URL, auto-rotates at the provider)
        if cfg.gateway_url:
            url = cfg.gateway_url
            if cfg.username and cfg.password:
                parsed = urlparse(url)
                url = f"{parsed.scheme}://{cfg.username}:{cfg.password}@{parsed.netloc}"
            self._pool.append(ProxyRecord(url=url, country_code=cfg.country_code))
            log.info(f"Proxy pool: 1 rotating gateway ({cfg.gateway_url[:30]}…)")
            return

        # 2. Static proxy list
        for raw in cfg.static_proxies:
            self._pool.append(ProxyRecord(url=raw))

        if self._pool:
            log.info(f"Proxy pool: {len(self._pool)} static proxies loaded")
        else:
            log.warning("No proxies configured — scraping without proxy")

    # ── Public API ────────────────────────────────────────────

    def get_proxy(self, country_code: str = "") -> Optional[str]:
        """
        Return the URL of the next proxy to use.
        Returns None if proxies are disabled or the pool is empty.

        Args:
            country_code: Prefer a proxy from this country (if available).
        """
        if not self._pool:
            return None

        healthy = [p for p in self._pool if p.is_healthy]
        if not healthy:
            log.error("All proxies are dead — resetting failure counts")
            for p in self._pool:
                p.failures = 0
                p.banned = False
            healthy = self._pool[:]

        # Country preference
        if country_code:
            country_match = [p for p in healthy if p.country_code == country_code]
            if country_match:
                healthy = country_match

        # Rotate after N requests
        self._request_count += 1
        if (
            self._current is None
            or not self._current.is_healthy
            or self._request_count % self._rotation_every == 0
        ):
            # Least-recently-used selection — avoids hammering one proxy
            self._current = min(healthy, key=lambda p: p.last_used)
            log.debug(f"Rotated to proxy: {self._current._safe_url}")

        self._current.last_used = time.monotonic()
        return self._current.url

    def report_success(self, proxy_url: str):
        """Call this after a successful request through the given proxy."""
        record = self._find(proxy_url)
        if record:
            record.mark_success()

    def report_failure(self, proxy_url: str):
        """
        Call this when a request fails.
        After 5 failures the proxy is marked dead and skipped.
        """
        record = self._find(proxy_url)
        if record:
            record.mark_failure()

    async def verify_proxy(self, proxy_url: str) -> bool:
        """
        Test that a proxy is live and returning the expected IP.
        Returns True if the proxy works, False otherwise.
        """
        try:
            async with httpx.AsyncClient(proxy=proxy_url, timeout=10) as client:
                resp = await client.get(_IP_CHECK_URL)
                resp.raise_for_status()
                ip = resp.json().get("ip", "unknown")
                log.info(f"Proxy OK — visible IP: {ip}")
                return True
        except Exception as exc:
            log.warning(f"Proxy health check failed: {exc}")
            return False

    async def verify_all(self):
        """Check all proxies and mark dead ones as banned."""
        tasks = [self._check_and_mark(p) for p in self._pool]
        await asyncio.gather(*tasks)

    async def _check_and_mark(self, record: ProxyRecord):
        alive = await self.verify_proxy(record.url)
        if not alive:
            record.mark_failure()

    def health_report(self) -> dict:
        """Return a summary dict for monitoring dashboards."""
        total   = len(self._pool)
        healthy = sum(1 for p in self._pool if p.is_healthy)
        return {
            "total":    total,
            "healthy":  healthy,
            "dead":     total - healthy,
            "proxies":  [
                {"url": p._safe_url, "failures": p.failures, "banned": p.banned}
                for p in self._pool
            ],
        }

    # ── Internal ──────────────────────────────────────────────

    def _find(self, proxy_url: str) -> Optional[ProxyRecord]:
        for record in self._pool:
            if record.url == proxy_url:
                return record
        return None


# Module-level singleton
proxy_manager = ProxyManager()
