from functools import wraps
from hmac import compare_digest
import time

from flask import current_app, flash, redirect, render_template, request, session, url_for


class AdminController:
    """管理画面、楽曲同期、CSV 出力のルーティングを担当する。"""

    def __init__(self, audio_catalog, analytics_service, csv_export_service):
        self.audio_catalog = audio_catalog
        self.analytics_service = analytics_service
        self.csv_export_service = csv_export_service
        self._failed_logins = {}

    def register(self, app):
        app.add_url_rule(
            "/admin/login",
            endpoint="admin_login",
            view_func=self.login,
            methods=["GET", "POST"],
        )
        app.add_url_rule(
            "/admin/logout",
            endpoint="admin_logout",
            view_func=self.logout,
            methods=["POST"],
        )

        routes = [
            ("/admin/sync-songs", "sync_songs", self.sync_songs, ["POST"]),
            ("/admin", "admin", self.admin, ["GET"]),
            (
                "/admin/export/participants.csv",
                "export_participants",
                self.export_participants,
                ["GET"],
            ),
            (
                "/admin/export/button-presses.csv",
                "export_button_presses",
                self.export_button_presses,
                ["GET"],
            ),
            (
                "/admin/export/press-events.csv",
                "export_press_events",
                self.export_press_events,
                ["GET"],
            ),
            (
                "/admin/export/impression-ratings.csv",
                "export_impression_ratings",
                self.export_impression_ratings,
                ["GET"],
            ),
            (
                "/admin/export/analysis-dataset.csv",
                "export_analysis_dataset",
                self.export_analysis_dataset,
                ["GET"],
            ),
        ]

        for rule, endpoint, view_func, methods in routes:
            app.add_url_rule(
                rule,
                endpoint=endpoint,
                view_func=self.admin_required(view_func),
                methods=methods,
            )

    def admin_required(self, view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if session.get("admin_authenticated"):
                return view_func(*args, **kwargs)

            next_url = request.full_path if request.query_string else request.path
            flash("管理画面を表示するにはログインしてください。", "info")
            return redirect(url_for("admin_login", next=next_url))

        return wrapper

    def login(self):
        if session.get("admin_authenticated"):
            return redirect(url_for("admin"))

        next_url = self.safe_admin_next(
            request.args.get("next") or request.form.get("next")
        )
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            expected_username = current_app.config["ADMIN_USERNAME"]
            expected_password = current_app.config["ADMIN_PASSWORD"]
            client_key = request.remote_addr or "unknown"
            now = time.monotonic()
            failed_at, failed_count = self._failed_logins.get(client_key, (0.0, 0))
            if now - failed_at < 60 and failed_count >= 5:
                flash("ログイン試行が多すぎます。1分後に再試行してください。", "error")
                return render_template(
                    "admin_login.html",
                    next_url=next_url,
                    admin_username=current_app.config["ADMIN_USERNAME"],
                ), 429

            if compare_digest(username, expected_username) and compare_digest(
                password,
                expected_password,
            ):
                session["admin_authenticated"] = True
                session["admin_username"] = username
                self._failed_logins.pop(client_key, None)
                flash("管理者としてログインしました。", "success")
                return redirect(next_url or url_for("admin"))

            if now - failed_at >= 60:
                failed_count = 0
            self._failed_logins[client_key] = (now, failed_count + 1)
            flash("管理者IDまたはパスワードが正しくありません。", "error")

        return render_template(
            "admin_login.html",
            next_url=next_url,
            admin_username=current_app.config["ADMIN_USERNAME"],
        )

    def logout(self):
        session.pop("admin_authenticated", None)
        session.pop("admin_username", None)
        flash("管理者ログアウトしました。", "info")
        return redirect(url_for("index"))

    @staticmethod
    def safe_admin_next(next_url):
        if next_url and next_url.startswith("/admin"):
            return next_url
        return url_for("admin")

    def sync_songs(self):
        song_summary = self.audio_catalog.sync_songs_from_static()
        flash(
            "楽曲カタログを更新しました。"
            f"練習 {song_summary['practice_count']} 曲 / "
            f"本試行 {song_summary['main_count']} 曲 / "
            f"合計 {song_summary['active_count']} 曲。",
            "success",
        )
        return redirect(url_for("admin"))

    def admin(self):
        song_summary = self.audio_catalog.sync_songs_from_static()
        dashboard_context = self.analytics_service.build_dashboard_context()
        return render_template(
            "admin_dashboard.html",
            song_summary=song_summary,
            **dashboard_context,
        )

    def export_participants(self):
        return self.csv_export_service.export_participants()

    def export_button_presses(self):
        return self.csv_export_service.export_button_presses()

    def export_press_events(self):
        return self.csv_export_service.export_press_events()

    def export_impression_ratings(self):
        return self.csv_export_service.export_impression_ratings()

    def export_analysis_dataset(self):
        return self.csv_export_service.export_analysis_dataset()
