import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path

from flask import current_app
from models import ButtonPress, ImpressionRating


class PreferenceProfileService:
    FEATURE_COLUMNS = {
        "energy": ("rms",),
        "rhythm": ("low_peaks", "middle_peaks", "high_peaks", "super_high_peaks"),
        "brightness": ("spectral_centroids", "spectral_rolloff"),
        "spread": ("spectral_bandwidth",),
    }
    CHROMA_COLUMNS = tuple(f"chroma_{i}" for i in range(1, 13))
    TRAIT_DEFINITIONS = (
        ("energy", "エネルギー", "音の強さ", "おだやかな音", "ほどよい強さの音", "力強い音", "おだやか", "力強い"),
        ("rhythm", "リズム", "リズムの動き", "ゆったりしたリズム", "ほどよく動くリズム", "動きのあるリズム", "ゆったり", "動きが多い"),
        ("brightness", "明るさ", "音の明るさ", "落ち着いた音", "バランスのよい明るさ", "明るくきらびやかな音", "落ち着いた", "明るい"),
        ("spread", "広がり", "音の広がり", "まとまりのある音", "ほどよく広がる音", "広がりのある音", "まとまり", "広がり"),
        ("harmony", "響き", "響きの彩り", "芯のある響き", "ほどよく彩りのある響き", "彩り豊かな響き", "芯のある", "彩り豊か"),
    )
    WITHIN_LABELS = {
        "energy": ("力が落ち着く瞬間", "平均的な強さの瞬間", "力強さが増す瞬間"),
        "rhythm": ("動きが少ない瞬間", "平均的なリズムの瞬間", "動きが増す瞬間"),
        "brightness": ("落ち着いた音色の瞬間", "平均的な明るさの瞬間", "明るさが増す瞬間"),
        "spread": ("まとまりのある瞬間", "平均的な広がりの瞬間", "広がりが増す瞬間"),
        "harmony": ("響きがシンプルな瞬間", "平均的な彩りの瞬間", "響きが彩り豊かな瞬間"),
    }

    def __init__(self):
        self._cache_key = None
        self._cached_dataset = None

    def generate(self, participant):
        if not participant.experiment_completed:
            raise ValueError("本実験の保存完了前にはプロフィールを生成できません。")
        if ImpressionRating.query.filter_by(participant_id=participant.participant_id, is_practice=False).count() != current_app.config["OPENLAB_MAIN_SONG_COUNT"]:
            raise ValueError("本実験5曲分の評価が揃っていません。")
        profiles = self._build_profiles(participant)
        between = profiles["between_profile"]
        title = self._build_profile_title(between["trait_cards"]) if between["available"] else "あなたの音楽好みプロフィール"
        return {
            "title": title,
            "description": "曲全体の好みと、曲の中で惹かれる瞬間をそれぞれ別に分析しています。",
            **profiles,
            "acoustic_available": profiles["within_profile"]["available"],
            "acoustic_message": profiles["within_profile"]["message"],
            "selected_segment_count": profiles["within_profile"]["selected_segment_count"],
            "trait_cards": profiles["within_profile"]["trait_cards"],
            "stability": profiles["within_profile"].get("stability", {"label": "参考度低", "detail": "安定度を計算できませんでした。"}),
            "selection_reasons": profiles["within_profile"].get("selection_reasons", []),
            "is_fallback": False,
        }

    @staticmethod
    def _build_profile_title(cards):
        cards = sorted(cards, key=lambda card: abs(card["score"] - 50), reverse=True)[:2]
        return f'あなたは「{"、".join(card["direction_label"] for card in cards)}」サウンドタイプ'

    @staticmethod
    def fallback():
        message = "音楽プロフィールを表示できませんでした。"
        return {
            "title": "ご参加ありがとうございました",
            "description": "回答データはすべて保存済みです。結果表示のみ作成できませんでした。",
            "between_profile": {"available": False, "message": message, "liked_song_count": 0, "trait_cards": []},
            "within_profile": {"available": False, "message": message, "selected_segment_count": 0, "trait_cards": []},
            "acoustic_available": False, "acoustic_message": message, "selected_segment_count": 0, "trait_cards": [], "is_fallback": True,
        }

    def _build_profiles(self, participant):
        path = Path(current_app.config["AUDIO_FEATURES_PATH"])
        if not path.exists():
            return self._profiles_unavailable("音の特徴データがまだ準備されていないため、傾向を表示できません。")
        try:
            rows, dataset = self._load_feature_dataset(path)
        except (OSError, ValueError) as error:
            current_app.logger.warning("Acoustic feature data is unavailable: %s", error)
            return self._profiles_unavailable("音の特徴データを読み込めなかったため、傾向を表示できません。")
        ratings = ImpressionRating.query.filter_by(participant_id=participant.participant_id, is_practice=False).all()
        if "representatives" not in dataset:
            selections = [p for p in ButtonPress.query.filter_by(participant_id=participant.participant_id, is_practice=False).all() if p.selected_segment_start_sec is not None]
            if not selections:
                return {"between_profile": {"available": False, "message": "", "liked_song_count": 0, "trait_cards": []}, "within_profile": self._within_unavailable("今回は「ここ好き！」の最終選択がなかったため、曲内プロフィールは表示していません。")}
            selected = self._nearest_rows_for_selections(rows, selections)
            return {"between_profile": {"available": False, "message": "", "liked_song_count": 0, "trait_cards": []}, "within_profile": {"available": bool(selected), "message": f"{len(selected)}か所の「ここ好き！」から分析しています。", "selected_segment_count": len(selected), "trait_cards": self._build_trait_cards(selected, dataset) if selected else [], "stability": self._build_stability(selected, dataset), "selection_reasons": self._selection_reasons(selections)}}
        between = self._build_between_profile(ratings, dataset)
        selections = [p for p in ButtonPress.query.filter_by(participant_id=participant.participant_id, is_practice=False).all() if p.selected_segment_start_sec is not None]
        if not selections:
            within = self._within_unavailable("今回は「ここ好き！」の最終選択がなかったため、曲内プロフィールは表示していません。")
        else:
            selected = self._nearest_rows_for_selections(rows, selections)
            within = self._within_unavailable("選んだ場所に対応する音の特徴データが見つかりませんでした。") if not selected else {
                "available": True,
                "message": f"{len(selected)}か所の「ここ好き！」を、それぞれの曲の中で比較しました。",
                "selected_segment_count": len(selected),
                "trait_cards": self._build_within_trait_cards(selected, dataset["within"]),
                "stability": self._build_stability(selected, dataset["within"]),
                "selection_reasons": self._selection_reasons(selections),
            }
        return {"between_profile": between, "within_profile": within}

    @staticmethod
    def _within_unavailable(message):
        return {"available": False, "message": message, "selected_segment_count": 0, "trait_cards": [], "stability": {"label": "参考度低", "detail": "選択区間がないため判定できません。"}, "selection_reasons": []}

    @staticmethod
    def _selection_reasons(selections):
        return sorted({reason.strip() for selection in selections for reason in (selection.selection_reason or "").replace("選択理由: ", "").split(" / ") if reason.strip()})

    def _build_stability(self, rows, populations):
        if len(rows) < 2:
            return {"label": "参考度低", "detail": "選択区間が1か所のため、参考値として表示しています。"}
        if rows and "within_traits" in rows[0]:
            changes = []
            for key, *_ in self.TRAIT_DEFINITIONS:
                scores = [self._percentile_rank(populations[row["song_id"]][key], row["within_traits"][key]) for row in rows]
                changes.append(max(scores) - min(scores))
        else:
            changes = []
            for key, *_ in self.TRAIT_DEFINITIONS:
                scores = [self._percentile_rank(populations[key], row["traits"][key]) for row in rows]
                changes.append(max(scores) - min(scores))
        largest = max(changes, default=100)
        return {"label": "安定" if largest <= 10 else "やや変動" if largest <= 25 else "参考度低", "detail": f"選択区間ごとの最大差: {round(largest)}ポイント"}

    def _profiles_unavailable(self, message):
        return {"between_profile": {"available": False, "message": message, "liked_song_count": 0, "trait_cards": []}, "within_profile": self._within_unavailable(message)}

    def _load_feature_dataset(self, path):
        stat = path.stat()
        key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        if key == self._cache_key and self._cached_dataset is not None:
            return self._cached_dataset
        rows = self._load_feature_rows(path)
        rows, dataset = self._calculate_trait_values(rows)
        self._cache_key, self._cached_dataset = key, (rows, dataset)
        return self._cached_dataset

    def _load_feature_rows(self, path):
        continuous = {name for names in self.FEATURE_COLUMNS.values() for name in names}
        required = {"song_id", "window_start", "window_end", *continuous, *self.CHROMA_COLUMNS}
        rows, seen = [], set()
        with path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            missing = sorted(required - set(reader.fieldnames or []))
            if missing:
                raise ValueError("特徴量CSVの必須列がありません: " + ", ".join(missing))
            for line, source in enumerate(reader, start=2):
                try:
                    start, end = float(source["window_start"]), float(source["window_end"])
                    values = {name: float(source[name]) for name in continuous | set(self.CHROMA_COLUMNS)}
                except (TypeError, ValueError) as error:
                    raise ValueError(f"{line}行目に不正な数値があります。") from error
                song = (source.get("song_id") or "").strip()
                if not song or not all(math.isfinite(v) for v in (start, end, *values.values())) or start < 0 or not math.isclose(end - start, 4.0, abs_tol=1e-6):
                    raise ValueError(f"{line}行目に不正な特徴量があります。")
                if (song, start) in seen:
                    raise ValueError(f"{line}行目の窓が重複しています。")
                seen.add((song, start))
                rows.append({"song_id": song, "window_start": start, "window_end": end, **values})
        if not rows:
            raise ValueError("利用できる特徴量行がありません。")
        expected = current_app.config["OPENLAB_STIMULUS_POOL_SIZE"]
        if len({row["song_id"] for row in rows}) != expected:
            raise ValueError(f"特徴量CSVは本番{expected}曲分必要です")
        return rows

    def _calculate_trait_values(self, rows):
        continuous = [name for names in self.FEATURE_COLUMNS.values() for name in names]
        by_song = defaultdict(list)
        for row in rows:
            by_song[row["song_id"]].append(row)
        entropy = {id(row): self._chroma_entropy(row) for row in rows}
        within_stats = {}
        for song, items in by_song.items():
            within_stats[song] = {name: (statistics.fmean(r[name] for r in items), statistics.pstdev(r[name] for r in items) or 1.0) for name in continuous}
            values = [entropy[id(r)] for r in items]
            within_stats[song]["harmony"] = (statistics.fmean(values), statistics.pstdev(values) or 1.0)
        within = {song: {key: [] for key, *_ in self.TRAIT_DEFINITIONS} for song in by_song}
        for row in rows:
            stats = within_stats[row["song_id"]]
            z = {name: (row[name] - stats[name][0]) / stats[name][1] for name in continuous}
            z["harmony"] = (entropy[id(row)] - stats["harmony"][0]) / stats["harmony"][1]
            row["within_traits"] = {key: statistics.fmean(z[name] for name in names) for key, names in self.FEATURE_COLUMNS.items()}
            row["within_traits"]["harmony"] = z["harmony"]
            for key, value in row["within_traits"].items():
                within[row["song_id"]][key].append(value)
        representatives = []
        for song, items in by_song.items():
            representative = {"song_id": song, **{name: statistics.fmean(r[name] for r in items) for name in continuous}, "harmony": statistics.fmean(entropy[id(r)] for r in items)}
            representatives.append(representative)
        between_stats = {name: (statistics.fmean(r[name] for r in representatives), statistics.pstdev(r[name] for r in representatives) or 1.0) for name in continuous + ["harmony"]}
        between_population = {key: [] for key, *_ in self.TRAIT_DEFINITIONS}
        for representative in representatives:
            z = {name: (representative[name] - between_stats[name][0]) / between_stats[name][1] for name in continuous + ["harmony"]}
            representative["traits"] = {key: statistics.fmean(z[name] for name in names) for key, names in self.FEATURE_COLUMNS.items()}
            representative["traits"]["harmony"] = z["harmony"]
            for key, value in representative["traits"].items():
                between_population[key].append(value)
        return rows, {"representatives": representatives, "between": between_population, "within": within}

    def _build_between_profile(self, ratings, dataset):
        reps = {r["song_id"]: r for r in dataset["representatives"]}
        weighted = {key: [] for key, *_ in self.TRAIT_DEFINITIONS}
        total, liked = 0, 0
        for rating in ratings:
            weight = max(0, 4 - rating.like_dislike)
            rep = reps.get(rating.song_id)
            if weight <= 0 or rep is None:
                continue
            liked += 1
            total += weight
            for key in weighted:
                weighted[key].append((self._percentile_rank(dataset["between"][key], rep["traits"][key]), weight))
        if total == 0:
            return {"available": False, "message": "今回は「好き」と評価した曲がなかったため、曲全体の好みプロフィールは表示していません。", "liked_song_count": 0, "trait_cards": []}
        return {"available": True, "message": f"{liked}曲の「好き」評価から分析しました。", "liked_song_count": liked, "trait_cards": self._weighted_trait_cards(weighted, total)}

    def _weighted_trait_cards(self, values, total):
        cards = []
        for key, category, name, low, middle, high, low_label, high_label in self.TRAIT_DEFINITIONS:
            score = round(sum(value * weight for value, weight in values[key]) / total)
            cards.append({"key": key, "category": category, "name": name, "score": score, "label": low if score < 34 else high if score > 66 else middle, "direction_label": low_label if score < 34 else high_label if score > 66 else "バランスのよい", "low_label": low_label, "high_label": high_label})
        return cards

    def _build_within_trait_cards(self, rows, populations):
        cards = []
        for key, category, name, _low, _middle, _high, low_label, high_label in self.TRAIT_DEFINITIONS:
            percentiles = [self._percentile_rank(populations[row["song_id"]][key], row["within_traits"][key]) for row in rows]
            score = round(statistics.fmean(percentiles))
            labels = self.WITHIN_LABELS[key]
            cards.append({"key": key, "category": category, "name": name, "score": score, "label": labels[0] if score < 34 else labels[2] if score > 66 else labels[1], "direction_label": low_label if score < 34 else high_label if score > 66 else "平均的な", "low_label": low_label, "high_label": high_label})
        return cards

    def _build_trait_cards(self, rows, populations):
        """旧呼び出し元向け。新実装では楽曲内カードを明示的に生成する。"""
        if isinstance(populations, dict) and "within" in populations:
            return self._build_within_trait_cards(rows, populations["within"])
        cards = []
        for key, category, name, low, middle, high, low_label, high_label in self.TRAIT_DEFINITIONS:
            score = round(statistics.fmean(
                self._percentile_rank(populations[key], row["traits"][key]) for row in rows
            ))
            cards.append({
                "key": key, "category": category, "name": name, "score": score,
                "label": low if score < 34 else high if score > 66 else middle,
                "direction_label": high_label if score > 50 else low_label if score < 50 else "バランスのよい",
                "low_label": low_label, "high_label": high_label,
            })
        return cards

    @staticmethod
    def _nearest_rows_for_selections(rows, selections):
        by_song = defaultdict(list)
        for row in rows:
            by_song[row["song_id"]].append(row)
        matched = []
        for selection in selections:
            candidates = by_song.get(selection.song_id, [])
            if candidates:
                start = float(selection.selected_segment_start_sec)
                matched.append(min(candidates, key=lambda row: (abs(row["window_start"] - start), row["window_start"])))
        return matched

    @staticmethod
    def _percentile_rank(population, value):
        return 100 * (sum(x < value for x in population) + 0.5 * sum(x == value for x in population)) / len(population)

    def _chroma_entropy(self, row):
        values = [max(row[name], 0.0) for name in self.CHROMA_COLUMNS]
        total = sum(values)
        if total <= 0:
            return 0.0
        probabilities = [value / total for value in values if value > 0]
        return -sum(value * math.log(value) for value in probabilities) / math.log(len(self.CHROMA_COLUMNS))
