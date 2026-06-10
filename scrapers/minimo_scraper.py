# scrapers/minimo_scraper.py
import asyncio
import re
from datetime import date
from typing import List, Tuple
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from models.scraped_item import SalonProfile, FailedURL
from utils.logger import get_logger
from utils.user_agents import get_weighted_ua

log = get_logger("minimo")

LIST_BASE_URL = "https://minimodel.jp/list/1/0/c0/1?p={page}"

# ── 都道府県 → 備考 (営業所) マッピング ──────────────────────
PREF_TO_BIKO = {
    "東京都": "東京本社", "神奈川県": "東京本社",
    "千葉県": "東京本社", "埼玉県": "東京本社",
    "茨城県": "東京郊外", "群馬県": "東京郊外", "栃木県": "東京郊外",
    "愛知県": "名古屋営業所", "岐阜県": "名古屋営業所", "三重県": "名古屋営業所",
    "大阪府": "大阪営業所", "京都府": "大阪営業所", "奈良県": "大阪営業所",
    "兵庫県": "大阪営業所", "滋賀県": "大阪営業所",
    "宮城県": "仙台・盛岡営業所", "福島県": "仙台・盛岡営業所",
    "山形県": "仙台・盛岡営業所", "岩手県": "仙台・盛岡営業所",
    "青森県": "仙台・盛岡営業所", "秋田県": "仙台・盛岡営業所",
    "福岡県": "福岡営業所", "佐賀県": "福岡営業所",
    "長崎県": "福岡営業所", "熊本県": "福岡営業所", "大分県": "福岡営業所",
}

# 山口県・鹿児島県の特例市区
YAMAGUCHI_FUKUOKA = {"宇部市", "山陽小野田市", "下関市"}
KAGOSHIMA_FUKUOKA = {"鹿児島市", "霧島市", "姶良市"}

# 都道府県リスト (住所から抽出用)
ALL_PREFS = list(PREF_TO_BIKO.keys()) + [
    "北海道", "山口県", "鹿児島県", "沖縄県",
    "山梨県", "長野県", "静岡県", "新潟県",
    "富山県", "石川県", "福井県", "鳥取県",
    "島根県", "岡山県", "広島県", "香川県",
    "愛媛県", "高知県", "徳島県", "佐賀県",
    "宮崎県", "和歌山県", "岡山県",
]


def determine_biko(prefecture: str | None, address: str | None) -> str:
    """
    都道府県と住所から営業所 (備考) を判定する。
    """
    if not prefecture:
        return "未判定"

    # 特例: 山口県
    if prefecture == "山口県":
        if address:
            for city in YAMAGUCHI_FUKUOKA:
                if city in address:
                    return "福岡営業所"
        return "ZOOM"

    # 特例: 鹿児島県
    if prefecture == "鹿児島県":
        if address:
            for city in KAGOSHIMA_FUKUOKA:
                if city in address:
                    return "福岡営業所"
        return "ZOOM"

    # 通常マッピング
    biko = PREF_TO_BIKO.get(prefecture)
    if biko:
        return biko

    return "ZOOM"


def extract_prefecture(address: str | None) -> str | None:
    """住所文字列から都道府県を抽出する。"""
    if not address:
        return None
    for pref in ALL_PREFS:
        if pref in address:
            return pref
    return None


def extract_postal_code(address: str | None) -> str | None:
    """住所から郵便番号を抽出する (〒000-0000 形式)。"""
    if not address:
        return None
    m = re.search(r"〒?\s*(\d{3}[-－]\d{4})", address)
    return m.group(1) if m else None


def normalize_url(url: str | None) -> str | None:
    """
    URLルール:
    - クエリ除去: ?以降を削除
    - 末尾スラッシュ除去
    - ドメインベースに正規化
    """
    if not url:
        return None
    try:
        parsed = urlparse(url)
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        clean = clean.rstrip("/")
        # /menu など余分パス除去 (/r/XXXXX のみ残す)
        m = re.match(r"(https://minimodel\.jp/r/[A-Za-z0-9]+)", clean)
        if m:
            return m.group(1)
        return clean
    except Exception:
        return url


def clean_text(text: str | None) -> str | None:
    """不要文字 ( , " ' ` ) を除去する。"""
    if not text:
        return None
    for ch in [",", '"', "'", "`"]:
        text = text.replace(ch, "")
    return text.strip() or None


def clean_profile_url(href: str) -> str:
    """/r/XXXXX/menu → https://minimodel.jp/r/XXXXX"""
    m = re.match(r"(/r/[A-Za-z0-9]+)", href)
    if m:
        return "https://minimodel.jp" + m.group(1)
    return ""


# ── Tel 分類 ──────────────────────────────────────────────────
def classify_phones(phones: list[str]) -> Tuple[str | None, str | None]:
    tel1 = tel2 = None
    for p in phones:
        digits = re.sub(r"\D", "", p)
        if digits.startswith("0120") or digits.startswith("0800"):
            if tel2 is None:
                tel2 = p
        else:
            if tel1 is None:
                tel1 = p
    return tel1, tel2


# ── Selenium で電話番号取得 ────────────────────────────────────
def get_phone_numbers(url: str) -> Tuple[str | None, str | None]:
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    try:
        wait = WebDriverWait(driver, 15)
        driver.get(url)
        tel_link = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, '/tel')]"))
        )
        tel_link.click()
        boxes = wait.until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, "div[class*='__emphasisBox']")
            )
        )
        phones = [b.text.strip() for b in boxes if b.text.strip()]
        return classify_phones(phones)
    except Exception as exc:
        log.warning(f"Phone取得失敗 ({url}): {str(exc)[:120]}")
        return None, None
    finally:
        driver.quit()


# ── List page から URL 収集 ───────────────────────────────────
async def collect_profile_urls_from_page(
    page: int, client: httpx.AsyncClient
) -> List[str]:
    url = LIST_BASE_URL.format(page=page)
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except Exception as exc:
        log.warning(f"List page {page} 取得失敗: {exc}")
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    seen, urls = set(), []
    for a in soup.select("a[href*='/r/']"):
        clean = clean_profile_url(a.get("href", ""))
        if clean and clean not in seen:
            seen.add(clean)
            urls.append(clean)
    log.info(f"Page {page}: {len(urls)} unique profiles found")
    return urls


# ── Profile scrape ────────────────────────────────────────────
async def scrape_profile(url: str, client: httpx.AsyncClient) -> SalonProfile | None:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except Exception as exc:
        log.error(f"Profile 取得失敗 {url}: {exc}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # 店名
    shop_name = None
    el = soup.select_one("div[class*='__salonName']")
    if el:
        a = el.select_one("a")
        shop_name = clean_text((a or el).get_text(strip=True))

    # 住所 (raw)
    raw_address = None
    el = soup.select_one("div[class*='__salonAddress']")
    if el:
        raw_address = re.sub(
            r"\s+", " ",
            el.get_text(separator=" ", strip=True)
              .replace("( Map )", "").replace("( マップ )", "")
              .replace("(地図)", "").replace("地図", "")
              .replace("Map", "")
        ).strip() or None

    # 都道府県・郵便番号・住所１
    prefecture  = extract_prefecture(raw_address)
    postal_code = extract_postal_code(raw_address)

    # 住所１ = 郵便番号・都道府県を除いたクリーン住所
    address1 = raw_address
    if address1 and postal_code:
        address1 = address1.replace(f"〒{postal_code}", "").replace(postal_code, "").strip()
    if address1 and prefecture:
        address1 = address1.replace(prefecture, "").strip()
    address1 = clean_text(address1)

    # 備考 = 営業所判定
    biko = determine_biko(prefecture, raw_address)

    # URL 正規化
    normalized_url = normalize_url(url)

    # Tel (Selenium)
    tel1, tel2 = await asyncio.to_thread(get_phone_numbers, url)
    log.info(f"Tel1={tel1} Tel2={tel2} 備考={biko} → {url}")

    return SalonProfile(
        page_url    = url,
        name        = shop_name,   # CompanyProfile の "名前" フィールド
        postal_code = postal_code,
        prefecture  = prefecture,
        address1    = address1,
        tel1        = tel1,
        tel2        = tel2,
        url         = normalized_url,
        biko        = biko,
        media       = "minimo",
    )


# ── Main Scraper Class ────────────────────────────────────────
class MinimoScraper:
    name = "minimo"

    def __init__(self, page_start=1, page_end=100, workers=2):
        self.page_start = page_start
        self.page_end   = page_end
        self.workers    = workers
        self._profiles: List[SalonProfile] = []
        self._failures: List[FailedURL]    = []

    async def run(self):
        headers = {"User-Agent": get_weighted_ua()}
        async with httpx.AsyncClient(
            headers=headers, timeout=30, follow_redirects=True
        ) as client:
            all_urls, seen = [], set()
            for page in range(self.page_start, self.page_end + 1):
                urls = await collect_profile_urls_from_page(page, client)
                if not urls:
                    log.info(f"Page {page}: empty — stopping")
                    break
                for u in urls:
                    if u not in seen:
                        seen.add(u)
                        all_urls.append(u)
                await asyncio.sleep(1.5)

            log.info(f"Total unique URLs: {len(all_urls)}")
            semaphore = asyncio.Semaphore(self.workers)

            async def worker(url):
                async with semaphore:
                    import random
                    await asyncio.sleep(random.uniform(2, 5))
                    profile = await scrape_profile(url, client)
                    if profile:
                        self._profiles.append(profile)
                        log.info(f"✓ {profile.shop_name or url}")
                    else:
                        self._failures.append(FailedURL(
                            url=url, error_type="scrape_error",
                            message="parse or fetch failed", scraper_name=self.name,
                        ))

            await asyncio.gather(*[worker(u) for u in all_urls])

        log.info(f"Done — {len(self._profiles)} ok, {len(self._failures)} failed")
        return self._profiles, self._failures
