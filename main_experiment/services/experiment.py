from decimal import Decimal
import random
import secrets

from flask import current_app, session

from constants import (
    ATTENTION_CHECK_EXPECTED_VALUE,
    ATTENTION_CHECK_VERSION,
    SD_ITEMS,
)
from models import (
    AttentionCheck,
    ButtonPress,
    ButtonPressCandidate,
    ImpressionRating,
    Participant,
    ParticipantSongOrder,
    PressEvent,
    QualityFlag,
    Song,
    TrialTelemetry,
    db,
    utcnow,
)


class ExperimentService:
    """実験進行、参加者状態、押下位置の確定を担当する。"""

    SEGMENT_RULE = "pre_4sec"
    PRE_REACTION_CONTEXT_SEC = Decimal("4.000000")

    def __init__(self, credential_service=None):
        self.credential_service = credential_service

    def generate_participant_code(self):
        timestamp = utcnow().strftime("%Y%m%d%H%M%S")
        for _ in range(20):
            code = f"P{timestamp}{secrets.token_hex(2).upper()}"
            if Participant.query.filter_by(participant_id=code).first() is None:
                return code
        raise ValueError("参加者IDを自動発行できませんでした。もう一度お試しください。")

    def get_active_participant(self):
        participant_db_id = session.get("participant_db_id")
        if participant_db_id is None:
            return None
        return db.session.get(Participant, participant_db_id)

    def start_or_resume_participant(
        self,
        participant_code,
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
        worker_id=None,
        resume_code=None,
    ):
        participant = Participant.query.filter_by(participant_id=participant_code).first()
        created = False

        if participant is None:
            participant = Participant(
                participant_id=participant_code,
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
                consented_at=utcnow() if consent_given else None,
            )
            db.session.add(participant)
            db.session.flush()
            if self.credential_service is not None:
                self.credential_service.create_credential(
                    participant=participant,
                    worker_id=worker_id,
                    resume_code=resume_code,
                )
            self.create_participant_song_order(participant)
            created = True
        else:
            self._update_participant_demographics(
                participant,
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
            )
            self._apply_participant_consent(participant, consent_given)
            if not participant.assignments:
                self.create_participant_song_order(participant)

        db.session.commit()
        return participant, created

    @staticmethod
    def _update_participant_demographics(
        participant,
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
    ):
        if age is not None:
            participant.age = age
        if gender:
            participant.gender = gender
        if music_experience:
            participant.music_experience = music_experience
            participant.music_experience_years = music_experience_years
            participant.music_experience_type = music_experience_type
        if listening_environment:
            participant.listening_environment = listening_environment
            participant.listening_environment_note = listening_environment_note
        if experiment_browser:
            participant.experiment_browser = experiment_browser
            participant.experiment_browser_note = experiment_browser_note
        if listening_device:
            participant.listening_device = listening_device
            participant.listening_device_note = listening_device_note

    @staticmethod
    def _apply_participant_consent(participant, consent_given):
        if consent_given and not participant.consent_given:
            participant.consent_given = True
            participant.consented_at = utcnow()
        elif participant.consent_given and participant.consented_at is None:
            participant.consented_at = utcnow()

    def create_participant_song_order(self, participant):
        practice_songs = (
            Song.query.filter_by(is_practice=True, is_active=True)
            .order_by(Song.display_order.asc(), Song.song_id.asc())
            .all()
        )
        main_songs = (
            Song.query.filter_by(is_practice=False, is_active=True)
            .order_by(Song.display_order.asc(), Song.song_id.asc())
            .all()
        )

        if not practice_songs and not main_songs:
            raise ValueError(
                "static/audio/ 配下に楽曲が見つかりません。音源ファイルを配置してから再開してください。"
            )

        practice_order = practice_songs[:]
        main_order = main_songs[:]

        rng = random.SystemRandom()
        if current_app.config["RANDOMIZE_PRACTICE_SONGS"]:
            rng.shuffle(practice_order)
        if current_app.config["RANDOMIZE_MAIN_SONGS"]:
            rng.shuffle(main_order)

        combined_order = practice_order + main_order
        for index, song in enumerate(combined_order):
            db.session.add(
                ParticipantSongOrder(
                    participant_id=participant.id,
                    song_id=song.id,
                    order_index=index,
                    is_practice=song.is_practice,
                )
            )

        if main_order:
            first_end = min(14, len(main_order))
            participant.attention_check_trial_1 = (
                rng.randint(8, first_end) if first_end >= 8 else None
            )
            second_end = min(25, len(main_order))
            participant.attention_check_trial_2 = (
                rng.randint(19, second_end) if second_end >= 19 else None
            )

    def get_current_assignment(self, participant):
        if participant is None:
            return None
        return ParticipantSongOrder.query.filter_by(
            participant_id=participant.id,
            order_index=participant.current_assignment_index,
        ).first()

    def get_progress_snapshot(self, participant, assignment):
        assignments = (
            ParticipantSongOrder.query.filter_by(participant_id=participant.id)
            .order_by(ParticipantSongOrder.order_index.asc())
            .all()
        )

        grouped = [item for item in assignments if item.is_practice == assignment.is_practice]
        group_index = next(
            index for index, item in enumerate(grouped, start=1) if item.id == assignment.id
        )
        practice_total = sum(1 for item in assignments if item.is_practice)
        main_total = len(assignments) - practice_total

        return {
            "all_current": assignment.order_index + 1,
            "all_total": len(assignments),
            "group_current": group_index,
            "group_total": len(grouped),
            "practice_total": practice_total,
            "main_total": main_total,
            "phase_label": "練習" if assignment.is_practice else "本番",
        }

    def get_candidate_presses(self, participant, song, is_practice):
        return (
            ButtonPressCandidate.query.filter_by(
                participant_id=participant.participant_id,
                song_id=song.song_id,
                is_practice=is_practice,
            )
            .order_by(
                ButtonPressCandidate.press_order.asc(),
                ButtonPressCandidate.created_at.asc(),
            )
            .all()
        )

    def record_button_candidate(
        self,
        participant,
        assignment,
        audio_time_sec,
        performance_time_ms=None,
        client_timestamp=None,
    ):
        song = assignment.song
        is_practice = assignment.is_practice
        mode = current_app.config["BUTTON_PRESS_MODE"]
        existing_records = self.get_candidate_presses(participant, song, is_practice)
        press_event = self._create_press_event(
            participant=participant,
            assignment=assignment,
            audio_time_sec=audio_time_sec,
            performance_time_ms=performance_time_ms,
            client_timestamp=client_timestamp,
        )

        if mode == "first_only" and existing_records:
            self._refresh_assignment_press_summary(participant, assignment)
            db.session.commit()
            return press_event, True

        if mode == "last_only" and existing_records:
            record = existing_records[-1]
            record.assignment_id = assignment.id
            record.press_event_id = press_event.id
            record.press_order = press_event.press_index
            record.pressed_time = audio_time_sec
            record.created_at = press_event.server_received_at
            self._refresh_assignment_press_summary(participant, assignment)
            db.session.commit()
            return press_event, True

        record = ButtonPressCandidate(
            participant_id=participant.participant_id,
            song_id=song.song_id,
            assignment_id=assignment.id,
            press_event_id=press_event.id,
            is_practice=is_practice,
            press_order=press_event.press_index,
            pressed_time=audio_time_sec,
            created_at=press_event.server_received_at,
        )
        db.session.add(record)
        self._refresh_assignment_press_summary(participant, assignment)
        db.session.commit()
        return press_event, True

    @staticmethod
    def _current_timestamp():
        return utcnow()

    def _create_press_event(
        self,
        participant,
        assignment,
        audio_time_sec,
        performance_time_ms=None,
        client_timestamp=None,
    ):
        segment = self.build_pre_4sec_segment(audio_time_sec)
        server_received_at = self._current_timestamp()

        press_event = PressEvent(
            assignment_id=assignment.id,
            participant_id=participant.participant_id,
            song_id=assignment.song.song_id,
            is_practice=assignment.is_practice,
            press_index=self.count_press_events(participant, assignment) + 1,
            audio_time_sec=segment["audio_time_sec"],
            performance_time_ms=performance_time_ms,
            client_timestamp=client_timestamp,
            server_received_at=server_received_at,
            segment_rule=segment["segment_rule"],
            segment_start_sec=segment["segment_start_sec"],
            segment_end_sec=segment["segment_end_sec"],
            segment_duration_sec=segment["segment_duration_sec"],
            segment_clipped_start=segment["segment_clipped_start"],
            is_selected=False,
            created_at=server_received_at,
        )
        db.session.add(press_event)
        db.session.flush()
        return press_event

    @classmethod
    def build_pre_4sec_segment(cls, audio_time_sec):
        # 押下時刻を終点とし、その直前の音だけを分析対象にする。
        # 曲開始から4秒未満で押した場合は、0秒から押下時刻までの短い区間になる。
        audio_time_sec = Decimal(audio_time_sec).quantize(Decimal("0.000001"))
        segment_start_sec = max(
            Decimal("0.000000"),
            audio_time_sec - cls.PRE_REACTION_CONTEXT_SEC,
        )
        segment_end_sec = audio_time_sec
        return {
            "audio_time_sec": audio_time_sec,
            "segment_rule": cls.SEGMENT_RULE,
            "segment_start_sec": segment_start_sec,
            "segment_end_sec": segment_end_sec,
            "segment_duration_sec": segment_end_sec - segment_start_sec,
            "segment_clipped_start": audio_time_sec < cls.PRE_REACTION_CONTEXT_SEC,
        }

    def get_press_events(self, participant, assignment):
        return (
            PressEvent.query.filter_by(
                assignment_id=assignment.id,
                participant_id=participant.participant_id,
                song_id=assignment.song.song_id,
                is_practice=assignment.is_practice,
            )
            .order_by(PressEvent.press_index.asc(), PressEvent.server_received_at.asc())
            .all()
        )

    def count_press_events(self, participant, assignment):
        return PressEvent.query.filter_by(
            assignment_id=assignment.id,
            participant_id=participant.participant_id,
            song_id=assignment.song.song_id,
            is_practice=assignment.is_practice,
        ).count()

    def _refresh_assignment_press_summary(self, participant, assignment):
        press_events = self.get_press_events(participant, assignment)
        if press_events:
            press_count = len(press_events)
            all_press_audio_times = self._serialize_press_audio_times(
                press_events,
                index_attribute="press_index",
                time_attribute="audio_time_sec",
            )
        else:
            candidates = self.get_candidate_presses(
                participant=participant,
                song=assignment.song,
                is_practice=assignment.is_practice,
            )
            press_count = len(candidates)
            all_press_audio_times = self._serialize_press_audio_times(
                candidates,
                index_attribute="press_order",
                time_attribute="pressed_time",
            )

        assignment.press_count = press_count
        assignment.has_press = press_count > 0
        assignment.all_press_audio_times = all_press_audio_times

    @staticmethod
    def _serialize_press_audio_times(records, index_attribute, time_attribute):
        return "; ".join(
            f"押下{getattr(record, index_attribute)}:{float(getattr(record, time_attribute)):.6f}"
            for record in records
        )

    def finish_playback(self, participant, assignment, telemetry_payload=None):
        self._refresh_assignment_press_summary(participant, assignment)
        self.record_playback_completion(
            participant,
            assignment,
            telemetry_payload or {},
        )
        participant.current_phase = "rating"
        db.session.commit()
        return "rating"

    def select_candidate_press(self, participant, assignment, candidate_id, selection_reason):
        candidates = self.get_candidate_presses(
            participant=participant,
            song=assignment.song,
            is_practice=assignment.is_practice,
        )
        if len(candidates) == 1 and candidate_id is None:
            candidate_id = candidates[0].id

        selected_candidate = next(
            (candidate for candidate in candidates if candidate.id == candidate_id),
            None,
        )

        if selected_candidate is None:
            return False

        self.persist_selected_press(
            participant=participant,
            assignment=assignment,
            candidate=selected_candidate,
            selection_reason=selection_reason,
        )
        self.advance_to_next_assignment(participant)
        if participant.current_phase == "complete":
            self.refresh_straightlining_flag(participant)
        db.session.commit()
        return True

    def persist_selected_press(self, participant, assignment, candidate, selection_reason=None):
        song = assignment.song
        is_practice = assignment.is_practice
        press_event = self._resolve_candidate_press_event(participant, assignment, candidate)
        segment = self._segment_from_press_event_or_candidate(press_event, candidate)

        PressEvent.query.filter_by(assignment_id=assignment.id).update(
            {PressEvent.is_selected: False},
            synchronize_session=False,
        )
        if press_event is not None:
            press_event.is_selected = True
            assignment.selected_press_event_id = press_event.id

        record = ButtonPress.query.filter_by(assignment_id=assignment.id).first()
        if record is None:
            record = ButtonPress.query.filter_by(
                participant_id=participant.participant_id,
                song_id=song.song_id,
                is_practice=is_practice,
            ).first()

        if record is None:
            record = ButtonPress(
                participant_id=participant.participant_id,
                song_id=song.song_id,
                is_practice=is_practice,
            )
            db.session.add(record)

        record.assignment_id = assignment.id
        record.press_event_id = press_event.id if press_event else None
        record.press_order = press_event.press_index if press_event else candidate.press_order
        record.pressed_time = segment["audio_time_sec"]
        record.selected_audio_time_sec = segment["audio_time_sec"]
        record.selected_segment_rule = segment["segment_rule"]
        record.selected_segment_start_sec = segment["segment_start_sec"]
        record.selected_segment_end_sec = segment["segment_end_sec"]
        record.selected_segment_duration_sec = segment["segment_duration_sec"]
        record.selection_reason = selection_reason
        record.created_at = (
            press_event.server_received_at if press_event is not None else candidate.created_at
        )

        self._refresh_assignment_press_summary(participant, assignment)
        self.clear_candidate_presses(participant, song, is_practice)

    def _resolve_candidate_press_event(self, participant, assignment, candidate):
        press_event = candidate.press_event
        if press_event is not None:
            return press_event

        if candidate.press_event_id is not None:
            return db.session.get(PressEvent, candidate.press_event_id)

        return self._create_press_event(
            participant=participant,
            assignment=assignment,
            audio_time_sec=candidate.pressed_time,
            performance_time_ms=None,
            client_timestamp=None,
        )

    def _segment_from_press_event_or_candidate(self, press_event, candidate):
        if press_event is None:
            return self.build_pre_4sec_segment(candidate.pressed_time)

        return {
            "audio_time_sec": press_event.audio_time_sec,
            "segment_rule": press_event.segment_rule,
            "segment_start_sec": press_event.segment_start_sec,
            "segment_end_sec": press_event.segment_end_sec,
            "segment_duration_sec": press_event.segment_duration_sec,
            "segment_clipped_start": press_event.segment_clipped_start,
        }

    def clear_candidate_presses(self, participant, song, is_practice):
        ButtonPressCandidate.query.filter_by(
            participant_id=participant.participant_id,
            song_id=song.song_id,
            is_practice=is_practice,
        ).delete(synchronize_session=False)

    def get_existing_rating(self, participant, assignment):
        return ImpressionRating.query.filter_by(
            participant_id=participant.participant_id,
            song_id=assignment.song.song_id,
            is_practice=assignment.is_practice,
        ).first()

    def count_candidate_presses(self, participant, assignment):
        return len(
            self.get_candidate_presses(
                participant=participant,
                song=assignment.song,
                is_practice=assignment.is_practice,
            )
        )

    def get_rating_form_values(self, rating):
        if rating is None:
            return {}
        return {item["name"]: getattr(rating, item["name"]) for item in SD_ITEMS}

    def save_rating(self, participant, assignment, values, attention_value=None):
        rating_record = self.get_existing_rating(participant, assignment)
        if rating_record is None:
            rating_record = ImpressionRating(
                participant_id=participant.participant_id,
                song_id=assignment.song.song_id,
                is_practice=assignment.is_practice,
            )
            db.session.add(rating_record)

        for field_name, value in values.items():
            setattr(rating_record, field_name, value)

        self.record_rating_submission(participant, assignment)
        if self.should_show_attention_check(participant, assignment):
            self.save_attention_check(participant, assignment, attention_value)

        candidates = self.get_candidate_presses(
            participant=participant,
            song=assignment.song,
            is_practice=assignment.is_practice,
        )

        if len(candidates) >= 1:
            self._refresh_assignment_press_summary(participant, assignment)
            participant.current_phase = "selection"
            db.session.commit()
            return participant.current_phase

        self._refresh_assignment_press_summary(participant, assignment)
        self.advance_to_next_assignment(participant)
        if participant.current_phase == "complete":
            self.refresh_straightlining_flag(participant)
        db.session.commit()
        return participant.current_phase

    def advance_to_next_assignment(self, participant):
        completed_assignment = self.get_current_assignment(participant)
        participant.current_assignment_index += 1
        next_assignment = self.get_current_assignment(participant)
        if next_assignment is None:
            participant.current_phase = "complete"
            return

        if self.should_show_practice_volume_check(participant, completed_assignment, next_assignment):
            participant.current_phase = "volume_check"
            return

        participant.current_phase = "playback"

    @staticmethod
    def should_show_practice_volume_check(
        participant,
        completed_assignment,
        next_assignment,
    ):
        if completed_assignment is None or next_assignment is None:
            return False
        if participant.practice_volume_confirmed_at is not None:
            return False
        return completed_assignment.is_practice and not next_assignment.is_practice

    def save_practice_volume_response(self, participant, volume_impression, volume_level):
        participant.practice_volume_impression = volume_impression
        participant.practice_volume_level = volume_level
        participant.practice_volume_confirmed_at = utcnow()
        participant.current_phase = "playback"
        db.session.commit()

    def build_completion_summary(self, participant):
        total_trials = ParticipantSongOrder.query.filter_by(participant_id=participant.id).count()
        button_press_count = ButtonPress.query.filter_by(
            participant_id=participant.participant_id
        ).count()
        rating_count = ImpressionRating.query.filter_by(
            participant_id=participant.participant_id
        ).count()

        return {
            "total_trials": total_trials,
            "button_press_count": button_press_count,
            "rating_count": rating_count,
        }

    def get_main_trial_number(self, participant, assignment):
        if assignment.is_practice:
            return None
        main_assignments = [item for item in participant.assignments if not item.is_practice]
        for index, item in enumerate(main_assignments, start=1):
            if item.id == assignment.id:
                return index
        return None

    def should_show_attention_check(self, participant, assignment):
        main_trial_number = self.get_main_trial_number(participant, assignment)
        return main_trial_number is not None and main_trial_number in {
            participant.attention_check_trial_1,
            participant.attention_check_trial_2,
        }

    def get_attention_check_expected_value(self, participant, assignment):
        """Choose and persist the target number once for this attention check."""
        record = AttentionCheck.query.filter_by(assignment_id=assignment.id).first()
        if record is None:
            telemetry = self.get_or_create_telemetry(participant, assignment)
            record = AttentionCheck(
                participant_id=participant.id,
                assignment_id=assignment.id,
                main_trial_number=self.get_main_trial_number(participant, assignment),
                expected_value=ATTENTION_CHECK_EXPECTED_VALUE,
                prompt_version=ATTENTION_CHECK_VERSION,
                displayed_at=telemetry.rating_viewed_at or utcnow(),
                submitted_at=telemetry.rating_viewed_at or utcnow(),
            )
            db.session.add(record)
            db.session.commit()
        elif record.actual_value is None:
            record.expected_value = ATTENTION_CHECK_EXPECTED_VALUE
            record.prompt_version = ATTENTION_CHECK_VERSION
        return record.expected_value

    def get_or_create_telemetry(self, participant, assignment):
        telemetry = TrialTelemetry.query.filter_by(assignment_id=assignment.id).first()
        if telemetry is None:
            telemetry = TrialTelemetry(
                participant_id=participant.id,
                assignment_id=assignment.id,
            )
            db.session.add(telemetry)
            db.session.flush()
        return telemetry

    def record_playback_page_view(self, participant, assignment):
        telemetry = self.get_or_create_telemetry(participant, assignment)
        if telemetry.playback_page_viewed_at is None:
            telemetry.playback_page_viewed_at = utcnow()
            db.session.commit()

    def record_rating_page_view(self, participant, assignment):
        telemetry = self.get_or_create_telemetry(participant, assignment)
        if telemetry.rating_viewed_at is None:
            telemetry.rating_viewed_at = utcnow()
            db.session.commit()

    def record_playback_completion(self, participant, assignment, payload):
        telemetry = self.get_or_create_telemetry(participant, assignment)
        telemetry.playback_completed_at = utcnow()
        telemetry.client_ended = bool(payload.get("client_ended"))
        telemetry.audio_duration_sec = (
            assignment.song.duration_seconds
            or self._safe_nonnegative_decimal(payload.get("audio_duration_sec"))
        )
        telemetry.audio_current_time_sec = self._safe_nonnegative_decimal(
            payload.get("audio_current_time_sec")
        )
        telemetry.hidden_count = self._safe_nonnegative_int(payload.get("hidden_count"))
        telemetry.hidden_duration_ms = self._safe_nonnegative_int(
            payload.get("hidden_duration_ms")
        )
        telemetry.seek_attempt_count = self._safe_nonnegative_int(
            payload.get("seek_attempt_count")
        )
        telemetry.unexpected_pause_count = self._safe_nonnegative_int(
            payload.get("unexpected_pause_count")
        )
        telemetry.playback_error_count = self._safe_nonnegative_int(
            payload.get("playback_error_count")
        )

        duration = telemetry.audio_duration_sec
        current = telemetry.audio_current_time_sec
        if not telemetry.client_ended or not duration or current is None or current < duration * Decimal("0.95"):
            ratio = float(current / duration) if duration and current is not None else 0.0
            self.add_quality_flag(
                participant,
                assignment,
                "playback_incomplete",
                f"completion_ratio={ratio:.4f}",
            )
        if duration:
            hidden_limit_ms = min(10000, max(1, int(float(duration) * 100.0)))
            if telemetry.hidden_duration_ms > hidden_limit_ms:
                self.add_quality_flag(
                    participant,
                    assignment,
                    "playback_hidden_excessive",
                    f"hidden_ms={telemetry.hidden_duration_ms};limit_ms={hidden_limit_ms}",
                )

    def record_rating_submission(self, participant, assignment):
        telemetry = self.get_or_create_telemetry(participant, assignment)
        telemetry.rating_submitted_at = utcnow()
        if telemetry.rating_viewed_at:
            elapsed = telemetry.rating_submitted_at - telemetry.rating_viewed_at
            telemetry.rating_response_ms = max(0, int(elapsed.total_seconds() * 1000))
        if (
            self.should_show_attention_check(participant, assignment)
            and telemetry.rating_response_ms is not None
            and telemetry.rating_response_ms < 5000
        ):
            self.add_quality_flag(
                participant,
                assignment,
                "rating_too_fast",
                f"response_ms={telemetry.rating_response_ms}",
            )

    def save_attention_check(self, participant, assignment, actual_value):
        telemetry = self.get_or_create_telemetry(participant, assignment)
        expected_value = self.get_attention_check_expected_value(participant, assignment)
        submitted_at = utcnow()
        response_time_ms = None
        if telemetry.rating_viewed_at:
            response_time_ms = max(
                0,
                int((submitted_at - telemetry.rating_viewed_at).total_seconds() * 1000),
            )
        passed = actual_value == expected_value
        record = AttentionCheck.query.filter_by(assignment_id=assignment.id).first()
        record.actual_value = actual_value
        record.passed = passed
        record.submitted_at = submitted_at
        record.response_time_ms = response_time_ms
        if not passed:
            self.add_quality_flag(
                participant,
                assignment,
                "attention_check_failed",
                f"expected={expected_value};actual={actual_value if actual_value is not None else 'missing'}",
            )

    def refresh_straightlining_flag(self, participant):
        ratings = ImpressionRating.query.filter_by(
            participant_id=participant.participant_id,
            is_practice=False,
        ).all()
        if not ratings:
            return
        straight_count = sum(
            1
            for rating in ratings
            if len({getattr(rating, item["name"]) for item in SD_ITEMS}) == 1
        )
        ratio = straight_count / len(ratings)
        if ratio >= 0.80:
            self.add_quality_flag(
                participant,
                None,
                "rating_straightlining",
                f"ratio={ratio:.4f};trials={len(ratings)}",
            )

    @staticmethod
    def _safe_nonnegative_int(value):
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _safe_nonnegative_decimal(value):
        try:
            parsed = Decimal(str(value))
        except (TypeError, ValueError, ArithmeticError):
            return None
        return parsed if parsed >= 0 else None

    @staticmethod
    def add_quality_flag(participant, assignment, code, observed_value=None):
        query = QualityFlag.query.filter_by(
            participant_id=participant.id,
            code=code,
        )
        if assignment is None:
            flag = query.filter(QualityFlag.assignment_id.is_(None)).first()
        else:
            flag = query.filter_by(assignment_id=assignment.id).first()
        if flag is None:
            flag = QualityFlag(
                participant_id=participant.id,
                assignment_id=assignment.id if assignment else None,
                code=code,
            )
            db.session.add(flag)
        flag.observed_value = observed_value
