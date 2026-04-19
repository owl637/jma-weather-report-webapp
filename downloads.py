import json
import os
import re
from io import StringIO

import pandas as pd
import requests

from app_core import BASE_DIR, DEFAULT_MONTH, DEFAULT_YEAR, get_save_dir, load_json

YEAR = DEFAULT_YEAR
MONTH = DEFAULT_MONTH
BASE_URL = "https://www.data.jma.go.jp/stats/etrn/view/{base_php}.php?prec_no={prec_no}&block_no={block_no}&year={year}&month={month}&day=&view="
BASE_PHP_BY_STATUS = {
    'sfc': ['monthly_s1', '10daily_s1', 'daily_s1', 'nml_sfc_ym', 'nml_sfc_10d', 'nml_sfc_d'],
    'amd': ['monthly_a1', '10daily_a1', 'daily_a1', 'nml_amd_ym', 'nml_amd_10d', 'nml_amd_d'],
}
ZERO_PAD_MONTH_BASES = {'nml_sfc_d', 'nml_amd_d'}
RANK_BASE_PHP_BY_STATUS = {
    'sfc': 'rank_s',
    'amd': 'rank_a',
}
RANK_TARGETS = [
    ('all', 13),
    ('month', MONTH),
]
BIO_URL = 'https://www.data.jma.go.jp/daitou/shosai/kansoku/kansoku_seibutu.html'
BIO_START_YEAR = 2023



def create_url(prec_no, block_no, base_php, year=None, month=None):
    target_year = YEAR if year is None else year
    target_month = MONTH if month is None else month
    if isinstance(target_month, int) and base_php in ZERO_PAD_MONTH_BASES:
        target_month = f'{target_month:02d}'

    return BASE_URL.format(
        base_php=base_php,
        prec_no=prec_no,
        block_no=block_no,
        year=target_year,
        month=target_month,
    )


def get_output_columns(base_php):
    output_columns = COLUMN_CONFIGS.get(base_php)
    if output_columns is None:
        raise KeyError(f"column_config.json に {base_php} の設定がありません。")
    return output_columns


def fetch_table(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    tables = pd.read_html(StringIO(response.text), attrs={'id': 'tablefix1'})
    if not tables:
        raise ValueError('対象のテーブルが見つかりませんでした。')

    return tables[0]


def normalize_dataframe(df, base_php):
    output_columns = get_output_columns(base_php)
    if len(df.columns) != len(output_columns):
        raise ValueError(
            f"{base_php} の列数が一致しません。取得={len(df.columns)} / 設定={len(output_columns)}"
        )

    normalized_df = df.copy()
    normalized_df.columns = output_columns
    return normalized_df


def normalize_rank_dataframe(df):
    normalized_df = df.copy()

    if isinstance(normalized_df.columns, pd.MultiIndex):
        columns = []
        for column in normalized_df.columns:
            parts = [str(part).strip() for part in column if str(part).strip() and 'Unnamed' not in str(part)]
            columns.append(' '.join(parts))
        normalized_df.columns = columns

    normalized_df.columns = [re.sub(r'\s+', ' ', str(column)).strip() for column in normalized_df.columns]
    return normalized_df


def download_data(base_php, prec_no, block_no, year=None, month=None, save_dir=None):
    target_year = YEAR if year is None else year
    target_month = MONTH if month is None else month
    resolved_save_dir = get_save_dir(target_year, target_month) if save_dir is None else save_dir
    save_file = os.path.join(resolved_save_dir, f"{base_php}_{prec_no}_{block_no}.csv")
    url = create_url(prec_no, block_no, base_php, year=target_year, month=target_month)

    print(f"Fetching data from: {url}")
    try:
        raw_df = fetch_table(url)
        df = normalize_dataframe(raw_df, base_php)
    except (requests.exceptions.RequestException, ValueError, KeyError) as e:
        print(f"Error processing {url}: {e}")
        return None

    if df.empty:
        print(f"No data found for {target_year}-{target_month}. Skipping file save.")
        return None

    df.to_csv(save_file, index=False, encoding='utf-8-sig')
    print(f"Data for {target_year}-{target_month} saved to {save_file}.")
    return df


def download_rank_data(status, prec_no, block_no, year=None, month=None, save_dir=None):
    target_year = YEAR if year is None else year
    target_month = MONTH if month is None else month
    resolved_save_dir = get_save_dir(target_year, target_month) if save_dir is None else save_dir
    base_php = RANK_BASE_PHP_BY_STATUS.get(status)
    if not base_php:
        return

    rank_targets = [
        ('all', 13),
        ('month', target_month),
    ]

    for label, target_scope_month in rank_targets:
        save_file = os.path.join(resolved_save_dir, f"{base_php}_{label}_{prec_no}_{block_no}.csv")
        url = create_url(prec_no, block_no, base_php, year=target_year, month=target_scope_month)

        print(f"Fetching rank data from: {url}")
        try:
            raw_df = fetch_table(url)
            df = normalize_rank_dataframe(raw_df)
        except (requests.exceptions.RequestException, ValueError) as e:
            print(f"Error processing {url}: {e}")
            continue

        if df.empty:
            print(f"No rank data found for {target_year}-{target_scope_month}. Skipping file save.")
            continue

        df.to_csv(save_file, index=False, encoding='utf-8-sig')
        print(f"Rank data saved to {save_file}.")


def normalize_biological_dataframe(df):
    normalized_df = df.copy()

    if isinstance(normalized_df.columns, pd.MultiIndex):
        columns = []
        for column in normalized_df.columns:
            parts = [str(part).strip() for part in column if str(part).strip() and 'Unnamed' not in str(part)]
            columns.append(' '.join(parts))
        normalized_df.columns = columns

    normalized_df.columns = [re.sub(r'\s+', ' ', str(column)).strip() for column in normalized_df.columns]
    normalized_df = normalized_df.fillna('')

    first_column = normalized_df.columns[0]
    normalized_df[first_column] = normalized_df[first_column].replace('', pd.NA).ffill().fillna('')
    return normalized_df


def download_biological_data(year=None, month=None, save_dir=None):
    target_year = YEAR if year is None else year
    target_month = MONTH if month is None else month
    resolved_save_dir = get_save_dir(target_year, target_month) if save_dir is None else save_dir

    print(f"Fetching biological data from: {BIO_URL}")
    try:
        response = requests.get(BIO_URL, timeout=30)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or 'utf-8'
        tables = pd.read_html(StringIO(response.text))
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"Error processing biological page: {e}")
        return

    if len(tables) < 2:
        print('Biological observation tables were not found.')
        return

    current_df = normalize_biological_dataframe(tables[0])
    history_df = normalize_biological_dataframe(tables[1])

    current_year_columns = [column for column in history_df.columns if re.fullmatch(r'\d{4}年', column)]
    if not current_year_columns:
        print('No year columns found in biological observation history.')
        return

    latest_year = max(int(re.search(r'\d{4}', column).group()) for column in current_year_columns)
    current_year = latest_year + 1

    current_export_df = current_df.iloc[:, :6].copy()
    current_export_df.columns = ['種別', '現象', '観測日', '平年値', '最早日', '最晩日']
    current_export_df.insert(0, '年', current_year)
    current_export_df.to_csv(os.path.join(resolved_save_dir, f'seibutu_{current_year}.csv'), index=False, encoding='utf-8-sig')
    print(f"Biological data saved to {os.path.join(resolved_save_dir, f'seibutu_{current_year}.csv')}.")

    species_column = history_df.columns[0]
    phenomenon_column = history_df.columns[1]
    normal_column = next((column for column in history_df.columns if '平年' in column), '')
    earliest_column = next((column for column in history_df.columns if '最早' in column), '')
    latest_column = next((column for column in history_df.columns if '最晩' in column), '')

    for year_column in current_year_columns:
        target_year = int(re.search(r'\d{4}', year_column).group())
        if target_year < BIO_START_YEAR:
            continue

        export_df = history_df[[species_column, phenomenon_column, year_column, normal_column, earliest_column, latest_column]].copy()
        export_df.columns = ['種別', '現象', '観測日', '平年値', '最早日', '最晩日']
        export_df.insert(0, '年', target_year)
        save_file = os.path.join(resolved_save_dir, f'seibutu_{target_year}.csv')
        export_df.to_csv(save_file, index=False, encoding='utf-8-sig')
        print(f"Biological data saved to {save_file}.")


def main(year=None, month=None):
    target_year = YEAR if year is None else year
    target_month = MONTH if month is None else month
    save_dir = get_save_dir(target_year, target_month)

    for obs in OBS_LIST:
        prec_no = obs['prec_no']
        block_no = obs['block_no']
        status = obs['status']

        for base_php in BASE_PHP_BY_STATUS.get(status, []):
            download_data(base_php, prec_no, block_no, year=target_year, month=target_month, save_dir=save_dir)

        download_rank_data(status, prec_no, block_no, year=target_year, month=target_month, save_dir=save_dir)

    download_biological_data(year=target_year, month=target_month, save_dir=save_dir)


SAVE_DIR = get_save_dir(YEAR, MONTH)
OBS_LIST = load_json('obs_list.json')
COLUMN_CONFIGS = load_json('column_config.json')


if __name__ == '__main__':
    main()