import os
import re
import tempfile
import unittest
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app_factory import create_app
from constants import SD_ITEMS
from models import (
    AttentionCheck,
    Participant,
    ParticipantCredential,
    QualityFlag,
    Song,
    TrialTelemetry,
    db,
    utcnow,
)
from services import CredentialService, CsvExportService, ExperimentService


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
        for index in range(1, count + 1):
            db.session.add(
                Song(
                    song_id=f"main_{index:02d}",
                    file_path=f"audio/main_{index:02d}.wav",
                    display_order=index,
                    is_practice=False,
                    is_active=True,
                )
            )
        db.session.commit()

    def create_participant(self, worker_id="worker-001"):
        participant = Participant(
            participant_id=f"P{Participant.query.count() + 1:04d}",
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
            ("2.500000", "0.000000", "2.500000", "2.500000"),
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
        self.assertIn("CloudWorksワーカーID", response.get_data(as_text=True))
        with client.session_transaction() as flask_session:
            self.assertEqual(len(flask_session["pending_resume_code"]), 12)

    def test_post_without_csrf_is_rejected_when_protection_is_enabled(self):
        self.app.config["WTF_CSRF_ENABLED"] = True
        response = self.app.test_client().post(
            "/admin/login",
            data={"username": "admin", "password": "admin-password"},
        )
        self.assertEqual(response.status_code, 400)

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
