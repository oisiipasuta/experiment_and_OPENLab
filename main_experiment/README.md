# 音楽聴取実験用 Web アプリ

Flask で動く、音楽聴取実験用の Web アプリです。ローカル開発では SQLite、PythonAnywhere の本番環境では MySQL を使用します。
楽曲再生中の「良い」と感じたタイミングを複数回記録でき、再生後に曲全体についての 7 段階回答を保存できます。

## 使い方（最短手順）

### 実験管理者：ローカルで起動する

macOS / Linux では、リポジトリのルートから次を実行します。

```zsh
cd main_experiment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY=local-dev-secret
export ADMIN_PASSWORD=local-admin-password
python -m flask --app app db upgrade
python -m flask --app app sync-songs
python -m flask --app app run
```

Windows PowerShell では、仮想環境の有効化と環境変数の設定を次のように置き換えます。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY = "local-dev-secret"
$env:ADMIN_PASSWORD = "local-admin-password"
python -m flask --app app db upgrade
python -m flask --app app sync-songs
python -m flask --app app run
```

起動後のURLは次のとおりです。

- 参加者用：[http://127.0.0.1:5000](http://127.0.0.1:5000)
- 途中再開：[http://127.0.0.1:5000/resume](http://127.0.0.1:5000/resume)
- 管理者用：[http://127.0.0.1:5000/admin](http://127.0.0.1:5000/admin)

起動時にDB作成や楽曲同期は自動実行されません。初回とアプリ更新後は `db upgrade` と `sync-songs` を必ず実行してください。

### 実験管理者：音源を登録する

1. 練習曲を `static/audio/practice/` に配置します。
2. 共通曲15曲を `static/audio/common/` に配置します。
3. セット1・2・3それぞれについて、ランダム学習曲10曲を `static/audio/random_sets/<番号>/train/`、ランダムテスト曲5曲を `static/audio/random_sets/<番号>/test/` に配置します。3セット全体でランダム学習30曲・ランダムテスト15曲です。決定済みの曲リストに従い、曲の区分を固定してください。
4. 参加者にセット番号（1・2・3）を指定します。参加者情報画面のプルダウンから番号を選ぶと、そのセットを使います。参加コードや `STIMULUS_PARTICIPANT_CODES` 環境変数の設定は不要です。
5. `python -m flask --app app sync-songs` を実行します。管理画面から再同期した場合も同じセット割り当てになります。
6. 管理画面で音源数を確認します。本番の構成は共通15曲、各セットの学習10曲・テスト5曲です。参加者1人あたり共通15曲＋指定セットの学習10曲＋テスト5曲＝30曲を提示します。現在はデバッグのため曲数チェックを一時的に外しており、配置済みの曲だけで開始できます。`train/` の曲は本試行用で、練習試行の `practice/` とは別です。

品質確認を設計どおり本試行中に2回出すには、本試行の音源が25曲以上必要です。ファイル名と練習曲の判定ルールは「独自音源を使う場合」を参照してください。

### CloudWorks参加者：実験に回答する

1. 指定されたセット番号（1・2・3）をプルダウンで選択し、CloudWorksのワーカーIDと参加者情報を入力します。ワーカーIDの生値は保存されません。
2. 画面に表示される12文字の途中再開コードを、実験終了まで手元に控えます。
3. 説明→参加者情報→練習→音量確認→本試行の順に進みます。
4. 各曲で、音源を最後まで再生し、「好き」と感じた箇所があればボタンを押します。押さない回答も認められています。
5. 再生後に9項目を1〜7で評定します。一部の本試行では10項目目が表示されるため、文面の指示に従います。
6. 毎曲、評定後に理由回答画面へ進みます。ボタンを押した曲では該当区間と理由を選択します。押さなかった曲では押さなかった理由を複数選択（最低1つ必須）し、任意で補足を記入します。曲の聴き直しも任意でできます。
7. 実験完了画面に表示される `CW-XXXXXXXXXX` 形式の確認コードをCloudWorksに提出します。

途中でブラウザを閉じた場合は、`/resume` で同じCloudWorksワーカーIDと途中再開コードを入力すると、保存済みの続きから再開できます。同じワーカーIDで最初から再参加することはできません。

### 実験管理者：回答とCloudWorks確認コードを確認する

1. `/admin` を開き、管理者ID（既定値は `admin`）と設定した管理者パスワードでログインします。
2. 「データ品質とCloudWorks確認」で、品質フラグあり/なしを絞り込みます。フラグは確認用であり、自動削除や自動非承認は行われません。
3. CloudWorksから回収した確認コードを1行に1件ずつ貼り付け、「照合して使用済みにする」を押します。`valid`、`duplicate`、`incomplete`、`unknown` のいずれかで判定されます。
4. 分析には「分析用 CSV」を使います。必要に応じて participants、button_presses、press_events、impression_ratings の個別CSVもダウンロードできます。

PythonAnywhereへの公開方法は「PythonAnywhere本番構成」、CloudWorksの募集文は [CloudWorks募集文テンプレート.md](CloudWorks募集文テンプレート.md) を参照してください。

## 主な機能

- 参加者IDの自動発行と進行状態の保持
- 年齢 / 性別 / 音楽経験 / 聴取環境 / ブラウザ / 使用機器の取得と保存
- 練習後の音量確認と保存
- 練習試行と本試行の両対応
- participant ごとの楽曲提示順ランダム化と固定保存
- `static/audio/` からの楽曲自動読み込み
- 楽曲再生中の複数回ボタン操作記録
- 全ボタン操作地点の保存と、最終的に選んだ 1 件の保存
- 押下時刻を終点とする直前4秒区間の保存。開始4秒未満の押下は冒頭0〜4秒を保存
- 9 項目の 7 段階回答
- SQLite への永続化
- 管理画面のタブ切り替え
- 管理画面での参加者別 / 楽曲別の視覚的サマリー
- 楽曲別平均評点のヒートマップ表示
- 分析用の横持ち CSV エクスポート
- 管理画面での一覧確認
- participants / button_presses / press_events / impression_ratings の CSV エクスポート
- 本試行中2回の指示遵守チェック（評定画面で「5」を指定）
- CloudWorksワーカーIDのHMAC照合、途中再開コード、参加者別完了コード
- 再生・タブ離脱・評定時間の品質テレメトリと確認フラグ
- CSRF保護、管理者ログイン制限、セキュリティヘッダー
- SQLite開発環境とPythonAnywhere MySQL本番環境の切り替え

## ディレクトリ構成

```text
main_experiment/
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
  - `no_press_reason_choices`: 押下なしの理由コードのJSON配列（nullable）
  - `no_press_reason_note`: 任意の補足（最大500文字、nullable）
  - `no_press_reason_submitted_at`: 理由回答の保存時刻（nullable）
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
- `participant_credentials`: ワーカーIDと再開コードのHMAC、完了コード発行・照合時刻
- `attention_checks`: 品質確認の期待値・実回答・合否・回答時間
- `trial_telemetry`: 再生完了率、タブ離脱、シーク、一時停止、評定時間
- `quality_flags`: 自動除外を行わない分析確認用フラグ

## セットアップ（詳細）

リポジトリのルートから作業する場合は、先にこのアプリのフォルダへ移動してください。

```zsh
cd main_experiment
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

### 3. ローカル用SECRET_KEYと管理者ログインの設定

現在のアプリは、Flask のセッションを使うため `SECRET_KEY` を使用します。
環境変数 `SECRET_KEY` を設定している場合はその値を使い、設定していない場合は `instance/.secret_key` に安全なランダムキーを自動生成します。

管理画面はログインが必要です。開発環境では `ADMIN_PASSWORD` を使用できます。本番環境では平文パスワードを設定せず、`ADMIN_PASSWORD_HASH` が必須です。

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

### 4. DBの初期化・更新

```zsh
python -m flask --app app db upgrade
```

macOS / Linux では、既定で SQLite ファイルを `instance/experiment.db` に作成します。  
Windows で `LOCALAPPDATA` が設定されている場合は、`%LOCALAPPDATA%\music-listening-experiment\experiment.db` を使います。保存先を変更したい場合は `EXPERIMENT_DB_PATH` 環境変数で上書きできます。
既存DBがある場合も、同じコマンドでAlembicの最新スキーマへ更新されます。`init-db` は後方互換用の別名で、現在は同じマイグレーションを実行します。

### 5. 楽曲の同期

`static/audio/` に置いた音源をDBへ明示的に同期します。アプリ起動時にはDB作成・マイグレーション・楽曲同期を実行しません。

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

## 参加者の実験フロー（詳細）

1. トップ画面から実験説明へ進む
2. 実験説明を確認し、参加者情報入力へ進む
3. 参加者IDは自動発行されるため、年齢、性別、楽器演奏などの音楽経験、実験に使う端末・OS、ブラウザ、音楽を聴くときに使う機器を入力
4. 練習試行がある場合は先に提示
5. 練習試行が終わったら、設定した音量の感じ方とおおよその音量レベルを回答
6. 音声を再生し、良いと感じた瞬間にボタンを押す
7. 曲が終わったら、曲全体について9項目すべてに回答。抽選された本試行2曲では「5」を選ぶ品質確認項目にも回答
8. 毎曲、回答後に理由回答画面へ進む。ボタンを押した場合は記録された部分を確認し理由を回答、押さなかった場合は押さなかった理由を選択し任意の補足を記入
9. 次の楽曲へ進行
10. すべて終わると完了画面を表示

## 動作確認手順

1. `source ~/.venv/pylec/bin/activate`
2. `export SECRET_KEY=local-dev-secret`
3. `export ADMIN_PASSWORD=local-admin-password`
4. `python -m flask --app app db upgrade`
5. `python -m flask --app app sync-songs`
6. `python -m flask --app app run`
7. ブラウザで `/` を開く
8. 説明を確認し、参加者情報を入力して開始
9. 音源を再生し、ボタンを数回押す
10. 曲全体について回答し、記録された部分の理由、またはボタンを押さなかった理由を回答
11. 完了後に `/admin` へアクセスし、管理者IDとパスワードでログインして保存データを確認
12. CSV エクスポートを試す

## 独自音源を使う場合

1. 練習曲、共通曲、各セットの曲を上記フォルダに配置します。
2. 参加者に使用するセット番号（1・2・3）を指定します。
3. `python -m flask --app app sync-songs` を実行します。
4. 参加者は実験者から指定されたセット番号をプルダウンで選択して開始します。

音源ファイルと動画ファイルは容量・権利管理の都合で Git 管理外にしています。GitHub に保存されるのは置き場所の説明だけです。

自動登録のルール:

- `static/audio/` 配下を再帰的に走査します
- `static/audio/practice/` 配下のファイル、または `practice_` / `practice-` で始まるファイル名は練習試行として扱います
- `common/` の直下は共通曲、`random_sets/<番号>/train/` はランダム学習曲、`random_sets/<番号>/test/` はランダムテスト曲として扱います
- `random_sets/<番号>/` の直下に置いた曲は本試行に使いません
- それ以外の一般フォルダの曲は本試行に使いません
- `song_id` はファイルの相対パスから自動生成されます
- 共通曲と指定セットの学習曲・テスト曲を参加者作成時に選び、提示順と曲の組み合わせをDBに保存します。本番の想定は共通15曲＋学習10曲＋テスト5曲＝30曲ですが、現在はデバッグのため曲数・内訳チェックを一時的に外しています。曲が1曲以上あれば開始でき、配置済みの曲だけを提示します
- 分析用CSVの `song_type` は `common`・`random_train`・`random_test`（練習試行は `practice`）で区別できます
- 以後の再アクセスでは保存済みの曲と順序を使います

例:

- `static/audio/practice/practice_a.wav` -> 練習試行
- `static/audio/common/theme_01.mp3` -> 共通曲
- `static/audio/random_sets/2/train/theme_02.wav` -> セット2のランダム学習曲
- `static/audio/random_sets/2/test/theme_03.wav` -> セット2のランダムテスト曲

## 実装上の補足

- 押下なしの曲も、練習・本試行ともに評定後の理由回答を保存してから次へ進みます。聴き直しは押下・再生完了ログを変更しません。
- `db upgrade` で `0007_no_press_reasons` の追加列を適用してください。既存試行の理由は補完しません。分析用CSVと管理画面のDatasetに理由・補足・保存時刻を出力し、CSVの理由コードはセミコロン区切りです。押下なしでは押下数0と選択区間未設定を維持します。

- ボタン押下保存は `BUTTON_PRESS_MODE` 設定で将来的に切り替えやすくしています。
  - `all`: すべて保存
  - `first_only`: 最初の 1 回だけ保存
  - `last_only`: 最後の 1 回だけ有効にする想定
- 全ボタン操作は `press_events` に保存されます。最終的に選んだ 1 件は `button_presses` にも保存されます。
- `participant_song_orders.all_press_audio_times` には、`押下1:1.000000; 押下2:5.250000` のように、その曲で押した全時刻をまとめて保存します。
- 区間は `segment_rule = pre_4sec` として保存します。押下位置が4秒以上の場合は `[押下時刻 - 4秒, 押下時刻]`、4秒未満の場合は冒頭の `[0秒, 4秒]` です。開始4秒未満では押下後の音も区間に含まれます。
- `audio_time_sec` はブラウザの `audio.currentTime` を基準に保存し、`server_received_at` は参考ログとして保存します。
- `created_at` は日本時間（Asia/Tokyo）で保存します。
- 管理画面では、生データ一覧に加えて、参加者別の評価カード表示と、楽曲別の平均値バー表示・個別回答表示を確認できます。
- 管理画面は `Overview / Participants / Songs / Dataset` のタブに分かれており、`Songs` タブでは平均評点ヒートマップ、`Dataset` タブでは分析用の横持ちデータを確認できます。
- DBスキーマ変更はFlask-Migrate/Alembicで管理し、本番反映時に `python -m flask --app app db upgrade` を実行します。
- 質問項目を増やしたい場合は `constants.py` の `SD_ITEMS` を追加してください。

## 起動できないとき

`SECRET_KEY` を明示的に指定したい場合は、`flask` コマンドの前に `SECRET_KEY` を設定してください。

macOS / zsh:

```zsh
source ~/.venv/pylec/bin/activate
export SECRET_KEY=local-dev-secret
python -m flask --app app run
```

DBが古い、またはテーブルが未作成の場合は、以下を実行してください。

```zsh
python -m flask --app app db upgrade
python -m flask --app app sync-songs
```

## PythonAnywhere本番構成

DeveloperプランのWebアプリ3ワーカーとMySQLを使用します。

1. `.env.example` を `.env` にコピーし、すべての `replace-with-...` と `USERNAME` を実値へ変更します。
2. 管理者パスワードハッシュは次のように生成します。

```zsh
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('十分に長い管理者パスワード', method='pbkdf2:sha256:600000'))"
```

3. PythonAnywhereのWSGI設定へ `pythonanywhere_wsgi.py.example` の内容をコピーし、`USERNAME` を変更します。
4. Web設定で `/static/` を `/home/USERNAME/main_experiment/static/` に割り当て、Force HTTPSを有効にします。
5. 初回と更新時に以下を実行します。

```zsh
workon YOUR_VIRTUALENV
cd /home/USERNAME/main_experiment
pip install -r requirements.txt
python -m flask --app app db upgrade
python -m flask --app app sync-songs
```

MySQLのパスワードに記号が含まれる場合は、`DATABASE_URL` 内でURLエンコードしてください。音源は静的URLで配信されるため、URLを知る参加者による直接アクセスを技術的には禁止できません。

## テスト

```zsh
PYTHONPATH=. pytest -q
```

## 保存期限

`.env` の `RESEARCH_END_DATE` を `YYYY-MM-DD` で設定します。期限確認は削除せずに実行されます。

```zsh
python -m flask --app app purge-expired-data
```

件数を確認後、削除するときだけ `--confirm` を付けます。支払い照合済みの認証情報は90日後、研究回答は研究終了日の1年後に削除対象となります。
