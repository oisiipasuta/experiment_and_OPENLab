"""本番音源から推薦用の4秒窓特徴量CSVを事前生成する。"""

import argparse
import csv
import math
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from services.audio_catalog import AudioCatalogService


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audio-root",
        type=Path,
        default=APP_DIR / "static" / "audio",
        help="音源ルート（practice/ は除外されます）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=APP_DIR / "data" / "acoustic_features.csv",
    )
    parser.add_argument("--window-size", type=float, default=4.0)
    parser.add_argument("--hop-size", type=float, default=1.0)
    parser.add_argument("--sample-rate", type=int, default=22050)
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        import librosa
        import numpy as np
        from scipy.signal import find_peaks
    except ImportError as error:
        raise SystemExit(
            "特徴量用依存関係がありません。"
            "pip install -r requirements-features.txt を実行してください。"
        ) from error

    catalog = AudioCatalogService()
    supported = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
    audio_paths = [
        path
        for path in sorted(args.audio_root.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in supported
        and not catalog.infer_is_practice(path.relative_to(args.audio_root))
    ]
    if len(audio_paths) != 15:
        raise SystemExit(f"本番音源は15曲必要です（検出: {len(audio_paths)}曲）。")

    fieldnames = [
        "song_id",
        "title",
        "artist",
        "window_start",
        "window_end",
        "rms_mean",
        "peak_count",
        "peak_rate",
        "spectral_bandwidth",
        *[f"mfcc_{index}" for index in range(1, 14)],
        *[f"chroma_{index}" for index in range(1, 13)],
    ]
    rows = []
    for audio_path in audio_paths:
        relative_path = audio_path.relative_to(args.audio_root)
        song_id = catalog.build_song_id(relative_path)
        audio, sample_rate = librosa.load(
            audio_path,
            sr=args.sample_rate,
            mono=True,
        )
        duration = len(audio) / sample_rate
        if duration <= 0:
            continue
        last_start = max(0.0, duration - args.window_size)
        window_count = math.floor(last_start / args.hop_size) + 1
        starts = [index * args.hop_size for index in range(window_count)]
        if not starts or abs(starts[-1] - last_start) > 1e-6:
            starts.append(last_start)

        for start in starts:
            end = min(start + args.window_size, duration)
            start_sample = round(start * sample_rate)
            end_sample = round(end * sample_rate)
            segment = audio[start_sample:end_sample]
            if segment.size == 0:
                continue

            rms = librosa.feature.rms(y=segment)[0]
            onset_envelope = librosa.onset.onset_strength(
                y=segment,
                sr=sample_rate,
            )
            prominence = max(float(np.std(onset_envelope)) * 0.5, 1e-9)
            peaks, _ = find_peaks(onset_envelope, prominence=prominence)
            bandwidth = librosa.feature.spectral_bandwidth(
                y=segment,
                sr=sample_rate,
            )[0]
            mfcc = librosa.feature.mfcc(y=segment, sr=sample_rate, n_mfcc=13)
            chroma = librosa.feature.chroma_stft(y=segment, sr=sample_rate)

            row = {
                "song_id": song_id,
                "title": relative_path.stem,
                "artist": "",
                "window_start": round(start, 6),
                "window_end": round(end, 6),
                "rms_mean": float(np.mean(rms)),
                "peak_count": int(len(peaks)),
                "peak_rate": float(len(peaks) / max(end - start, 1e-9)),
                "spectral_bandwidth": float(np.mean(bandwidth)),
            }
            row.update(
                {f"mfcc_{index + 1}": float(np.mean(mfcc[index])) for index in range(13)}
            )
            row.update(
                {
                    f"chroma_{index + 1}": float(np.mean(chroma[index]))
                    for index in range(12)
                }
            )
            rows.append(row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Generated {len(rows)} windows from {len(audio_paths)} songs: {args.output}")


if __name__ == "__main__":
    main()
