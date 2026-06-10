# models/scraped_item.py
# ─────────────────────────────────────────────────────────────────────────────
# company_list テーブルの全カラムに対応した共通モデル。
# スクレイパーごとに必要なフィールドだけセットし、残りは None(NULL) になる。
# ─────────────────────────────────────────────────────────────────────────────

from datetime import datetime, date, timezone
from typing import Optional
from pydantic import BaseModel, field_validator, model_validator


class ScrapedItem(BaseModel):
    page_url:     str
    domain:       str = ""
    scraped_at:   Optional[datetime] = None
    scraper_name: str = ""

    @model_validator(mode="after")
    def _set_defaults(self):
        if not self.scraped_at:
            self.scraped_at = datetime.now(timezone.utc)
        if not self.domain and self.page_url:
            from urllib.parse import urlparse
            self.domain = urlparse(self.page_url).netloc
        return self

    class Config:
        extra = "allow"


class CompanyProfile(ScrapedItem):
    """
    company_list テーブルの全カラムに対応する汎用モデル。
    どのウェブサイトをスクレイピングするときも、このモデルを使う。
    必要なフィールドだけセットし、不要なフィールドは None のまま(DB では NULL) にする。
    """
    scraper_name: str = ""

    # ── 基本情報 ──────────────────────────────────────────────
    uuid:         Optional[str] = None   # UUID
    kind:         Optional[str] = None   # 種別
    name:         Optional[str] = None   # 名前  ※ NOT NULL だが model は Optional で受け取る
    kana:         Optional[str] = None   # カナ

    # ── 住所 ─────────────────────────────────────────────────
    postal_code:  Optional[str] = None   # 郵便番号
    prefecture:   Optional[str] = None   # 都道府県
    address1:     Optional[str] = None   # 住所１
    address2:     Optional[str] = None   # 住所２
    address_kana: Optional[str] = None   # 住所カナ

    # ── 電話 / FAX / URL ─────────────────────────────────────
    tel1:         Optional[str] = None   # Tel1
    tel2:         Optional[str] = None   # Tel2
    tel3:         Optional[str] = None   # Tel3
    tel4:         Optional[str] = None   # Tel4
    fax:          Optional[str] = None   # FAX
    url:          Optional[str] = None   # URL

    # ── その他情報 ────────────────────────────────────────────
    biko:         Optional[str] = None   # 備考
    old_name:     Optional[str] = None   # 旧社名
    lead_source:  Optional[str] = None   # リードソース
    list_date:    Optional[date] = None  # リスト取得日
    open_date:    Optional[str] = None   # オープン日
    media:        Optional[str] = None   # 媒体等
    good_person:  Optional[str] = None   # 【毎コール確認必須】良い人
    industry_major: Optional[str] = None # 大業種
    industry_minor: Optional[str] = None # 中業種

    # ── source URL (DB UNIQUE KEY) ────────────────────────────
    # page_url が source_url として DB に入る (ScrapedItem から継承)

    @field_validator("name", "address1", "address2", "url", mode="before")
    @classmethod
    def clean_str(cls, v):
        if isinstance(v, str):
            for ch in [",", '"', "'", "`"]:
                v = v.replace(ch, "")
            return v.strip() or None
        return v


# ── 後方互換: minimo 等の既存スクレイパーが SalonProfile を import している場合 ──
class SalonProfile(CompanyProfile):
    """後方互換エイリアス。新規スクレイパーは CompanyProfile を使うこと。"""
    scraper_name: str = "minimo"
    media: Optional[str] = "minimo"

    # SalonProfile 固有の旧フィールド名 → CompanyProfile フィールドへマッピング
    @property
    def shop_name(self):   return self.name
    @property
    def biko_old(self):    return self.biko

    @model_validator(mode="before")
    @classmethod
    def _compat_fields(cls, data):
        """旧フィールド名 (shop_name, biko) を新フィールド名にコピー。"""
        if isinstance(data, dict):
            if "shop_name" in data and "name" not in data:
                data["name"] = data.pop("shop_name")
        return data


class FailedURL(BaseModel):
    url:          str
    error_type:   str
    status:       Optional[str] = None
    message:      str
    failed_at:    Optional[datetime] = None
    scraper_name: str = ""

    @model_validator(mode="after")
    def _set_time(self):
        if not self.failed_at:
            self.failed_at = datetime.now(timezone.utc)
        return self
