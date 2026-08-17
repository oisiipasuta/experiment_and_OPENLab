import os
import secrets
from pathlib import Path

from flask import Flask
from sqlalchemy import inspect as sa_inspect, text

from constants import (
    EXPERIMENT_BROWSER_LABELS,
    EXPERIMENT_BROWSER_OPTIONS,
    EXPERIMENT_FLOW_STEPS,
    EXPERIMENT_NOTES,
    EXPERIMENT_DESCRIPTION_ITEMS,
    GENDER_LABELS,
    GENDER_OPTIONS,
    LISTENING_ENVIRONMENT_LABELS,
    LISTENING_ENVIRONMENT_OPTIONS,
    LISTENING_DEVICE_LABELS,
    LISTENING_DEVICE_OPTIONS,
    MUSIC_EXPERIENCE_HELP,
    MUSIC_EXPERIENCE_LABELS,
    MUSIC_EXPERIENCE_OPTIONS,
    MUSIC_EXPERIENCE_TYPE_LABELS,
    MUSIC_EXPERIENCE_TYPE_OPTIONS,
    PILOT_NOTICE,
    SD_ITEMS,
    SELECTION_REASON_OPTIONS,
    VOLUME_IMPRESSION_LABELS,
    VOLUME_IMPRESSION_OPTIONS,
)
from controllers import AdminController, ExperimentController
from models import db
from services import (
    AdminAnalyticsService,
    AudioCatalogService,
    CsvExportService,
    ExperimentService,
)
from validators import FormValidator


class MusicExperimentApplication:
    """アプリ全体の設定、初期化、依存関係の組み立てを担当する。"""

    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent
        self.validator = FormValidator()
        self.audio_catalog = AudioCatalogService()
        self.experiment_service = ExperimentService()
        self.analytics_service = AdminAnalyticsService()
        self.csv_export_service = CsvExportService(self.analytics_service)
        self.experiment_controller = ExperimentController(
            audio_catalog=self.audio_catalog,
            experiment_service=self.experiment_service,
            validator=self.validator,
        )
        self.admin_controller = AdminController(
            audio_catalog=self.audio_catalog,
            analytics_service=self.analytics_service,
            csv_export_service=self.csv_export_service,
        )

    def create_app(self):
        app = Flask(__name__)
        self._configure_app(app)

        db.init_app(app)
        self._register_template_helpers(app)
        self._register_cli_commands(app)
        self.experiment_controller.register(app)
        self.admin_controller.register(app)

        with app.app_context():
            self._initialize_database()

        return app

    def _configure_app(self, app):
        database_path = self._get_database_path()
        database_path.parent.mkdir(parents=True, exist_ok=True)

        secret_key = self._get_secret_key(database_path.parent)

        app.config["SECRET_KEY"] = secret_key
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{database_path}"
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        app.config["BUTTON_PRESS_MODE"] = os.environ.get("BUTTON_PRESS_MODE", "all")
        app.config["RANDOMIZE_PRACTICE_SONGS"] = True
        app.config["RANDOMIZE_MAIN_SONGS"] = True
        app.config["DATABASE_PATH"] = str(database_path)
        app.config["ADMIN_USERNAME"] = (
            os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin"
        )
        app.config["ADMIN_PASSWORD"] = self._get_admin_password(database_path.parent)

    def _register_template_helpers(self, app):
        @app.template_filter("datetime")
        def format_datetime(value):
            if not value:
                return "-"
            return value.strftime("%Y-%m-%d %H:%M:%S")

        @app.template_filter("music_experience_type")
        def format_music_experience_type(value):
            if not value:
                return "-"
            labels = [
                MUSIC_EXPERIENCE_TYPE_LABELS.get(item, item)
                for item in value.split(";")
                if item
            ]
            return "、".join(labels) if labels else "-"

        @app.context_processor
        def inject_template_globals():
            return {
                "sd_items": SD_ITEMS,
                "experiment_browser_options": EXPERIMENT_BROWSER_OPTIONS,
                "gender_options": GENDER_OPTIONS,
                "listening_environment_options": LISTENING_ENVIRONMENT_OPTIONS,
                "listening_device_options": LISTENING_DEVICE_OPTIONS,
                "volume_impression_options": VOLUME_IMPRESSION_OPTIONS,
                "music_experience_options": MUSIC_EXPERIENCE_OPTIONS,
                "music_experience_type_options": MUSIC_EXPERIENCE_TYPE_OPTIONS,
                "experiment_browser_labels": EXPERIMENT_BROWSER_LABELS,
                "gender_labels": GENDER_LABELS,
                "listening_environment_labels": LISTENING_ENVIRONMENT_LABELS,
                "listening_device_labels": LISTENING_DEVICE_LABELS,
                "volume_impression_labels": VOLUME_IMPRESSION_LABELS,
                "music_experience_labels": MUSIC_EXPERIENCE_LABELS,
                "music_experience_type_labels": MUSIC_EXPERIENCE_TYPE_LABELS,
                "experiment_description_items": EXPERIMENT_DESCRIPTION_ITEMS,
                "experiment_flow_steps": EXPERIMENT_FLOW_STEPS,
                "experiment_notes": EXPERIMENT_NOTES,
                "music_experience_help": MUSIC_EXPERIENCE_HELP,
                "pilot_notice": PILOT_NOTICE,
                "selection_reason_options": SELECTION_REASON_OPTIONS,
            }

    def _register_cli_commands(self, app):
        @app.cli.command("init-db")
        def init_db_command():
            db.create_all()
            self._apply_lightweight_migrations()
            print("Initialized the SQLite database.")

        @app.cli.command("seed-data")
        def seed_data_command():
            db.create_all()
            self._apply_lightweight_migrations()
            self.audio_catalog.seed_sample_data()
            print("Seeded sample songs and generated audio files.")

        @app.cli.command("sync-songs")
        def sync_songs_command():
            db.create_all()
            self._apply_lightweight_migrations()
            summary = self.audio_catalog.sync_songs_from_static()
            print(
                "Synced songs from static/audio "
                f"(practice={summary['practice_count']}, "
                f"main={summary['main_count']}, "
                f"total={summary['active_count']})."
            )

    def _initialize_database(self):
        db.create_all()
        self._apply_lightweight_migrations()
        self.audio_catalog.sync_songs_from_static()

    def _get_database_path(self):
        configured_path = os.environ.get("EXPERIMENT_DB_PATH", "").strip()
        if configured_path:
            return Path(configured_path).expanduser().resolve()

        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return (
                Path(local_app_data) / "music-listening-experiment" / "experiment.db"
            ).resolve()

        return (self.base_dir / "instance" / "experiment.db").resolve()

    def _get_secret_key(self, storage_dir):
        configured_secret = os.environ.get("SECRET_KEY", "").strip()
        if configured_secret:
            return configured_secret
        return self._load_or_create_secret_value(storage_dir / ".secret_key", length=48)

    def _get_admin_password(self, storage_dir):
        configured_password = os.environ.get("ADMIN_PASSWORD", "").strip()
        if configured_password:
            return configured_password
        return self._load_or_create_secret_value(
            storage_dir / ".admin_password",
            length=18,
        )

    @staticmethod
    def _load_or_create_secret_value(path, length):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing_value = path.read_text(encoding="utf-8").strip()
            if existing_value:
                return existing_value

        generated_value = secrets.token_urlsafe(length)
        path.write_text(generated_value, encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return generated_value

    @staticmethod
    def _apply_lightweight_migrations():
        inspector = sa_inspect(db.engine)
        existing_tables = set(inspector.get_table_names())

        migrations = {
            "participants": [
                ("age", "ALTER TABLE participants ADD COLUMN age INTEGER"),
                ("gender", "ALTER TABLE participants ADD COLUMN gender VARCHAR(50)"),
                (
                    "music_experience",
                    "ALTER TABLE participants ADD COLUMN music_experience VARCHAR(100)",
                ),
                (
                    "music_experience_years",
                    "ALTER TABLE participants ADD COLUMN music_experience_years INTEGER",
                ),
                (
                    "music_experience_type",
                    "ALTER TABLE participants ADD COLUMN music_experience_type TEXT",
                ),
                (
                    "listening_environment",
                    "ALTER TABLE participants ADD COLUMN listening_environment VARCHAR(50)",
                ),
                (
                    "listening_environment_note",
                    "ALTER TABLE participants ADD COLUMN listening_environment_note TEXT",
                ),
                (
                    "experiment_browser",
                    "ALTER TABLE participants ADD COLUMN experiment_browser VARCHAR(50)",
                ),
                (
                    "experiment_browser_note",
                    "ALTER TABLE participants ADD COLUMN experiment_browser_note TEXT",
                ),
                (
                    "listening_device",
                    "ALTER TABLE participants ADD COLUMN listening_device VARCHAR(50)",
                ),
                (
                    "listening_device_note",
                    "ALTER TABLE participants ADD COLUMN listening_device_note TEXT",
                ),
                (
                    "practice_volume_impression",
                    "ALTER TABLE participants ADD COLUMN practice_volume_impression VARCHAR(50)",
                ),
                (
                    "practice_volume_level",
                    "ALTER TABLE participants ADD COLUMN practice_volume_level INTEGER",
                ),
                (
                    "practice_volume_confirmed_at",
                    "ALTER TABLE participants ADD COLUMN practice_volume_confirmed_at DATETIME",
                ),
                (
                    "consent_given",
                    "ALTER TABLE participants ADD COLUMN consent_given BOOLEAN NOT NULL DEFAULT 0",
                ),
                ("consented_at", "ALTER TABLE participants ADD COLUMN consented_at DATETIME"),
            ],
            "songs": [
                (
                    "is_active",
                    "ALTER TABLE songs ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1",
                ),
            ],
            "participant_song_orders": [
                (
                    "press_count",
                    "ALTER TABLE participant_song_orders ADD COLUMN press_count INTEGER NOT NULL DEFAULT 0",
                ),
                (
                    "has_press",
                    "ALTER TABLE participant_song_orders ADD COLUMN has_press BOOLEAN NOT NULL DEFAULT 0",
                ),
                (
                    "all_press_audio_times",
                    "ALTER TABLE participant_song_orders ADD COLUMN all_press_audio_times TEXT",
                ),
                (
                    "selected_press_event_id",
                    "ALTER TABLE participant_song_orders ADD COLUMN selected_press_event_id INTEGER",
                ),
            ],
            "button_presses": [
                (
                    "assignment_id",
                    "ALTER TABLE button_presses ADD COLUMN assignment_id INTEGER",
                ),
                (
                    "press_event_id",
                    "ALTER TABLE button_presses ADD COLUMN press_event_id INTEGER",
                ),
                (
                    "selected_audio_time_sec",
                    "ALTER TABLE button_presses ADD COLUMN selected_audio_time_sec NUMERIC(12, 6)",
                ),
                (
                    "selected_segment_rule",
                    "ALTER TABLE button_presses ADD COLUMN selected_segment_rule VARCHAR(20)",
                ),
                (
                    "selected_segment_start_sec",
                    "ALTER TABLE button_presses ADD COLUMN selected_segment_start_sec NUMERIC(12, 6)",
                ),
                (
                    "selected_segment_end_sec",
                    "ALTER TABLE button_presses ADD COLUMN selected_segment_end_sec NUMERIC(12, 6)",
                ),
                (
                    "selected_segment_duration_sec",
                    "ALTER TABLE button_presses ADD COLUMN selected_segment_duration_sec NUMERIC(12, 6)",
                ),
                (
                    "selection_reason",
                    "ALTER TABLE button_presses ADD COLUMN selection_reason TEXT",
                ),
            ],
            "button_press_candidates": [
                (
                    "assignment_id",
                    "ALTER TABLE button_press_candidates ADD COLUMN assignment_id INTEGER",
                ),
                (
                    "press_event_id",
                    "ALTER TABLE button_press_candidates ADD COLUMN press_event_id INTEGER",
                ),
            ],
        }

        with db.engine.begin() as connection:
            for table_name, table_migrations in migrations.items():
                if table_name not in existing_tables:
                    continue

                current_columns = {
                    row[1]
                    for row in connection.execute(text(f"PRAGMA table_info({table_name})"))
                }
                for column_name, sql in table_migrations:
                    if column_name not in current_columns:
                        connection.execute(text(sql))

            if "press_events" in existing_tables:
                connection.execute(
                    text(
                        """
                        UPDATE press_events
                        SET
                            segment_rule = 'pre_4sec',
                            segment_start_sec = CASE
                                WHEN audio_time_sec < 4.0 THEN 0.0
                                ELSE audio_time_sec - 4.0
                            END,
                            segment_end_sec = CASE
                                WHEN audio_time_sec < 4.0 THEN 4.0
                                ELSE audio_time_sec
                            END,
                            segment_duration_sec = 4.0,
                            segment_clipped_start = CASE
                                WHEN audio_time_sec < 4.0 THEN 1
                                ELSE 0
                            END
                        WHERE segment_rule = 'pre_4sec'
                        """
                    )
                )
                if "participant_song_orders" in existing_tables:
                    connection.execute(
                        text(
                            """
                            UPDATE participant_song_orders
                            SET all_press_audio_times = COALESCE(
                                (
                                    SELECT group_concat(
                                        '押下' || ordered_presses.press_index || ':' ||
                                        printf('%.6f', ordered_presses.audio_time_sec),
                                        '; '
                                    )
                                    FROM (
                                        SELECT press_index, audio_time_sec
                                        FROM press_events
                                        WHERE press_events.assignment_id = participant_song_orders.id
                                        ORDER BY press_index ASC
                                    ) AS ordered_presses
                                ),
                                ''
                            )
                            """
                        )
                    )

            if "button_presses" in existing_tables:
                connection.execute(
                    text(
                        """
                        UPDATE button_presses
                        SET
                            selected_segment_rule = 'pre_4sec',
                            selected_segment_start_sec = CASE
                                WHEN selected_audio_time_sec < 4.0 THEN 0.0
                                ELSE selected_audio_time_sec - 4.0
                            END,
                            selected_segment_end_sec = CASE
                                WHEN selected_audio_time_sec < 4.0 THEN 4.0
                                ELSE selected_audio_time_sec
                            END,
                            selected_segment_duration_sec = 4.0
                        WHERE selected_audio_time_sec IS NOT NULL
                        """
                    )
                )


def create_app():
    return MusicExperimentApplication().create_app()
