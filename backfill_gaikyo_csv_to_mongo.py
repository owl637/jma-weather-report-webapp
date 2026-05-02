from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from mongo_gaikyo import (
    DEFAULT_RETENTION_DAYS,
    ensure_indexes,
    get_client,
    get_database,
    upsert_raw_overview,
)

COLUMN_TO_SLOT = {
    "5時": "05",
    "11時": "11",
    "17時": "17",
}


def normalize_line(text: str) -> str:
    t = str(text).replace("\u3000", " ")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"(?<=[\u3040-\u30ff\u3400-\u9fff])\s+(?=[\u3040-\u30ff\u3400-\u9fff])", "", t)
    t = t.replace("地方 ", "地方")
    return t


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="概況CSVをMongoDBへバックフィルする")
    parser.add_argument("--month", required=True, help="対象月 YYYYMM")
    parser.add_argument("--csv", default="", help="入力CSVパス（省略時: data/YYYY_MM/YYYYMM-概況.csv）")
    parser.add_argument("--area-code", default="472000", help="地域コード")
    parser.add_argument("--area-name", default="大東島地方", help="地域名")
    parser.add_argument("--source-url", default="manual://csv-backfill", help="保存する source_url")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help="TTL保持日数",
    )
    return parser.parse_args()


def resolve_csv_path(month: str, csv_arg: str) -> Path:
    if csv_arg:
        return Path(csv_arg)
    year = month[:4]
    mon = month[4:]
    return Path(__file__).resolve().parent / "data" / f"{year}_{mon}" / f"{month}-概況.csv"


def parse_observed_date(month: str, month_day: str) -> str:
    parts = str(month_day).strip().split("/")
    if len(parts) != 2:
        raise ValueError(f"月日形式が不正です: {month_day}")
    m = int(parts[0])
    d = int(parts[1])
    y = int(month[:4])
    return f"{y:04d}-{m:02d}-{d:02d}"


def main() -> None:
    args = parse_args()
    month = args.month.strip()
    if len(month) != 6 or not month.isdigit():
        raise ValueError(f"--month は YYYYMM 形式で指定してください: {month!r}")

    csv_path = resolve_csv_path(month, args.csv)
    if not csv_path.exists():
        raise FileNotFoundError(f"入力CSVが見つかりません: {csv_path}")

    df = pd.read_csv(csv_path)
    required = {"月日", "5時", "11時", "17時"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV列が不足しています: {sorted(missing)}")

    client = get_client()
    inserted = 0
    skipped = 0
    try:
        db = get_database(client)
        ensure_indexes(db)

        for _, row in df.iterrows():
            observed_date = parse_observed_date(month, str(row["月日"]))
            for col, slot in COLUMN_TO_SLOT.items():
                text = normalize_line(str(row.get(col, "")))
                if not text or text.lower() == "nan":
                    skipped += 1
                    continue

                # 手動補完データなので fetched_at は実行時UTCで記録
                ok = upsert_raw_overview(
                    db,
                    area_code=args.area_code,
                    area_name=args.area_name,
                    observed_date=observed_date,
                    text=text,
                    source_url=args.source_url,
                    slot=slot,
                    fetched_at=datetime.now(timezone.utc),
                    retention_days=args.retention_days,
                )
                if ok:
                    inserted += 1
                else:
                    skipped += 1
    finally:
        client.close()

    print(f"[OK] backfill completed month={month} inserted_or_updated={inserted} skipped={skipped}")


if __name__ == "__main__":
    main()
