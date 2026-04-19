import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def get_previous_month(reference_date=None):
    today = reference_date or date.today()
    previous_month_day = today.replace(day=1) - timedelta(days=1)
    return previous_month_day.year, previous_month_day.month


FALLBACK_YEAR, FALLBACK_MONTH = get_previous_month()
DEFAULT_YEAR = int(os.environ.get('JMA_YEAR', str(FALLBACK_YEAR)))
DEFAULT_MONTH = int(os.environ.get('JMA_MONTH', str(FALLBACK_MONTH)))
PERIODS = ['月', '上旬', '中旬', '下旬']


def get_target_year_month(year=None, month=None):
    target_year = DEFAULT_YEAR if year is None else int(year)
    target_month = DEFAULT_MONTH if month is None else int(month)
    return target_year, target_month


def get_save_dir(year=None, month=None):
    target_year, target_month = get_target_year_month(year, month)
    save_dir = BASE_DIR / 'data' / f'{target_year}_{target_month:02d}'
    save_dir.mkdir(parents=True, exist_ok=True)
    return str(save_dir)


def load_json(file_path):
    resolved_path = Path(file_path)
    if not resolved_path.is_absolute():
        resolved_path = BASE_DIR / resolved_path

    with open(resolved_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def run_script(script_name, year, month):
    env = os.environ.copy()
    env['JMA_YEAR'] = str(year)
    env['JMA_MONTH'] = str(month)
    script_path = BASE_DIR / script_name
    subprocess.run([sys.executable, str(script_path)], check=True, cwd=BASE_DIR, env=env)
