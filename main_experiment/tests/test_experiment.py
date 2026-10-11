import os
import re
import csv
import io
import tempfile
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app_factory import create_app
from constants import SD_ITEMS
from models import (
    AttentionCheck,
    ButtonPress,
    ImpressionRating,
    Participant,
    ParticipantCredential,
    ParticipantSongOrder,
    PressEvent,
    QualityFlag,
    Song,
    TrialTelemetry,
    db,
    utcnow,
)
from services import (
    AdminAnalyticsService,
    AudioCatalogService,
    CredentialService,
    CsvExportService,
    ExperimentService,
)


class ExperimentApplicationTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = os.path.join(self.temp_dir.name, "test.db")
        self.environment = patch.dict(
            os.environ,
            {
                "APP_ENV": "testing",
                "EXPERIMENT_DB_PATH": database_path,
                "SECRET_KEY": "test-secret",
                "WORKER_ID_PEPPER": "worker-pepper",
                "RESUME_CODE_SECRET": "resume-secret",
                "COMPLETION_CODE_SECRET": "completion-secret",
                "ADMIN_PASSWORD_HASH": generate_password_hash(
                    "admin-password", method="pbkdf2:sha256:1000"
                ),
            },
            clear=False,
        )
        self.environment.start()
        self.app = create_app()
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.credentials = CredentialService()
        self.service = ExperimentService(self.credentials)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        self.environment.stop()
        self.temp_dir.cleanup()

    def seed_main_songs(self, count=30):
        common_count = min(15, count)
        random_count = max(0, count - common_count)
        for index in range(1, common_count + 1):
            db.session.add(
                Song(
                    song_id=f"common_{index:02d}",
                    file_path=f"audio/common_{index:02d}.wav",
                    display_order=index,
                    is_practice=False,
                    is_common=True,
                    is_active=True,
                    duration_seconds=Decimal("32"),
                )
            )
        for index in range(1, random_count + 1):
            role = "train" if index <= 10 else "test"
            db.session.add(
                Song(
                    song_id=f"set1_{index:02d}",
                    file_path=f"audio/random_sets/1/{role}/set1_{index:02d}.wav",
                    display_order=index,
                    is_practice=False,
                    stimulus_set_id=1,
                    is_active=True,
                    duration_seconds=Decimal("32"),
                )
            )
        db.session.commit()

    def create_participant(self, worker_id="worker-001"):
        participant = Participant(
            participant_id=f"P{Participant.query.count() + 1:04d}",
            stimulus_set_id=1,
            consent_given=True,
            consented_at=utcnow(),
        )
        db.session.add(participant)
        db.session.flush()
        self.credentials.create_credential(participant, worker_id, "ABCDEFGH2345")
        db.session.commit()
        return participant

    def test_pre_4sec_segment_regression(self):
        cases = [
            ("2.500000", "0.000000", "4.000000", "4.000000"),
            ("4.000000", "0.000000", "4.000000", "4.000000"),
            ("8.250000", "4.250000", "8.250000", "4.000000"),
        ]
        for pressed, expected_start, expected_end, expected_duration in cases:
            segment = self.service.build_pre_4sec_segment(Decimal(pressed))
            self.assertEqual(segment["segment_start_sec"], Decimal(expected_start))
            self.assertEqual(segment["segment_end_sec"], Decimal(expected_end))
            self.assertEqual(
                segment["segment_duration_sec"],
                Decimal(expected_duration),
            )
            self.assertEqual(
                segment["segment_clipped_start"],
                Decimal(pressed) < Decimal("4.000000"),
            )
            if Decimal(pressed) >= Decimal("4.000000"):
                self.assertEqual(segment["segment_end_sec"], Decimal(pressed))

    def test_attention_trials_are_persisted_in_required_ranges(self):
        self.seed_main_songs()
        participant = self.create_participant()
        self.service.create_participant_song_order(participant)
        db.session.commit()
        self.assertIn(participant.attention_check_trial_1, range(8, 15))
        self.assertIn(participant.attention_check_trial_2, range(19, 26))

    def test_failed_attention_check_is_stored_separately_and_flagged(self):
        self.seed_main_songs()
        participant = self.create_participant()
        self.service.create_participant_song_order(participant)
        db.session.commit()
        assignment = [item for item in participant.assignments if not item.is_practice][7]
        participant.attention_check_trial_1 = 8
        telemetry = TrialTelemetry(
            participant_id=participant.id,
            assignment_id=assignment.id,
            rating_viewed_at=utcnow() - timedelta(seconds=8),
        )
        db.session.add(telemetry)
        db.session.commit()

        self.service.save_attention_check(participant, assignment, 6)
        db.session.commit()

        check = AttentionCheck.query.filter_by(assignment_id=assignment.id).one()
        self.assertEqual(check.actual_value, 6)
        self.assertFalse(check.passed)
        self.assertIsNotNone(
            QualityFlag.query.filter_by(
                participant_id=participant.id,
                assignment_id=assignment.id,
                code="attention_check_failed",
            ).first()
        )

    def test_wrong_attention_answer_does_not_block_progression(self):
        self.seed_main_songs()
        participant = self.create_participant()
        self.service.create_participant_song_order(participant)
        db.session.commit()
        assignment = [item for item in participant.assignments if not item.is_practice][7]
        participant.current_assignment_index = assignment.order_index
        participant.current_phase = "rating"
        participant.attention_check_trial_1 = 8
        self.service.record_rating_page_view(participant, assignment)

        next_phase = self.service.save_rating(
            participant,
            assignment,
            {item["name"]: (index % 7) + 1 for index, item in enumerate(SD_ITEMS)},
            attention_value=2,
        )

        self.assertEqual(next_phase, "playback")
        self.assertEqual(participant.current_assignment_index, assignment.order_index + 1)
        self.assertFalse(
            AttentionCheck.query.filter_by(assignment_id=assignment.id).one().passed
        )

    def test_worker_and_resume_values_are_hashed(self):
        participant = self.create_participant(worker_id="raw-worker-name")
        credential = ParticipantCredential.query.filter_by(
            participant_id=participant.id
        ).one()
        self.assertNotEqual(credential.worker_id_hash, "raw-worker-name")
        self.assertNotEqual(credential.resume_code_hash, "ABCDEFGH2345")
        self.assertEqual(len(credential.worker_id_hash), 64)

    def test_duplicate_worker_id_is_rejected(self):
        self.create_participant(worker_id="duplicate-worker")
        second = Participant(participant_id="PSECOND", consent_given=True)
        db.session.add(second)
        db.session.flush()
        with self.assertRaises(ValueError):
            self.credentials.create_credential(
                second,
                "duplicate-worker",
                "ABCDEFGH2345",
            )
        db.session.rollback()

    def test_completion_code_is_stable_and_requires_completion(self):
        participant = self.create_participant()
        with self.assertRaises(ValueError):
            self.credentials.issue_completion_code(participant)
        participant.current_phase = "complete"
        db.session.commit()
        first = self.credentials.issue_completion_code(participant)
        second = self.credentials.issue_completion_code(participant)
        self.assertEqual(first, second)
        self.assertRegex(first, r"^CW-[A-Z2-7]{10}$")

    def test_thirty_trial_csv_keeps_order_zero_press_trials_and_all_press_times(self):
        self.seed_main_songs()
        participant = self.create_participant()
        self.service.create_participant_song_order(participant)
        db.session.commit()
        assignments = ParticipantSongOrder.query.filter_by(
            participant_id=participant.id
        ).order_by(ParticipantSongOrder.order_index.asc()).all()
        self.assertEqual(len(assignments), 30)
        self.assertEqual(sum(1 for item in assignments if item.song.is_common), 15)
        self.assertEqual(
            sum(1 for item in assignments if item.song.stimulus_set_id == 1), 15
        )
        self.assertEqual(sum(item.song.random_song_role == "train" for item in assignments), 10)
        self.assertEqual(sum(item.song.random_song_role == "test" for item in assignments), 5)
        fixed_order = [item.song_id for item in assignments]
        db.session.expire_all()
        restored = ParticipantSongOrder.query.filter_by(
            participant_id=participant.id
        ).order_by(ParticipantSongOrder.order_index.asc()).all()
        self.assertEqual([item.song_id for item in restored], fixed_order)
        assignments = restored

        values = {item["name"]: 4 for item in SD_ITEMS}
        first = assignments[0]
        self.service.record_button_candidate(participant, first, Decimal("8.2"))
        self.service.record_button_candidate(participant, first, Decimal("15.6"))
        self.service.record_button_candidate(participant, first, Decimal("25.1"))
        first_events = PressEvent.query.filter_by(assignment_id=first.id).all()
        self.assertEqual([float(event.audio_time_sec) for event in first_events], [8.2, 15.6, 25.1])
        self.service.record_playback_progress(
            participant, first, Decimal("12.35"), Decimal("32")
        )
        self.service.record_playback_progress(
            participant, first, Decimal("10.0"), Decimal("32")
        )
        self.service.finish_playback(participant, first, {"client_ended": True})
        self.service.save_rating(participant, first, values)
        candidate = self.service.get_candidate_presses(participant, first.song, False)[1]
        self.service.select_candidate_press(participant, first, candidate.id, "test")
        for assignment in assignments[1:]:
            participant.current_assignment_index = assignment.order_index
            participant.current_phase = "rating"
            self.service.save_rating(participant, assignment, values)
        self.assertEqual(participant.current_phase, "complete")
        self.assertEqual(ImpressionRating.query.filter_by(
            participant_id=participant.participant_id,
            is_practice=False,
        ).count(), 30)

        rows = AdminAnalyticsService().build_flattened_export_rows(
            participants=[participant],
            button_presses=ButtonPress.query.all(),
            impression_ratings=ImpressionRating.query.all(),
        )
        self.assertEqual(len(rows), 30)
        self.assertEqual([row["trial_order"] for row in rows], list(range(1, 31)))
        self.assertEqual(rows[0]["press_time_sec_history"], "8.200000;15.600000;25.100000")
        self.assertEqual(rows[0]["selected_audio_time_sec"], "15.600000")
        self.assertEqual(rows[0]["selected_segment_start_sec"], "11.600000")
        self.assertEqual(rows[0]["playback_time_sec_audio_position"], "12.350000")
        self.assertEqual(rows[0]["audio_duration_sec"], "32.000000")
        self.assertEqual(rows[1]["press_count"], 0)
        self.assertEqual(rows[1]["like_dislike"], 4)

        response = CsvExportService(AdminAnalyticsService()).export_analysis_dataset()
        csv_rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
        self.assertEqual(len(csv_rows), 30)
        self.assertEqual(csv_rows[0]["trial_order"], "1")
        self.assertEqual(
            csv_rows[0]["press_time_sec_history"],
            "8.200000;15.600000;25.100000",
        )
        self.assertEqual(csv_rows[0]["selected_audio_time_sec"], "15.600000")
        self.assertEqual(csv_rows[1]["press_count"], "0")
        self.assertEqual(csv_rows[1]["like_dislike"], "4")
        self.assertEqual(sum(row["song_type"] == "common" for row in csv_rows), 15)
        self.assertEqual(sum(row["song_type"] == "random_train" for row in csv_rows), 10)
        self.assertEqual(sum(row["song_type"] == "random_test" for row in csv_rows), 5)

    def test_debugging_allows_random_songs_with_incomplete_split(self):
        self.seed_main_songs()
        song = Song.query.filter_by(song_id="set1_10").one()
        song.file_path = "audio/random_sets/1/test/set1_10.wav"
        db.session.commit()
        participant = self.create_participant()
        self.service.create_participant_song_order(participant)
        db.session.commit()
        self.assertEqual(len(participant.assignments), 30)
        self.assertEqual(sum(item.song.random_song_role == "train" for item in participant.assignments), 9)
        self.assertEqual(sum(item.song.random_song_role == "test" for item in participant.assignments), 6)

    def test_catalog_sync_and_assignment_keep_three_set_train_test_split(self):
        catalog = AudioCatalogService()
        audio_root = Path(self.temp_dir.name) / "audio"
        paths = [Path("common") / f"common_{index:02d}.wav" for index in range(15)]
        for set_id in (1, 2, 3):
            for role, count in (("train", 10), ("test", 5)):
                paths.extend(
                    Path("random_sets") / str(set_id) / role / f"song_{index:02d}.wav"
                    for index in range(count)
                )
        paths.extend([Path("practice/practice.wav"), Path("root.wav"), Path("random_sets/1/old.wav")])
        for relative_path in paths:
            catalog.write_sample_wave_file(audio_root / relative_path, 0.001, 440)
        with patch.object(catalog, "get_audio_root", return_value=audio_root):
            summary = catalog.sync_songs_from_static()
            self.assertEqual(summary["common_count"], 15)
            self.assertEqual(summary["random_train_count"], 30)
            self.assertEqual(summary["random_test_count"], 15)
            self.assertEqual(summary["active_count"], 61)
            self.assertEqual(summary["main_count"], 60)
            self.assertEqual(summary["stimulus_set_role_counts"], {
                str(set_id): {"train": 10, "test": 5} for set_id in (1, 2, 3)
            })
            # Re-sync keeps IDs and the same fixed stimulus classification.
            song_ids = {song.song_id: song.id for song in Song.query.all()}
            self.assertEqual(catalog.sync_songs_from_static(), summary)
            self.assertEqual({song.song_id: song.id for song in Song.query.all()}, song_ids)
        for set_id in (1, 2, 3):
            participant = Participant(participant_id=f"split-{set_id}", stimulus_set_id=set_id)
            db.session.add(participant)
            db.session.flush()
            self.service.create_participant_song_order(participant)
            db.session.commit()
            assignments = participant.assignments
            self.assertEqual(len(assignments), 31)  # Practice + 30 main trials.
            self.assertEqual(sum(item.song.is_common for item in assignments), 15)
            self.assertEqual(sum(item.song.random_song_role == "train" for item in assignments), 10)
            self.assertEqual(sum(item.song.random_song_role == "test" for item in assignments), 5)
            self.assertTrue(all(
                item.song.stimulus_set_id == set_id
                for item in assignments if item.song.random_song_role
            ))

    def test_debugging_allows_missing_random_test_song(self):
        self.seed_main_songs(count=29)
        participant = self.create_participant()
        self.service.create_participant_song_order(participant)
        db.session.commit()
        self.assertEqual(len(participant.assignments), 29)
        self.assertEqual(sum(item.song.random_song_role == "test" for item in participant.assignments), 4)

    def test_admin_shows_train_and_test_counts_per_set(self):
        self.seed_main_songs()
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["admin_authenticated"] = True
        response = client.get("/admin")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("ランダム学習 10 / 30 曲", html)
        self.assertIn("ランダムテスト 5 / 15 曲", html)
        self.assertIn("セット 1: 学習 10 / 10 曲・テスト 5 / 5 曲", html)
        self.assertIn("セット 2: 学習 0 / 10 曲・テスト 0 / 5 曲", html)

    def test_rating_page_only_shows_attention_item_for_target_trial(self):
        self.seed_main_songs()
        participant = self.create_participant()
        self.service.create_participant_song_order(participant)
        db.session.commit()
        participant.current_assignment_index = 0
        participant.current_phase = "rating"
        participant.attention_check_trial_1 = 1
        db.session.commit()
        assignment = participant.assignments[0]
        client = self.app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["participant_db_id"] = participant.id
        participant.attention_check_trial_1 = 8
        db.session.commit()
        normal_response = client.get(f"/experiment/rating/{assignment.id}")
        self.assertNotIn(
            "attention_check_value", normal_response.get_data(as_text=True)
        )
        participant.attention_check_trial_1 = 1
        db.session.commit()
        response = client.get(f"/experiment/rating/{assignment.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attention_check_value", response.get_data(as_text=True))

    def test_csv_formula_prefixes_are_neutralized(self):
        self.assertEqual(
            CsvExportService._sanitize_spreadsheet_cell("=SUM(A1:A2)"),
            "'=SUM(A1:A2)",
        )

    def test_security_headers_are_present(self):
        response = self.app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_participant_info_loads_after_instructions(self):
        client = self.app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["instructions_acknowledged"] = True
            flask_session["consent_agreed"] = True

        response = client.get("/participant-info")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("CloudWorksワーカーID", html)
        self.assertIn('<select id="stimulus_set_id" name="stimulus_set_id" required>', html)
        for set_id in (1, 2, 3):
            self.assertRegex(html, rf'<option value="{set_id}"\s*>{set_id}</option>')
        self.assertNotIn('name="stimulus_access_code"', html)
        with client.session_transaction() as flask_session:
            self.assertEqual(len(flask_session["pending_resume_code"]), 12)

    def test_dropdown_selection_starts_each_set_with_the_correct_songs(self):
        self.seed_main_songs()
        for set_id in (2, 3):
            for index in range(1, 16):
                role = "train" if index <= 10 else "test"
                db.session.add(Song(
                    song_id=f"set{set_id}_{index:02d}",
                    file_path=f"audio/random_sets/{set_id}/{role}/song_{index:02d}.wav",
                    is_practice=False,
                    is_common=False,
                    stimulus_set_id=set_id,
                    is_active=True,
                    duration_seconds=Decimal("32"),
                ))
        db.session.commit()
        for set_id in (1, 2, 3):
            with self.subTest(set_id=set_id):
                client = self.app.test_client()
                with client.session_transaction() as flask_session:
                    flask_session["instructions_acknowledged"] = True
                    flask_session["consent_agreed"] = True
                client.get("/participant-info")
                response = client.post("/start", data={
                    "stimulus_set_id": str(set_id),
                    "crowdworks_worker_id": f"dropdown-worker-{set_id}",
                    "music_experience": "no",
                    "listening_environment": "mac",
                    "experiment_browser": "chrome",
                    "listening_device": "speaker",
                })
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.location.endswith("/experiment/current"))
                with client.session_transaction() as flask_session:
                    participant = db.session.get(Participant, flask_session["participant_db_id"])
                self.assertEqual(participant.stimulus_set_id, set_id)
                self.assertEqual(len(participant.assignments), 30)
                self.assertEqual(sum(item.song.is_common for item in participant.assignments), 15)
                random_songs = [item.song for item in participant.assignments if not item.song.is_common]
                self.assertTrue(all(song.stimulus_set_id == set_id for song in random_songs))
                self.assertEqual(sum(song.random_song_role == "train" for song in random_songs), 10)
                self.assertEqual(sum(song.random_song_role == "test" for song in random_songs), 5)

    def test_start_rejects_missing_or_invalid_set_number(self):
        client = self.app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["instructions_acknowledged"] = True
            flask_session["consent_agreed"] = True
        for value in (None, "", "0", "4", "AB7KQ2", "1.0"):
            with self.subTest(value=value):
                data = {} if value is None else {"stimulus_set_id": value}
                response = client.post("/start", data=data)
                self.assertEqual(response.status_code, 200)
                self.assertIn("セット番号を1・2・3から選択してください。", response.get_data(as_text=True))
                self.assertEqual(Participant.query.count(), 0)

    def test_set_selection_is_preserved_after_form_validation_error(self):
        client = self.app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["instructions_acknowledged"] = True
            flask_session["consent_agreed"] = True
        response = client.post("/start", data={
            "stimulus_set_id": "3",
            "crowdworks_worker_id": "validation-worker",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('<option value="3" selected>3</option>', response.get_data(as_text=True))
        self.assertEqual(Participant.query.count(), 0)

    def test_debugging_starts_with_one_common_train_and_test_song(self):
        self.seed_main_songs(count=1)
        for set_id in (1, 2):
            for role in ("train", "test"):
                db.session.add(Song(
                    song_id=f"debug_set{set_id}_{role}",
                    file_path=f"audio/random_sets/{set_id}/{role}/debug.wav",
                    stimulus_set_id=set_id,
                    is_active=True,
                    is_practice=False,
                    is_common=False,
                ))
        db.session.commit()
        client = self.app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["instructions_acknowledged"] = True
            flask_session["consent_agreed"] = True
        client.get("/participant-info")
        response = client.post("/start", data={
            "stimulus_set_id": "1",
            "crowdworks_worker_id": "debug-worker",
            "music_experience": "no",
            "listening_environment": "mac",
            "experiment_browser": "chrome",
            "listening_device": "speaker",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/experiment/current"))
        participant = Participant.query.one()
        self.assertEqual(len(participant.assignments), 3)
        self.assertEqual(sum(item.song.is_common for item in participant.assignments), 1)
        self.assertEqual(sum(item.song.random_song_role == "train" for item in participant.assignments), 1)
        self.assertEqual(sum(item.song.random_song_role == "test" for item in participant.assignments), 1)
        self.assertTrue(all(item.song.stimulus_set_id in (None, 1) for item in participant.assignments))
        self.assertIsNone(participant.attention_check_trial_1)
        self.assertIsNone(participant.attention_check_trial_2)

    def test_post_without_csrf_is_rejected_when_protection_is_enabled(self):
        self.app.config["WTF_CSRF_ENABLED"] = True
        response = self.app.test_client().post(
            "/admin/login",
            data={"username": "admin", "password": "admin-password"},
        )
        self.assertEqual(response.status_code, 400)

    def test_playback_progress_api_saves_decimal_times_and_checks_duration(self):
        self.seed_main_songs()
        for payload_format in ("json", "form"):
            with self.subTest(payload_format=payload_format):
                participant = self.create_participant(worker_id=f"progress-{payload_format}")
                self.service.create_participant_song_order(participant)
                db.session.commit()
                assignment = participant.assignments[0]
                client = self.app.test_client()
                with client.session_transaction() as flask_session:
                    flask_session["participant_db_id"] = participant.id
                url = f"/api/trials/{assignment.id}/playback-progress"

                def save_progress(current_time):
                    payload = {
                        "audio_current_time_sec": current_time,
                        "audio_duration_sec": 32.0,
                    }
                    return client.post(url, **{("json" if payload_format == "json" else "data"): payload})

                response = save_progress(12.35)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.get_json()["ok"])
                telemetry = TrialTelemetry.query.filter_by(assignment_id=assignment.id).one()
                self.assertEqual(telemetry.audio_current_time_sec, Decimal("12.350000"))
                self.assertEqual(telemetry.audio_duration_sec, Decimal("32.000000"))

                self.assertEqual(save_progress(10.0).status_code, 200)
                db.session.refresh(telemetry)
                self.assertEqual(telemetry.audio_current_time_sec, Decimal("12.350000"))

                self.assertEqual(save_progress(32.25).status_code, 200)
                response = save_progress(32.250001)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.get_json()["ok"])
                self.assertIn("曲の長さを超えています", response.get_json()["message"])
                db.session.refresh(telemetry)
                self.assertEqual(telemetry.audio_current_time_sec, Decimal("32.250000"))

    def test_button_api_returns_json_for_missing_and_invalid_csrf(self):
        self.app.config["WTF_CSRF_ENABLED"] = True
        client = self.app.test_client()
        for headers in ({}, {"X-CSRFToken": "invalid-token"}):
            with self.subTest(headers=headers):
                response = client.post("/api/button-press", json={"audio_time_sec": 1}, headers=headers)
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.is_json)
                self.assertEqual(response.get_json()["code"], "csrf_error")
                self.assertIn("再読み込み", response.get_json()["message"])
        self.assertEqual(PressEvent.query.count(), 0)

    def test_button_api_saves_press_with_valid_csrf(self):
        self.seed_main_songs()
        participant = self.create_participant()
        self.service.create_participant_song_order(participant)
        db.session.commit()
        assignment = participant.assignments[0]
        self.app.config["WTF_CSRF_ENABLED"] = True
        client = self.app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["participant_db_id"] = participant.id
        page = client.get("/").get_data(as_text=True)
        token = re.search(r'<meta name="csrf-token" content="([^"]+)"', page).group(1)
        response = client.post("/api/button-press", json={
            "assignment_id": assignment.id, "audio_time_sec": 3.3,
            "performance_time_ms": 5000, "client_timestamp": "2026-10-11T08:00:00.000Z",
        }, headers={"X-CSRFToken": token})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(PressEvent.query.count(), 1)

    def test_api_http_errors_return_json_and_keep_allow_header(self):
        client = self.app.test_client()
        response = client.get("/api/nonexistent")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.get_json()["ok"])
        response = client.get("/api/button-press")
        self.assertEqual(response.status_code, 405)
        self.assertFalse(response.get_json()["ok"])
        self.assertIn("POST", response.headers["Allow"])

    def test_button_api_internal_error_returns_json_without_private_details(self):
        self.seed_main_songs()
        participant = self.create_participant()
        self.service.create_participant_song_order(participant)
        db.session.commit()
        client = self.app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["participant_db_id"] = participant.id
        self.app.config["PROPAGATE_EXCEPTIONS"] = False
        with patch.object(ExperimentService, "record_button_candidate", side_effect=RuntimeError("private SQL diagnostic")):
            with self.assertLogs(self.app.logger, level="ERROR") as logs:
                response = client.post("/api/button-press", json={
                    "assignment_id": participant.assignments[0].id, "audio_time_sec": 3.3,
                })
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["code"], "server_error")
        self.assertNotIn("private SQL diagnostic", response.get_data(as_text=True))
        self.assertTrue(any("private SQL diagnostic" in log for log in logs.output))

    def test_instructions_post_accepts_valid_csrf_token(self):
        self.app.config["WTF_CSRF_ENABLED"] = True
        client = self.app.test_client()
        page = client.get("/experiment/instructions")
        token_match = re.search(
            r'name="csrf_token" value="([^"]+)"',
            page.get_data(as_text=True),
        )
        self.assertIsNotNone(token_match)

        response = client.post(
            "/experiment/instructions",
            data={
                "csrf_token": token_match.group(1),
                "instruction_acknowledged": "yes",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/participant-info"))

    def test_admin_completion_code_verification_detects_duplicate(self):
        participant = self.create_participant()
        participant.current_phase = "complete"
        db.session.commit()
        code = self.credentials.issue_completion_code(participant)
        client = self.app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["admin_authenticated"] = True
        first = client.post(
            "/admin/completion-codes/verify",
            data={"completion_codes": code},
        )
        second = client.post(
            "/admin/completion-codes/verify",
            data={"completion_codes": code},
        )
        self.assertIn(">valid<", first.get_data(as_text=True))
        self.assertIn(">duplicate<", second.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
