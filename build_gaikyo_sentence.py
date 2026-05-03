"""
概況文だけを生成するスクリプト。
グラフ・ランキング出力は行わず、概況文.csv のみを出力する。
count_and_plot.py には依存しない、独立実行可能版。
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

KEYWORD_CSV = "keyword.csv"
PERIODS: list[str] = ["上旬", "中旬", "下旬"]


def month_to_data_dir(month: str) -> Path:
    if len(month) != 6 or not month.isdigit():
        raise ValueError(f"month must be YYYYMM format: {month}")
    year = month[:4]
    month_num = month[4:]
    return Path("data") / f"{year}_{month_num}"


def resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parent / path


def normalize_text(text: str) -> str:
    return str(text).replace(" ", "").replace("\u3000", "").replace("、", "").replace("。", "")


def to_weather(text: str) -> str:
    t = normalize_text(text)
    if "雨" in t or "雷雨" in t:
        return "雨"
    if "曇" in t or "雲が広が" in t:
        return "曇り"
    if "晴" in t:
        return "晴れ"
    return "その他"


def get_period(day_str: str) -> str:
    try:
        day = int(str(day_str).split("/")[1])
        if day <= 10:
            return "上旬"
        if day <= 20:
            return "中旬"
        return "下旬"
    except ValueError:
        return "不明"


def load_rules(keyword_path: str) -> pd.DataFrame:
    df = pd.read_csv(keyword_path, skipinitialspace=True).fillna("")
    df = df.rename(columns={"要因": "factor", "中文": "connector", "結果": "result"})
    for col in ["factor", "connector", "result"]:
        df[col] = df[col].astype(str).str.strip()
    df = df[df["factor"] != ""].copy()
    df["factor_n"] = df["factor"].map(normalize_text)
    df["connector_n"] = df["connector"].map(normalize_text)
    df["result_n"] = df["result"].map(normalize_text)
    df["weather"] = df["result"].map(to_weather)
    df["priority"] = (
        df["factor_n"].str.len() + df["connector_n"].str.len() + df["result_n"].str.len()
    )
    return df.sort_values("priority", ascending=False).reset_index(drop=True)


def build_connector_dict(keyword_path: str) -> dict[str, str]:
    """要因→中文の辞書を生成。各要因の最初の中文を使用する。"""
    df = pd.read_csv(keyword_path, skipinitialspace=True).fillna("")
    connector_dict: dict[str, str] = {}
    for _, row in df.iterrows():
        factor = str(row.get("要因", "")).strip()
        conn = str(row.get("中文", "")).strip()
        if factor and factor not in connector_dict and conn:
            connector_dict[factor] = conn
    return connector_dict


def _phrase_and_day(factor: str, weathers: list[str], connector_dict: dict[str, str]) -> tuple[str, str]:
    """(フレーズ, 日の表現) を返す。晴れのみなら「晴れた日」、それ以外は「○○の日」。"""
    conn = connector_dict.get(factor, "の影響で")
    unique_w = list(dict.fromkeys(weathers))
    if unique_w == ["晴れ"]:
        return f"{factor}{conn}晴れた", "日"
    return f"{factor}{conn}{'や'.join(unique_w)}", "の日"


def build_gaikyo_sentence(
    counts_df: pd.DataFrame,
    connector_dict: dict[str, str],
    area_name: str,
) -> str:
    """
    要因天気頻度DataFrameから概況文を生成する。
    同一要因に複数の天気がある場合は頻度を合算し、天気を「曇りや雨」のように結合する。
    各天気の頻度が要因全体の1/3未満なら省略する。
    """
    base = counts_df[counts_df["要因"] != "雲のすき間"]
    freq_df = base.groupby("要因")["頻度"].sum().reset_index(name="頻度")
    
    # 各要因ごとに1/3以上の天気のみを抽出
    def get_weathers_above_threshold(factor: str) -> list[str]:
        factor_data = base[base["要因"] == factor]
        total = factor_data["頻度"].sum()
        threshold = total / 3
        filtered = factor_data[factor_data["頻度"] >= threshold]
        weathers = filtered.sort_values("頻度", ascending=False)["天気"].unique()
        return list(dict.fromkeys(weathers))
    
    weathers_list = []
    for factor in freq_df["要因"]:
        weathers = get_weathers_above_threshold(factor)
        weathers_list.append({"要因": factor, "天気リスト": weathers})
    
    weathers_df = pd.DataFrame(weathers_list)
    
    df = (
        freq_df.merge(weathers_df, on="要因")
        .sort_values("頻度", ascending=False)
        .reset_index(drop=True)
    )
    if df.empty:
        return ""

    r1 = df.iloc[0]
    freq1 = int(r1["頻度"])
    ph1, d1 = _phrase_and_day(r1["要因"], r1["天気リスト"], connector_dict)
    n = len(df)

    if n == 1:
        return f"{area_name}は、{ph1}{d1}が多かった。"

    r2 = df.iloc[1]
    freq2 = int(r2["頻度"])
    freq3 = int(df.iloc[2]["頻度"]) if n >= 3 else 0

    if freq2 + freq3 <= freq1 / 2:
        return f"{area_name}は、{ph1}{d1}が多かった。"

    if freq2 >= freq1 / 2:
        # 3位も2位と同数なら両方載せる
        if n >= 3 and freq3 == freq2:
            r3 = df.iloc[2]
            conn3 = connector_dict.get(r3["要因"], "の影響で")
            combined_weathers = list(dict.fromkeys(r2["天気リスト"] + r3["天気リスト"]))
            if set(r2["天気リスト"]) == set(r3["天気リスト"]):
                return (
                    f"{area_name}は、{ph1}{d1}もあったが、"
                    f"{r2['要因']}や{r3['要因']}{conn3}{'や'.join(combined_weathers)}の日もあった。"
                )
            # 2位か3位が1位と同じ天気なら1位とまとめる
            if set(r2["天気リスト"]) == set(r1["天気リスト"]):
                conn2 = connector_dict.get(r2["要因"], "の影響で")
                combined12 = list(dict.fromkeys(r1["天気リスト"] + r2["天気リスト"]))
                ph3, d3 = _phrase_and_day(r3["要因"], r3["天気リスト"], connector_dict)
                return (
                    f"{area_name}は、{r1['要因']}や{r2['要因']}{conn2}{'や'.join(combined12)}の日もあったが、"
                    f"{ph3}{d3}もあった。"
                )
            if set(r3["天気リスト"]) == set(r1["天気リスト"]):
                combined13 = list(dict.fromkeys(r1["天気リスト"] + r3["天気リスト"]))
                ph2, d2 = _phrase_and_day(r2["要因"], r2["天気リスト"], connector_dict)
                return (
                    f"{area_name}は、{r1['要因']}や{r3['要因']}{conn3}{'や'.join(combined13)}の日もあったが、"
                    f"{ph2}{d2}もあった。"
                )
            ph2, d2 = _phrase_and_day(r2["要因"], r2["天気リスト"], connector_dict)
            ph3, d3 = _phrase_and_day(r3["要因"], r3["天気リスト"], connector_dict)
            return (
                f"{area_name}は、{ph1}{d1}もあったが、"
                f"{ph2}{d2}や{ph3}{d3}もあった。"
            )
        conn2 = connector_dict.get(r2["要因"], "の影響で")
        combined_weathers12 = list(dict.fromkeys(r1["天気リスト"] + r2["天気リスト"]))
        if set(r1["天気リスト"]) == set(r2["天気リスト"]):
            return (
                f"{area_name}は、{r1['要因']}や{r2['要因']}{conn2}{'や'.join(combined_weathers12)}の日が多かった。"
            )
        ph2, d2 = _phrase_and_day(r2["要因"], r2["天気リスト"], connector_dict)
        return f"{area_name}は、{ph1}{d1}もあったが、{ph2}{d2}もあった。"

    total_freq = int(df["頻度"].sum())
    if n < 3 or freq2 + freq3 < total_freq * 2 / 5:
        return f"{area_name}は、{ph1}{d1}が多かった。"

    r3 = df.iloc[2]
    conn3 = connector_dict.get(r3["要因"], "の影響で")
    combined_weathers = list(dict.fromkeys(r2["天気リスト"] + r3["天気リスト"]))
    if set(r2["天気リスト"]) == set(r3["天気リスト"]):
        return (
            f"{area_name}は、{ph1}{d1}もあったが、"
            f"{r2['要因']}や{r3['要因']}{conn3}{'や'.join(combined_weathers)}の日もあった。"
        )
    # 2位か3位が1位と同じ天気なら1位とまとめる
    if set(r2["天気リスト"]) == set(r1["天気リスト"]):
        conn2 = connector_dict.get(r2["要因"], "の影響で")
        combined12 = list(dict.fromkeys(r1["天気リスト"] + r2["天気リスト"]))
        ph3, d3 = _phrase_and_day(r3["要因"], r3["天気リスト"], connector_dict)
        return (
            f"{area_name}は、{r1['要因']}や{r2['要因']}{conn2}{'や'.join(combined12)}の日もあったが、"
            f"{ph3}{d3}もあった。"
        )
    if set(r3["天気リスト"]) == set(r1["天気リスト"]):
        combined13 = list(dict.fromkeys(r1["天気リスト"] + r3["天気リスト"]))
        ph2, d2 = _phrase_and_day(r2["要因"], r2["天気リスト"], connector_dict)
        return (
            f"{area_name}は、{r1['要因']}や{r3['要因']}{conn3}{'や'.join(combined13)}の日もあったが、"
            f"{ph2}{d2}もあった。"
        )
    ph2, d2 = _phrase_and_day(r2["要因"], r2["天気リスト"], connector_dict)
    ph3, d3 = _phrase_and_day(r3["要因"], r3["天気リスト"], connector_dict)
    return (
        f"{area_name}は、{ph1}{d1}もあったが、"
        f"{ph2}{d2}や{ph3}{d3}もあった。"
    )


def rule_matches(text_n: str, text_weather: str, rule: pd.Series) -> bool:
    if rule["factor_n"] not in text_n:
        return False
    if rule["connector_n"] and rule["connector_n"] not in text_n:
        return False
    result_hit = rule["result_n"] in text_n if rule["result_n"] else False
    weather_hit = rule["weather"] != "その他" and rule["weather"] == text_weather
    return result_hit or weather_hit


def extract_pairs_from_text(text: str, rules_df: pd.DataFrame) -> list[tuple[str, str]]:
    text_n = normalize_text(text)
    text_weather = to_weather(text)
    if text_weather == "その他":
        return []
    used_spans = []
    pairs = []
    for _, rule in rules_df.iterrows():
        factor_n = rule["factor_n"]
        if not factor_n:
            continue
        start = text_n.find(factor_n)
        if start == -1:
            continue
        end = start + len(factor_n)
        overlap = any(us <= start < ue or us < end <= ue for us, ue in used_spans)
        if overlap:
            continue
        if rule_matches(text_n, text_weather, rule):
            pairs.append((rule["factor"], rule["weather"]))
            used_spans.append((start, end))
    return pairs


def collect_factor_weather_records(df: pd.DataFrame, rules_df: pd.DataFrame) -> pd.DataFrame:
    text_cols = [c for c in df.columns if c not in ("期間", "月日")]
    records: list[dict[str, str]] = []
    for _, row in df.iterrows():
        for col in text_cols:
            for factor, weather in extract_pairs_from_text(str(row[col]), rules_df):
                records.append({"要因": factor, "天気": weather})
    return pd.DataFrame(records)


def generate_sentences(
    input_csv: Path,
    keyword_csv: Path,
    area_name: str,
) -> list[dict[str, str]]:
    """概況CSVから月・上旬・中旬・下旬の概況文を生成して返す。"""
    df = pd.read_csv(input_csv).fillna("")
    rules_df = load_rules(str(keyword_csv))
    connector_dict = build_connector_dict(str(keyword_csv))
    df["期間"] = df["月日"].map(get_period)

    period_slices = [("月", df)] + [(p, df[df["期間"] == p]) for p in PERIODS]
    sentences: list[dict[str, str]] = []
    for label, sub_df in period_slices:
        df_records = collect_factor_weather_records(sub_df, rules_df)
        if df_records.empty:
            continue
        counts = df_records.groupby(["要因", "天気"]).size().reset_index(name="頻度")
        sentence = build_gaikyo_sentence(counts, connector_dict, area_name)
        if sentence:
            sentences.append({"期間": label, "概況文": sentence})
    return sentences


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="概況CSVから概況文のみを生成する")
    parser.add_argument("--month", help="対象月 (YYYYMM)。入力CSV未指定時は YYYYMM-概況.csv を使用")
    parser.add_argument("--input-csv", default=None, help="入力CSVパス")
    parser.add_argument("--keyword-csv", default=KEYWORD_CSV, help="キーワード定義CSVパス")
    parser.add_argument("--output-dir", default=None, help="出力先ディレクトリ（省略時は input_csv と同じ場所）")
    parser.add_argument("--area-name", required=True, help="地方名（例: 大東島地方）")
    args = parser.parse_args()

    if not args.input_csv and not args.month:
        parser.error("--month または --input-csv を指定してください")

    return args


def main() -> None:
    os.chdir(os.path.dirname(__file__))
    args = parse_args()

    if args.input_csv:
        input_csv = resolve_path(args.input_csv)
    else:
        month_dir = month_to_data_dir(args.month)
        input_csv = resolve_path(str(month_dir / f"{args.month}-概況.csv"))

    if not input_csv.exists():
        raise FileNotFoundError(f"入力CSVが見つかりません: {input_csv}")

    keyword_csv = resolve_path(args.keyword_csv)
    if not keyword_csv.exists():
        raise FileNotFoundError(f"キーワードCSVが見つかりません: {keyword_csv}")

    if args.output_dir:
        output_dir = resolve_path(args.output_dir)
    elif args.month:
        output_dir = resolve_path(str(month_to_data_dir(args.month)))
    else:
        output_dir = input_csv.parent

    output_dir.mkdir(parents=True, exist_ok=True)

    sentences = generate_sentences(input_csv, keyword_csv, args.area_name)
    if not sentences:
        print("[スキップ] 概況文なし（データ不足）")
        return

    out_path = output_dir / "概況文.csv"
    pd.DataFrame(sentences).to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[出力] {out_path}")
    for s in sentences:
        print(f"  [{s['期間']}] {s['概況文']}")


if __name__ == "__main__":
    main()
