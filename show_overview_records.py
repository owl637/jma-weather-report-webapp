from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from fetch_overview_to_mongo import extract_current_overview_line
from mongo_gaikyo import get_client, get_database_name, get_raw_collection

JST = ZoneInfo("Asia/Tokyo")
DEFAULT_URL = "https://www.jma.go.jp/bosai/forecast/data/overview_forecast/472000.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MongoDBに保存した府県天気概況を確認する")
    parser.add_argument("--area-code", default="472000", help="地域コード")
    parser.add_argument("--days", type=int, default=3, help="表示する日数（直近）")
    parser.add_argument("--limit", type=int, default=15, help="最大表示件数")
    parser.add_argument("--with-live", action="store_true", help="現在のJMA JSON本文1行も表示する")
    parser.add_argument("--url", default=DEFAULT_URL, help="概況JSONのURL")
    return parser.parse_args()


def format_dt(dt: object) -> str:
    if isinstance(dt, datetime):
        return dt.astimezone(JST).strftime("%Y-%m-%d %H:%M:%S")
    return ""


def main() -> None:
    args = parse_args()

    start_date = (datetime.now(JST).date() - timedelta(days=max(args.days - 1, 0))).isoformat()

    client = get_client()
    try:
        db = client[get_database_name()]
        raw = get_raw_collection(db)
        cursor = (
            raw.find(
                {
                    "area_code": args.area_code,
                    "observed_date": {"$gte": start_date},
                },
                {
                    "_id": 0,
                    "observed_date": 1,
                    "slot": 1,
                    "area_name": 1,
                    "text": 1,
                    "fetched_at": 1,
                    "updated_at": 1,
                },
            )
            .sort([("observed_date", -1), ("slot", -1)])
            .limit(args.limit)
        )
        rows = list(cursor)
    finally:
        client.close()

    print(f"[INFO] area_code={args.area_code} start_date={start_date} rows={len(rows)}")
    for row in rows:
        observed_date = str(row.get("observed_date", ""))
        slot = str(row.get("slot", ""))
        area_name = str(row.get("area_name", ""))
        text = str(row.get("text", "")).strip()
        fetched_at = format_dt(row.get("fetched_at"))
        updated_at = format_dt(row.get("updated_at"))
        print("-" * 80)
        print(f"date={observed_date} slot={slot} area={area_name}")
        print(f"fetched_at={fetched_at} updated_at={updated_at}")
        print(f"text={text}")

    if args.with_live:
        payload = requests.get(args.url, timeout=30).json()
        live_text = extract_current_overview_line(str(payload.get("text", "")))
        live_dt = str(payload.get("reportDatetime", "")).strip()
        print("-" * 80)
        print(f"[LIVE] reportDatetime={live_dt}")
        print(f"[LIVE] text={live_text}")


if __name__ == "__main__":
    main()
