# db/queries.py — পরিবর্তন করবেন না
from datetime import date, datetime, timezone
from typing import List
from db.connection import get_pool
from models.scraped_item import CompanyProfile, FailedURL
from utils.logger import get_logger

log = get_logger("db.queries")

MIGRATIONS = [
    """
    CREATE TABLE IF NOT EXISTS company_list (
        id              BIGSERIAL PRIMARY KEY,
        "UUID"          TEXT DEFAULT NULL,
        "種別"          TEXT DEFAULT NULL,
        "名前"          TEXT,
        "カナ"          TEXT DEFAULT NULL,
        "郵便番号"      VARCHAR(20) DEFAULT NULL,
        "都道府県"      VARCHAR(50) DEFAULT NULL,
        "住所１"        TEXT DEFAULT NULL,
        "住所２"        TEXT DEFAULT NULL,
        "住所カナ"      TEXT DEFAULT NULL,
        "Tel1"          VARCHAR(50) DEFAULT NULL,
        "Tel2"          VARCHAR(50) DEFAULT NULL,
        "Tel3"          VARCHAR(50) DEFAULT NULL,
        "Tel4"          VARCHAR(50) DEFAULT NULL,
        "FAX"           VARCHAR(50) DEFAULT NULL,
        "URL"           TEXT DEFAULT NULL,
        "備考"          TEXT DEFAULT NULL,
        "旧社名"        TEXT DEFAULT NULL,
        "リードソース"  TEXT DEFAULT NULL,
        "リスト取得日"  DATE DEFAULT NULL,
        "オープン日"    TEXT DEFAULT NULL,
        "媒体等"        TEXT DEFAULT NULL,
        "【毎コール確認必須】良い人" TEXT DEFAULT NULL,
        "大業種"        TEXT DEFAULT NULL,
        "中業種"        TEXT DEFAULT NULL,
        source_url      TEXT DEFAULT NULL
    );
    """,
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "UUID"                       TEXT DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "種別"                       TEXT DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "カナ"                       TEXT DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "郵便番号"                   VARCHAR(20) DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "都道府県"                   VARCHAR(50) DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "住所１"                     TEXT DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "住所２"                     TEXT DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "住所カナ"                   TEXT DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "Tel1"                       VARCHAR(50) DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "Tel2"                       VARCHAR(50) DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "Tel3"                       VARCHAR(50) DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "Tel4"                       VARCHAR(50) DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "FAX"                        VARCHAR(50) DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "URL"                        TEXT DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "備考"                       TEXT DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "旧社名"                     TEXT DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "リードソース"               TEXT DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "リスト取得日"               DATE DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "オープン日"                 TEXT DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "媒体等"                     TEXT DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "【毎コール確認必須】良い人" TEXT DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "大業種"                     TEXT DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS "中業種"                     TEXT DEFAULT NULL;',
    'ALTER TABLE company_list ADD COLUMN IF NOT EXISTS source_url                   TEXT DEFAULT NULL;',
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_cl_source_url ON company_list(source_url) WHERE source_url IS NOT NULL;",
    'CREATE INDEX IF NOT EXISTS idx_cl_tel1  ON company_list("Tel1");',
    'CREATE INDEX IF NOT EXISTS idx_cl_pref  ON company_list("都道府県");',
    'CREATE INDEX IF NOT EXISTS idx_cl_media ON company_list("媒体等");',
    """
    CREATE TABLE IF NOT EXISTS failed_urls (
        id SERIAL PRIMARY KEY, url TEXT NOT NULL, error_type TEXT,
        status TEXT, message TEXT, scraper_name TEXT,
        failed_at TIMESTAMPTZ DEFAULT NOW()
    );
    """,
]

UPSERT_SQL = """
    INSERT INTO company_list (
        "UUID","種別","名前","カナ","郵便番号","都道府県","住所１","住所２","住所カナ",
        "Tel1","Tel2","Tel3","Tel4","FAX","URL","備考","旧社名","リードソース",
        "リスト取得日","オープン日","媒体等","【毎コール確認必須】良い人","大業種","中業種",
        source_url
    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25)
    ON CONFLICT (source_url) WHERE source_url IS NOT NULL DO UPDATE SET
        "UUID"=COALESCE(EXCLUDED."UUID",company_list."UUID"),"名前"=EXCLUDED."名前","カナ"=COALESCE(EXCLUDED."カナ",company_list."カナ"),
        "郵便番号"=COALESCE(EXCLUDED."郵便番号",company_list."郵便番号"),
        "都道府県"=COALESCE(EXCLUDED."都道府県",company_list."都道府県"),
        "住所１"=COALESCE(EXCLUDED."住所１",company_list."住所１"),
        "住所２"=COALESCE(EXCLUDED."住所２",company_list."住所２"),
        "住所カナ"=COALESCE(EXCLUDED."住所カナ",company_list."住所カナ"),
        "Tel1"=COALESCE(EXCLUDED."Tel1",company_list."Tel1"),
        "Tel2"=COALESCE(EXCLUDED."Tel2",company_list."Tel2"),
        "Tel3"=COALESCE(EXCLUDED."Tel3",company_list."Tel3"),
        "Tel4"=COALESCE(EXCLUDED."Tel4",company_list."Tel4"),
        "FAX"=COALESCE(EXCLUDED."FAX",company_list."FAX"),
        "URL"=COALESCE(EXCLUDED."URL",company_list."URL"),
        "備考"=COALESCE(EXCLUDED."備考",company_list."備考"),
        "旧社名"=COALESCE(EXCLUDED."旧社名",company_list."旧社名"),
        "リードソース"=COALESCE(EXCLUDED."リードソース",company_list."リードソース"),
        "リスト取得日"=COALESCE(EXCLUDED."リスト取得日",company_list."リスト取得日"),
        "オープン日"=COALESCE(EXCLUDED."オープン日",company_list."オープン日"),
        "媒体等"=COALESCE(EXCLUDED."媒体等",company_list."媒体等"),
        "【毎コール確認必須】良い人"=COALESCE(EXCLUDED."【毎コール確認必須】良い人",company_list."【毎コール確認必須】良い人"),
        "大業種"=COALESCE(EXCLUDED."大業種",company_list."大業種"),
        "中業種"=COALESCE(EXCLUDED."中業種",company_list."中業種");
"""

INSERT_FAILED = "INSERT INTO failed_urls(url,error_type,status,message,scraper_name) VALUES($1,$2,$3,$4,$5);"


def _to_tuple(p: CompanyProfile) -> tuple:
    return (
        p.uuid, p.kind, p.name or p.page_url, p.kana,
        p.postal_code, p.prefecture, p.address1, p.address2, p.address_kana,
        p.tel1, p.tel2, p.tel3, p.tel4, p.fax, p.url,
        p.biko, p.old_name, p.lead_source,
        p.list_date or date.today(), p.open_date,
        p.media, p.good_person, p.industry_major, p.industry_minor,
        p.page_url,
    )


async def run_migrations():
    pool = await get_pool()
    async with pool.acquire() as conn:
        for sql in MIGRATIONS:
            await conn.execute(sql)
    log.info("DB migrations applied")


async def save_profiles(profiles: List[CompanyProfile]):
    if not profiles:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(UPSERT_SQL, [_to_tuple(p) for p in profiles])
    log.info(f"Saved {len(profiles)} profiles")


async def save_failed_urls(failures: List[FailedURL]):
    if not failures:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            INSERT_FAILED,
            [(f.url, f.error_type, f.status, f.message, f.scraper_name) for f in failures]
        )
