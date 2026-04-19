# 大東島地方の天候レポート Webアプリ

気象庁の公開データを取得し、月報用の表とグラフを HTML で表示する Flask アプリです。

## 主な機能

- 年月を指定してレポート表示
- 気象庁データの自動取得
- 月・旬の表生成
- 3地点のグラフ表示
- 極値・順位表、生物季節観測表の表示

## 必要ファイルの整理

### Webアプリ運用に必要

- [app.py](app.py)
- [app_core.py](app_core.py)
- [create_report_docx.py](create_report_docx.py)
- [downloads.py](downloads.py)
- [build_word_table.py](build_word_table.py)
- [templates/report.html](templates/report.html)
- [static/style.css](static/style.css)
- [obs_list.json](obs_list.json)
- [column_config.json](column_config.json)
- 階級区分の CSV 一式
- [requirements.txt](requirements.txt)
- [render.yaml](render.yaml)
- 配布用キャッシュの [data](data)

### 任意・保守用

- [make_word.py](make_word.py)
- [pdf_to_images.py](pdf_to_images.py)
- [convert_kubun.py](convert_kubun.py)

## ローカル起動

1. 依存関係をインストール

   python -m pip install -r requirements.txt

2. アプリを起動

   python app.py

3. ブラウザで開く

   http://127.0.0.1:5000

## Render デプロイ

このリポジトリには Render 用の [render.yaml](render.yaml) が含まれています。

### 手順

1. GitHub に push
2. Render で New Web Service を作成
3. 対象リポジトリを選択
4. Blueprint または render.yaml を読み込む
5. デプロイ開始

### Render 設定

- Build Command: pip install -r requirements.txt
- Start Command: waitress-serve --host 0.0.0.0 --port $PORT app:app
- Health Check Path: /health

## 環境変数

- AUTO_PREPARE_DATA=1
  - リクエスト時に必要データが無ければ自動生成します。
- FLASK_DEBUG=0
- PYTHON_VERSION=3.11.9

## 備考

- 主要な月別 CSV は [data](data) に同梱しており、初回表示の高速化に使います。
- [data](data) に無い年月だけ、アクセス時に自動取得と整形を行います。
- 気象庁サイトへのアクセス状況により応答時間が前後します。
