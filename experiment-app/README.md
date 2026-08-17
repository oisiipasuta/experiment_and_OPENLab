# 音楽聴取実験用 Web アプリ

Flask + SQLite で動く、音楽聴取実験用のローカル Web アプリです。  
楽曲再生中の「良い」と感じたタイミングを複数回記録でき、再生後に曲全体についての 7 段階回答を保存できます。

## 主な機能

- 参加者IDの自動発行と進行状態の保持
- 年齢 / 性別 / 音楽経験 / 聴取環境 / ブラウザ / 使用機器の取得と保存
- 練習後の音量確認と保存
- 練習試行と本試行の両対応
- participant ごとの楽曲提示順ランダム化と固定保存
- `static/audio/` からの楽曲自動読み込み
- 楽曲再生中の複数回ボタン操作記録
- 全ボタン操作地点の保存と、最終的に選んだ 1 件の保存
- 押した時刻から作る 4 秒固定区間の保存
- 9 項目の 7 段階回答
- SQLite への永続化
- 管理画面のタブ切り替え
- 管理画面での参加者別 / 楽曲別の視覚的サマリー
- 楽曲別平均評点のヒートマップ表示
- 分析用の横持ち CSV エクスポート
- 管理画面での一覧確認
- participants / button_presses / press_events / impression_ratings の CSV エクスポート

## ディレクトリ構成

```text
experiment-app/
├─ app.py
├─ models.py
├─ requirements.txt
├─ README.md
├─ templates/
│  ├─ base.html
│  ├─ index.html
│  ├─ player.html
│  ├─ rating.html
│  ├─ complete.html
│  ├─ select_press.html
│  └─ admin_dashboard.html
└─ static/
   ├─ css/
   │  └─ style.css
   ├─ js/
   │  ├─ admin.js
   │  ├─ player.js
   │  └─ select_press_preview.js
   └─ audio/
      └─ *.mp3 / *.wav
```

## DB 構成

必須テーブルに加えて、参加者ごとの提示順を固定保存する `participant_song_orders` を追加しています。
全ボタン操作は `press_events` に保存し、理由回答前の一時データとして `button_press_candidates` も使います。

- `participants`
  - `id`
  - `participant_id`
  - `age`
  - `gender`
  - `music_experience`
  - `music_experience_years`
  - `music_experience_type`
  - `listening_environment`
  - `listening_environment_note`
  - `experiment_browser`
  - `experiment_browser_note`
  - `listening_device`
  - `listening_device_note`
  - `practice_volume_impression`
  - `practice_volume_level`
  - `practice_volume_confirmed_at`
  - `current_assignment_index`
  - `current_phase`
  - `consent_given`
  - `consented_at`
  - `created_at`
- `songs`
  - `id`
  - `song_id`
  - `file_path`
  - `display_order`
  - `is_practice`
  - `is_active`
- `participant_song_orders`
  - `id`
  - `participant_id`
  - `song_id`
  - `order_index`
  - `is_practice`
  - `press_count`
  - `has_press`
  - `all_press_audio_times`
  - `selected_press_event_id`
- `press_events`
  - `id`
  - `assignment_id`
  - `participant_id`
  - `song_id`
  - `press_index`
  - `audio_time_sec`
  - `performance_time_ms`
  - `client_timestamp`
  - `server_received_at`
  - `segment_rule`
  - `segment_start_sec`
  - `segment_end_sec`
  - `segment_duration_sec`
  - `segment_clipped_start`
  - `is_selected`
- `button_presses`
  - `id`
  - `participant_id`
  - `song_id`
  - `assignment_id`
  - `press_event_id`
  - `is_practice`
  - `press_order`
  - `pressed_time`
  - `selected_audio_time_sec`
  - `selected_segment_rule`
  - `selected_segment_start_sec`
  - `selected_segment_end_sec`
  - `selected_segment_duration_sec`
  - `selection_reason`
  - `created_at`
- `button_press_candidates`
  - `id`
  - `participant_id`
  - `song_id`
  - `is_practice`
  - `press_order`
  - `pressed_time`
  - `created_at`
- `impression_ratings`
  - `id`
  - `participant_id`
  - `song_id`
  - `is_practice`
  - `bright_dark`
  - `smooth_rough`
  - `rich_thin`
  - `clear_muddy`
  - `intense_calm`
  - `heavy_light`
  - `soft_hard`
  - `thick_thin`
  - `like_dislike`
  - `created_at`

## セットアップ

リポジトリのルートから作業する場合は、先にこのアプリのフォルダへ移動してください。

```zsh
cd experiment-app
```

### 1. Python 環境の有効化

この環境では、以下で Python 環境を有効化できます。

```zsh
source ~/.venv/pylec/bin/activate
```

新しく仮想環境を作る場合は、以下のように作成してください。

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. 依存関係のインストール

```powershell
pip install -r requirements.txt
```

### 3. SECRET_KEY と管理者ログインの設定

現在のアプリは、Flask のセッションを使うため `SECRET_KEY` を使用します。
環境変数 `SECRET_KEY` を設定している場合はその値を使い、設定していない場合は `instance/.secret_key` に安全なランダムキーを自動生成します。

管理画面はログインが必要です。管理者IDは既定で `admin` です。
環境変数 `ADMIN_PASSWORD` を設定している場合はその値を使い、設定していない場合は `instance/.admin_password` にランダムな管理者パスワードを自動生成します。

macOS / zsh:

```zsh
export SECRET_KEY=local-dev-secret
export ADMIN_PASSWORD=local-admin-password
```

Windows PowerShell:

```powershell
$env:SECRET_KEY = "local-dev-secret"
$env:ADMIN_PASSWORD = "local-admin-password"
```

### 4. DB 初期化

```zsh
python -m flask --app app init-db
```

macOS / Linux では、既定で SQLite ファイルを `instance/experiment.db` に作成します。  
Windows で `LOCALAPPDATA` が設定されている場合は、`%LOCALAPPDATA%\music-listening-experiment\experiment.db` を使います。保存先を変更したい場合は `EXPERIMENT_DB_PATH` 環境変数で上書きできます。

### 5. 楽曲の同期

`static/audio/` に置いた音源を DB に同期します。アプリ起動時にも自動同期されますが、手動で確認したい場合は以下を実行してください。

```zsh
python -m flask --app app sync-songs
```

サンプル音源を自動生成したい場合だけ、以下を実行してください。

```zsh
python -m flask --app app seed-data
```

### 6. アプリ起動

```zsh
python -m flask --app app run
```

起動後に以下へアクセスします。

- 実験画面: [http://127.0.0.1:5000](http://127.0.0.1:5000)
- 管理画面: [http://127.0.0.1:5000/admin](http://127.0.0.1:5000/admin)

## 実行方法

1. トップ画面から実験説明へ進む
2. 実験説明を確認し、参加者情報入力へ進む
3. 参加者IDは自動発行されるため、年齢、性別、楽器演奏などの音楽経験、実験に使う端末・OS、ブラウザ、音楽を聴くときに使う機器を入力
4. 練習試行がある場合は先に提示
5. 練習試行が終わったら、設定した音量の感じ方とおおよその音量レベルを回答
6. 音声を再生し、良いと感じた瞬間にボタンを押す
7. 曲が終わったら、曲全体について 9 項目すべてに回答
8. ボタンを押した部分がある場合は、回答後に記録された部分を確認し、理由を回答
9. 次の楽曲へ進行
10. すべて終わると完了画面を表示

## 動作確認手順

1. `source ~/.venv/pylec/bin/activate`
2. `export SECRET_KEY=local-dev-secret`
3. `export ADMIN_PASSWORD=local-admin-password`
4. `python -m flask --app app init-db`
5. `python -m flask --app app sync-songs`
6. `python -m flask --app app run`
7. ブラウザで `/` を開く
8. 説明を確認し、参加者情報を入力して開始
9. 音源を再生し、ボタンを数回押す
10. 曲全体について回答し、必要に応じて記録された部分の理由を回答
11. 完了後に `/admin` へアクセスし、管理者IDとパスワードでログインして保存データを確認
12. CSV エクスポートを試す

## 独自音源を使う場合

1. 音源ファイルを `static/audio/` に配置
2. 必要なら `python -m flask --app app sync-songs` を実行する
3. 新しく自動発行された参加者IDで開始

音源ファイルと動画ファイルは容量・権利管理の都合で Git 管理外にしています。GitHub に保存されるのは置き場所の説明だけです。

自動登録のルール:

- `static/audio/` 配下を再帰的に走査します
- `static/audio/practice/` 配下のファイル、または `practice_` / `practice-` で始まるファイル名は練習試行として扱います
- それ以外は本試行として扱います
- `song_id` はファイルの相対パスから自動生成されます
- 実際の提示順は participant ごとにランダム化されますが、その順序は開始時に固定保存されます

例:

- `static/audio/practice/practice_a.wav` -> 練習試行
- `static/audio/main/theme_01.mp3` -> 本試行
- `static/audio/theme_02.wav` -> 本試行

## 実装上の補足

- ボタン押下保存は `BUTTON_PRESS_MODE` 設定で将来的に切り替えやすくしています。
  - `all`: すべて保存
  - `first_only`: 最初の 1 回だけ保存
  - `last_only`: 最後の 1 回だけ有効にする想定
- 全ボタン操作は `press_events` に保存されます。最終的に選んだ 1 件は `button_presses` にも保存されます。
- `participant_song_orders.all_press_audio_times` には、`押下1:1.000000; 押下2:5.250000` のように、その曲で押した全時刻をまとめて保存します。
- 4 秒区間は `segment_rule = pre_4sec` として保存します。曲の開始直後に押した場合も、`0.000000` 秒から始まる 4 秒固定区間として保存します。
- `audio_time_sec` はブラウザの `audio.currentTime` を基準に保存し、`server_received_at` は参考ログとして保存します。
- `created_at` は日本時間（Asia/Tokyo）で保存します。
- 管理画面では、生データ一覧に加えて、参加者別の評価カード表示と、楽曲別の平均値バー表示・個別回答表示を確認できます。
- 管理画面は `Overview / Participants / Songs / Dataset` のタブに分かれており、`Songs` タブでは平均評点ヒートマップ、`Dataset` タブでは分析用の横持ちデータを確認できます。
- 既存 DB に新しい列が足りない場合は、起動時に軽量マイグレーションで不足列を追加します。
- 質問項目を増やしたい場合は `constants.py` の `SD_ITEMS` を追加してください。

## 起動できないとき

`SECRET_KEY` を明示的に指定したい場合は、`flask` コマンドの前に `SECRET_KEY` を設定してください。

macOS / zsh:

```zsh
source ~/.venv/pylec/bin/activate
export SECRET_KEY=local-dev-secret
python -m flask --app app run
```

DB を作り直したい場合は、以下を実行してください。

```zsh
python -m flask --app app init-db
python -m flask --app app sync-songs
```
