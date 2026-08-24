# プロフィール用の事前計算音響特徴量

`acoustic_features.csv` をこのフォルダに準備します。実験中には特徴量を計算せず、
本実験5曲の保存完了後だけ、選択秒数に最も近い0.1秒刻みの4秒窓を参照します。

## 実データの抽出

382MBの `acoustic_features_sliding_4sec_1sec.csv` から、`static/audio`
直下の本番15曲だけを抽出します。`practice/` は対象外です。

```zsh
python scripts/prepare_preference_features.py
```

スクリプトは音源名の完全一致、15曲の存在、4秒窓、重複、欠損、非有限値を検査し、
問題がある場合は出力を更新しません。`--input`、`--audio-root`、`--output`
で各パスを変更できます。

## CSV列

```text
song_id,title,window_start,window_end,
rms,spectral_centroids,spectral_bandwidth,spectral_rolloff,zcr,
low_peaks,middle_peaks,high_peaks,super_high_peaks,
mfcc_0,...,mfcc_19,
chroma_1,...,chroma_12
```

- 音の強さ: `rms`
- リズムの動き: 4周波数帯の時間方向ピーク
- 音の明るさ: `spectral_centroids`, `spectral_rolloff`
- 音の広がり: `spectral_bandwidth`
- 響きの彩り: `chroma_1`〜`chroma_12`の正規化エントロピー

別の場所に置く場合は `AUDIO_FEATURES_PATH` にCSVの絶対パスを設定します。
旧環境変数名 `FEATURE_DATA_PATH` も利用できます。

## プロフィール計算

1. 各曲の最終選択秒に最も近い4秒窓を取得
2. 本番15曲の全窓を使い、各特徴列をZ標準化
3. 複数列からなる軸は同じ重みで平均
4. 選択した窓の平均を、全窓中のパーセンタイル0〜100に変換
5. 34未満・34〜66・66超の3段階で特徴ラベルを表示

最終選択が0件の場合は、無理に音響的な好みを推定しません。
