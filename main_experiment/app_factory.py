import os
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

import click
from flask import Flask, request
from flask_migrate import Migrate, upgrade
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash

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
from models import (
    AdminLoginAttempt,
    Participant,
    ParticipantCredential,
    ResumeAttempt,
    db,
    utcnow,
)
from services import (
    AdminAnalyticsService,
    AudioCatalogService,
    CsvExportService,
    CredentialService,
    ExperimentService,
)
from validators import FormValidator


class MusicExperimentApplication:
    """アプリ全体の設定、初期化、依存関係の組み立てを担当する。"""

    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent
        self.validator = FormValidator()
        self.audio_catalog = AudioCatalogService()
        self.credential_service = CredentialService()
        self.experiment_service = ExperimentService(self.credential_service)
        self.analytics_service = AdminAnalyticsService()
        self.csv_export_service = CsvExportService(self.analytics_service)
        self.experiment_controller = ExperimentController(
            audio_catalog=self.audio_catalog,
            experiment_service=self.experiment_service,
            validator=self.validator,
            credential_service=self.credential_service,
        )
        self.admin_controller = AdminController(
            audio_catalog=self.audio_catalog,
            analytics_service=self.analytics_service,
            csv_export_service=self.csv_export_service,
            credential_service=self.credential_service,
        )

    def create_app(self):
        app = Flask(__name__)
        self._configure_app(app)

        db.init_app(app)
        Migrate(app, db)
        CSRFProtect(app)
        self._register_template_helpers(app)
        self._register_cli_commands(app)
        self._register_security_headers(app)
        self.experiment_controller.register(app)
        self.admin_controller.register(app)

        return app

    def _configure_app(self, app):
        production = os.environ.get("APP_ENV", "development").strip().lower() == "production"
        database_path = self._get_database_path()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        database_uri = os.environ.get("DATABASE_URL", "").strip()
        if database_uri.startswith("mysql://"):
            database_uri = database_uri.replace("mysql://", "mysql+pymysql://", 1)
        if production and not database_uri:
            raise RuntimeError("本番環境では DATABASE_URL の設定が必要です。")

        app.config["SECRET_KEY"] = self._required_or_development_secret(
            "SECRET_KEY", database_path.parent / ".secret_key", 48, production
        )
        app.config["WORKER_ID_PEPPER"] = self._required_or_development_secret(
            "WORKER_ID_PEPPER", database_path.parent / ".worker_id_pepper", 48, production
        )
        app.config["RESUME_CODE_SECRET"] = self._required_or_development_secret(
            "RESUME_CODE_SECRET", database_path.parent / ".resume_code_secret", 48, production
        )
        app.config["COMPLETION_CODE_SECRET"] = self._required_or_development_secret(
            "COMPLETION_CODE_SECRET",
            database_path.parent / ".completion_code_secret",
            48,
            production,
        )
        app.config["SQLALCHEMY_DATABASE_URI"] = database_uri or f"sqlite:///{database_path}"
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        if database_uri.startswith("mysql+"):
            app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
                "pool_pre_ping": True,
                "pool_recycle": 280,
            }
        app.config["BUTTON_PRESS_MODE"] = os.environ.get("BUTTON_PRESS_MODE", "all")
        app.config["RANDOMIZE_PRACTICE_SONGS"] = True
        app.config["RANDOMIZE_MAIN_SONGS"] = True
        app.config["DATABASE_PATH"] = str(database_path)
        app.config["IS_PRODUCTION"] = production
        app.config["SESSION_COOKIE_NAME"] = "__Host-main-experiment" if production else "main-experiment"
        app.config["SESSION_COOKIE_SECURE"] = production
        app.config["SESSION_COOKIE_HTTPONLY"] = True
        app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
        app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=24)
        # Flask-WTF 1.2 passes this value to itsdangerous as max_age, which
        # expects seconds rather than datetime.timedelta.
        app.config["WTF_CSRF_TIME_LIMIT"] = 6 * 60 * 60
        app.config["RESEARCH_END_DATE"] = os.environ.get("RESEARCH_END_DATE", "").strip()
        trusted_hosts = os.environ.get("TRUSTED_HOSTS", "").strip()
        if production and not trusted_hosts:
            raise RuntimeError("本番環境では TRUSTED_HOSTS の設定が必要です。")
        if trusted_hosts:
            app.config["TRUSTED_HOSTS"] = [
                item.strip() for item in trusted_hosts.split(",") if item.strip()
            ]
        app.config["ADMIN_USERNAME"] = (
            os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin"
        )
        configured_hash = os.environ.get("ADMIN_PASSWORD_HASH", "").strip()
        if production and not configured_hash:
            raise RuntimeError("本番環境では ADMIN_PASSWORD_HASH の設定が必要です。")
        if not configured_hash:
            configured_hash = generate_password_hash(
                self._get_admin_password(database_path.parent),
                method="pbkdf2:sha256:600000",
            )
        app.config["ADMIN_PASSWORD_HASH"] = configured_hash

    @staticmethod
    def _register_security_headers(app):
        @app.after_request
        def add_security_headers(response):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; media-src 'self'; connect-src 'self'; "
                "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
            )
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            response.headers["X-Frame-Options"] = "DENY"
            if app.config["IS_PRODUCTION"]:
                response.headers["Strict-Transport-Security"] = (
                    "max-age=31536000; includeSubDomains"
                )
            if not request.path.startswith("/static/"):
                response.headers["Cache-Control"] = "no-store"
            return response

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
            upgrade()
            click.echo("Initialized or upgraded the database to the latest migration.")

        @app.cli.command("seed-data")
        def seed_data_command():
            db.create_all()
            self.audio_catalog.seed_sample_data()
            click.echo("Seeded sample songs and generated audio files.")

        @app.cli.command("sync-songs")
        def sync_songs_command():
            summary = self.audio_catalog.sync_songs_from_static()
            click.echo(
                "Synced songs from static/audio "
                f"(practice={summary['practice_count']}, "
                f"main={summary['main_count']}, "
                f"total={summary['active_count']})."
            )

        @app.cli.command("purge-expired-data")
        @click.option(
            "--confirm",
            is_flag=True,
            help="実際に期限切れデータを削除する。指定しない場合は件数確認のみ。",
        )
        def purge_expired_data_command(confirm):
            credential_cutoff = utcnow() - timedelta(days=90)
            credential_query = ParticipantCredential.query.filter(
                ParticipantCredential.completion_redeemed_at.is_not(None),
                ParticipantCredential.completion_redeemed_at <= credential_cutoff,
            )
            expired_credential_count = credential_query.count()
            expired_participant_count = 0
            research_purge_due = False
            research_end_raw = app.config["RESEARCH_END_DATE"]
            if research_end_raw:
                try:
                    research_end = datetime.strptime(
                        research_end_raw, "%Y-%m-%d"
                    ).date()
                except ValueError as error:
                    raise click.ClickException(
                        "RESEARCH_END_DATE は YYYY-MM-DD 形式で設定してください。"
                    ) from error
                research_purge_due = date.today() >= research_end + timedelta(days=365)
                if research_purge_due:
                    expired_participant_count = Participant.query.count()

            click.echo(
                f"credential records due={expired_credential_count}, "
                f"research participants due={expired_participant_count}"
            )
            if not confirm:
                click.echo("確認のみです。削除する場合は --confirm を付けて再実行してください。")
                return
            if research_purge_due:
                Participant.query.delete(synchronize_session=False)
            else:
                credential_query.delete(synchronize_session=False)
            ResumeAttempt.query.filter(
                ResumeAttempt.attempted_at <= credential_cutoff
            ).delete(synchronize_session=False)
            AdminLoginAttempt.query.filter(
                AdminLoginAttempt.attempted_at <= credential_cutoff
            ).delete(synchronize_session=False)
            db.session.commit()
            click.echo("期限切れデータを削除しました。")

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

    def _required_or_development_secret(self, env_name, path, length, production):
        configured = os.environ.get(env_name, "").strip()
        if configured:
            return configured
        if production:
            raise RuntimeError(f"本番環境では {env_name} の設定が必要です。")
        return self._load_or_create_secret_value(path, length)

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


def create_app():
    return MusicExperimentApplication().create_app()
