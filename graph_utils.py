import base64
import calendar
import math
import os
import re
from html import escape

import pandas as pd

from app_core import get_save_dir

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


def get_station_display_name(station_name):
    return STATION_DISPLAY_NAMES.get(station_name, station_name)


def normalize_text(value, default=''):
    text = '' if pd.isna(value) else str(value).strip()
    return text if text else default


def extract_numeric_value(text):
    match = re.search(r'-?\d+(?:\.\d+)?', str(text).replace(',', ''))
    return float(match.group()) if match else None


def get_month_last_day(year, month):
    return calendar.monthrange(year, month)[1]


def extract_day_number(value):
    match = re.search(r'(\d+)', str(value))
    return int(match.group(1)) if match else None


def to_plot_value(value):
    text = normalize_text(value, '')
    if text in {'', '///', '--', '---', '×', 'X'}:
        return None
    return extract_numeric_value(text)


def load_graph_csv(year, month, base_php, prec_no, block_no):
    csv_path = os.path.join(get_save_dir(year, month), f'{base_php}_{prec_no}_{block_no}.csv')
    if not os.path.exists(csv_path):
        return None
    return pd.read_csv(csv_path, dtype=str).fillna('')


def find_first_existing_column(df, candidates):
    for column in candidates:
        if column in df.columns:
            return column
    return None


def extract_series_by_day(df, day_column, value_candidates, last_day):
    values = [None] * last_day
    if df is None or day_column not in df.columns:
        return values

    value_column = find_first_existing_column(df, value_candidates)
    if value_column is None:
        return values

    for _, row in df.iterrows():
        day = extract_day_number(row.get(day_column, ''))
        if day is None or day < 1 or day > last_day:
            continue
        values[day - 1] = to_plot_value(row.get(value_column, ''))

    return values


def build_station_graph_dataset(year, month, station_name):
    station_meta = STATION_META[station_name]
    last_day = get_month_last_day(year, month)
    daily_base = 'daily_s1' if station_meta['status'] == 'sfc' else 'daily_a1'
    normal_base = 'nml_sfc_d' if station_meta['status'] == 'sfc' else 'nml_amd_d'

    observed_df = load_graph_csv(year, month, daily_base, station_meta['prec_no'], station_meta['block_no'])
    normal_df = load_graph_csv(year, month, normal_base, station_meta['prec_no'], station_meta['block_no'])

    return {
        'station': station_name,
        'display_name': get_station_display_name(station_name),
        'days': list(range(1, last_day + 1)),
        'temp_max': extract_series_by_day(observed_df, '日', ['日最高気温(℃)'], last_day),
        'temp_min': extract_series_by_day(observed_df, '日', ['日最低気温(℃)'], last_day),
        'temp_mean': extract_series_by_day(observed_df, '日', ['日平均気温(℃)'], last_day),
        'temp_max_normal': extract_series_by_day(normal_df, '要素', ['平年最高気温(℃)', '平年日最高気温(℃)'], last_day),
        'temp_min_normal': extract_series_by_day(normal_df, '要素', ['平年最低気温(℃)', '平年日最低気温(℃)'], last_day),
        'temp_mean_normal': extract_series_by_day(normal_df, '要素', ['平年平均気温(℃)'], last_day),
        'precip': extract_series_by_day(observed_df, '日', ['日降水量(mm)'], last_day),
        'precip_normal': extract_series_by_day(normal_df, '要素', ['平年降水量(mm)'], last_day),
        'sun': extract_series_by_day(observed_df, '日', ['日照時間(h)'], last_day),
        'sun_normal': extract_series_by_day(normal_df, '要素', ['平年日照時間(h)'], last_day),
    }


def gather_graph_values(datasets, keys):
    values = []
    for dataset in datasets:
        for key in keys:
            values.extend([value for value in dataset.get(key, []) if value is not None])
    return values


def choose_nice_step(values, default_step, force_zero=False, target_ticks=6, min_step=None):
    if not values:
        return default_step

    lower = 0 if force_zero else min(values)
    upper = max(values)
    span = max(upper - lower, default_step)
    raw_step = span / max(target_ticks, 1)
    magnitude = 10 ** math.floor(math.log10(raw_step)) if raw_step > 0 else 1
    normalized = raw_step / magnitude

    if normalized <= 1.5:
        nice_fraction = 1
    elif normalized <= 3:
        nice_fraction = 2
    elif normalized <= 4:
        nice_fraction = 2.5
    elif normalized <= 7:
        nice_fraction = 5
    else:
        nice_fraction = 10

    step = nice_fraction * magnitude
    if min_step is not None:
        step = max(step, min_step)
    return step


def compute_axis_bounds(values, step, force_zero=False):
    if not values:
        lower = 0 if force_zero else 0
        upper = step * 2
        return lower, upper

    lower = min(values)
    upper = max(values)

    if force_zero:
        lower = 0
    else:
        lower = math.floor(lower / step) * step

    upper = math.ceil(upper / step) * step
    if upper <= lower:
        upper = lower + step
    return lower, upper


def build_graph_scales(datasets):
    temp_values = gather_graph_values(datasets, ['temp_max', 'temp_min', 'temp_mean', 'temp_max_normal', 'temp_min_normal', 'temp_mean_normal'])
    precip_values = gather_graph_values(datasets, ['precip', 'precip_normal'])
    sun_values = gather_graph_values(datasets, ['sun', 'sun_normal'])

    temp_step = choose_nice_step(temp_values, 5, force_zero=False, target_ticks=5, min_step=5)
    precip_step = choose_nice_step(precip_values, 10, force_zero=True, target_ticks=6, min_step=5)
    sun_step = choose_nice_step(sun_values, 5, force_zero=True, target_ticks=6, min_step=2.5)

    temp_min, temp_max = compute_axis_bounds(temp_values, temp_step, force_zero=False)
    precip_min, precip_max = compute_axis_bounds(precip_values, precip_step, force_zero=True)
    sun_min, sun_max = compute_axis_bounds(sun_values, sun_step, force_zero=True)

    return {
        'temp': {'min': temp_min, 'max': temp_max, 'step': temp_step},
        'precip': {'min': precip_min, 'max': precip_max, 'step': precip_step},
        'sun': {'min': sun_min, 'max': sun_max, 'step': sun_step},
    }


def build_svg_path(days, values, left, top, width, height, y_min, y_max):
    if y_max == y_min:
        return ''

    commands = []
    started = False
    last_day = max(days) if days else 1

    for day, value in zip(days, values):
        if value is None:
            started = False
            continue

        x = left if last_day <= 1 else left + ((day - 1) / (last_day - 1)) * width
        y = top + height - ((value - y_min) / (y_max - y_min)) * height
        commands.append(f"{'M' if not started else 'L'}{x:.2f},{y:.2f}")
        started = True

    return ' '.join(commands)


def render_legend(entries, x, y, columns=1):
    fragments = []
    rows = max(1, math.ceil(len(entries) / columns))

    for index, entry in enumerate(entries):
        column = index // rows
        row = index % rows
        lx = x + column * 62
        ly = y + row * 15
        dash_attr = f' stroke-dasharray="{entry["dash"]}"' if entry.get('dash') else ''
        fragments.append(f'<line x1="{lx}" y1="{ly}" x2="{lx + 18}" y2="{ly}" stroke="{entry["color"]}" stroke-width="2.6"{dash_attr} />')
        fragments.append(f'<text x="{lx + 22}" y="{ly + 4}" font-size="10" font-weight="700">{escape(entry["label"])}</text>')

    return ''.join(fragments)


def render_metric_panel(title, unit, days, series_specs, legend_specs, scale, month, top_offset, show_top_border=True):
    panel_left = 0
    panel_top = top_offset
    panel_width = 258
    panel_height = 206
    panel_right = panel_left + panel_width - 1
    panel_bottom = panel_top + panel_height - 1
    left = 24
    plot_top = top_offset + 50
    plot_width = 228
    plot_height = 122
    bottom = plot_top + plot_height
    right = left + plot_width
    y_min = scale['min']
    y_max = scale['max']
    y_step = scale['step']

    border_fragments = [
        f'<line x1="{panel_left}" y1="{panel_top}" x2="{panel_left}" y2="{panel_bottom}" stroke="#555" stroke-width="1.8" />',
        f'<line x1="{panel_right}" y1="{panel_top}" x2="{panel_right}" y2="{panel_bottom}" stroke="#555" stroke-width="1.8" />',
        f'<line x1="{panel_left}" y1="{panel_bottom}" x2="{panel_right}" y2="{panel_bottom}" stroke="#555" stroke-width="1.8" />',
    ]
    if show_top_border:
        border_fragments.insert(0, f'<line x1="{panel_left}" y1="{panel_top}" x2="{panel_right}" y2="{panel_top}" stroke="#555" stroke-width="1.8" />')

    fragments = [
        *border_fragments,
        f'<text x="6" y="{top_offset + 18}" font-size="15" font-weight="700">({escape(unit)}) {escape(title)}</text>',
        render_legend(legend_specs, 108, top_offset + 10, columns=2 if len(legend_specs) > 2 else 1),
        f'<rect x="{left}" y="{plot_top}" width="{plot_width}" height="{plot_height}" fill="#ffffff" stroke="#444" stroke-width="1.2" />',
    ]

    tick = y_min
    while tick <= y_max + 1e-9:
        y = plot_top + plot_height - ((tick - y_min) / (y_max - y_min)) * plot_height
        fragments.append(f'<line x1="{left}" y1="{y:.2f}" x2="{right}" y2="{y:.2f}" stroke="#d0d0d0" stroke-width="1" />')
        fragments.append(f'<text x="{left - 5}" y="{y + 4:.2f}" font-size="10" font-weight="700" text-anchor="end">{int(tick) if float(tick).is_integer() else tick}</text>')
        tick += y_step

    x_ticks = [1] + [day for day in range(5, max(days) + 1, 5) if day != 1]
    for day in x_ticks:
        x = left if max(days) <= 1 else left + ((day - 1) / (max(days) - 1)) * plot_width
        fragments.append(f'<line x1="{x:.2f}" y1="{bottom}" x2="{x:.2f}" y2="{bottom + 4}" stroke="#444" stroke-width="1" />')
        if day == 1:
            fragments.append(
                f'<text x="{x:.2f}" y="{bottom + 12}" font-size="10" font-weight="700" text-anchor="middle">'
                f'<tspan x="{x:.2f}" dy="0">1</tspan>'
                f'<tspan x="{x:.2f}" dy="9">{month}月</tspan>'
                f'</text>'
            )
        else:
            fragments.append(f'<text x="{x:.2f}" y="{bottom + 12}" font-size="10" font-weight="700" text-anchor="middle">{day}</text>')

    last_day = max(days) if days else 1
    bar_slot = plot_width / max(1, last_day)
    bar_width = max(2.5, bar_slot * 0.45)

    for spec in series_specs:
        if spec.get('type') == 'bar':
            for day, value in zip(days, spec['values']):
                if value is None:
                    continue
                x = left + ((day - 0.5) / last_day) * plot_width - (bar_width / 2)
                y_value = max(value, y_min)
                y = plot_top + plot_height - ((y_value - y_min) / (y_max - y_min)) * plot_height
                fragments.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{bottom - y:.2f}" fill="{spec["color"]}" opacity="0.95" />')
            continue

        path = build_svg_path(days, spec['values'], left, plot_top, plot_width, plot_height, y_min, y_max)
        if not path:
            continue
        dash_attr = f' stroke-dasharray="{spec["dash"]}"' if spec.get('dash') else ''
        fragments.append(f'<path d="{path}" fill="none" stroke="{spec["color"]}" stroke-width="2.2"{dash_attr} />')

    return ''.join(fragments)


def build_station_graph_svg(dataset, year, month, scales):
    days = dataset['days']
    width = 258
    panel_height = 206
    current_top = 0
    panels = []

    panels.append(render_metric_panel(
        '気温',
        '℃',
        days,
        [
            {'values': dataset['temp_max'], 'color': '#ff2d2d', 'dash': '7 3'},
            {'values': dataset['temp_min'], 'color': '#2d4dff', 'dash': '7 3'},
            {'values': dataset['temp_mean'], 'color': '#32cd32'},
            {'values': dataset['temp_max_normal'], 'color': '#444444', 'dash': '3 2'},
            {'values': dataset['temp_min_normal'], 'color': '#444444', 'dash': '3 2'},
            {'values': dataset['temp_mean_normal'], 'color': '#444444', 'dash': '3 2'},
        ],
        [
            {'label': '日最高気温', 'color': '#ff2d2d', 'dash': '7 3'},
            {'label': '日最低気温', 'color': '#2d4dff', 'dash': '7 3'},
            {'label': '日平均気温', 'color': '#32cd32'},
            {'label': '平年値', 'color': '#444444', 'dash': '3 2'},
        ],
        scales['temp'],
        month,
        current_top,
        show_top_border=True,
    ))
    current_top += panel_height - 1

    panels.append(render_metric_panel(
        '降水量',
        'mm',
        days,
        [
            {'values': dataset['precip'], 'color': '#32cd32', 'type': 'bar'},
            {'values': dataset['precip_normal'], 'color': '#444444', 'dash': '3 2'},
        ],
        [
            {'label': '日別値', 'color': '#32cd32'},
            {'label': '平年値', 'color': '#444444', 'dash': '3 2'},
        ],
        scales['precip'],
        month,
        current_top,
        show_top_border=False,
    ))
    current_top += panel_height - 1

    has_sun_data = any(value is not None for value in dataset['sun']) or any(value is not None for value in dataset['sun_normal'])
    if has_sun_data:
        panels.append(render_metric_panel(
            '日照時間',
            'h',
            days,
            [
                {'values': dataset['sun'], 'color': '#ff9900', 'type': 'bar'},
                {'values': dataset['sun_normal'], 'color': '#444444', 'dash': '3 2'},
            ],
            [
                {'label': '日別値', 'color': '#ff9900'},
                {'label': '平年値', 'color': '#444444', 'dash': '3 2'},
            ],
            scales['sun'],
            month,
            current_top,
            show_top_border=False,
        ))
        current_top += panel_height - 1

    height = max(current_top + 1, panel_height)

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" style="background:#ffffff;font-family:Yu Gothic, Meiryo, sans-serif">'
        f'{"".join(panels)}'
        f'</svg>'
    )


def svg_to_data_url(svg_text):
    encoded = base64.b64encode(svg_text.encode('utf-8')).decode('ascii')
    return f'data:image/svg+xml;base64,{encoded}'


def build_graph_cards(year, month):
    datasets = [build_station_graph_dataset(year, month, station_name) for station_name in STATION_ORDER]
    scales = build_graph_scales(datasets)

    cards = []
    for index, dataset in enumerate(datasets, start=1):
        svg = build_station_graph_svg(dataset, year, month, scales)
        cards.append({
            'name': dataset['display_name'],
            'image_url': svg_to_data_url(svg),
            'image_alt': f"{dataset['station']}の気温・降水量・日照時間グラフ",
            'slot': index,
        })
    return cards
