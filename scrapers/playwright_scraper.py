# scrapers/playwright_scraper.py
# ─────────────────────────────────────────────────────────────
# Base class for sites that require a real browser (JavaScript
# rendering, dynamic content, SPAs).
#
# Uses Playwright (async) instead of httpx.
#
# ANTI-BOT MITIGATIONS APPLIED:
#   1. Realistic viewport and locale settings
#   2. User-agent rotation
#   3. Disabling the `navigator.webdriver` flag (primary headless
#      browser detection signal)
#   4. Random mouse movements and scroll before extracting data
#   5. Human-like typing delays
#   6. Randomised delays between page actions
#
# COMMON MISTAKE: using default Playwright settings exposes
#   dozens of detectable signals (webdriver flag, missing plugins,
#   perfect timing). This class addresses the main ones.
# ─────────────────────────────────────────────────────────────

import asyncio
import random
from abc import abstractmethod
from typing import List, Tuple

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from config.settings import settings
from middlewares.proxy_manager import proxy_manager
from middlewares.rate_limiter import rate_limiter
from models.scraped_item import ScrapedItem, FailedURL
from utils.logger import get_logger
from utils.robots import is_allowed
from utils.user_agents import get_weighted_ua

# Realistic viewport sizes (based on real browser stats)
_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 800},
]

# JavaScript to remove webdriver detection signals
_STEALTH_JS = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    window.chrome = { runtime: {} };
"""


class PlaywrightScraper:
    """
    Base class for Playwright-based scrapers.

    Subclass and implement parse_page(page, url) → ScrapedItem.
    """

    start_urls: List[str] = []
    name: str = "playwright_base"

    def __init__(self):
        self.log = get_logger(self.name)
        self._data: List[ScrapedItem] = []
        self._failures: List[FailedURL] = []

    @abstractmethod
    async def parse_page(self, page: Page, url: str) -> ScrapedItem:
        """Extract data from the loaded page. Must be implemented by subclass."""
        ...

    # ── Browser lifecycle ─────────────────────────────────────

    async def _create_context(self, browser: Browser) -> BrowserContext:
        """Create a new browser context with anti-detection settings."""
        proxy_url = proxy_manager.get_proxy()
        proxy_conf = {"server": proxy_url} if proxy_url else None

        viewport = random.choice(_VIEWPORTS)

        context = await browser.new_context(
            user_agent=get_weighted_ua(),
            viewport=viewport,
            locale="en-US",
            timezone_id="America/New_York",
            proxy=proxy_conf,
            # Pretend to have real geolocation (optional — remove if not needed)
            # geolocation={"latitude": 40.7128, "longitude": -74.0060},
            # permissions=["geolocation"],
        )

        # Inject stealth JS on every new page
        await context.add_init_script(_STEALTH_JS)

        return context

    # ── Human-like interaction helpers ────────────────────────

    async def _human_scroll(self, page: Page):
        """Scroll down the page in a human-like way."""
        for _ in range(random.randint(2, 4)):
            await page.mouse.wheel(0, random.randint(200, 600))
            await asyncio.sleep(random.uniform(0.3, 0.8))

    async def _random_delay(self, min_s: float | None = None, max_s: float | None = None):
        """Sleep for a random duration."""
        lo = min_s or settings.scraper.delay_min
        hi = max_s or settings.scraper.delay_max
        await asyncio.sleep(random.uniform(lo, hi))

    # ── Core visit logic ──────────────────────────────────────

    async def _visit(self, page: Page, url: str) -> bool:
        """
        Navigate to a URL and wait for the page to be ready.
        Returns True on success, False on error.
        """
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=settings.scraper.timeout * 1000)
            await self._random_delay(0.5, 1.5)
            await self._human_scroll(page)
            return True
        except Exception as exc:
            self.log.error(f"Navigation failed: {url} — {exc}")
            return False

    # ── Main loop ─────────────────────────────────────────────

    async def scrape_one(self, browser: Browser, url: str) -> ScrapedItem | None:
        """Scrape a single URL using a fresh browser context."""
        if settings.scraper.respect_robots and not is_allowed(url):
            self.log.warning(f"Skipped (robots.txt): {url}")
            return None

        await rate_limiter.acquire(url)
        await self._random_delay()

        context = await self._create_context(browser)
        page = await context.new_page()

        try:
            for attempt in range(1, settings.scraper.max_retries + 1):
                if await self._visit(page, url):
                    try:
                        item = await self.parse_page(page, url)
                        self.log.info(f"✓ {url}")
                        return item
                    except Exception as exc:
                        self.log.error(f"✗ Parse error: {url} — {exc}")
                        self._failures.append(FailedURL(
                            url=url, error_type="parse_error",
                            message=str(exc), scraper_name=self.name,
                        ))
                        return None
                if attempt < settings.scraper.max_retries:
                    self.log.warning(f"Retry {attempt}/{settings.scraper.max_retries}: {url}")
                    await self._random_delay(2, 5)

            self._failures.append(FailedURL(
                url=url, error_type="navigation_error",
                message="Max retries exceeded", scraper_name=self.name,
            ))
            return None
        finally:
            await context.close()

    async def run(self, urls: List[str] | None = None) -> Tuple[List[ScrapedItem], List[FailedURL]]:
        """Launch browser, scrape all URLs, return (data, failures)."""
        url_list = list(dict.fromkeys(urls or self.start_urls))
        self.log.info(f"Starting {self.name} — {len(url_list)} URLs")

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=settings.scraper.headless)
            semaphore = asyncio.Semaphore(settings.scraper.workers)

            async def _worker(url: str):
                async with semaphore:
                    item = await self.scrape_one(browser, url)
                    if item:
                        self._data.append(item)

            await asyncio.gather(*[_worker(u) for u in url_list])
            await browser.close()

        self.log.info(f"Done — {len(self._data)} ok, {len(self._failures)} failed")
        return self._data, self._failures
