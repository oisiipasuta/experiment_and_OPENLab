"""大規模特徴量CSVから実験本番15曲の4秒窓だけを抽出する。"""

import argparse
import csv
import hashlib
import math
import os
import re
import tempfile
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
EXPECTED_MAIN_SONG_COUNT = 15
MFCC_COLUMNS = [f"mfcc_{index}" for index in range(20)]
PEAK_COLUMNS = ["low_peaks", "middle_peaks", "high_peaks", "super_high_peaks"]
SOURCE_CHROMA_COLUMNS = [
    "chroma_mean_C", "chroma_mean_C_sharp", "chroma_mean_D",
    "chroma_mean_D_sharp", "chroma_mean_E", "chroma_mean_F",
    "chroma_mean_F_sharp", "chroma_mean_G", "chroma_mean_G_sharp",
    "chroma_mean_A", "chroma_mean_A_sharp", "chroma_mean_B",
]
BASE_FEATURE_COLUMNS = ["rms", "spectral_centroids", "spectral_bandwidth", "spectral_rolloff", "zcr"]
SOURCE_REQUIRED_COLUMNS = {
    "filename", "window_start_sec", "window_end_sec",
    *BASE_FEATURE_COLUMNS, *MFCC_COLUMNS, *PEAK_COLUMNS, *SOURCE_CHROMA_COLUMNS,
}
OUTPUT_COLUMNS = [
    "song_id", "title", "window_start", "window_end",
    *BASE_FEATURE_COLUMNS, *MFCC_COLUMNS, *PEAK_COLUMNS,
    *[f"chroma_{index}" for index in range(1, 13)],
]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=APP_DIR / "data" / "acoustic_features_sliding_4sec_1sec.csv")
    parser.add_argument("--audio-root", type=Path, default=APP_DIR / "static" / "audio")
    parser.add_argument("--output", type=Path, default=APP_DIR / "data" / "acoustic_features.csv")
    return parser.parse_args()


def build_song_id(stem):
    compact = re.sub(r"\s+", "_", stem).strip("_") or "song"
    if len(compact) <= 100:
        return compact
    digest = hashlib.md5(stem.encode("utf-8")).hexdigest()[:12]
    return f"{compact[:87]}__{digest}"


def discover_main_audio(audio_root, expected_song_count=EXPECTED_MAIN_SONG_COUNT):
    if not audio_root.is_dir():
        raise ValueError(f"音源ディレクトリがありません: {audio_root}")
    audio_paths = sorted(path for path in audio_root.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS)
    if len(audio_paths) != expected_song_count:
        raise ValueError(f"本番音源は{expected_song_count}曲必要です（検出: {len(audio_paths)}曲）。")
    by_stem = {}
    for path in audio_paths:
        if path.stem in by_stem:
            raise ValueError(f"拡張子を除いた音源名が重複しています: {path.stem}")
        by_stem[path.stem] = build_song_id(path.stem)
    return by_stem


def prepare_features(input_path, audio_root, output_path, expected_song_count=EXPECTED_MAIN_SONG_COUNT):
    songs = discover_main_audio(audio_root, expected_song_count)
    if not input_path.is_file():
        raise ValueError(f"抽出元CSVがありません: {input_path}")
    rows, seen_windows, matched_songs = [], set(), set()
    with input_path.open(encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)
        missing_headers = sorted(SOURCE_REQUIRED_COLUMNS - set(reader.fieldnames or []))
        if missing_headers:
            raise ValueError("抽出元CSVの必須列がありません: " + ", ".join(missing_headers))
        numeric_columns = BASE_FEATURE_COLUMNS + MFCC_COLUMNS + PEAK_COLUMNS + SOURCE_CHROMA_COLUMNS
        for line_number, source in enumerate(reader, start=2):
            filename = (source.get("filename") or "").strip()
            if filename not in songs:
                continue
            try:
                start, end = float(source["window_start_sec"]), float(source["window_end_sec"])
                values = {name: float(source[name]) for name in numeric_columns}
            except (TypeError, ValueError) as error:
                raise ValueError(f"{line_number}行目に不正な数値があります。") from error
            if not all(math.isfinite(value) for value in (start, end, *values.values())):
                raise ValueError(f"{line_number}行目に非有限値があります。")
            if start < 0 or not math.isclose(end - start, 4.0, abs_tol=1e-6):
                raise ValueError(f"{line_number}行目が有効な4秒窓ではありません。")
            key = (filename, start)
            if key in seen_windows:
                raise ValueError(f"{line_number}行目の窓が重複しています。")
            seen_windows.add(key)
            matched_songs.add(filename)
            output_row = {
                "song_id": songs[filename], "title": filename,
                "window_start": start, "window_end": end,
                **{name: values[name] for name in BASE_FEATURE_COLUMNS},
                **{name: values[name] for name in MFCC_COLUMNS},
                **{name: values[name] for name in PEAK_COLUMNS},
            }
            output_row.update({f"chroma_{index}": values[source_name] for index, source_name in enumerate(SOURCE_CHROMA_COLUMNS, start=1)})
            rows.append(output_row)

    missing_songs = sorted(set(songs) - matched_songs)
    if missing_songs:
        raise ValueError("特徴量CSVに対応する音源がありません: " + ", ".join(missing_songs))
    rows.sort(key=lambda row: (row["song_id"], row["window_start"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=output_path.parent, prefix=f".{output_path.name}.", suffix=".tmp", delete=False) as output_file:
            temporary_path = Path(output_file.name)
            writer = csv.DictWriter(output_file, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return {"song_count": len(matched_songs), "row_count": len(rows)}


def main():
    args = parse_args()
    try:
        result = prepare_features(args.input, args.audio_root, args.output)
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(f'Prepared {result["row_count"]} windows from {result["song_count"]} songs: {args.output}')


if __name__ == "__main__":
    main()
