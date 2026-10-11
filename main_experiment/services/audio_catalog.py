import hashlib
import math
import re
import struct
import wave
from pathlib import Path

from flask import current_app

from constants import (
    RANDOM_SONG_COUNTS,
    SAMPLE_SONGS,
    STIMULUS_SET_IDS,
    SUPPORTED_AUDIO_EXTENSIONS,
)
from models import Song, db


class AudioCatalogService:
    """音源の発見、登録、サンプル生成を担当する。"""

    def get_audio_root(self):
        return Path(current_app.root_path) / "static" / "audio"

    def discover_audio_files(self):
        audio_root = self.get_audio_root()
        audio_root.mkdir(parents=True, exist_ok=True)
        discovered_files = []

        for audio_path in sorted(audio_root.rglob("*")):
            if not audio_path.is_file():
                continue
            if audio_path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
                continue

            relative_audio_path = audio_path.relative_to(audio_root)
            is_practice = self.infer_is_practice(relative_audio_path)
            is_common, stimulus_set_id = self.classify_stimulus(relative_audio_path)
            relative_static_path = Path("audio") / relative_audio_path
            discovered_files.append(
                {
                    "song_id": self.build_song_id(relative_audio_path),
                    "file_path": relative_static_path.as_posix(),
                    "is_practice": is_practice,
                    "is_common": is_common,
                    "stimulus_set_id": stimulus_set_id,
                    "file_size_bytes": audio_path.stat().st_size,
                    "content_sha256": self._sha256_file(audio_path),
                    "duration_seconds": self._wave_duration(audio_path),
                }
            )

        return discovered_files

    @staticmethod
    def classify_stimulus(relative_audio_path):
        parts = relative_audio_path.parts
        if len(parts) == 2 and parts[0].lower() == "common":
            return True, None
        if (
            len(parts) == 4
            and parts[0] == "random_sets"
            and parts[2] in RANDOM_SONG_COUNTS
        ):
            set_id = parts[1]
            if set_id.isdecimal() and int(set_id) > 0:
                return False, int(set_id)
        return False, None

    def build_song_id(self, relative_audio_path):
        relative_without_suffix = relative_audio_path.with_suffix("").as_posix()
        compact = re.sub(r"[/\\]+", "__", relative_without_suffix)
        compact = re.sub(r"\s+", "_", compact).strip("_")
        compact = compact or "song"
        if len(compact) <= 100:
            return compact

        digest = hashlib.md5(relative_without_suffix.encode("utf-8")).hexdigest()[:12]
        return f"{compact[:87]}__{digest}"

    def infer_is_practice(self, relative_audio_path):
        path_parts = [part.lower() for part in relative_audio_path.parts[:-1]]
        stem = relative_audio_path.stem.lower()
        return (
            "practice" in path_parts
            or "練習" in relative_audio_path.parts[:-1]
            or stem.startswith(("practice_", "practice-", "練習_", "練習-"))
        )

    def sync_songs_from_static(self):
        discovered_files = self.discover_audio_files()
        Song.query.update(
            {
                Song.is_active: False,
                Song.is_common: False,
                Song.stimulus_set_id: None,
            },
            synchronize_session=False,
        )

        practice_order = 0
        main_order = 0

        for item in discovered_files:
            categorized = (
                item["is_practice"]
                or item["is_common"]
                or item["stimulus_set_id"] is not None
            )
            if item["is_practice"]:
                practice_order += 1
                display_order = practice_order
            elif categorized:
                main_order += 1
                display_order = main_order
            else:
                # Root-level main songs are intentionally not eligible for trials.
                display_order = 0

            song = Song.query.filter_by(song_id=item["song_id"]).first()
            if song is None:
                song = Song(song_id=item["song_id"])
                db.session.add(song)

            song.file_path = item["file_path"]
            song.is_practice = item["is_practice"]
            song.display_order = display_order
            song.is_active = categorized
            song.is_common = item["is_common"]
            song.stimulus_set_id = item["stimulus_set_id"]
            song.file_size_bytes = item["file_size_bytes"]
            song.content_sha256 = item["content_sha256"]
            song.duration_seconds = item["duration_seconds"]

        db.session.commit()

        return self.get_catalog_summary()

    def get_catalog_summary(self):
        songs = Song.query.filter_by(is_active=True).all()
        set_counts = {
            str(set_id): dict.fromkeys(RANDOM_SONG_COUNTS, 0) for set_id in STIMULUS_SET_IDS
        }
        role_counts = dict.fromkeys(RANDOM_SONG_COUNTS, 0)
        for song in songs:
            if song.is_practice or song.stimulus_set_id is None:
                continue
            set_id = str(song.stimulus_set_id)
            counts = set_counts.setdefault(set_id, dict.fromkeys(RANDOM_SONG_COUNTS, 0))
            role = song.random_song_role
            if role in counts:
                counts[role] += 1
                role_counts[role] += 1
        return {
            "active_count": len(songs),
            "practice_count": sum(song.is_practice for song in songs),
            "main_count": sum(not song.is_practice for song in songs),
            "common_count": sum(
                song.is_common and not song.is_practice for song in songs
            ),
            "random_train_count": role_counts["train"],
            "random_test_count": role_counts["test"],
            "stimulus_set_counts": {
                set_id: sum(counts.values()) for set_id, counts in set_counts.items()
            },
            "stimulus_set_role_counts": dict(
                sorted(set_counts.items(), key=lambda item: int(item[0]))
            ),
            "audio_root": str(self.get_audio_root()),
        }

    @staticmethod
    def _sha256_file(path):
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _wave_duration(path):
        if path.suffix.lower() != ".wav":
            return None
        try:
            with wave.open(str(path), "rb") as wav_file:
                frame_rate = wav_file.getframerate()
                if frame_rate <= 0:
                    return None
                return wav_file.getnframes() / frame_rate
        except (wave.Error, OSError):
            return None

    def resolve_audio_path(self, file_path):
        return Path(current_app.root_path) / "static" / file_path

    def seed_sample_data(self):
        audio_root = self.get_audio_root()
        audio_root.mkdir(parents=True, exist_ok=True)

        for item in SAMPLE_SONGS:
            audio_path = Path(current_app.root_path) / "static" / item["file_path"]
            if audio_path.exists():
                continue

            self.write_sample_wave_file(
                audio_path=audio_path,
                duration_seconds=item["duration_seconds"],
                frequency_hz=item["frequency_hz"],
            )

        self.sync_songs_from_static()

    def write_sample_wave_file(self, audio_path, duration_seconds, frequency_hz):
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 48000
        amplitude = 11000
        total_frames = int(sample_rate * duration_seconds)

        with wave.open(str(audio_path), "w") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)

            for frame_index in range(total_frames):
                value = int(
                    amplitude
                    * math.sin(2 * math.pi * frequency_hz * frame_index / sample_rate)
                )
                wav_file.writeframesraw(struct.pack("<h", value))
