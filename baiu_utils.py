"""沖縄梅雨入り確定値の取得と文章生成ユーティリティ"""
from __future__ import annotations

import re
from datetime import date
from io import StringIO
from typing import Optional

import pandas as pd
import requests

BAIU_OKINAWA_URL = "https://www.data.jma.go.jp/cpd/baiu/kako_baiu01.html"
BAIU_SOKUHOU_URL = "https://www.data.jma.go.jp/cpd/baiu/sokuhou_baiu.html"


def _parse_md(text: str) -> Optional[tuple[int, int]]:
    """「5月22日頃」→ (5, 22)。解析不能な値はNone。"""
    t = str(text).strip()
    if t in {"", "－", "-", "　", "nan"}:
        return None
    m = re.search(r"(\d+)月(\d+)日", t)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _diff_days(a: tuple[int, int], b: tuple[int, int]) -> int:
    """a - b の日数差（2000年ベース）。"""
    return (date(2000, a[0], a[1]) - date(2000, b[0], b[1])).days


def _parse_year(yr_str: str) -> Optional[int]:
    """年号文字列を西暦int に変換。解析不能はNone。昭和/平成/令和/西暦に対応。"""
    t = str(yr_str).strip()
    m = re.search(r"(\d{4})年", t)
    if m:
        return int(m.group(1))
    m = re.search(r"令和\s*(\d+)年", t)
    if m:
        return 2018 + int(m.group(1))
    m = re.search(r"平成\s*(\d+)年", t)
    if m:
        return 1988 + int(m.group(1))
    m = re.search(r"昭和\s*(\d+)年", t)
    if m:
        return 1925 + int(m.group(1))
    return None


def _fetch_baiu_df() -> pd.DataFrame:
    """
    沖縄梅雨入り・梅雨明け確定値ページを取得し DataFrame を返す。
    返値の columns: 年号 (str), 梅雨入り (str), 梅雨明け (str)
    """
    resp = requests.get(BAIU_OKINAWA_URL, timeout=30)
    resp.raise_for_status()
    # Content-Typeヘッダがエンコーディングを返さない場合があるためUTF-8で明示デコード
    html = resp.content.decode("utf-8", errors="replace")
    tables = pd.read_html(StringIO(html))
    for df in tables:
        df = df.dropna(how="all")
        if df.shape[1] < 3:
            continue
        # MultiIndex columns の場合はフラット化（下位レベルを使用）
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [str(c[-1]) for c in df.columns]
        else:
            df.columns = [str(c) for c in df.columns]
        col0 = df.iloc[:, 0].astype(str)
        if not col0.str.contains(r"\d{4}年|平\s*年", regex=True).any():
            continue
        result = df.iloc[:, :3].copy()
        result.columns = ["年号", "梅雨入り", "梅雨明け"]
        return result
    raise ValueError("梅雨データテーブルが見つかりませんでした")


def build_baiu_entry_sentence(year: int, report_month: int) -> str:
    """
    指定年・月の梅雨入り文を返す。

    確定値ページ (kako_baiu01.html) にデータがなければ
    速報値ページ (sokuhou_baiu.html) にフォールバックする。

    - 梅雨入りが report_month でなければ空文字を返す。
    - データ取得失敗時も空文字を返す。
    - 過去最早/最晩の場合は記録文を付記する。

    返値例:
        「なお、沖縄地方は5月22日ごろに梅雨入りしたとみられ＊、平年より12日遅く、昨年より1日遅い梅雨入りとなった。」
        「なお、…早い梅雨入りとなった。統計を開始した1951年以降、最も早い梅雨入りとなった。」
    """
    entry: Optional[tuple[int, int]] = None
    normal_entry: Optional[tuple[int, int]] = None
    prev_entry: Optional[tuple[int, int]] = None
    df_cache: Optional[pd.DataFrame] = None

    # --- 1. 確定値ページから取得 ---
    try:
        df = _fetch_baiu_df()
        df_cache = df
        row = df[df["年号"].str.strip() == f"{year}年"]
        if not row.empty:
            e = _parse_md(row.iloc[0]["梅雨入り"])
            if e is not None and e[0] == report_month:
                normal_row = df[df["年号"].str.contains(r"平\s*年", na=False, regex=True)]
                normal_entry = _parse_md(normal_row.iloc[0]["梅雨入り"]) if not normal_row.empty else None
                prev_row = df[df["年号"].str.strip() == f"{year - 1}年"]
                prev_entry = _parse_md(prev_row.iloc[0]["梅雨入り"]) if not prev_row.empty else None
                entry = e
    except Exception:
        pass

    # --- 2. 速報値ページにフォールバック ---
    if entry is None:
        try:
            result = _fetch_sokuhou_okinawa_entry(year)
            if result is not None:
                e, normal_entry, prev_entry = result
                if e[0] == report_month:
                    entry = e
                    if df_cache is None:
                        try:
                            df_cache = _fetch_baiu_df()
                        except Exception:
                            pass
        except Exception:
            pass

    if entry is None:
        return ""

    main = _build_comparison_sentence(entry, normal_entry, prev_entry, kind="入り")
    record = ""
    if df_cache is not None:
        try:
            record = _get_record_sentence(entry, year, df_cache, "梅雨入り", kind="入り")
        except Exception:
            pass

    return f"{main}{record}" if record else main


def _fetch_sokuhou_okinawa_entry(year: int) -> Optional[tuple[tuple[int, int], Optional[tuple[int, int]], Optional[tuple[int, int]]]]:
    """
    速報値ページから指定年の沖縄梅雨入りデータを取得する。

    Returns:
        (entry, normal_entry, prev_entry) のタプル、またはデータなし時 None。
        各要素は (month, day) タプルまたは None。

    速報値テーブルの列順（インデックス）:
        0: 地方
        1: 当年時期
        2: 当年階級
        3: 当年平年差
        4: 当年昨年差
        5: 平年の時期
        6: 昨年時期
        7: 昨年階級
    """
    resp = requests.get(BAIU_SOKUHOU_URL, timeout=30)
    resp.raise_for_status()
    html = resp.content.decode("utf-8", errors="replace")
    tables = pd.read_html(StringIO(html))
    if not tables:
        return None

    df = tables[0]  # 梅雨入りテーブル

    # 列ヘッダから対象年（西暦）を抽出（「令和8年」→ 2026）
    target_year_from_page = None
    for col in df.columns:
        m = re.search(r"令和(\d+)年", str(col))
        if m:
            target_year_from_page = 2018 + int(m.group(1))
            break

    if target_year_from_page != year:
        return None  # 速報ページの対象年が一致しない

    if df.shape[1] < 7:
        return None

    # 列をフラット化（位置アクセスのため列名は不要）
    df.columns = range(df.shape[1])

    # 地方列（0列目）で「沖縄」行を検索
    okinawa_row = df[df[0].astype(str).str.strip() == "沖縄"]
    if okinawa_row.empty:
        return None

    row = okinawa_row.iloc[0]
    entry = _parse_md(row[1])          # 当年時期
    if entry is None:
        return None

    normal_entry = _parse_md(row[5])   # 平年の時期
    prev_entry = _parse_md(row[6])     # 昨年時期

    return entry, normal_entry, prev_entry


def _build_comparison_sentence(
    entry: tuple[int, int],
    normal_entry: Optional[tuple[int, int]],
    prev_entry: Optional[tuple[int, int]],
    kind: str = "入り",
) -> str:
    """
    梅雨入り/明け日・平年・昨年から文章を組み立てる共通ロジック。

    kind="入り" → 「梅雨入りしたとみられ＊」「梅雨入りとなった」
    kind="明け" → 「梅雨が明けたとみられ＊」「梅雨明けとなった」
    """
    entry_month, entry_day = entry
    date_text = f"{entry_month}月{entry_day}日"

    if kind == "明け":
        intro_suffix = "梅雨が明けたとみられ＊"
        end_label = "梅雨明け"
    else:
        intro_suffix = "梅雨入りしたとみられ＊"
        end_label = "梅雨入り"

    comparisons: list[tuple[str, int]] = []
    if normal_entry:
        comparisons.append(("平年", _diff_days(entry, normal_entry)))
    if prev_entry:
        comparisons.append(("昨年", _diff_days(entry, prev_entry)))

    if not comparisons:
        return f"なお、沖縄地方は{date_text}ごろに{intro_suffix}、{end_label}となった。"

    parts: list[str] = []
    for i, (label, diff) in enumerate(comparisons):
        is_last = (i == len(comparisons) - 1)
        if diff == 0:
            if is_last:
                parts.append(f"{label}と同じ{end_label}となった。")
            else:
                parts.append(f"{label}と同じく")
        else:
            abs_diff = abs(diff)
            if is_last:
                direction = "遅い" if diff > 0 else "早い"
                parts.append(f"{label}より{abs_diff}日{direction}{end_label}となった。")
            else:
                direction = "遅く" if diff > 0 else "早く"
                parts.append(f"{label}より{abs_diff}日{direction}")

    comparison_text = "、".join(parts)
    return f"なお、沖縄地方は{date_text}ごろに{intro_suffix}、{comparison_text}"


def _get_record_sentence(
    current: tuple[int, int],
    current_year: int,
    df: pd.DataFrame,
    col: str,
    kind: str = "入り",
) -> str:
    """
    current が過去最早/最晩かどうかを判定し、記録文を返す。空文字=記録なし。

    col: "梅雨入り" or "梅雨明け"
    kind: "入り" or "明け"
    返値例:「統計を開始した1951年以降、2015年と並んで最も早い梅雨明けとなった。」
    """
    historical: dict[int, tuple[int, int]] = {}
    for _, row in df.iterrows():
        y = _parse_year(row["年号"])
        if y is None or y >= current_year:
            continue
        parsed = _parse_md(row[col])
        if parsed is not None:
            historical[y] = parsed

    if not historical:
        return ""

    start_year = min(historical.keys())
    ref = (1, 1)  # 比較基準（同年内なので1月1日からの通算日数で比較）
    current_d = _diff_days(current, ref)
    hist_d = {y: _diff_days(d, ref) for y, d in historical.items()}
    min_d = min(hist_d.values())
    max_d = max(hist_d.values())

    if current_d < min_d:
        direction = "早い"
        tied_years: list[int] = []
    elif current_d == min_d:
        direction = "早い"
        tied_years = sorted(y for y, d in hist_d.items() if d == min_d)
    elif current_d > max_d:
        direction = "遅い"
        tied_years = []
    elif current_d == max_d:
        direction = "遅い"
        tied_years = sorted(y for y, d in hist_d.items() if d == max_d)
    else:
        return ""

    kind_label = "梅雨明け" if kind == "明け" else "梅雨入り"
    if tied_years:
        years_text = "・".join(str(y) for y in tied_years) + "年と並んで"
    else:
        years_text = ""

    return f"統計を開始した{start_year}年以降、{years_text}最も{direction}{kind_label}となった。"


def _fetch_sokuhou_okinawa_end(year: int) -> Optional[tuple[tuple[int, int], Optional[tuple[int, int]], Optional[tuple[int, int]]]]:
    """
    速報値ページから指定年の沖縄梅雨明けデータを取得する。

    テーブル1（梅雨明け）の列構造はテーブル0（梅雨入り）と同じ。
    Returns:
        (end, normal_end, prev_end) のタプル、またはデータなし時 None。
    """
    resp = requests.get(BAIU_SOKUHOU_URL, timeout=30)
    resp.raise_for_status()
    html = resp.content.decode("utf-8", errors="replace")
    tables = pd.read_html(StringIO(html))
    if len(tables) < 2:
        return None

    df = tables[1]  # 梅雨明けテーブル

    target_year_from_page = None
    for col in df.columns:
        m = re.search(r"令和(\d+)年", str(col))
        if m:
            target_year_from_page = 2018 + int(m.group(1))
            break

    if target_year_from_page != year:
        return None

    if df.shape[1] < 7:
        return None

    df.columns = range(df.shape[1])

    okinawa_row = df[df[0].astype(str).str.strip() == "沖縄"]
    if okinawa_row.empty:
        return None

    row = okinawa_row.iloc[0]
    end = _parse_md(row[1])
    if end is None:
        return None

    normal_end = _parse_md(row[5])
    prev_end = _parse_md(row[6])

    return end, normal_end, prev_end


def build_baiu_end_sentence(year: int, report_month: int) -> str:
    """
    指定年・月の梅雨明け文を返す。

    確定値ページ (kako_baiu01.html) にデータがなければ
    速報値ページ (sokuhou_baiu.html) にフォールバックする。

    - 梅雨明けが report_month でなければ空文字を返す。
    - データ取得失敗時も空文字を返す。
    - 過去最早/最晩の場合は記録文を付記する。

    返値例:
        「なお、沖縄地方は6月8日ごろに梅雨が明けたとみられ＊、平年より13日早く、昨年より12日早い梅雨明けとなった。
         統計を開始した1951年以降、2015年と並んで最も早い梅雨明けとなった。」
    """
    end: Optional[tuple[int, int]] = None
    normal_end: Optional[tuple[int, int]] = None
    prev_end: Optional[tuple[int, int]] = None
    df_cache: Optional[pd.DataFrame] = None

    # --- 1. 確定値ページから取得 ---
    try:
        df = _fetch_baiu_df()
        df_cache = df
        row = df[df["年号"].str.strip() == f"{year}年"]
        if not row.empty:
            e = _parse_md(row.iloc[0]["梅雨明け"])
            if e is not None and e[0] == report_month:
                normal_row = df[df["年号"].str.contains(r"平\s*年", na=False, regex=True)]
                normal_end = _parse_md(normal_row.iloc[0]["梅雨明け"]) if not normal_row.empty else None
                prev_row = df[df["年号"].str.strip() == f"{year - 1}年"]
                prev_end = _parse_md(prev_row.iloc[0]["梅雨明け"]) if not prev_row.empty else None
                end = e
    except Exception:
        pass

    # --- 2. 速報値ページにフォールバック ---
    if end is None:
        try:
            result = _fetch_sokuhou_okinawa_end(year)
            if result is not None:
                e, normal_end, prev_end = result
                if e[0] == report_month:
                    end = e
                    if df_cache is None:
                        try:
                            df_cache = _fetch_baiu_df()
                        except Exception:
                            pass
        except Exception:
            pass

    if end is None:
        return ""

    main = _build_comparison_sentence(end, normal_end, prev_end, kind="明け")
    record = ""
    if df_cache is not None:
        try:
            record = _get_record_sentence(end, year, df_cache, "梅雨明け", kind="明け")
        except Exception:
            pass

    return f"{main}{record}" if record else main
