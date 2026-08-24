from pathlib import Path

from flask import (
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from models import db


class ExperimentController:
    """参加者向けの実験画面ルーティングを担当する。"""

    def __init__(
        self, audio_catalog, experiment_service, validator, preference_profile_service
    ):
        self.audio_catalog = audio_catalog
        self.experiment_service = experiment_service
        self.validator = validator
        self.preference_profile_service = preference_profile_service

    def register(self, app):
        routes = [
            ("/", "index", self.index, ["GET"]),
            (
                "/experiment/instructions",
                "experiment_instructions",
                self.experiment_instructions,
                ["GET", "POST"],
            ),
            (
                "/participant-info",
                "participant_info",
                self.participant_info,
                ["GET"],
            ),
            ("/start", "start_experiment", self.start_experiment, ["POST"]),
            ("/experiment/current", "current_trial", self.current_trial, ["GET"]),
            (
                "/experiment/volume-check",
                "volume_check",
                self.volume_check,
                ["GET", "POST"],
            ),
            ("/experiment/song/<int:assignment_id>", "play_song", self.play_song, ["GET"]),
            ("/api/button-press", "save_button_press", self.save_button_press, ["POST"]),
            (
                "/api/trials/<int:assignment_id>/complete-playback",
                "complete_playback",
                self.complete_playback,
                ["POST"],
            ),
            (
                "/experiment/select-press/<int:assignment_id>",
                "select_button_press",
                self.select_button_press,
                ["GET", "POST"],
            ),
            (
                "/experiment/rating/<int:assignment_id>",
                "rating",
                self.rating,
                ["GET", "POST"],
            ),
            ("/complete", "complete", self.complete, ["GET"]),
        ]

        for rule, endpoint, view_func, methods in routes:
            app.add_url_rule(rule, endpoint=endpoint, view_func=view_func, methods=methods)

    def index(self):
        song_summary = self.audio_catalog.sync_songs_from_static()
        participant = self.experiment_service.get_active_participant()
        has_active_session = (
            participant is not None and participant.current_phase != "complete"
        )

        return render_template(
            "index.html",
            active_participant=participant,
            has_active_session=has_active_session,
            song_summary=song_summary,
        )

    def experiment_instructions(self):
        if request.method == "POST":
            if request.form.get("instruction_acknowledged") != "yes":
                flash("説明内容を確認したうえで、チェックを入れて次へ進んでください。", "error")
                return self._render_instructions()
            session["instructions_acknowledged"] = True
            session["consent_agreed"] = True
            return redirect(url_for("participant_info"))

        return self._render_instructions()

    def participant_info(self):
        if not session.get("instructions_acknowledged"):
            flash("作成の流れと注意事項を確認してから基本情報を入力してください。", "info")
            return redirect(url_for("experiment_instructions"))
        return self._render_participant_info(form_values={})

    def start_experiment(self):
        if not session.get("instructions_acknowledged"):
            flash("作成の流れと注意事項を確認してからプロフィール作成を開始してください。", "error")
            return redirect(url_for("experiment_instructions"))

        participant_code = self._get_form_participant_code()
        form_data = request.form.copy()
        if session.get("consent_agreed"):
            form_data["consent_agreed"] = "yes"

        (
            age,
            gender,
            music_experience,
            music_experience_years,
            music_experience_type,
            listening_environment,
            listening_environment_note,
            experiment_browser,
            experiment_browser_note,
            listening_device,
            listening_device_note,
            consent_given,
            errors,
        ) = self.validator.validate_participant_form(form_data)

        if errors:
            for error in errors:
                flash(error, "error")
            return self._render_participant_info(form_values=form_data)

        self.audio_catalog.sync_songs_from_static()

        try:
            participant, created = self.experiment_service.start_or_resume_participant(
                participant_code=participant_code,
                age=age,
                gender=gender,
                music_experience=music_experience,
                music_experience_years=music_experience_years,
                music_experience_type=music_experience_type,
                listening_environment=listening_environment,
                listening_environment_note=listening_environment_note,
                experiment_browser=experiment_browser,
                experiment_browser_note=experiment_browser_note,
                listening_device=listening_device,
                listening_device_note=listening_device_note,
                consent_given=consent_given,
            )
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
            return redirect(url_for("participant_info"))

        session["participant_db_id"] = participant.id
        session["participant_code"] = participant.participant_id
        session.pop("pending_participant_code", None)

        if created:
            flash("音楽好みプロフィールの作成を開始します。", "success")
        else:
            flash(
                "既存の参加者IDを読み込み、保存済みの続きから再開します。",
                "info",
            )

        return redirect(url_for("current_trial"))

    def current_trial(self):
        participant = self.experiment_service.get_active_participant()
        if participant is None:
            flash("最初に参加者情報を入力してください。", "error")
            return redirect(url_for("participant_info"))

        assignment = self.experiment_service.get_current_assignment(participant)
        if assignment is None or participant.current_phase == "complete":
            participant.current_phase = "complete"
            db.session.commit()
            return redirect(url_for("complete"))

        if participant.current_phase == "selection":
            return redirect(url_for("select_button_press", assignment_id=assignment.id))

        if participant.current_phase == "rating":
            return redirect(url_for("rating", assignment_id=assignment.id))

        if participant.current_phase == "volume_check":
            return redirect(url_for("volume_check"))

        return redirect(url_for("play_song", assignment_id=assignment.id))

    def volume_check(self):
        participant = self.experiment_service.get_active_participant()
        if participant is None:
            flash("プロフィール作成を開始してください。", "error")
            return redirect(url_for("participant_info"))

        assignment = self.experiment_service.get_current_assignment(participant)
        if assignment is None:
            participant.current_phase = "complete"
            db.session.commit()
            return redirect(url_for("complete"))

        if participant.current_phase != "volume_check":
            flash("現在の進行に合わせた画面へ移動しました。", "info")
            return redirect(url_for("current_trial"))

        if request.method == "POST":
            volume_impression, volume_level, errors = (
                self.validator.validate_volume_check_form(request.form)
            )
            if errors:
                for error in errors:
                    flash(error, "error")
                return self._render_volume_check(
                    participant=participant,
                    assignment=assignment,
                    form_values=request.form,
                )

            self.experiment_service.save_practice_volume_response(
                participant=participant,
                volume_impression=volume_impression,
                volume_level=volume_level,
            )
            flash("音量についての確認を保存しました。本番の曲へ進みます。", "success")
            return redirect(url_for("current_trial"))

        return self._render_volume_check(
            participant=participant,
            assignment=assignment,
            form_values={},
        )

    def play_song(self, assignment_id):
        participant, assignment = self._get_active_trial()
        if participant is None or assignment is None:
            flash("プロフィール作成を開始してください。", "error")
            return redirect(url_for("participant_info"))

        if participant.current_phase != "playback" or assignment.id != assignment_id:
            flash("現在の進行に合わせた画面へ移動しました。", "info")
            return redirect(url_for("current_trial"))

        song = assignment.song
        audio_path = self.audio_catalog.resolve_audio_path(song.file_path)
        if not audio_path.exists():
            flash(
                f"音声ファイルが見つかりません: {song.file_path}。static/audio/ 配下を確認してください。",
                "error",
            )
            return redirect(url_for("participant_info"))

        return render_template(
            "player.html",
            participant=participant,
            assignment=assignment,
            song=song,
            song_url=url_for("static", filename=song.file_path),
            progress=self.experiment_service.get_progress_snapshot(participant, assignment),
        )

    def save_button_press(self):
        participant, assignment = self._get_active_trial()
        if participant is None or assignment is None:
            return jsonify({"ok": False, "message": "参加者情報が見つかりません。"}), 400

        if participant.current_phase != "playback":
            return (
                jsonify({"ok": False, "message": "現在はボタン記録を受け付けていません。"}),
                400,
            )

        payload = request.get_json(silent=True) or request.form
        assignment_id = self.validator.safe_int(payload.get("assignment_id"))
        audio_time_sec = self.validator.safe_decimal(
            payload.get("audio_time_sec", payload.get("pressed_time"))
        )
        audio_duration_sec = self.validator.safe_decimal(payload.get("audio_duration_sec"))
        performance_time_ms = self.validator.safe_decimal(payload.get("performance_time_ms"))
        client_timestamp_raw = payload.get("client_timestamp")
        client_timestamp = (
            str(client_timestamp_raw).strip() if client_timestamp_raw else None
        )

        if assignment_id != assignment.id:
            return jsonify({"ok": False, "message": "現在の曲と一致しません。"}), 400

        if audio_time_sec is None or audio_time_sec < 0:
            return jsonify({"ok": False, "message": "再生時間の値が不正です。"}), 400

        press_event, was_recorded = self.experiment_service.record_button_candidate(
            participant=participant,
            assignment=assignment,
            audio_time_sec=audio_time_sec,
            performance_time_ms=performance_time_ms,
            client_timestamp=client_timestamp,
            audio_duration_sec=audio_duration_sec,
        )

        if was_recorded:
            message = (
                f"「ここ好き！」を記録しました（{press_event.press_index} 回目 / "
                f"{float(press_event.audio_time_sec):.3f} 秒）"
            )
        else:
            message = "現在の設定ではこのボタン操作は保存されませんでした。"

        return jsonify(
            {
                "ok": True,
                "press_order": press_event.press_index if press_event else None,
                "press_id": press_event.id if press_event else None,
                "message": message,
            }
        )

    def complete_playback(self, assignment_id):
        participant, assignment = self._get_active_trial()
        if participant is None or assignment is None:
            return jsonify({"ok": False, "message": "参加者情報が見つかりません。"}), 400

        if assignment.id != assignment_id:
            return jsonify({"ok": False, "message": "現在の曲と一致しません。"}), 400

        next_step = self.experiment_service.finish_playback(participant, assignment)
        next_url = (
            url_for("select_button_press", assignment_id=assignment.id)
            if next_step == "selection"
            else url_for("rating", assignment_id=assignment.id)
        )

        return jsonify({"ok": True, "next_url": next_url, "next_step": next_step})

    def select_button_press(self, assignment_id):
        participant, assignment = self._get_active_trial()
        if participant is None or assignment is None:
            flash("プロフィール作成を開始してください。", "error")
            return redirect(url_for("participant_info"))

        if participant.current_phase != "selection" or assignment.id != assignment_id:
            flash("現在の進行に合わせた画面へ移動しました。", "info")
            return redirect(url_for("current_trial"))

        candidates = self.experiment_service.get_candidate_presses(
            participant=participant,
            song=assignment.song,
            is_practice=assignment.is_practice,
        )

        if not candidates:
            participant.current_phase = "rating"
            db.session.commit()
            return redirect(url_for("current_trial"))

        if request.method == "POST":
            selected_candidate_id = self.validator.safe_int(
                request.form.get("selected_candidate_id")
            )
            selection_payload = self.validator.validate_selection_form(request.form)
            errors = selection_payload["errors"]
            if errors:
                for error in errors:
                    flash(error, "error")
                return self._render_selection(
                    participant=participant,
                    assignment=assignment,
                    candidates=candidates,
                    form_values=self._build_selection_form_values(request.form, candidates),
                )

            was_selected = self.experiment_service.select_candidate_press(
                participant=participant,
                assignment=assignment,
                candidate_id=selected_candidate_id,
                selection_reason=selection_payload["serialized_reason"],
            )

            if not was_selected:
                flash("採用する部分を 1 つ選択してください。", "error")
            else:
                flash("一番好きだったところと理由を保存しました。", "success")
                return redirect(url_for("current_trial"))

        return self._render_selection(
            participant=participant,
            assignment=assignment,
            candidates=candidates,
            form_values=self._build_selection_form_values({}, candidates),
        )

    def rating(self, assignment_id):
        participant, assignment = self._get_active_trial()
        if participant is None or assignment is None:
            flash("プロフィール作成を開始してください。", "error")
            return redirect(url_for("participant_info"))

        if participant.current_phase != "rating" or assignment.id != assignment_id:
            flash("現在の進行に合わせた画面へ移動しました。", "info")
            return redirect(url_for("current_trial"))

        existing_rating = self.experiment_service.get_existing_rating(participant, assignment)
        if request.method == "POST":
            values, errors = self.validator.validate_rating_form(request.form)
            if errors:
                for error in errors:
                    flash(error, "error")
                return self._render_rating(
                    participant=participant,
                    assignment=assignment,
                    form_values=request.form,
                )

            next_phase = self.experiment_service.save_rating(
                participant=participant,
                assignment=assignment,
                values=values,
            )
            flash("曲の印象についての回答を保存しました。", "success")

            if next_phase == "complete":
                return redirect(url_for("complete"))
            return redirect(url_for("current_trial"))

        return self._render_rating(
            participant=participant,
            assignment=assignment,
            form_values=self.experiment_service.get_rating_form_values(existing_rating),
        )

    def complete(self):
        participant = self.experiment_service.get_active_participant()
        if participant is None:
            flash("基本情報を入力してプロフィール作成を開始してください。", "info")
            return redirect(url_for("participant_info"))

        current_assignment = self.experiment_service.get_current_assignment(participant)
        if participant.current_phase != "complete" and current_assignment is not None:
            flash("実験はまだ完了していません。現在の曲へ戻ります。", "info")
            return redirect(url_for("current_trial"))

        if not participant.experiment_completed:
            flash("本実験5曲の保存が完了していません。", "error")
            return redirect(url_for("current_trial"))

        # 最終評価の commit 後にのみ表示用プロフィールを生成する。
        try:
            profile = self.preference_profile_service.generate(participant)
        except Exception:
            current_app.logger.exception("Preference profile generation failed")
            profile = self.preference_profile_service.fallback()

        summary = self.experiment_service.build_completion_summary(participant)
        return render_template(
            "complete.html",
            participant=participant,
            total_trials=summary["total_trials"],
            button_press_count=summary["button_press_count"],
            rating_count=summary["rating_count"],
            profile=profile,
        )

    def _render_participant_info(self, form_values):
        song_summary = self.audio_catalog.sync_songs_from_static()
        participant = self.experiment_service.get_active_participant()
        has_active_session = (
            participant is not None and participant.current_phase != "complete"
        )

        return render_template(
            "participant_info.html",
            active_participant=participant,
            has_active_session=has_active_session,
            song_summary=song_summary,
            form_values=form_values,
            auto_participant_code=self._get_display_participant_code(participant),
            selected_music_experience_types=self._get_music_experience_types_for_form(
                form_values,
                participant,
            ),
        )

    def _render_instructions(self):
        video_static_path = "video/experiment_instruction.mp4"
        video_path = Path(current_app.root_path) / current_app.static_folder / video_static_path
        return render_template(
            "experiment_instructions.html",
            instruction_video_url=url_for("static", filename=video_static_path),
            instruction_video_exists=video_path.exists(),
        )

    def _render_rating(self, participant, assignment, form_values):
        return render_template(
            "rating.html",
            participant=participant,
            assignment=assignment,
            song=assignment.song,
            progress=self.experiment_service.get_progress_snapshot(participant, assignment),
            form_values=form_values,
        )

    def _render_volume_check(self, participant, assignment, form_values):
        return render_template(
            "volume_check.html",
            participant=participant,
            assignment=assignment,
            progress=self.experiment_service.get_progress_snapshot(participant, assignment),
            form_values=form_values,
        )

    def _render_selection(self, participant, assignment, candidates, form_values):
        return render_template(
            "select_press.html",
            participant=participant,
            assignment=assignment,
            song=assignment.song,
            song_url=url_for("static", filename=assignment.song.file_path),
            progress=self.experiment_service.get_progress_snapshot(participant, assignment),
            candidates=candidates,
            form_values=form_values,
        )

    @staticmethod
    def _build_selection_form_values(form_values, candidates):
        if hasattr(form_values, "getlist"):
            selected_choices = form_values.getlist("selection_reason_choices")
            selected_candidate_id = form_values.get("selected_candidate_id")
        else:
            selected_choices = list(form_values.get("selection_reason_choices", []))
            selected_candidate_id = form_values.get("selected_candidate_id")

        if selected_candidate_id is None and len(candidates) == 1:
            selected_candidate_id = str(candidates[0].id)

        return {
            "selected_candidate_id": selected_candidate_id or "",
            "selection_reason_choices": selected_choices,
        }

    def _get_form_participant_code(self):
        participant = self.experiment_service.get_active_participant()
        if participant is not None and participant.current_phase != "complete":
            return participant.participant_id

        return self._get_or_create_pending_participant_code()

    def _get_display_participant_code(self, participant):
        if participant is not None and participant.current_phase != "complete":
            return participant.participant_id
        return self._get_or_create_pending_participant_code()

    def _get_or_create_pending_participant_code(self):
        participant_code = session.get("pending_participant_code")
        if participant_code:
            return participant_code

        participant_code = self.experiment_service.generate_participant_code()
        session["pending_participant_code"] = participant_code
        return participant_code

    @staticmethod
    def _get_music_experience_types_for_form(form_values, participant):
        if hasattr(form_values, "getlist"):
            return [
                value
                for value in form_values.getlist("music_experience_type")
                if value
            ]

        form_type = form_values.get("music_experience_type") if form_values else None
        if isinstance(form_type, (list, tuple)):
            return [value for value in form_type if value]
        if form_type:
            return [form_type]

        if participant is not None and participant.music_experience_type:
            return [
                value
                for value in participant.music_experience_type.split(";")
                if value
            ]

        return []

    def _get_active_trial(self):
        participant = self.experiment_service.get_active_participant()
        assignment = (
            self.experiment_service.get_current_assignment(participant) if participant else None
        )
        return participant, assignment
