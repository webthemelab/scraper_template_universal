# scrapers/base_scraper.py
import asyncio
import random
from abc import ABC, abstractmethod
from typing import List, Tuple

import httpx
from bs4 import BeautifulSoup

from config.settings import settings
from middlewares.proxy_manager import proxy_manager
from middlewares.rate_limiter import rate_limiter
from middlewares.retry import with_retry, MaxRetriesExceeded, RETRYABLE_STATUSES
from models.scraped_item import ScrapedItem, FailedURL
from utils.logger import get_logger
from utils.robots import is_allowed
from utils.user_agents import get_weighted_ua


class BaseScraper(ABC):
    start_urls: List[str] = []
    name: str = "base"

    def __init__(self):
        self.log = get_logger(self.name)
        self._data: List[ScrapedItem] = []
        self._failures: List[FailedURL] = []

    @abstractmethod
    async def parse(self, html: str, url: str) -> ScrapedItem:
        ...

    async def get_urls(self) -> List[str]:
        return self.start_urls

    async def _fetch(self, url: str, proxy: str | None = None) -> str:
        headers = {"User-Agent": get_weighted_ua()}

        # ── FIX: httpx 0.24+ では proxy= に文字列を渡す ──
        client_kwargs = dict(
            headers=headers,
            timeout=settings.scraper.timeout,
            follow_redirects=True,
        )
        if proxy:
            client_kwargs["proxy"] = proxy   # dict ではなく string

        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.get(url)
            if resp.status_code in RETRYABLE_STATUSES:
                raise httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}", request=resp.request, response=resp
                )
            resp.raise_for_status()
            return resp.text

    async def scrape_one(self, url: str) -> ScrapedItem | None:
        if settings.scraper.respect_robots and not is_allowed(url):
            self.log.warning(f"Skipped (robots.txt): {url}")
            return None

        await rate_limiter.acquire(url)

        delay = random.uniform(settings.scraper.delay_min, settings.scraper.delay_max)
        await asyncio.sleep(delay)

        html = None
        for attempt in range(1, settings.scraper.max_retries + 1):
            proxy = proxy_manager.get_proxy()
            try:
                html = await self._fetch(url, proxy=proxy)
                if proxy:
                    proxy_manager.report_success(proxy)
                break
            except Exception as exc:
                if proxy:
                    proxy_manager.report_failure(proxy)
                if attempt == settings.scraper.max_retries:
                    self.log.error(f"✗ Failed after {attempt} attempts: {url} — {exc}")
                    self._failures.append(FailedURL(
                        url=url,
                        error_type=type(exc).__name__,
                        status=str(getattr(getattr(exc, "response", None), "status_code", None)),
                        message=str(exc),
                        scraper_name=self.name,
                    ))
                    return None
                backoff = (settings.scraper.retry_backoff ** attempt) + random.uniform(0, 0.5)
                self.log.warning(f"Attempt {attempt} failed ({exc}), retry in {backoff:.1f}s")
                await asyncio.sleep(backoff)

        try:
            item = await self.parse(html, url)
            self.log.info(f"✓ {url}")
            return item
        except Exception as exc:
            self.log.error(f"✗ Parse error on {url}: {exc}")
            self._failures.append(FailedURL(
                url=url,
                error_type="parse_error",
                message=str(exc),
                scraper_name=self.name,
            ))
            return None

    async def run(self, urls: List[str] | None = None) -> Tuple[List[ScrapedItem], List[FailedURL]]:
        url_list = urls or await self.get_urls()
        url_list = list(dict.fromkeys(url_list))

        self.log.info(f"Starting {self.name} — {len(url_list)} URLs, "
                      f"{settings.scraper.workers} workers")

        semaphore = asyncio.Semaphore(settings.scraper.workers)

        async def _worker(url: str):
            async with semaphore:
                item = await self.scrape_one(url)
                if item:
                    self._data.append(item)

        await asyncio.gather(*[_worker(u) for u in url_list])
        self.log.info(f"Done — {len(self._data)} ok, {len(self._failures)} failed")
        return self._data, self._failures
