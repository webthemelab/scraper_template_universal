# scrapers/example_playwright.py
# Copy this for JS-heavy sites. Only parse_page() and start_urls change.

from playwright.async_api import Page
from scrapers.playwright_scraper import PlaywrightScraper
from models.scraped_item import SalonProfile


class ExamplePlaywrightScraper(PlaywrightScraper):
    name = "example_playwright"

    start_urls = [
        "https://example.com/profile/1",
        "https://example.com/profile/2",
    ]

    async def parse_page(self, page: Page, url: str) -> SalonProfile:
        salon_name = await page.text_content(".salon-name") or ""
        staff_name = await page.text_content(".staff-name") or ""
        location   = await page.text_content(".address")   or ""

        return SalonProfile(
            page_url   = url,
            salon_name = salon_name.strip(),
            staff_name = staff_name.strip(),
            location   = location.strip(),
        )
