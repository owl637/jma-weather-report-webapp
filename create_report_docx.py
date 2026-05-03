import os
import re
from datetime import datetime, date

import pandas as pd
from flask import Flask, render_template, request

from app_core import BASE_DIR, PERIODS, get_previous_month, get_save_dir, run_script
from biological_utils import build_biological_section
from graph_utils import build_graph_cards, get_month_last_day
PLACEHOLDER_TEXT = '（後で記入）'
OBSERVATORY_NAME = '南大東島地方気象台'
BIO_OBSERVATION_PLACE = '南大東島'
BIO_SPECIES_DISPLAY_NAMES = {
    'ひかんざくら': 'さくら（ひかんざくら）',
}
COLUMN_DISPLAY_NAMES = {
    '気温階級': '階級',
    '降水量階級': '階級',
    '日照時間階級': '階級',
}
CLASS_SOURCE_COLUMNS = {'気温階級', '降水量階級', '日照時間階級'}
SLASH_RENDER_COLUMNS = {
    '気温階級',
    '降水量階級',
    '日照時間階級',
    '日照時間(h)',
    '平年比(%)',
}
STATION_DISPLAY_NAMES = {
    '南大東': '南大東（南大東村在所）',
    '旧東': '旧東（南大東空港）',
    '北大東': '北大東（北大東空港）',
}
STATION_ORDER = ['南大東', '旧東', '北大東']
STATION_META = {
    '南大東': {'status': 'sfc', 'prec_no': 91, 'block_no': 47945},
    '旧東': {'status': 'amd', 'prec_no': 91, 'block_no': 1518},
    '北大東': {'status': 'amd', 'prec_no': 91, 'block_no': 1517},
}
CLASS_PHRASES = {
    '気温': {
        'かなり低い': 'かなり低かった',
        '低い': '低かった',
        '平年並': '平年並だった',
        '高い': '高かった',
        'かなり高い': 'かなり高かった',
    },
    '降水量': {
        'かなり少ない': 'かなり少なかった',
        '少ない': '少なかった',
        '平年並': '平年並だった',
        '多い': '多かった',
        'かなり多い': 'かなり多かった',
    },
    '日照時間': {
        'かなり少ない': 'かなり少なかった',
        '少ない': '少なかった',
        '平年並': '平年並だった',
        '多い': '多かった',
        'かなり多い': 'かなり多かった',
    },
}

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'), static_folder=os.path.join(BASE_DIR, 'static'))


def ensure_report_inputs(year, month):
    save_dir = get_save_dir(year, month)
    required_files = [os.path.join(save_dir, f'Word用_{period}.csv') for period in PERIODS]

    for station_name in STATION_ORDER:
        station_meta = STATION_META[station_name]
        if station_meta['status'] == 'sfc':
            required_files.extend([
                os.path.join(save_dir, f"daily_s1_{station_meta['prec_no']}_{station_meta['block_no']}.csv"),
                os.path.join(save_dir, f"nml_sfc_d_{station_meta['prec_no']}_{station_meta['block_no']}.csv"),
            ])
        else:
            required_files.extend([
                os.path.join(save_dir, f"daily_a1_{station_meta['prec_no']}_{station_meta['block_no']}.csv"),
                os.path.join(save_dir, f"nml_amd_d_{station_meta['prec_no']}_{station_meta['block_no']}.csv"),
            ])

    if all(os.path.exists(file_path) for file_path in required_files):
        gaikyo_csv = os.path.join(save_dir, '概況文.csv')
        raw_gaikyo_csv = os.path.join(save_dir, f'{year}{month:02d}-概況.csv')
        if not os.path.exists(gaikyo_csv) and os.path.exists(raw_gaikyo_csv):
            run_script('build_gaikyo_sentence.py', year, month, ['--month', f'{year}{month:02d}', '--area-name', '大東島地方'])
        return

    run_script('downloads.py', year, month)
    run_script('build_word_table.py', year, month)

    gaikyo_csv = os.path.join(save_dir, '概況文.csv')
    raw_gaikyo_csv = os.path.join(save_dir, f'{year}{month:02d}-概況.csv')
    if not os.path.exists(gaikyo_csv) and os.path.exists(raw_gaikyo_csv):
        run_script('build_gaikyo_sentence.py', year, month, ['--month', f'{year}{month:02d}', '--area-name', '大東島地方'])


def to_reiwa(year):
    if year == 2019:
        return '元'
    if year >= 2019:
        return str(year - 2018)
    return ''


def build_publication_date(date_obj):
    return {
        'year': date_obj.year,
        'month': date_obj.month,
        'day': date_obj.day,
        'reiwa': to_reiwa(date_obj.year),
    }


def load_period_csv(period_name, year, month):
    csv_path = os.path.join(get_save_dir(year, month), f'Word用_{period_name}.csv')
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f'{csv_path} が見つかりません。先に build_word_table.py を実行してください。')
    return pd.read_csv(csv_path, dtype=str).fillna('')


def normalize_value(value, default='／'):
    text = '' if pd.isna(value) else str(value).strip()
    return text if text else default


def load_gaikyo_sentences(year, month):
    gaikyo_path = os.path.join(get_save_dir(year, month), '概況文.csv')
    if not os.path.exists(gaikyo_path):
        return {}

    df = pd.read_csv(gaikyo_path, dtype=str).fillna('')
    if '期間' not in df.columns or '概況文' not in df.columns:
        return {}

    sentence_map = {}
    for row in df.to_dict(orient='records'):
        period = normalize_value(row.get('期間', ''), '')
        sentence = normalize_value(row.get('概況文', ''), '')
        if period and sentence:
            sentence_map[period] = sentence
    return sentence_map


def build_summary_text(period_name, gaikyo_sentences):
    sentence = gaikyo_sentences.get(period_name, '')
    if sentence:
        return sentence
    return f'大東島地方は、{PLACEHOLDER_TEXT}'


def build_table_caption(period_name, month):
    if period_name == '月':
        return f'{month}月の平均気温・降水量・日照時間の平年差（比）と階級※'
    else:
        return f'{period_name}の平均気温・降水量・日照時間の平年差（比）と階級'

def build_table_data(df):
    raw_columns = [re.sub(r'\.\d+$', '', str(column_name)) for column_name in df.columns]
    columns = [COLUMN_DISPLAY_NAMES.get(column_name, column_name) for column_name in raw_columns]
    column_classes = [
        'col-station',
        'col-value',
        'col-ratio',
        'col-class',
        'col-value',
        'col-ratio',
        'col-class',
        'col-value',
        'col-ratio',
        'col-class',
    ][: len(raw_columns)]

    rows = []
    for row in df.itertuples(index=False, name=None):
        row_cells = []
        for index, value in enumerate(row):
            raw_name = raw_columns[index]
            text = normalize_value(value, '')
            class_names = []

            if raw_name in SLASH_RENDER_COLUMNS and text in {'', '／'}:
                text = ''
                class_names.append('slash-cell')

            if raw_name == '地点名':
                class_names.append('station-cell')

            row_cells.append({'text': text, 'class_name': ' '.join(class_names)})
        rows.append(row_cells)

    return columns, rows, column_classes


def get_station_display_name(station_name):
    return STATION_DISPLAY_NAMES.get(station_name, station_name)


def clean_element_name(element_name):
    return re.sub(r'\s*[（(].*?[）)]', '', str(element_name)).strip()


def extract_unit(element_name):
    match = re.search(r'([（(].*?[）)])', str(element_name))
    return match.group(1).strip('()（）') if match else ''


def format_value_with_unit(value_text, element_name):
    text = str(value_text).strip()
    unit = extract_unit(element_name)
    unit_map = {
        'mm': 'ミリ',
        'h': '時間',
        '％': '％',
        '%': '％',
        '℃': '℃',
    }
    display_unit = unit_map.get(unit, unit)

    if not display_unit or not text or display_unit in text or ' ' in text:
        return text
    return f'{text}{display_unit}'


def parse_rank_entry(entry_text):
    text = normalize_value(entry_text, '')
    if text in {'', '///', '--'}:
        return None

    match = re.search(r'^(.*?)\s*\((\d{4}/\d{1,2}(?:/\d{1,2})?)\)$', text)
    if not match:
        return None

    return {
        'value': match.group(1).strip(),
        'date_text': match.group(2),
    }


def parse_rank_date(date_text):
    parts = [int(part) for part in date_text.split('/')]
    if len(parts) == 2:
        return {'year': parts[0], 'month': parts[1], 'day': None}
    return {'year': parts[0], 'month': parts[1], 'day': parts[2]}


def format_rank_date(date_text):
    date_info = parse_rank_date(date_text)
    if date_info['day'] is None:
        return f"{date_info['year']}年{date_info['month']}月"
    return f"{date_info['year']}年{date_info['month']}月{date_info['day']}日"


def get_period_name_by_day(day):
    if day is None:
        return '月'
    if day <= 10:
        return '上旬'
    if day <= 20:
        return '中旬'
    return '下旬'


def extract_numeric_value(text):
    match = re.search(r'-?\d+(?:\.\d+)?', str(text).replace(',', ''))
    return float(match.group()) if match else None


def determine_update_action(rank, entry, baseline_entry):
    if rank == 1:
        return 'updated'

    current_value = extract_numeric_value(entry['value'])
    baseline_value = extract_numeric_value(baseline_entry['value']) if baseline_entry else None

    if current_value is not None and baseline_value is not None and current_value == baseline_value:
        return 'recorded'
    return 'ranked'


def load_rank_csv(year, month, status, block_no, scope_label):
    base_php = 'rank_s' if status == 'sfc' else 'rank_a'
    csv_path = os.path.join(get_save_dir(year, month), f'{base_php}_{scope_label}_91_{block_no}.csv')
    if not os.path.exists(csv_path):
        return None
    return pd.read_csv(csv_path, dtype=str).fillna('')


def collect_rank_updates(year, month):
    updates = {'all': [], 'month': []}

    for station_name in STATION_ORDER:
        station_meta = STATION_META[station_name]

        for scope_label in ['all', 'month']:
            df = load_rank_csv(year, month, station_meta['status'], station_meta['block_no'], scope_label)
            if df is None or df.empty:
                continue

            best_updates = {}

            for row_index, row in df.iterrows():
                element = normalize_value(row.get('要素名／順位', ''), '')
                if not element or element in {'///', '--'}:
                    continue

                for rank in range(1, 4):
                    entry = parse_rank_entry(row.get(f'{rank}位', ''))
                    if entry is None:
                        continue

                    date_info = parse_rank_date(entry['date_text'])
                    if date_info['year'] != year or date_info['month'] != month:
                        continue

                    comparison_column = f'{rank + 1}位' if rank < 10 else ''
                    comparison_entry = parse_rank_entry(row.get(comparison_column, '')) if comparison_column else None
                    previous_column = '2位' if rank == 1 else '1位'
                    previous_entry = parse_rank_entry(row.get(previous_column, ''))
                    action = determine_update_action(rank, entry, previous_entry)

                    current_value = extract_numeric_value(entry['value'])
                    comparison_value = extract_numeric_value(comparison_entry['value']) if comparison_entry else None
                    is_tied_with_lower_rank = current_value is not None and comparison_value is not None and current_value == comparison_value
                    display_value = entry['value'] + '*' if is_tied_with_lower_rank else entry['value']
                    update_item = {
                        'station': station_name,
                        'station_display': get_station_display_name(station_name),
                        'scope': scope_label,
                        'source_order': row_index,
                        'element': re.sub(r'\s+', ' ', element).strip(),
                        'updated_value': display_value,
                        'observed_date': format_rank_date(entry['date_text']),
                        'rank': rank,
                        'extreme_value': previous_entry['value'] if previous_entry else PLACEHOLDER_TEXT,
                        'extreme_date': format_rank_date(previous_entry['date_text']) if previous_entry else PLACEHOLDER_TEXT,
                        'period_name': get_period_name_by_day(date_info['day']),
                        'day': date_info['day'],
                        'action': action,
                    }

                    key = (station_name, update_item['element'])
                    current_best = best_updates.get(key)
                    if current_best is None or rank < current_best['rank']:
                        best_updates[key] = update_item

            updates[scope_label].extend(best_updates.values())

    return updates


def join_items(items):
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f'{items[0]}と{items[1]}'
    return '、'.join(items[:-1]) + f'、{items[-1]}'


def join_action_clauses(clauses):
    if not clauses:
        return ''
    if len(clauses) == 1:
        return clauses[0] + 'した。'
    return 'し、'.join(clauses[:-1]) + 'し、' + clauses[-1] + 'した。'


def build_station_value_phrase(item):
    return f"{item['station_display']}で{clean_element_name(item['element'])}{format_value_with_unit(item['updated_value'], item['element'])}"


def build_month_extreme_sentence(rank_updates, month):
    annual_monthly = [item for item in rank_updates['all'] if item['period_name'] == '月' and item['rank'] == 1]
    monthly_monthly = [item for item in rank_updates['month'] if item['period_name'] == '月' and item['rank'] == 1]

    sentences = []
    grouped_by_element = {}
    for item in annual_monthly:
        grouped_by_element.setdefault(item['element'], []).append(item)

    shared_summary_elements = set()
    for element, items in grouped_by_element.items():
        value_parts = [
            f"{item['station_display']}で{format_value_with_unit(item['updated_value'], element)}"
            for item in items
        ]
        count_phrase = '3地点すべてで' if len(items) == len(STATION_ORDER) else ''
        action_word = '記録' if all(item['action'] == 'recorded' for item in items) else '更新'
        base_label = clean_element_name(element).split('の')[0]
        sentences.append(
            f"{month}月の{base_label}は、" + '、'.join(value_parts) + f"を観測し、{count_phrase}{clean_element_name(element)}の通年の極値を{action_word}した。"
        )
        if len(items) > 1:
            shared_summary_elements.add(element)

    for station_name in STATION_ORDER:
        station_items = [
            item for item in monthly_monthly
            if item['station'] == station_name and item['element'] not in shared_summary_elements
        ]
        if not station_items:
            continue

        value_phrases = [f"{clean_element_name(item['element'])}{format_value_with_unit(item['updated_value'], item['element'])}" for item in station_items]
        updated_elements = [clean_element_name(item['element']) for item in station_items if item['action'] == 'updated']
        recorded_elements = [clean_element_name(item['element']) for item in station_items if item['action'] == 'recorded']
        clauses = []
        if updated_elements:
            clauses.append(f"{join_items(updated_elements)}の{month}月としての極値を更新")
        if recorded_elements:
            clauses.append(f"{join_items(recorded_elements)}の{month}月としての極値を記録")
        if clauses:
            sentences.append(f"{get_station_display_name(station_name)}では、{join_items(value_phrases)}を観測し、" + join_action_clauses(clauses))

    if not sentences:
        # return f'極値を更新した場合の文章は、{PLACEHOLDER_TEXT}'
        return f''

    lead = sentences[0]
    for sentence in sentences[1:]:
        lead += ' また、' + sentence
    return lead


def build_period_extreme_sentence(rank_updates, period_name, month):
    annual_daily = [item for item in rank_updates['all'] if item['period_name'] == period_name and item['rank'] == 1]
    monthly_daily = [item for item in rank_updates['month'] if item['period_name'] == period_name and item['rank'] == 1]

    sentences = []
    target_days = sorted({item['day'] for item in annual_daily + monthly_daily if item['day'] is not None})

    for day in target_days:
        day_annual = [item for item in annual_daily if item['day'] == day]
        day_monthly = [item for item in monthly_daily if item['day'] == day]
        day_items = day_annual + day_monthly
        stations = sorted({item['station'] for item in day_items}, key=STATION_ORDER.index)

        if len(stations) == 1:
            station_name = stations[0]
            station_items = [item for item in day_items if item['station'] == station_name]
            unique_items = {}
            for item in station_items:
                unique_items.setdefault(item['element'], item)

            value_phrases = [
                f"{clean_element_name(item['element'])}{format_value_with_unit(item['updated_value'], item['element'])}"
                for item in unique_items.values()
            ]

            clauses = []
            annual_elements = [clean_element_name(item['element']) for item in day_annual if item['station'] == station_name]
            if annual_elements:
                clauses.append(f"{join_items(annual_elements)}の通年の極値を更新")

            updated_elements = [clean_element_name(item['element']) for item in day_monthly if item['station'] == station_name and item['action'] == 'updated']
            recorded_elements = [clean_element_name(item['element']) for item in day_monthly if item['station'] == station_name and item['action'] == 'recorded']
            if updated_elements:
                clauses.append(f"{join_items(updated_elements)}の{month}月としての極値を更新")
            if recorded_elements:
                clauses.append(f"{join_items(recorded_elements)}の{month}月としての極値を記録")

            if clauses:
                sentences.append(f"{day}日は、{get_station_display_name(station_name)}で{join_items(value_phrases)}を観測し、" + join_action_clauses(clauses))
            continue

        grouped = {}
        for item in day_items:
            key = (item['scope'], item['element'], item['action'])
            grouped.setdefault(key, []).append(item)

        day_sentences = []
        for (scope, element, action), items in sorted(grouped.items(), key=lambda pair: (pair[1][0]['rank'], STATION_ORDER.index(pair[1][0]['station']))):
            items = sorted(items, key=lambda item: STATION_ORDER.index(item['station']))
            phrases = [
                f"{item['station_display']}で{clean_element_name(item['element'])}{format_value_with_unit(item['updated_value'], item['element'])}"
                for item in items
            ]
            scope_text = '通年の極値' if scope == 'all' else f'{month}月としての極値'
            action_text = '記録' if action == 'recorded' else '更新'
            if len(items) > 1:
                day_sentences.append(f"{join_items(phrases)}をそれぞれ観測し、ともに{clean_element_name(element)}の{scope_text}を{action_text}した。")
            else:
                day_sentences.append(f"{phrases[0]}を観測し、{clean_element_name(element)}の{scope_text}を{action_text}した。")

        if day_sentences:
            first_sentence = f"{day}日は、{day_sentences[0]}"
            sentences.append(first_sentence + (' ' + ' '.join(day_sentences[1:]) if len(day_sentences) > 1 else ''))

    return ' '.join(sentences) if sentences else f''


def build_extreme_sentence(rank_updates, period_name, month):
    if period_name == '月':
        return build_month_extreme_sentence(rank_updates, month)
    return build_period_extreme_sentence(rank_updates, period_name, month)


def build_main_station_class_sentence(records):
    main_record = None
    for record in records:
        station = normalize_value(record.get('地点名', ''), '')
        if station == '南大東':
            main_record = record
            break

    if main_record is None:
        return f'南大東（南大東村在所）の階級については、{PLACEHOLDER_TEXT}'

    sentences = []
    for item_name, column_name, label in [
        ('気温', '気温階級', '平均気温'),
        ('降水量', '降水量階級', '降水量'),
        ('日照時間', '日照時間階級', '日照時間'),
    ]:
        class_name = normalize_value(main_record.get(column_name, '／'))
        phrase = CLASS_PHRASES[item_name].get(class_name)
        if phrase:
            sentences.append(f'{label}は{phrase}')

    if not sentences:
        return f'南大東（南大東村在所）の階級については、{PLACEHOLDER_TEXT}'

    return '南大東（南大東村在所）の' + '。'.join(sentences) + '。'


def build_section_paragraphs(records, summary, period_name, year, month, rank_updates):
    paragraphs = [
        summary,
        build_extreme_sentence(rank_updates, period_name, month),
        build_main_station_class_sentence(records),
    ]
    baiu_footnote = ""
    if period_name == '月':
        from baiu_utils import build_baiu_entry_sentence, build_baiu_end_sentence
        baiu_text = build_baiu_entry_sentence(year, month)
        if baiu_text:
            paragraphs.append(baiu_text)
        baiu_end_text = build_baiu_end_sentence(year, month)
        if baiu_end_text:
            paragraphs.append(baiu_end_text)
        if baiu_text or baiu_end_text:
            baiu_footnote = (
                f"＊速報値。気象予測をもとに行う梅雨明けの速報とは別に、梅雨の季節を過ぎてから、"
                f"春から夏にかけての実際の天候経過を考慮した検討を行います。"
                f"そこで検討した梅雨入りの確定値は、９月以降に気象庁ホームページや"
                f"「{year}年の沖縄地方の天候」（{year + 1}年１月発表）等において公表します。"
            )
    return paragraphs, baiu_footnote


def build_sections(year, month, rank_updates, gaikyo_sentences):
    sections = []
    for period_name in PERIODS:
        df = load_period_csv(period_name, year, month)
        columns, rows, column_classes = build_table_data(df)
        records = df.to_dict(orient='records')
        summary = build_summary_text(period_name, gaikyo_sentences)
        overview, baiu_footnote = build_section_paragraphs(records, summary, period_name, year, month, rank_updates)
        sections.append({
            'name': period_name,
            'summary': summary,
            'caption': build_table_caption(period_name, month),
            'overview': overview,
            'baiu_footnote': baiu_footnote,
            'columns': columns,
            'column_classes': column_classes,
            'rows': rows,
            'records': records,
        })
    return sections



def build_extreme_table_rows(update_items):
    sorted_items = sorted(
        update_items,
        key=lambda item: (STATION_ORDER.index(item['station']), item.get('source_order', 0), item['rank'])
    )

    return [
        [
            item['station'],
            item['element'],
            item['updated_value'],
            item['observed_date'],
            str(item['rank']),
            item['extreme_value'],
            item['extreme_date'],
        ]
        for item in sorted_items
    ]


def build_extreme_tables(rank_updates):
    columns = ['地点名', '要素', '更新した値', '観測日（月）', '順位', '極値', '観測日・月']
    column_classes = ['ext-col-station', 'ext-col-element', 'ext-col-value', 'ext-col-date', 'ext-col-rank', 'ext-col-value', 'ext-col-date']
    tables = []

    for title, items in [
        ('極値・順位値更新表（通年）', rank_updates['all']),
        ('極値・順位値更新表（月）', rank_updates['month']),
    ]:
        rows = build_extreme_table_rows(items)
        if not rows:
            continue
        tables.append({
            'title': title,
            'columns': columns,
            'column_classes': column_classes,
            'rows': rows,
        })

    return tables



def create_app():
    return app


@app.route('/')
def report():
    fallback_year, fallback_month = get_previous_month()
    year = request.args.get('year', default=fallback_year, type=int)
    month = request.args.get('month', default=fallback_month, type=int)

    report_date_str = request.args.get('report_date', default=None)
    if report_date_str:
        try:
            pub_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
        except ValueError:
            pub_date = date.today()
    else:
        pub_date = date.today()

    if os.environ.get('AUTO_PREPARE_DATA', '1') == '1':
        ensure_report_inputs(year, month)
    rank_updates = collect_rank_updates(year, month)
    gaikyo_sentences = load_gaikyo_sentences(year, month)
    sections = build_sections(year, month, rank_updates, gaikyo_sentences)
    month_section = sections[0]
    ten_day_sections = sections[1:]
    extreme_tables = build_extreme_tables(rank_updates)
    bio_section = build_biological_section(year, month)
    show_extreme_dedicated_page = len(extreme_tables) == 2
    merge_sections_into_graph_page = len(extreme_tables) == 0
    bio_page_number = 3 if merge_sections_into_graph_page else (5 if show_extreme_dedicated_page else 4)
    total_pages = bio_page_number

    return render_template(
        'report.html',
        year=year,
        month=month,
        reiwa=to_reiwa(year),
        report_date=build_publication_date(pub_date),
        report_date_str=pub_date.strftime('%Y-%m-%d'),
        month_last_day=get_month_last_day(year, month),
        month_section=month_section,
        ten_day_sections=ten_day_sections,
        graph_cards=build_graph_cards(year, month),
        extreme_tables=extreme_tables,
        bio_section=bio_section,
        show_extreme_dedicated_page=show_extreme_dedicated_page,
        merge_sections_into_graph_page=merge_sections_into_graph_page,
        bio_page_number=bio_page_number,
        total_pages=total_pages,
        generated_at=datetime.now().strftime('%Y-%m-%d %H:%M'),
        placeholder_text=PLACEHOLDER_TEXT,
        observatory_name=OBSERVATORY_NAME,
    )


@app.route('/health')
def health():
    return {'status': 'ok'}


def main():
    port = int(os.environ.get('PORT', '5000'))
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'

    print(f'Open http://127.0.0.1:{port} in your browser.')
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    main()
