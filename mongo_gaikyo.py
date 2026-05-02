from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError

JST = ZoneInfo("Asia/Tokyo")
DEFAULT_DB_NAME = "jma_weather"
DEFAULT_RETENTION_DAYS = 90
RAW_COLLECTION_NAME = "gaikyo_raw"
MONTHLY_META_COLLECTION_NAME = "gaikyo_monthly_meta"


class MongoConfigError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _load_env_file() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=env_path, override=False)


def get_mongo_uri() -> str:
    _load_env_file()
    mongo_uri = os.environ.get("MONGODB_URI", "").strip()
    if not mongo_uri:
        raise MongoConfigError(
            "MONGODB_URI が未設定です。.env を使う場合はプロジェクト直下の .env に"
            " MONGODB_URI=... を記載してください。"
        )
    return mongo_uri


def get_database_name() -> str:
    _load_env_file()
    return os.environ.get("MONGODB_DB", DEFAULT_DB_NAME).strip() or DEFAULT_DB_NAME


def get_client() -> MongoClient:
    return MongoClient(get_mongo_uri(), appname="jma-gaikyo")


def get_database(client: MongoClient | None = None) -> Database:
    mongo_client = get_client() if client is None else client
    return mongo_client[get_database_name()]


def get_raw_collection(db: Database) -> Collection:
    return db[RAW_COLLECTION_NAME]


def get_monthly_meta_collection(db: Database) -> Collection:
    return db[MONTHLY_META_COLLECTION_NAME]


def compute_slot(now_jst: datetime | None = None) -> str:
    current = now_jst.astimezone(JST) if now_jst else datetime.now(JST)
    hour = current.hour
    if hour < 8:
        return "05"
    if hour < 14:
        return "11"
    return "17"


def compute_expire_at(fetched_at: datetime, retention_days: int = DEFAULT_RETENTION_DAYS) -> datetime:
    return fetched_at + timedelta(days=retention_days)


def _to_observed_date_text(observed_date: date | str) -> str:
    if isinstance(observed_date, date):
        return observed_date.isoformat()
    return str(observed_date).strip()


def build_doc_hash(area_code: str, observed_date: date | str, slot: str, text: str) -> str:
    observed_date_text = _to_observed_date_text(observed_date)
    seed = f"{area_code}|{observed_date_text}|{slot}|{text}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def ensure_indexes(db: Database) -> None:
    raw = get_raw_collection(db)
    raw.create_index(
        [("area_code", ASCENDING), ("observed_date", ASCENDING), ("slot", ASCENDING)],
        unique=True,
        name="uq_area_date_slot",
    )
    raw.create_index(
        [("expire_at", ASCENDING)],
        expireAfterSeconds=0,
        name="ttl_expire_at",
    )
    raw.create_index(
        [("area_code", ASCENDING), ("observed_date", ASCENDING)],
        name="idx_area_observed_date",
    )

    monthly = get_monthly_meta_collection(db)
    monthly.create_index(
        [("yyyymm", ASCENDING)],
        unique=True,
        name="uq_yyyymm",
    )


def upsert_raw_overview(
    db: Database,
    *,
    area_code: str,
    area_name: str,
    observed_date: date | str,
    text: str,
    source_url: str,
    slot: str | None = None,
    fetched_at: datetime | None = None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> bool:
    if not text.strip():
        return False

    current_fetched_at = fetched_at or datetime.now(timezone.utc)
    current_slot = slot or compute_slot(current_fetched_at.astimezone(JST))
    observed_date_text = _to_observed_date_text(observed_date)
    doc_hash = build_doc_hash(area_code, observed_date_text, current_slot, text)

    doc = {
        "area_code": area_code,
        "area_name": area_name,
        "observed_date": observed_date_text,
        "slot": current_slot,
        "text": text.strip(),
        "source_url": source_url,
        "fetched_at": current_fetched_at,
        "expire_at": compute_expire_at(current_fetched_at, retention_days=retention_days),
        "hash": doc_hash,
        "updated_at": datetime.now(timezone.utc),
    }

    raw = get_raw_collection(db)
    result = raw.update_one(
        {
            "area_code": area_code,
            "observed_date": observed_date_text,
            "slot": current_slot,
        },
        {
            "$set": doc,
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )
    return bool(result.upserted_id) or result.modified_count > 0


def ping_database(client: MongoClient) -> None:
    try:
        client.admin.command("ping")
    except PyMongoError as exc:
        raise RuntimeError(f"MongoDBへの接続確認に失敗しました: {exc}") from exc
