## 大東島地方の天候レポート Webアプリ

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
- MONGODB_URI=mongodb+srv://... または mongodb://...
- MONGODB_DB=jma_weather（省略可）

## MongoDB 初期化（概況文保存の準備）

1. 依存関係を更新

    python -m pip install -r requirements.txt

2. 環境変数を設定（PowerShell例）

    $env:MONGODB_URI="mongodb+srv://<user>:<password>@<cluster>/"
    $env:MONGODB_DB="jma_weather"

   または、プロジェクト直下の `.env` に以下を記載しても動作します（自動読み込み）。

   MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>/
   MONGODB_DB=jma_weather

3. インデックスを作成

    python init_mongodb.py

この初期化で以下を作成します。

- `gaikyo_raw`:
   - area_code + observed_date + slot の一意インデックス
   - expire_at の TTL インデックス（保持期限切れ自動削除）
- `gaikyo_monthly_meta`:
   - yyyymm の一意インデックス

## 概況1回取得（MongoDB保存）

以下は1回だけ取得して保存する最小コマンドです。

python fetch_overview_to_mongo.py

必要に応じてスロットを明示指定できます（05/11/17）。

python fetch_overview_to_mongo.py --slot 17

## 概況文の目視確認（MongoDB）

MongoDBに保存された直近データを確認します。

python show_overview_records.py --days 5 --limit 20

MongoDB保存データに加えて、現在のJMA最新本文1行も並べて確認できます。

python show_overview_records.py --days 5 --limit 20 --with-live

## 本番向け定時実行（GitHub Actions）

このリポジトリには [overview_collect workflow](.github/workflows/overview_collect.yml) を追加しています。

- JST 05:05 / 11:05 / 17:05 に自動実行
- 実行先は GitHub Actions なので、ローカルPC常時起動は不要

事前に GitHub リポジトリの Secrets に以下を設定してください。

- `MONGODB_URI`
- `MONGODB_DB`（任意。未設定時は `jma_weather`）

手動実行する場合は Actions 画面の `Collect JMA Overview To MongoDB` から `Run workflow` を選び、必要なら slot (05/11/17) を指定します。

## Windows 定時実行（ローカル検証用）

1. タスク登録

powershell -ExecutionPolicy Bypass -File .\scripts\register_overview_tasks.ps1

2. 登録確認

schtasks /Query /TN JMA-Overview-05
schtasks /Query /TN JMA-Overview-11
schtasks /Query /TN JMA-Overview-17

3. 手動実行テスト

powershell -ExecutionPolicy Bypass -File .\scripts\run_overview_job.ps1 -Slot 17
Get-Content .\logs\overview-collector.log -Tail 50

4. タスク削除（必要時）

powershell -ExecutionPolicy Bypass -File .\scripts\unregister_overview_tasks.ps1

## 備考

- 主要な月別 CSV は [data](data) に同梱しており、初回表示の高速化に使います。
- [data](data) に無い年月だけ、アクセス時に自動取得と整形を行います。
- 気象庁サイトへのアクセス状況により応答時間が前後します。


## 今後の実装部分
- 府県天気概況文の自動保存 or 新たな概況文の作成ロジック
- 『荒れた天気』の実装
- 3地点のグラフの見た目の改善