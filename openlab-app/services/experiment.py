from decimal import Decimal
import json
import random
import secrets

from flask import current_app, session

from constants import SD_ITEMS
from models import (
    ButtonPress,
    ButtonPressCandidate,
    ImpressionRating,
    Participant,
    ParticipantSongOrder,
    PressEvent,
    Song,
    db,
    utcnow,
)


class ExperimentService:
    """実験進行、参加者状態、押下位置の確定を担当する。"""

    SEGMENT_RULE = "post_4sec"
    SEGMENT_DURATION_SEC = Decimal("4.000000")

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
    ):
        participant = Participant.query.filter_by(participant_id=participant_code).first()
        created = False

        if participant is None:
            participant = Participant(
                participant_id=participant_code,
                participant_group=current_app.config["PARTICIPANT_GROUP"],
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

        rng = random.SystemRandom()
        if not practice_songs:
            raise ValueError("OpenLab 用の練習曲がありません。static/audio/practice/ に1曲配置してください。")
        expected_pool_size = current_app.config["OPENLAB_STIMULUS_POOL_SIZE"]
        if len(main_songs) != expected_pool_size:
            raise ValueError(
                f"OpenLab 本実験には有効な本番曲がちょうど{expected_pool_size}曲必要です。"
            )

        practice_song = rng.choice(practice_songs)
        stimulus_set, main_order = self._select_balanced_song_set(main_songs, rng)
        rng.shuffle(main_order)
        combined_order = [practice_song] + main_order
        for index, song in enumerate(combined_order):
            db.session.add(
                ParticipantSongOrder(
                    participant_id=participant.id,
                    song_id=song.id,
                    order_index=index,
                    presentation_order=None if song.is_practice else index,
                    stimulus_set=None if song.is_practice else stimulus_set,
                    is_practice=song.is_practice,
                )
            )

    def _select_balanced_song_set(self, main_songs, rng):
        """表示順の15曲を5曲ずつ3セットに分け、割当人数が少ないセットを選ぶ。"""
        set_size = current_app.config["OPENLAB_STIMULUS_SET_SIZE"]
        song_sets = [
            (f"set_{index // set_size + 1}", main_songs[index : index + set_size])
            for index in range(0, len(main_songs), set_size)
        ]
        rng.shuffle(song_sets)
        return min(song_sets, key=lambda item: self._song_set_assignment_count(item[1]))

    @staticmethod
    def _song_set_assignment_count(songs):
        song_database_ids = [song.id for song in songs]
        return (
            ParticipantSongOrder.query.join(
                Participant, ParticipantSongOrder.participant_id == Participant.id
            )
            .filter(
                ParticipantSongOrder.song_id.in_(song_database_ids),
                ParticipantSongOrder.is_practice.is_(False),
                Participant.participant_group == current_app.config["PARTICIPANT_GROUP"],
            )
            .with_entities(ParticipantSongOrder.participant_id)
            .distinct()
            .count()
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
        audio_duration_sec=None,
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
            audio_duration_sec=audio_duration_sec,
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
        audio_duration_sec=None,
    ):
        segment = self.build_post_4sec_segment(audio_time_sec, audio_duration_sec)
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
            segment_clipped_end=segment["segment_clipped_end"],
            audio_duration_sec=segment["audio_duration_sec"],
            is_selected=False,
            created_at=server_received_at,
        )
        db.session.add(press_event)
        db.session.flush()
        return press_event

    @classmethod
    def build_post_4sec_segment(cls, audio_time_sec, audio_duration_sec=None):
        """押下位置を開始点とし、曲末では利用可能な長さまでに切り詰める。"""
        audio_time_sec = Decimal(audio_time_sec).quantize(Decimal("0.000001"))
        duration = (
            Decimal(audio_duration_sec).quantize(Decimal("0.000001"))
            if audio_duration_sec is not None
            else None
        )
        segment_start_sec = max(Decimal("0.000000"), audio_time_sec)
        if duration is not None:
            duration = max(duration, segment_start_sec)
        desired_end = segment_start_sec + cls.SEGMENT_DURATION_SEC
        segment_end_sec = min(desired_end, duration) if duration is not None else desired_end
        return {
            "audio_time_sec": audio_time_sec,
            "segment_rule": cls.SEGMENT_RULE,
            "segment_start_sec": segment_start_sec,
            "segment_end_sec": segment_end_sec,
            "segment_duration_sec": segment_end_sec - segment_start_sec,
            "segment_clipped_start": audio_time_sec < 0,
            "segment_clipped_end": segment_end_sec < desired_end,
            "audio_duration_sec": duration,
        }

    # 既存コードから呼ばれた場合の後方互換用。
    build_pre_4sec_segment = build_post_4sec_segment

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
        ordered = sorted(records, key=lambda record: getattr(record, index_attribute))
        return json.dumps(
            [float(getattr(record, time_attribute)) for record in ordered],
            ensure_ascii=False,
        )

    def finish_playback(self, participant, assignment):
        self._refresh_assignment_press_summary(participant, assignment)
        participant.current_phase = "selection" if assignment.press_count > 0 else "rating"
        db.session.commit()
        return participant.current_phase

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
        participant.current_phase = "rating"
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
            return self.build_post_4sec_segment(candidate.pressed_time)

        return {
            "audio_time_sec": press_event.audio_time_sec,
            "segment_rule": press_event.segment_rule,
            "segment_start_sec": press_event.segment_start_sec,
            "segment_end_sec": press_event.segment_end_sec,
            "segment_duration_sec": press_event.segment_duration_sec,
            "segment_clipped_start": press_event.segment_clipped_start,
            "segment_clipped_end": press_event.segment_clipped_end,
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

    def save_rating(self, participant, assignment, values):
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

        self._refresh_assignment_press_summary(participant, assignment)
        self.advance_to_next_assignment(participant)
        db.session.commit()
        return participant.current_phase

    def advance_to_next_assignment(self, participant):
        completed_assignment = self.get_current_assignment(participant)
        participant.current_assignment_index += 1
        next_assignment = self.get_current_assignment(participant)
        if next_assignment is None:
            participant.current_phase = "complete"
            completed_main_count = (
                ImpressionRating.query.filter_by(
                    participant_id=participant.participant_id,
                    is_practice=False,
                ).count()
            )
            participant.experiment_completed = (
                completed_main_count == current_app.config["OPENLAB_MAIN_SONG_COUNT"]
            )
            participant.completed_at = utcnow() if participant.experiment_completed else None
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
