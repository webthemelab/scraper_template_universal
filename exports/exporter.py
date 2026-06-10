# exports/exporter.py
import json
import csv
import xml.etree.ElementTree as ET
from datetime import date
from typing import List
from models.scraped_item import CompanyProfile
from utils.logger import get_logger

log = get_logger("exporter")

COLUMNS = [
    ("UUID",                         "uuid"),
    ("種別",                         "kind"),
    ("名前",                         "name"),
    ("カナ",                         "kana"),
    ("郵便番号",                     "postal_code"),
    ("都道府県",                     "prefecture"),
    ("住所１",                       "address1"),
    ("住所２",                       "address2"),
    ("住所カナ",                     "address_kana"),
    ("Tel1",                         "tel1"),
    ("Tel2",                         "tel2"),
    ("Tel3",                         "tel3"),
    ("Tel4",                         "tel4"),
    ("FAX",                          "fax"),
    ("URL",                          "url"),
    ("備考",                         "biko"),
    ("旧社名",                       "old_name"),
    ("リードソース",                 "lead_source"),
    ("リスト取得日",                 "_today"),
    ("オープン日",                   "open_date"),
    ("媒体等",                       "media"),
    ("【毎コール確認必須】良い人",   "good_person"),
    ("大業種",                       "industry_major"),
    ("中業種",                       "industry_minor"),
]


def _to_row(p: CompanyProfile) -> dict:
    today = date.today().strftime("%Y-%m-%d")
    row = {}
    for jp_key, py_key in COLUMNS:
        if py_key == "_today":
            row[jp_key] = today
        else:
            val = getattr(p, py_key, None)
            if val is None:
                row[jp_key] = ""
            elif hasattr(val, "isoformat"):
                row[jp_key] = val.isoformat()
            else:
                row[jp_key] = str(val)
    return row


def save_json(data: List[CompanyProfile], path: str = "result.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump([_to_row(p) for p in data], f, ensure_ascii=False, indent=2)
    log.info(f"Saved JSON → {path} ({len(data)} records)")


def save_csv(data: List[CompanyProfile], path: str = "result.csv"):
    if not data:
        return
    rows = [_to_row(p) for p in data]
    fieldnames = [c[0] for c in COLUMNS]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    log.info(f"Saved CSV  → {path} ({len(data)} records)")


def save_xml(data: List[CompanyProfile], path: str = "result.xml"):
    root = ET.Element("company_list")
    for p in data:
        item = ET.SubElement(root, "item")
        for jp_key, val in _to_row(p).items():
            safe_tag = (
                jp_key
                .replace("【", "").replace("】", "")
                .replace(" ", "_").replace("　", "_")
            )
            child = ET.SubElement(item, safe_tag)
            child.text = val
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    log.info(f"Saved XML  → {path} ({len(data)} records)")


def save_failures(failures, path: str = "failed_urls.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            [f.model_dump() for f in failures],
            f, ensure_ascii=False, indent=2, default=str
        )
    log.info(f"Saved failures → {path} ({len(failures)} entries)")
