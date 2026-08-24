# OpenLab 音楽聴取実験アプリ

高校生向け OpenLab 実験専用の Flask + SQLite アプリです。元の
`experiment-app` とはコード・DB・静的ファイルを分離しており、このディレクトリだけで動作します。

## 実験フロー

1. 参加者情報と同意
2. 練習曲1曲（再生 → 必要なら複数回「ここ好き！」→ 9軸SD評価 → 最終1箇所）
3. 音量確認
4. 本実験5曲（15曲を5曲ずつ分けた3セットから1セットを割当）
5. 5曲すべての研究データを保存し `experiment_completed = true` に確定
6. 保存とは独立して音楽好みプロフィールを生成・表示

0回押下も有効です。その場合は印象評価後の区間選択画面を飛ばし、`press_count = 0`、
`all_press_audio_times = []`、選択区間は `NULL` のまま保存します。

## 楽曲配置

- 練習曲: `static/audio/practice/`（有効なものから1曲を割当）
- 15曲の本番刺激: `static/audio/` のうち練習曲以外

本番15曲はDBの表示順（通常は音源ファイル名順）で、次の固定3セットに分割します。

- `set_1`: 1〜5曲目
- `set_2`: 6〜10曲目
- `set_3`: 11〜15曲目

共通曲はありません。参加者には、現時点で割当済み参加者数が最も少ないセットを
優先して割り当てます。同数の場合のみセットをランダムに選び、セット内5曲の
`presentation_order`（1〜5）も参加者ごとにランダム化します。

## 起動

```zsh
cd openlab-app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m flask --app app init-db
python -m flask --app app sync-songs
python -m flask --app app run
```

開発用音源を作る場合だけ `python -m flask --app app seed-data` を使います。
実運用では約32秒の本番15曲と練習曲を配置してください。

DBは既定で `openlab-app/instance/experiment.db` に作られます。元実験のDBは参照しません。
保存先は `EXPERIMENT_DB_PATH` で変更できます。

本番HTTPS環境では `SESSION_COOKIE_SECURE=1` を設定してください。実験の割当コホートを分ける場合は
`EXPERIMENT_COHORT_ID` にコホート名を設定します。3人ブロックごとに `set_1`〜`set_3` を1人ずつ、
ブロック内でランダムな順に割り当てます。

## OpenLab 固有データ

- `participants.participant_group`: 既定値 `highschool_openlab`
- `participants.experiment_completed`: 本番5曲完了時のみ `true`
- `participants.completed_at`
- `participant_song_orders.presentation_order`
- `participant_song_orders.stimulus_set`: `set_1`〜`set_3`
- `participant_song_orders.press_count`
- `participant_song_orders.all_press_audio_times`: JSON配列
- `press_events`: 全押下時刻と、押下位置から始まる最大4秒区間
- `participant_song_orders`: 再生開始・完了時刻、再生経過時間、データ品質フラグ
- `button_presses`: 最終選択した1区間と複数選択理由
- `impression_ratings`: 従来と同じ9軸・7段階

既存カラムを維持し、OpenLab固有カラムは軽量マイグレーションで追加します。
管理画面の `analysis_dataset.csv` にはグループ、完了状態、提示順、全押下、選択区間、
9軸評価が横持ちで出力されます。

## プロフィールと事前計算特徴量

プロフィールは `/complete` で、最終評価トランザクションの commit 後にだけ生成します。
選択した4秒窓を本番15曲の全窓と比べ、音の強さ・リズムの動き・明るさ・広がり・響きの彩りの5軸を表示します。
失敗しても研究データは変更・破棄されず、フォールバック表示になります。

実データ `data/acoustic_features_sliding_4sec_1sec.csv` は約382MBのため、
実験開始前に本番15曲分だけを抽出します。ファイル名に `1sec` とありますが、
実データの窓開始は0.1秒刻みです。

```zsh
python scripts/prepare_preference_features.py
```

出力される `data/acoustic_features.csv` は約3.4MBで、アプリはこのファイルだけを読み込みます。
音源を入れ替えた場合はスクリプトを再実行してください。詳細は `data/README.md` にあります。

## テスト

```zsh
python -m unittest discover -s tests -v
```
