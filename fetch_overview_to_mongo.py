from __future__ import annotations

import argparse
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from mongo_gaikyo import (
    DEFAULT_RETENTION_DAYS,
    ensure_indexes,
    get_client,
    get_database_name,
    upsert_raw_overview,
)

JST = ZoneInfo("Asia/Tokyo")
DEFAULT_URL = "https://www.jma.go.jp/bosai/forecast/data/overview_forecast/472000.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="府県天気概況を取得して MongoDB に保存する")
    parser.add_argument("--url", default=DEFAULT_URL, help="概況JSONのURL")
    parser.add_argument("--area-code", default="472000", help="地域コード")
    parser.add_argument("--area-name", default="大東島地方", help="地域名")
    parser.add_argument("--slot", choices=["05", "11", "17"], default=None, help="保存スロットを明示指定")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help="生データ保持日数（TTL）",
    )
    return parser.parse_args()


def normalize_line(text: str) -> str:
    t = text.replace("\u3000", " ")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"(?<=[\u3040-\u30ff\u3400-\u9fff])\s+(?=[\u3040-\u30ff\u3400-\u9fff])", "", t)
    t = t.replace("地方 ", "地方")
    return t


def extract_current_overview_line(full_text: str) -> str:
    for raw in full_text.splitlines():
        line = normalize_line(raw)
        if line:
            return line
    return ""


def compute_slot_from_report_datetime(report_dt_jst: datetime) -> str:
    hour = report_dt_jst.hour
    if hour < 8:
        return "05"
    if hour < 14:
        return "11"
    return "17"


def fetch_payload(url: str) -> dict:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("JSONの形式が不正です（dictではありません）")
    return payload


def main() -> None:
    args = parse_args()
    payload = fetch_payload(args.url)

    report_datetime_text = str(payload.get("reportDatetime", "")).strip()
    text = str(payload.get("text", "")).strip()

    if not report_datetime_text:
        raise ValueError("reportDatetime が見つかりません")
    if not text:
        raise ValueError("text が見つかりません")

    report_dt = datetime.fromisoformat(report_datetime_text)
    report_dt_jst = report_dt.astimezone(JST)
    slot = args.slot or compute_slot_from_report_datetime(report_dt_jst)

    current_line = extract_current_overview_line(text)
    if not current_line:
        raise ValueError("保存対象の概況文1行を抽出できませんでした")

    client = get_client()
    try:
        db = client[get_database_name()]
        ensure_indexes(db)
        changed = upsert_raw_overview(
            db,
            area_code=args.area_code,
            area_name=args.area_name,
            observed_date=report_dt_jst.date(),
            text=current_line,
            source_url=args.url,
            slot=slot,
            fetched_at=datetime.now(JST).astimezone(),
            retention_days=args.retention_days,
        )
    finally:
        client.close()

    status = "inserted/updated" if changed else "unchanged"
    print(
        f"[OK] {status} area={args.area_code} date={report_dt_jst.date().isoformat()} "
        f"slot={slot} line={current_line}"
    )


if __name__ == "__main__":
    main()
