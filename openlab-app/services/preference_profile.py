import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path

from flask import current_app

from models import ButtonPress, ImpressionRating


class PreferenceProfileService:
    """保存済みの選択区間と事前計算特徴量から、終了後表示だけを生成する。"""

    FEATURE_COLUMNS = {
        "energy": ("rms",),
        "rhythm": (
            "low_peaks",
            "middle_peaks",
            "high_peaks",
            "super_high_peaks",
        ),
        "brightness": ("spectral_centroids", "spectral_rolloff"),
        "spread": ("spectral_bandwidth",),
    }
    CHROMA_COLUMNS = tuple(f"chroma_{index}" for index in range(1, 13))
    TRAIT_DEFINITIONS = (
        ("energy", "エネルギー", "音の強さ", "おだやかな音", "ほどよい強さの音", "力強い音", "おだやか", "力強い"),
        ("rhythm", "リズム", "リズムの動き", "ゆったりしたリズム", "ほどよく動くリズム", "動きのあるリズム", "ゆったり", "動きが多い"),
        ("brightness", "音色", "音の明るさ", "落ち着いた音", "バランスのよい明るさ", "明るくきらびやかな音", "落ち着いた", "明るい"),
        ("spread", "音色", "音の広がり", "まとまりのある音", "ほどよく広がる音", "広がりのある音", "まとまり", "広がり"),
        ("harmony", "和声", "響きの彩り", "芯のある響き", "ほどよく彩りのある響き", "彩り豊かな響き", "芯のある", "彩り豊か"),
    )

    def __init__(self):
        self._cache_key = None
        self._cached_dataset = None

    def generate(self, participant):
        if not participant.experiment_completed:
            raise ValueError("本実験の保存完了前にはプロフィールを生成できません。")

        rating_count = ImpressionRating.query.filter_by(
            participant_id=participant.participant_id,
            is_practice=False,
        ).count()
        if rating_count != current_app.config["OPENLAB_MAIN_SONG_COUNT"]:
            raise ValueError("本実験5曲分の評価が揃っていません。")

        profile = self._build_acoustic_profile(participant)
        if profile["acoustic_available"]:
            strongest = max(
                profile["trait_cards"],
                key=lambda trait: abs(trait["score"] - 50),
            )
            title = f'あなたが惹かれやすいのは「{strongest["label"]}」'
            description = "選んだ4秒間の音を、15曲全体の音の特徴と比べた参考結果です。"
        else:
            title = "ご参加ありがとうございました"
            description = "回答データはすべて保存済みです。"

        return {
            "title": title,
            "description": description,
            **profile,
            "is_fallback": False,
        }

    @staticmethod
    def fallback():
        return {
            "title": "ご参加ありがとうございました",
            "description": "回答データはすべて保存済みです。結果表示のみ作成できませんでした。",
            "acoustic_available": False,
            "acoustic_message": "音楽プロフィールを表示できませんでした。",
            "selected_segment_count": 0,
            "trait_cards": [],
            "is_fallback": True,
        }

    def _build_acoustic_profile(self, participant):
        feature_path = Path(current_app.config["AUDIO_FEATURES_PATH"])
        if not feature_path.exists():
            return self._unavailable("音の特徴データがまだ準備されていないため、傾向を表示できません。")

        try:
            rows, populations = self._load_feature_dataset(feature_path)
        except (OSError, ValueError) as error:
            current_app.logger.warning("Acoustic feature data is unavailable: %s", error)
            return self._unavailable("音の特徴データを読み込めなかったため、傾向を表示できません。")

        selections = ButtonPress.query.filter_by(
            participant_id=participant.participant_id,
            is_practice=False,
        ).all()
        selections = [selection for selection in selections if selection.selected_segment_start_sec is not None]
        if not selections:
            return self._unavailable("今回は「ここ好き！」の最終選択がなかったため、音の特徴による傾向は表示していません。")

        selected_rows = self._nearest_rows_for_selections(rows, selections)
        if not selected_rows:
            return self._unavailable("選んだ場所に対応する音の特徴データが見つかりませんでした。")

        return {
            "acoustic_available": True,
            "acoustic_message": f"あなたが選んだ{len(selected_rows)}か所の音から、好みの傾向をまとめました。",
            "selected_segment_count": len(selected_rows),
            "trait_cards": self._build_trait_cards(selected_rows, populations),
        }

    @staticmethod
    def _unavailable(message):
        return {"acoustic_available": False, "acoustic_message": message, "selected_segment_count": 0, "trait_cards": []}

    def _load_feature_dataset(self, path):
        stat = path.stat()
        cache_key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        if cache_key == self._cache_key and self._cached_dataset is not None:
            return self._cached_dataset

        rows = self._load_feature_rows(path)
        rows, populations = self._calculate_trait_values(rows)
        self._cache_key = cache_key
        self._cached_dataset = (rows, populations)
        return self._cached_dataset

    def _load_feature_rows(self, path):
        continuous_columns = {name for names in self.FEATURE_COLUMNS.values() for name in names}
        required = {"song_id", "window_start", "window_end", *continuous_columns, *self.CHROMA_COLUMNS}
        rows = []
        seen_windows = set()

        with path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            missing_headers = sorted(required - set(reader.fieldnames or []))
            if missing_headers:
                raise ValueError("特徴量CSVの必須列がありません: " + ", ".join(missing_headers))

            numeric_columns = continuous_columns | set(self.CHROMA_COLUMNS)
            for line_number, source in enumerate(reader, start=2):
                song_id = (source.get("song_id") or "").strip()
                if not song_id:
                    raise ValueError(f"{line_number}行目の song_id が空です。")
                try:
                    start = float(source["window_start"])
                    end = float(source["window_end"])
                    values = {name: float(source[name]) for name in numeric_columns}
                except (TypeError, ValueError) as error:
                    raise ValueError(f"{line_number}行目に不正な数値があります。") from error
                if not all(math.isfinite(value) for value in (start, end, *values.values())):
                    raise ValueError(f"{line_number}行目に非有限値があります。")
                if start < 0 or not math.isclose(end - start, 4.0, abs_tol=1e-6):
                    raise ValueError(f"{line_number}行目が有効な4秒窓ではありません。")
                key = (song_id, start)
                if key in seen_windows:
                    raise ValueError(f"{line_number}行目の窓が重複しています。")
                seen_windows.add(key)
                rows.append({"song_id": song_id, "window_start": start, "window_end": end, **values})

        if not rows:
            raise ValueError("利用できる特徴量行がありません。")
        expected_song_count = current_app.config["OPENLAB_STIMULUS_POOL_SIZE"]
        actual_song_count = len({row["song_id"] for row in rows})
        if actual_song_count != expected_song_count:
            raise ValueError(
                f"特徴量CSVは本番{expected_song_count}曲分必要です"
                f"（検出: {actual_song_count}曲）。"
            )
        return rows

    def _calculate_trait_values(self, rows):
        continuous_columns = [name for names in self.FEATURE_COLUMNS.values() for name in names]
        stats = {
            name: (
                statistics.fmean(row[name] for row in rows),
                statistics.pstdev(row[name] for row in rows) or 1.0,
            )
            for name in continuous_columns
        }
        entropies = [self._chroma_entropy(row) for row in rows]
        entropy_mean = statistics.fmean(entropies)
        entropy_stdev = statistics.pstdev(entropies) or 1.0
        populations = {key: [] for key, *_ in self.TRAIT_DEFINITIONS}

        for row, entropy in zip(rows, entropies):
            z_values = {name: (row[name] - stats[name][0]) / stats[name][1] for name in continuous_columns}
            traits = {
                key: statistics.fmean(z_values[name] for name in names)
                for key, names in self.FEATURE_COLUMNS.items()
            }
            traits["harmony"] = (entropy - entropy_mean) / entropy_stdev
            row["traits"] = traits
            for key, value in traits.items():
                populations[key].append(value)
        return rows, populations

    @staticmethod
    def _nearest_rows_for_selections(rows, selections):
        rows_by_song = defaultdict(list)
        for row in rows:
            rows_by_song[row["song_id"]].append(row)
        matched = []
        for selection in selections:
            candidates = rows_by_song.get(selection.song_id, [])
            if candidates:
                selected_start = float(selection.selected_segment_start_sec)
                matched.append(min(candidates, key=lambda row: (abs(row["window_start"] - selected_start), row["window_start"])))
        return matched

    def _build_trait_cards(self, selected_rows, populations):
        cards = []
        for key, category, name, low, middle, high, low_label, high_label in self.TRAIT_DEFINITIONS:
            selected_value = statistics.fmean(row["traits"][key] for row in selected_rows)
            score = round(self._percentile_rank(populations[key], selected_value))
            label = low if score < 34 else high if score > 66 else middle
            cards.append({
                "key": key,
                "category": category,
                "name": name,
                "score": score,
                "label": label,
                "low_label": low_label,
                "high_label": high_label,
            })
        return cards

    @staticmethod
    def _percentile_rank(population, value):
        below = sum(item < value for item in population)
        equal = sum(item == value for item in population)
        return 100 * (below + 0.5 * equal) / len(population)

    def _chroma_entropy(self, row):
        values = [max(row[name], 0.0) for name in self.CHROMA_COLUMNS]
        total = sum(values)
        if total <= 0:
            return 0.0
        probabilities = [value / total for value in values if value > 0]
        return -sum(value * math.log(value) for value in probabilities) / math.log(len(self.CHROMA_COLUMNS))
