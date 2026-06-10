# workers/scraper_worker.py
# Pulls URLs from Redis queue, scrapes them, saves to DB.

import asyncio
from typing import Type

from scrapers.base_scraper import BaseScraper
from workers.queue_manager import queue_manager
from db.queries import save_profiles, save_failed_urls
from models.scraped_item import SalonProfile, FailedURL
from utils.logger import get_logger

log = get_logger("worker")


async def run_worker(scraper_class: Type[BaseScraper], worker_id: int = 0):
    """
    Continuously dequeue URLs and scrape them until the queue is empty.

    Args:
        scraper_class: The scraper subclass to use for parsing
        worker_id:     Identifier for log context
    """
    log = get_logger("worker", worker_id=worker_id)
    scraper = scraper_class()
    log.info(f"Worker {worker_id} started")

    while True:
        url = await queue_manager.dequeue()
        if url is None:
            log.info(f"Worker {worker_id}: queue empty, stopping")
            break

        item = await scraper.scrape_one(url)

        if item:
            await save_profiles([item])
            await queue_manager.complete(url)
        else:
            # Failure already logged in scraper; pull last failure record
            if scraper._failures:
                failure = scraper._failures[-1]
                await save_failed_urls([failure])
                await queue_manager.fail(url, {
                    "error_type": failure.error_type,
                    "message":    failure.message,
                })
            else:
                await queue_manager.fail(url, {"error_type": "unknown", "message": "no item returned"})

    log.info(f"Worker {worker_id} finished")


async def run_pool(scraper_class: Type[BaseScraper], num_workers: int = 4):
    """Launch N workers in parallel."""
    await queue_manager.requeue_stale()
    await asyncio.gather(*[
        run_worker(scraper_class, worker_id=i)
        for i in range(num_workers)
    ])
