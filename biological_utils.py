import os
import re
from datetime import datetime

import pandas as pd

from app_core import get_save_dir

BIO_OBSERVATION_PLACE = '南大東島'
BIO_SPECIES_DISPLAY_NAMES = {
    'ひかんざくら': 'さくら（ひかんざくら）',
}


def normalize_text(value, default='－'):
    text = '' if pd.isna(value) else str(value).strip()
    return text if text else default


def load_biological_csv(report_year, report_month, target_year):
    csv_path = os.path.join(get_save_dir(report_year, report_month), f'seibutu_{target_year}.csv')
    if not os.path.exists(csv_path):
        return None
    return pd.read_csv(csv_path, dtype=str).fillna('')


def get_biological_display_name(species_name):
    text = normalize_text(species_name, '')
    for keyword, display_name in BIO_SPECIES_DISPLAY_NAMES.items():
        if keyword in text:
            return display_name
    return text


def parse_biological_date(date_text, default_year=None):
    text = re.sub(r'\s+', '', normalize_text(date_text, ''))
    if text in {'', '-', '－', '―'}:
        return None

    match = re.search(r'(\d{1,2})月(\d{1,2})日', text)
    if not match:
        return None

    month = int(match.group(1))
    day = int(match.group(2))
    year_match = re.search(r'\((\d{4})年\)', text)
    actual_year = int(year_match.group(1)) if year_match else default_year

    date_value = None
    if actual_year is not None:
        try:
            date_value = datetime(actual_year, month, day)
        except ValueError:
            date_value = None

    return {'year': actual_year, 'month': month, 'day': day, 'date': date_value}


def format_biological_date(date_text):
    date_info = parse_biological_date(date_text)
    if not date_info:
        return '－'
    return f"{date_info['month']}月{date_info['day']}日"


def calculate_biological_difference(observed_text, normal_text, report_year):
    observed = parse_biological_date(observed_text, report_year)
    normal = parse_biological_date(normal_text, report_year)

    if not observed or not normal or observed['date'] is None or normal['date'] is None:
        return '－'

    diff_days = (observed['date'] - normal['date']).days
    return f'+{diff_days}' if diff_days > 0 else str(diff_days)


def find_biological_record_text(report_year, report_month, target_year, species_name, phenomenon):
    df = load_biological_csv(report_year, report_month, target_year)
    if df is None or df.empty:
        return '－'

    matched = df[(df['種別'] == species_name) & (df['現象'] == phenomenon)]
    if matched.empty:
        return '－'

    return format_biological_date(matched.iloc[0].get('観測日', ''))


def collect_biological_history(report_year, report_month, species_name, phenomenon):
    history = []

    for target_year in range(2023, report_year):
        df = load_biological_csv(report_year, report_month, target_year)
        if df is None or df.empty:
            continue

        matched = df[(df['種別'] == species_name) & (df['現象'] == phenomenon)]
        if matched.empty:
            continue

        date_info = parse_biological_date(matched.iloc[0].get('観測日', ''), target_year)
        if date_info:
            history.append(date_info)

    return history


def build_biological_section(year, month):
    notes = [
        '平年差の”－”は発現が平年に比べて早く、”＋”は発現が平年に比べて遅いことを示します。',
        '最早日、最晩日が更新された場合の「最早日」、「最晩日」欄は、従来の最早日、最晩日とします。',
    ]
    section = {
        'caption': f'{month}月の観測はありません。',
        'columns': ['観測場所', '種別', '現象', '本年発現（月日）', '平年値（月日）', '昨年発現（月日）', '発現平年差', '最早日', '最晩日'],
        'rows': [],
        'notes': notes,
    }

    current_df = load_biological_csv(year, month, year)
    if current_df is None or current_df.empty:
        return section

    caption_sentences = []

    for record in current_df.to_dict(orient='records'):
        species_name = normalize_text(record.get('種別', record.get('種目', '')), '')
        phenomenon = normalize_text(record.get('現象', ''), '')
        observed_text = record.get('観測日', '')
        observed_info = parse_biological_date(observed_text, year)

        if not species_name or not phenomenon or not observed_info or observed_info['month'] != month:
            continue

        historical_dates = collect_biological_history(year, month, species_name, phenomenon)
        previous_year_text = find_biological_record_text(year, month, year - 1, species_name, phenomenon)
        earliest_record = parse_biological_date(record.get('最早日', ''))
        latest_record = parse_biological_date(record.get('最晩日', ''))
        earliest_display = format_biological_date(record.get('最早日', ''))
        latest_display = format_biological_date(record.get('最晩日', ''))
        update_text = ''

        if historical_dates:
            earliest_previous = min(historical_dates, key=lambda item: (item['month'], item['day']))
            latest_previous = max(historical_dates, key=lambda item: (item['month'], item['day']))

            if earliest_record and observed_info['year'] == earliest_record['year'] and (observed_info['month'], observed_info['day']) == (earliest_record['month'], earliest_record['day']):
                earliest_display = f"{earliest_previous['month']}月{earliest_previous['day']}日"
                update_text = '最早日を更新した'
            elif latest_record and observed_info['year'] == latest_record['year'] and (observed_info['month'], observed_info['day']) == (latest_record['month'], latest_record['day']):
                latest_display = f"{latest_previous['month']}月{latest_previous['day']}日"
                update_text = '最晩日を更新した'

        sentence = f"{get_biological_display_name(species_name)}：{observed_info['day']}日に{phenomenon}を観測。"
        if update_text:
            sentence += f' 大東島地方では、{update_text}。'
        caption_sentences.append(sentence)

        section['rows'].append([
            BIO_OBSERVATION_PLACE,
            get_biological_display_name(species_name),
            phenomenon,
            format_biological_date(observed_text),
            format_biological_date(record.get('平年値', '')),
            previous_year_text,
            calculate_biological_difference(observed_text, record.get('平年値', ''), year),
            earliest_display,
            latest_display,
        ])

    if caption_sentences:
        section['caption'] = ' '.join(caption_sentences)

    return section
