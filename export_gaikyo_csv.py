"""
MongoDB の gaikyo_raw コレクションから指定月のデータを取得し、
data/YYYY_MM/yyyymm-概況.csv を生成する月次確定スクリプト。

使い方:
  python export_gaikyo_csv.py              # 前月を自動判定して出力
  python export_gaikyo_csv.py --month 202604   # 指定月
  python export_gaikyo_csv.py --month 202604 --area-code 472000
"""

from __future__ import annotations

import argparse
import calendar
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from mongo_gaikyo import get_client, get_database, get_raw_collection

JST = ZoneInfo("Asia/Tokyo")

SLOT_TO_COLUMN = {"05": "5時", "11": "11時", "17": "17時"}


def prev_month_yyyymm() -> str:
    today = datetime.now(JST).date()
    if today.month == 1:
        return f"{today.year - 1}12"
    return f"{today.year}{today.month - 1:02d}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MongoDB から月次概況CSV を生成する")
    parser.add_argument(
        "--month",
        default="",
        help="対象月 YYYYMM (省略時は前月を自動判定)",
    )
    parser.add_argument(
        "--area-code",
        default="472000",
        help="地域コード（デフォルト: 472000）",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="出力先ディレクトリ（省略時は data/YYYY_MM/）",
    )
    return parser.parse_args()


def fetch_month_records(area_code: str, yyyymm: str) -> list[dict]:
    """指定月の全レコードを MongoDB から取得する。"""
    year = yyyymm[:4]
    month_num = yyyymm[4:]
    # observed_date は 'YYYY-MM-DD' の文字列として保存されている
    prefix = f"{year}-{month_num}-"

    client = get_client()
    try:
        db = get_database(client)
        col = get_raw_collection(db)
        docs = list(
            col.find(
                {
                    "area_code": area_code,
                    "observed_date": {"$regex": f"^{prefix}"},
                },
                {"_id": 0, "observed_date": 1, "slot": 1, "text": 1},
            ).sort("observed_date", 1)
        )
    finally:
        client.close()

    return docs


def build_gaikyo_df(docs: list[dict], yyyymm: str) -> pd.DataFrame:
    """レコードリストを月日×スロットの DataFrame に変換する。"""
    year = int(yyyymm[:4])
    month = int(yyyymm[4:])
    days_in_month = calendar.monthrange(year, month)[1]

    rows: dict[str, dict[str, str]] = {}
    for d in range(1, days_in_month + 1):
        key = f"{month}/{d}"
        rows[key] = {"月日": key, "5時": "", "11時": "", "17時": ""}

    for doc in docs:
        observed_date = str(doc.get("observed_date", ""))
        slot = str(doc.get("slot", ""))
        text = str(doc.get("text", "")).strip()
        col_name = SLOT_TO_COLUMN.get(slot)
        if not col_name:
            continue
        try:
            d = date.fromisoformat(observed_date)
        except ValueError:
            continue
        key = f"{d.month}/{d.day}"
        if key in rows:
            rows[key][col_name] = text

    df = pd.DataFrame(list(rows.values()), columns=["月日", "5時", "11時", "17時"])
    return df


def resolve_output_dir(yyyymm: str, output_dir_arg: str) -> Path:
    if output_dir_arg:
        return Path(output_dir_arg)
    year = yyyymm[:4]
    month_num = yyyymm[4:]
    return Path(__file__).resolve().parent / "data" / f"{year}_{month_num}"


def main() -> None:
    args = parse_args()
    yyyymm = args.month.strip() or prev_month_yyyymm()
    if len(yyyymm) != 6 or not yyyymm.isdigit():
        raise ValueError(f"--month は YYYYMM 形式で指定してください: {yyyymm!r}")

    print(f"[INFO] 対象月: {yyyymm}  地域コード: {args.area_code}")

    docs = fetch_month_records(args.area_code, yyyymm)
    print(f"[INFO] MongoDB から {len(docs)} 件取得")

    if not docs:
        print("[WARN] データが 0 件です。MongoDB に当月データがあるか確認してください。")

    df = build_gaikyo_df(docs, yyyymm)

    out_dir = resolve_output_dir(yyyymm, args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{yyyymm}-概況.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[OK] 出力: {out_path}  ({len(df)} 行)")


if __name__ == "__main__":
    main()
