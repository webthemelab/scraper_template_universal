# middlewares/retry.py
# ─────────────────────────────────────────────────────────────
# Retry middleware with exponential backoff and jitter.
#
# WHY JITTER?
#   If 10 workers all fail at the same time and retry after
#   exactly 2s, they all hit the server simultaneously again.
#   Adding random jitter spreads the retries out so the server
#   isn't overwhelmed.
#
# COMMON MISTAKE:
#   Retrying immediately on every error without backoff. This
#   can cause a thundering-herd problem and get your IP banned
#   faster.
# ─────────────────────────────────────────────────────────────

import asyncio
import functools
import random
from typing import Callable, Tuple, Type

from config.settings import settings
from utils.logger import get_logger

log = get_logger("retry")

# HTTP status codes that are worth retrying (server-side issues)
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

# Status codes that indicate a permanent failure — don't retry
FATAL_STATUSES = {400, 401, 403, 404, 410}


class MaxRetriesExceeded(Exception):
    """Raised when all retry attempts are exhausted."""
    pass


def with_retry(
    max_attempts: int | None = None,
    backoff: float | None = None,
    jitter: float = 0.5,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """
    Decorator: retry an async function with exponential backoff + jitter.

    Args:
        max_attempts:          Total attempts (default: from settings)
        backoff:               Backoff multiplier in seconds (default: from settings)
        jitter:                Max random seconds added to each delay
        retryable_exceptions:  Only retry on these exception types

    Example:
        @with_retry(max_attempts=3, retryable_exceptions=(httpx.HTTPError,))
        async def fetch(url: str): ...
    """
    _max     = max_attempts or settings.scraper.max_retries
    _backoff = backoff      or settings.scraper.retry_backoff

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, _max + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_exc = exc
                    if attempt == _max:
                        break
                    # Exponential backoff: 2s, 4s, 8s … + random jitter
                    delay = (_backoff ** attempt) + random.uniform(0, jitter)
                    log.warning(
                        f"{func.__name__} attempt {attempt}/{_max} failed: {exc}. "
                        f"Retrying in {delay:.1f}s…"
                    )
                    await asyncio.sleep(delay)

            log.error(f"{func.__name__} failed after {_max} attempts: {last_exc}")
            raise MaxRetriesExceeded(
                f"{func.__name__} failed after {_max} attempts"
            ) from last_exc
        return wrapper
    return decorator


async def retry_with_new_proxy(func: Callable, proxy_manager, *args, **kwargs):
    """
    Call func(*args, **kwargs) and switch to a new proxy on failure.
    Unlike the decorator, this is used when you want to explicitly
    rotate the proxy between attempts rather than just wait.

    Args:
        func:          Async callable that accepts a `proxy` keyword arg
        proxy_manager: ProxyManager instance
    """
    max_attempts = settings.scraper.max_retries
    last_exc = None

    for attempt in range(1, max_attempts + 1):
        proxy = proxy_manager.get_proxy()
        try:
            result = await func(*args, proxy=proxy, **kwargs)
            if proxy:
                proxy_manager.report_success(proxy)
            return result
        except Exception as exc:
            last_exc = exc
            if proxy:
                proxy_manager.report_failure(proxy)
            log.warning(
                f"Attempt {attempt}/{max_attempts} failed with proxy "
                f"{proxy}: {exc}. Rotating proxy…"
            )
            delay = (settings.scraper.retry_backoff ** attempt) + random.uniform(0, 0.5)
            await asyncio.sleep(delay)

    raise MaxRetriesExceeded(
        f"All {max_attempts} attempts failed"
    ) from last_exc
