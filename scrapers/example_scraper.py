# scrapers/example_scraper.py
# ─────────────────────────────────────────────────────────────────────────────
# 新しいウェブサイト用スクレイパーのテンプレート。
#
# ルール:
#   1. CompanyProfile を import して使う。
#   2. そのサイトで取得できるフィールドだけをセットする。
#   3. 取得できないフィールドは何もしなければ自動的に None (DB: NULL) になる。
#   4. page_url と name は必ずセットする (name は DB の NOT NULL カラム)。
# ─────────────────────────────────────────────────────────────────────────────

from models.scraped_item import CompanyProfile, FailedURL
from utils.logger import get_logger

log = get_logger("example_scraper")


async def scrape_one(url: str) -> CompanyProfile | None:
    """
    1 ページをスクレイピングして CompanyProfile を返す実装例。
    実際のスクレイパーではここに httpx / BeautifulSoup / Playwright 等を書く。
    """

    # ── 例: 取得できたフィールドだけセット ───────────────────────────────
    # このサイトでは 名前 / 電話 / 都道府県 / URL だけ取れる想定
    return CompanyProfile(
        page_url       = url,                   # source_url (必須)
        name           = "サンプル株式会社",    # 名前      (必須: NOT NULL)
        tel1           = "03-1234-5678",        # Tel1
        prefecture     = "東京都",              # 都道府県
        url            = "https://example.com", # URL
        media          = "example_site",        # 媒体等 (スクレイパー識別子)
        scraper_name   = "example_scraper",

        # ↓ 取得できないフィールドはセットしなくて OK → 自動的に NULL になる
        # uuid, kind, kana, postal_code, address1, address2, address_kana,
        # tel2, tel3, tel4, fax, biko, old_name, lead_source, open_date,
        # good_person, industry_major, industry_minor
    )


# ── 別サイトの例: もっと多くのフィールドが取れる場合 ─────────────────────────
async def scrape_full_info(url: str) -> CompanyProfile | None:
    """より多くの情報が取れるサイトの例。"""
    return CompanyProfile(
        page_url        = url,
        name            = "フルデータ株式会社",
        kana            = "フルデータカブシキガイシャ",
        postal_code     = "100-0001",
        prefecture      = "東京都",
        address1        = "千代田区千代田1-1",
        address2        = "○○ビル 3F",
        address_kana    = "チヨダクチヨダ",
        tel1            = "03-9999-0001",
        tel2            = "0120-999-001",
        tel3            = None,   # 明示的に None でも OK
        tel4            = None,
        fax             = "03-9999-0002",
        url             = "https://fulldata.example.com",
        biko            = "東京営業所",
        old_name        = "旧社名株式会社",
        lead_source     = "web検索",
        open_date       = "2020-04-01",
        media           = "fulldata_site",
        good_person     = "田中部長",
        industry_major  = "IT",
        industry_minor  = "SaaS",
        scraper_name    = "fulldata_scraper",
    )
