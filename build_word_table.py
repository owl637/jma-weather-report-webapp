import os
import re

from bs4 import BeautifulSoup
import pandas as pd
import requests

from app_core import BASE_DIR, DEFAULT_MONTH, DEFAULT_YEAR, PERIODS, get_save_dir, load_json

YEAR = DEFAULT_YEAR
MONTH = DEFAULT_MONTH
PLACEHOLDER = '／'
SAVE_DIR = get_save_dir(YEAR, MONTH)
BASE_URL = "https://www.data.jma.go.jp/stats/etrn/view/{base_php}.php?prec_no={prec_no}&block_no={block_no}&year={year}&month={month}&day=&view="
DATA_BASES = {
    'sfc': {
        '月': ('monthly_s1', 'nml_sfc_ym'),
        '旬': ('10daily_s1', 'nml_sfc_10d'),
    },
    'amd': {
        '月': ('monthly_a1', 'nml_amd_ym'),
        '旬': ('10daily_a1', 'nml_amd_10d'),
    },
}
ELEMENT_LABELS = {
    '気温': ['かなり低い', '低い', '平年並', '高い', 'かなり高い'],
    '降水量': ['かなり少ない', '少ない', '平年並', '多い', 'かなり多い'],
    '日照時間': ['かなり少ない', '少ない', '平年並', '多い', 'かなり多い'],
}
OUTPUT_COLUMNS = [
    '地点名',
    '平均気温(℃)',
    '平年差(℃)',
    '気温階級',
    '降水量(mm)',
    '平年比(%)',
    '降水量階級',
    '日照時間(h)',
    '平年比(%)',
    '日照時間階級',
]

os.makedirs(SAVE_DIR, exist_ok=True)


def create_url(prec_no, block_no, base_php):
    return BASE_URL.format(
        base_php=base_php,
        prec_no=prec_no,
        block_no=block_no,
        year=YEAR,
        month=MONTH,
    )


def clean_number(value):
    if pd.isna(value):
        return None

    text = str(value).strip()
    if text in {'', '///', '---', 'nan', 'None'}:
        return None

    match = re.search(r'-?\d+(?:\.\d+)?', text.replace(',', ''))
    return float(match.group()) if match else None


def format_value(value, digits=1, signed=False):
    if value is None:
        return PLACEHOLDER
    if signed:
        return f"{value:+.{digits}f}"
    return f"{value:.{digits}f}"


def format_ratio(value):
    if value is None:
        return PLACEHOLDER
    return str(int(round(value)))


def calculate_ratio(actual, normal):
    if actual is None or normal in (None, 0):
        return None
    return actual / normal * 100


def load_station_kubun_tables():
    station_kubun = {}
    for file_name in os.listdir(BASE_DIR):
        month_match = re.match(r'^階級区分_月_(\d+)\.csv$', file_name)
        ten_match = re.match(r'^階級区分_旬_(\d+)\.csv$', file_name)
        file_path = os.path.join(BASE_DIR, file_name)

        if month_match:
            station_kubun[('月', month_match.group(1))] = pd.read_csv(file_path, dtype=str)
        elif ten_match:
            station_kubun[('旬', ten_match.group(1))] = pd.read_csv(file_path, dtype=str)

    return station_kubun


def get_station_name(prec_no, block_no, status):
    base_php = 'monthly_s1' if status == 'sfc' else 'monthly_a1'
    url = create_url(prec_no, block_no, base_php)

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        h3 = soup.find('h3')
        if h3:
            text = re.sub(r'\s+', ' ', h3.get_text(' ', strip=True))
            return text.split('（')[0].split(' ')[0]
    except requests.exceptions.RequestException:
        pass

    return str(block_no)


def get_data_frames(status, prec_no, block_no, period_name):
    kind = '月' if period_name == '月' else '旬'
    actual_base, normal_base = DATA_BASES[status][kind]

    actual_path = os.path.join(SAVE_DIR, f"{actual_base}_{prec_no}_{block_no}.csv")
    normal_path = os.path.join(SAVE_DIR, f"{normal_base}_{prec_no}_{block_no}.csv")
    if not os.path.exists(actual_path) or not os.path.exists(normal_path):
        raise FileNotFoundError('観測データCSVが見つかりません。先に downloads.py を実行してください。')

    return pd.read_csv(actual_path, dtype=str), pd.read_csv(normal_path, dtype=str)


def get_period_rows(status, prec_no, block_no, period_name):
    actual_df, normal_df = get_data_frames(status, prec_no, block_no, period_name)

    if period_name == '月':
        actual_row = actual_df[actual_df['月'].astype(str) == str(MONTH)].iloc[0]
        normal_row = normal_df[normal_df['要素'] == f'{MONTH}月'].iloc[0]
    else:
        actual_row = actual_df[
            (actual_df['月'].astype(str) == str(MONTH)) & (actual_df['旬'] == period_name)
        ].iloc[0]
        normal_row = normal_df[
            (normal_df['要素'] == f'{MONTH}月') & (normal_df['旬'] == period_name)
        ].iloc[0]

    return actual_row, normal_row


def get_station_thresholds(kubun_tables, block_no, item_name, period_name):
    kind = '月' if period_name == '月' else '旬'
    kubun_df = kubun_tables.get((kind, str(block_no)))
    if kubun_df is None:
        return None

    filtered_df = kubun_df[kubun_df['要素'] == item_name]
    if period_name == '月':
        filtered_df = filtered_df[filtered_df['期間'] == f'{MONTH}月']
    else:
        filtered_df = filtered_df[
            (filtered_df['月'].astype(str) == str(MONTH)) & (filtered_df['旬'] == period_name)
        ]

    if filtered_df.empty:
        return None

    row = filtered_df.iloc[0]
    return tuple(clean_number(row[f'階級区分{i}']) for i in range(1, 7))


def classify_by_station_value(value, thresholds, item_name):
    if value is None or thresholds is None or any(threshold is None for threshold in thresholds):
        return PLACEHOLDER

    labels = ELEMENT_LABELS[item_name]
    very_low_threshold = thresholds[1]
    low_threshold = thresholds[2]
    high_threshold = thresholds[3]
    very_high_threshold = thresholds[4]

    if value <= very_low_threshold:
        return labels[0]
    if value <= low_threshold:
        return labels[1]
    if value > very_high_threshold:
        return labels[4]
    if value > high_threshold:
        return labels[3]
    return labels[2]


def get_metric_result(actual_value, normal_value, item_name, thresholds):
    if item_name == '気温':
        compare_value = actual_value - normal_value if actual_value is not None and normal_value is not None else None
        compare_text = format_value(compare_value, signed=True)
    else:
        compare_text = format_ratio(calculate_ratio(actual_value, normal_value))

    return {
        'actual': format_value(actual_value),
        'compare': compare_text,
        'class': classify_by_station_value(actual_value, thresholds, item_name),
    }


def build_table_record(obs, period_name, kubun_tables):
    prec_no = obs['prec_no']
    block_no = obs['block_no']
    status = obs['status']
    actual_row, normal_row = get_period_rows(status, prec_no, block_no, period_name)

    if period_name == '月':
        temp_col = '月間平均日平均気温(℃)'
        precip_col = '月合計降水量(mm)'
        sun_col = '月間日照時間(h)' if status == 'sfc' else '日照時間(h)'
    else:
        temp_col = '旬間平均日平均気温(℃)'
        precip_col = '旬合計降水量(mm)'
        sun_col = '旬間日照時間(h)'

    temp = get_metric_result(
        clean_number(actual_row.get(temp_col)),
        clean_number(normal_row.get('平年平均気温(℃)')),
        '気温',
        get_station_thresholds(kubun_tables, block_no, '気温', period_name),
    )
    precip = get_metric_result(
        clean_number(actual_row.get(precip_col)),
        clean_number(normal_row.get('平年降水量(mm)')),
        '降水量',
        get_station_thresholds(kubun_tables, block_no, '降水量', period_name),
    )
    sun = get_metric_result(
        clean_number(actual_row.get(sun_col)),
        clean_number(normal_row.get('平年日照時間(h)')),
        '日照時間',
        get_station_thresholds(kubun_tables, block_no, '日照時間', period_name),
    )

    return {
        'station_name': get_station_name(prec_no, block_no, status),
        'period': period_name,
        'temperature': temp,
        'precipitation': precip,
        'sunshine': sun,
    }


def record_to_row(record):
    return [
        record['station_name'],
        record['temperature']['actual'],
        record['temperature']['compare'],
        record['temperature']['class'],
        record['precipitation']['actual'],
        record['precipitation']['compare'],
        record['precipitation']['class'],
        record['sunshine']['actual'],
        record['sunshine']['compare'],
        record['sunshine']['class'],
    ]


def generate_word_table_csvs(obs_list, kubun_tables):
    for period_name in PERIODS:
        records = [build_table_record(obs, period_name, kubun_tables) for obs in obs_list]
        rows = [record_to_row(record) for record in records]
        word_df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
        save_file = os.path.join(SAVE_DIR, f"Word用_{period_name}.csv")
        word_df.to_csv(save_file, index=False, encoding='utf-8-sig')
        print(f"Word table saved to {save_file}.")


def main():
    obs_list = load_json('obs_list.json')
    kubun_tables = load_station_kubun_tables()
    generate_word_table_csvs(obs_list, kubun_tables)


if __name__ == '__main__':
    main()
