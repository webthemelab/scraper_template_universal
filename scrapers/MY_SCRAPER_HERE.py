# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  scrapers/MY_SCRAPER_HERE.py                                            ║
# ║                                                                          ║
# ║  নতুন ওয়েবসাইট স্ক্র্যাপ করতে এই ফাইলটা কপি করুন।                    ║
# ║  ফাইলের নাম পরিবর্তন করুন, যেমন: rakuten_scraper.py                    ║
# ║                                                                          ║
# ║  শুধু এই ফাইলে কাজ করলেই হবে।                                          ║
# ║  অন্য কোনো ফাইল পরিবর্তন করতে হবে না।                                 ║
# ╚══════════════════════════════════════════════════════════════════════════╝

import asyncio
import re
from typing import List, Tuple

import httpx
from bs4 import BeautifulSoup

from models.scraped_item import CompanyProfile, FailedURL
from utils.logger import get_logger
from utils.user_agents import get_weighted_ua

log = get_logger("my_scraper")

# ══════════════════════════════════════════════════════════════════════════════
# ① এখানে পরিবর্তন করুন — আপনার website অনুযায়ী
# ══════════════════════════════════════════════════════════════════════════════

# ── আপনার scraper এর নাম (DB এ media column এ save হবে) ──────────────────
SCRAPER_NAME = "my_scraper"   # ← পরিবর্তন করুন, যেমন: "rakuten", "hotpepper"

# ── List page URL — {page} এর জায়গায় page number বসবে ────────────────────
LIST_URL = "https://example.com/list?page={page}"   # ← পরিবর্তন করুন


# ══════════════════════════════════════════════════════════════════════════════
# ② List page থেকে profile URL গুলো collect করুন
# ══════════════════════════════════════════════════════════════════════════════

async def collect_profile_urls(page: int, client: httpx.AsyncClient) -> List[str]:
    """
    List page থেকে প্রতিটি company/shop এর detail page URL বের করুন।

    উদাহরণ: https://example.com/list?page=1 এ গিয়ে
    সেখান থেকে https://example.com/shop/123 টাইপের URL গুলো collect করুন।
    """
    url = LIST_URL.format(page=page)
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except Exception as exc:
        log.warning(f"List page {page} failed: {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    urls = []
    seen = set()

    # ↓ এই selector টা আপনার website অনুযায়ী পরিবর্তন করুন
    for a in soup.select("a[href*='/shop/']"):   # ← পরিবর্তন করুন
        href = a.get("href", "")
        if not href:
            continue
        # Relative URL → Absolute URL
        if href.startswith("/"):
            href = "https://example.com" + href   # ← domain পরিবর্তন করুন
        if href not in seen:
            seen.add(href)
            urls.append(href)

    log.info(f"Page {page}: {len(urls)} URLs found")
    return urls


# ══════════════════════════════════════════════════════════════════════════════
# ③ Detail page থেকে data extract করুন
# ══════════════════════════════════════════════════════════════════════════════

async def scrape_profile(url: str, client: httpx.AsyncClient) -> CompanyProfile | None:
    """
    একটি company/shop এর detail page থেকে data extract করে CompanyProfile বানান।

    শুধু যে field গুলো এই website এ পাওয়া যায় সেগুলো set করুন।
    বাকি field গুলো না দিলে automatically NULL হবে — DB তে কোনো সমস্যা নেই।
    """
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except Exception as exc:
        log.error(f"Failed: {url} — {exc}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── নাম (必須: name は NOT NULL) ──────────────────────────────────────
    name = None
    el = soup.select_one("h1.shop-name")        # ← selector পরিবর্তন করুন
    if el:
        name = el.get_text(strip=True)

    # ── 電話番号 ──────────────────────────────────────────────────────────
    tel1 = None
    el = soup.select_one("span.tel")            # ← selector পরিবর্তন করুন
    if el:
        tel1 = el.get_text(strip=True)

    # ── 住所 ──────────────────────────────────────────────────────────────
    address1 = None
    el = soup.select_one("div.address")         # ← selector পরিবর্তন করুন
    if el:
        address1 = el.get_text(strip=True)

    # ── 都道府県 ─────────────────────────────────────────────────────────
    prefecture = None
    # 住所から自動抽出する場合:
    # prefecture = extract_prefecture_from_address(address1)

    # ── URL ──────────────────────────────────────────────────────────────
    company_url = None
    el = soup.select_one("a.official-url")      # ← selector পরিবর্তন করুন
    if el:
        company_url = el.get("href")

    # ─────────────────────────────────────────────────────────────────────
    # CompanyProfile を返す
    # 取れたフィールドだけセット — 残りは自動的に NULL になる
    # ─────────────────────────────────────────────────────────────────────
    return CompanyProfile(
        page_url        = url,           # source_url (必須)
        name            = name or url,   # 名前 (NOT NULL なので fallback に url)
        tel1            = tel1,
        address1        = address1,
        prefecture      = prefecture,
        url             = company_url,
        media           = SCRAPER_NAME,
        scraper_name    = SCRAPER_NAME,

        # ↓ このサイトで取れないフィールドは書かなくて OK (NULL になる)
        # uuid, kind, kana, postal_code, address2, address_kana,
        # tel2, tel3, tel4, fax, biko, old_name, lead_source,
        # open_date, good_person, industry_major, industry_minor
    )
