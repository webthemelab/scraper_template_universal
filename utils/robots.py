# utils/robots.py
# ─────────────────────────────────────────────────────────────
# Checks robots.txt before crawling any URL.
# Respecting robots.txt is both a legal best practice and the
# ethical foundation of responsible web scraping.
#
# Common mistake: skipping this check entirely.
# Best practice: cache parsed robots.txt per domain so you
# only fetch it once, not before every request.
# ─────────────────────────────────────────────────────────────

import asyncio
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from functools import lru_cache

import httpx

from utils.logger import get_logger

log = get_logger("robots")

USER_AGENT = "*"    # We check permissions for any bot


@lru_cache(maxsize=256)
def _get_parser(robots_url: str) -> RobotFileParser:
    """Fetch and parse robots.txt for a domain. Result is cached."""
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        log.info(f"Loaded robots.txt: {robots_url}")
    except Exception as exc:
        log.warning(f"Could not read {robots_url}: {exc} — assuming allowed")
    return rp


def is_allowed(url: str, user_agent: str = USER_AGENT) -> bool:
    """
    Return True if the given URL is allowed to be crawled.

    Args:
        url:        Full URL to check (e.g. "https://example.com/page")
        user_agent: Bot user-agent string to check against

    Returns:
        True  = crawling is permitted
        False = robots.txt disallows this URL
    """
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = _get_parser(robots_url)
    allowed = parser.can_fetch(user_agent, url)
    if not allowed:
        log.warning(f"robots.txt disallows: {url}")
    return allowed


def get_crawl_delay(url: str, user_agent: str = USER_AGENT) -> float:
    """
    Return the Crawl-delay directive for a domain (or 0.0 if not set).
    Always respect this value — it tells you the minimum gap the site owner
    wants between your requests.
    """
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = _get_parser(robots_url)
    delay = parser.crawl_delay(user_agent)
    return float(delay) if delay else 0.0
