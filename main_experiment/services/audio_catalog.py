import hashlib
import math
import re
import struct
import wave
from pathlib import Path

from flask import current_app

from constants import SAMPLE_SONGS, SUPPORTED_AUDIO_EXTENSIONS
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
            relative_static_path = Path("audio") / relative_audio_path
            discovered_files.append(
                {
                    "song_id": self.build_song_id(relative_audio_path),
                    "file_path": relative_static_path.as_posix(),
                    "is_practice": self.infer_is_practice(relative_audio_path),
                    "file_size_bytes": audio_path.stat().st_size,
                    "content_sha256": self._sha256_file(audio_path),
                    "duration_seconds": self._wave_duration(audio_path),
                }
            )

        return discovered_files

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
        Song.query.update({Song.is_active: False}, synchronize_session=False)

        practice_order = 0
        main_order = 0

        for item in discovered_files:
            if item["is_practice"]:
                practice_order += 1
                display_order = practice_order
            else:
                main_order += 1
                display_order = main_order

            song = Song.query.filter_by(song_id=item["song_id"]).first()
            if song is None:
                song = Song(song_id=item["song_id"])
                db.session.add(song)

            song.file_path = item["file_path"]
            song.is_practice = item["is_practice"]
            song.display_order = display_order
            song.is_active = True
            song.file_size_bytes = item["file_size_bytes"]
            song.content_sha256 = item["content_sha256"]
            song.duration_seconds = item["duration_seconds"]

        db.session.commit()

        return {
            "active_count": len(discovered_files),
            "practice_count": practice_order,
            "main_count": main_order,
            "audio_root": str(self.get_audio_root()),
        }

    def get_catalog_summary(self):
        return {
            "active_count": Song.query.filter_by(is_active=True).count(),
            "practice_count": Song.query.filter_by(
                is_active=True, is_practice=True
            ).count(),
            "main_count": Song.query.filter_by(
                is_active=True, is_practice=False
            ).count(),
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
