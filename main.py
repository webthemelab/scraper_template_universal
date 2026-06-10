# main.py — CLI দিয়ে scraper চালানোর file
import asyncio
import sys

from db.queries import run_migrations, save_profiles, save_failed_urls
from db.connection import close_pool
from exports.exporter import save_json, save_csv, save_xml, save_failures
from utils.logger import get_logger

log = get_logger("main")


async def main():
    log.info("=" * 55)
    log.info("Minimo Scraper starting")
    log.info("=" * 55)

    try:
        await run_migrations()
    except Exception as e:
        log.error(f"DB connection failed: {e}")
        sys.exit(1)

    from scrapers.minimo_scraper import MinimoScraper
    scraper = MinimoScraper(page_start=1, page_end=100, workers=2)
    data, failures = await scraper.run()

    if data:
        save_json(data)
        save_csv(data)
        save_xml(data)
    if failures:
        save_failures(failures)

    await save_profiles(data)
    await save_failed_urls(failures)

    log.info("=" * 55)
    log.info(f"Scraped  : {len(data)}")
    log.info(f"Failed   : {len(failures)}")
    log.info("=" * 55)

    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
