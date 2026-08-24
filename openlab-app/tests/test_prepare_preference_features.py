import csv
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_preference_features import (
    BASE_FEATURE_COLUMNS,
    MFCC_COLUMNS,
    PEAK_COLUMNS,
    SOURCE_CHROMA_COLUMNS,
    prepare_features,
)


class PreparePreferenceFeaturesTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.audio_root = self.root / "audio"
        self.audio_root.mkdir()
        (self.audio_root / "song_a.wav").touch()
        (self.audio_root / "song_b.wav").touch()
        practice = self.audio_root / "practice"
        practice.mkdir()
        (practice / "practice.wav").touch()
        self.input_path = self.root / "source.csv"
        self.output_path = self.root / "output.csv"
        self.fieldnames = [
            "filename", "window_start_sec", "window_end_sec",
            *BASE_FEATURE_COLUMNS, *MFCC_COLUMNS, *PEAK_COLUMNS,
            *SOURCE_CHROMA_COLUMNS,
        ]

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_row(self, filename, start=0.0, end=4.0):
        row = {
            "filename": filename,
            "window_start_sec": start,
            "window_end_sec": end,
        }
        row.update({name: 1.0 for name in BASE_FEATURE_COLUMNS})
        row.update({name: 2.0 for name in MFCC_COLUMNS})
        row.update({name: 3.0 for name in PEAK_COLUMNS})
        row.update({name: 0.5 for name in SOURCE_CHROMA_COLUMNS})
        return row

    def write_source(self, rows):
        with self.input_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=self.fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_extracts_only_top_level_audio_and_normalizes_columns(self):
        self.write_source([
            self.make_row("song_a"),
            self.make_row("song_b"),
            self.make_row("practice"),
            self.make_row("unrelated_song"),
        ])

        result = prepare_features(
            self.input_path, self.audio_root, self.output_path, expected_song_count=2
        )

        self.assertEqual({"song_count": 2, "row_count": 2}, result)
        with self.output_path.open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
        self.assertEqual(["song_a", "song_b"], [row["song_id"] for row in rows])
        self.assertEqual("0.5", rows[0]["chroma_1"])
        self.assertEqual("0.0", rows[0]["window_start"])

    def test_rejects_missing_song_without_overwriting_existing_output(self):
        self.write_source([self.make_row("song_a")])
        self.output_path.write_text("keep", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "song_b"):
            prepare_features(
                self.input_path, self.audio_root, self.output_path, expected_song_count=2
            )

        self.assertEqual("keep", self.output_path.read_text(encoding="utf-8"))

    def test_rejects_duplicate_and_invalid_windows(self):
        for rows, message in (
            ([self.make_row("song_a"), self.make_row("song_a"), self.make_row("song_b")], "重複"),
            ([self.make_row("song_a", end=3.9), self.make_row("song_b")], "4秒窓"),
        ):
            with self.subTest(message=message):
                self.write_source(rows)
                with self.assertRaisesRegex(ValueError, message):
                    prepare_features(
                        self.input_path,
                        self.audio_root,
                        self.output_path,
                        expected_song_count=2,
                    )

    def test_rejects_non_numeric_and_non_finite_values(self):
        for bad_value, message in (("", "不正な数値"), ("nan", "非有限値")):
            with self.subTest(value=bad_value):
                row = self.make_row("song_a")
                row["rms"] = bad_value
                self.write_source([row, self.make_row("song_b")])
                with self.assertRaisesRegex(ValueError, message):
                    prepare_features(
                        self.input_path,
                        self.audio_root,
                        self.output_path,
                        expected_song_count=2,
                    )


if __name__ == "__main__":
    unittest.main()
