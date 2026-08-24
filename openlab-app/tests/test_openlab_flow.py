import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from flask import Flask, render_template
from werkzeug.datastructures import MultiDict

from models import ButtonPress, ImpressionRating, Participant, Song, db
from services.experiment import ExperimentService
from services.admin_analytics import AdminAnalyticsService
from services.csv_export import CsvExportService
from services.preference_profile import PreferenceProfileService
from validators import FormValidator


RATING_VALUES = {
    "bright_dark": 2,
    "smooth_rough": 3,
    "rich_thin": 4,
    "clear_muddy": 3,
    "intense_calm": 5,
    "heavy_light": 4,
    "soft_hard": 3,
    "thick_thin": 4,
    "like_dislike": 2,
}


class OpenLabFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = Flask(
            __name__,
            template_folder=str(Path(__file__).resolve().parents[1] / "templates"),
        )
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI=f"sqlite:///{Path(self.temp_dir.name) / 'test.db'}",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SECRET_KEY="test-secret",
            BUTTON_PRESS_MODE="all",
            PARTICIPANT_GROUP="highschool_openlab",
            OPENLAB_MAIN_SONG_COUNT=5,
            OPENLAB_STIMULUS_POOL_SIZE=15,
            OPENLAB_STIMULUS_SET_SIZE=5,
            AUDIO_FEATURES_PATH=str(Path(self.temp_dir.name) / "missing-features.csv"),
        )
        self.app.add_url_rule("/", endpoint="index", view_func=lambda: "")
        self.app.add_url_rule(
            "/instructions", endpoint="experiment_instructions", view_func=lambda: ""
        )
        self.app.add_url_rule(
            "/participant", endpoint="participant_info", view_func=lambda: ""
        )
        self.app.add_url_rule("/admin", endpoint="admin", view_func=lambda: "")
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        db.session.add(Song(song_id="practice_01", file_path="audio/practice/p.wav", is_practice=True))
        for index in range(1, 16):
            db.session.add(
                Song(
                    song_id=f"main_{index:02d}",
                    file_path=f"audio/main_{index:02d}.wav",
                    display_order=index,
                    is_practice=False,
                )
            )
        db.session.commit()
        self.service = ExperimentService()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        self.temp_dir.cleanup()

    def create_participant(self, code="P001"):
        participant = Participant(
            participant_id=code,
            participant_group="highschool_openlab",
            consent_given=True,
        )
        db.session.add(participant)
        db.session.flush()
        self.service.create_participant_song_order(participant)
        db.session.commit()
        return participant

    def test_other_listening_choices_need_no_free_text(self):
        values = FormValidator().validate_participant_form(
            MultiDict(
                {
                    "music_experience": "no",
                    "listening_environment": "other",
                    "experiment_browser": "other",
                    "listening_device": "other",
                    "consent_agreed": "yes",
                    "listening_environment_note": "ignored",
                    "experiment_browser_note": "ignored",
                    "listening_device_note": "ignored",
                }
            )
        )

        self.assertEqual([], values[-1])
        self.assertEqual(("", "", ""), (values[6], values[8], values[10]))

    def test_selection_requires_choices_and_ignores_free_text(self):
        validator = FormValidator()
        note_only = validator.validate_selection_form(
            MultiDict({"selection_reason_note": "free text is no longer accepted"})
        )
        selected = validator.validate_selection_form(
            MultiDict([("selection_reason_choices", "melody")])
        )

        self.assertTrue(note_only["errors"])
        self.assertEqual("", note_only["note"])
        self.assertEqual([], selected["errors"])
        self.assertEqual("", selected["note"])
        self.assertEqual("選択理由: メロディが心地よかった", selected["serialized_reason"])

    def test_assignment_is_one_practice_plus_randomized_five_main(self):
        participant = self.create_participant()
        assignments = participant.assignments
        practice = [item for item in assignments if item.is_practice]
        main = [item for item in assignments if not item.is_practice]

        self.assertEqual(1, len(practice))
        self.assertEqual(5, len(main))
        self.assertEqual([1, 2, 3, 4, 5], sorted(item.presentation_order for item in main))
        self.assertEqual(1, len({item.stimulus_set for item in main}))
        assigned_ids = {item.song.song_id for item in main}
        valid_sets = [
            {f"main_{index:02d}" for index in range(start, start + 5)}
            for start in (1, 6, 11)
        ]
        self.assertIn(assigned_ids, valid_sets)

    def test_first_three_participants_are_distributed_across_three_sets(self):
        participants = [self.create_participant(code=f"P{index:03d}") for index in range(3)]
        assigned_sets = {
            next(item.stimulus_set for item in participant.assignments if not item.is_practice)
            for participant in participants
        }
        self.assertEqual({"set_1", "set_2", "set_3"}, assigned_sets)

    def test_assignment_rejects_a_pool_that_is_not_exactly_fifteen_songs(self):
        Song.query.filter_by(song_id="main_15").one().is_active = False
        participant = Participant(
            participant_id="P_BAD_POOL",
            participant_group="highschool_openlab",
        )
        db.session.add(participant)
        db.session.flush()

        with self.assertRaisesRegex(ValueError, "ちょうど15曲"):
            self.service.create_participant_song_order(participant)

    def test_zero_press_skips_selection_and_saves_empty_array(self):
        participant = self.create_participant()
        assignment = self.service.get_current_assignment(participant)

        self.assertEqual("rating", self.service.finish_playback(participant, assignment))
        self.assertEqual(0, assignment.press_count)
        self.assertEqual([], json.loads(assignment.all_press_audio_times))

        self.service.save_rating(participant, assignment, RATING_VALUES)
        self.assertEqual("volume_check", participant.current_phase)
        self.assertIsNone(assignment.selected_press_event_id)

    def test_multiple_presses_are_saved_and_selection_precedes_rating(self):
        participant = self.create_participant()
        assignment = self.service.get_current_assignment(participant)
        candidates = []
        for time_sec in (5.2, 13.8, 31.0):
            event, recorded = self.service.record_button_candidate(
                participant,
                assignment,
                time_sec,
                audio_duration_sec=32.0,
            )
            self.assertTrue(recorded)
            candidates.append(event)

        self.assertEqual("selection", self.service.finish_playback(participant, assignment))
        self.assertEqual([5.2, 13.8, 31.0], json.loads(assignment.all_press_audio_times))
        self.assertEqual(31.0, float(candidates[-1].segment_start_sec))
        self.assertEqual(32.0, float(candidates[-1].segment_end_sec))
        self.assertTrue(candidates[-1].segment_clipped_end)

        candidate = self.service.get_candidate_presses(
            participant, assignment.song, assignment.is_practice
        )[1]
        self.assertTrue(
            self.service.select_candidate_press(
                participant, assignment, candidate.id, "選択理由: メロディ"
            )
        )
        self.assertEqual("rating", participant.current_phase)
        selected = ButtonPress.query.filter_by(assignment_id=assignment.id).one()
        self.assertEqual(13.8, float(selected.selected_segment_start_sec))
        self.assertEqual(17.8, float(selected.selected_segment_end_sec))

        with self.app.test_request_context():
            csv_text = CsvExportService(AdminAnalyticsService()).export_press_events().get_data(
                as_text=True
            )
        self.assertIn("presentation_order", csv_text.splitlines()[0])
        self.assertIn("audio_duration_sec", csv_text.splitlines()[0])

    def test_completion_flag_and_profile_only_after_five_main_ratings(self):
        participant = self.create_participant()
        main_assignments = [item for item in participant.assignments if not item.is_practice]
        for assignment in main_assignments[:-1]:
            db.session.add(
                ImpressionRating(
                    participant_id=participant.participant_id,
                    song_id=assignment.song.song_id,
                    is_practice=False,
                    **RATING_VALUES,
                )
            )
        participant.current_assignment_index = main_assignments[-1].order_index
        participant.current_phase = "rating"
        db.session.commit()

        with self.assertRaises(ValueError):
            PreferenceProfileService().generate(participant)

        self.service.save_rating(participant, main_assignments[-1], RATING_VALUES)
        self.assertEqual("complete", participant.current_phase)
        self.assertTrue(participant.experiment_completed)
        self.assertIsNotNone(participant.completed_at)
        profile = PreferenceProfileService().generate(participant)
        self.assertFalse(profile["is_fallback"])

        with self.app.test_request_context():
            exporter = CsvExportService(AdminAnalyticsService())
            participants_csv = exporter.export_participants().get_data(as_text=True)
            analysis_csv = exporter.export_analysis_dataset().get_data(as_text=True)
        self.assertIn("participant_group", participants_csv.splitlines()[0])
        self.assertIn("experiment_completed", analysis_csv.splitlines()[0])
        self.assertIn("presentation_order", analysis_csv.splitlines()[0])

    def test_profile_uses_selected_windows_and_renders_five_traits(self):
        participant = self.create_participant()
        main_assignments = [item for item in participant.assignments if not item.is_practice]
        for assignment in main_assignments:
            db.session.add(
                ImpressionRating(
                    participant_id=participant.participant_id,
                    song_id=assignment.song.song_id,
                    is_practice=False,
                    **RATING_VALUES,
                )
            )
        participant.experiment_completed = True
        for assignment in main_assignments[:2]:
            db.session.add(
                ButtonPress(
                    participant_id=participant.participant_id,
                    song_id=assignment.song.song_id,
                    assignment_id=assignment.id,
                    is_practice=False,
                    press_order=1,
                    pressed_time=4.0,
                    selected_audio_time_sec=4.0,
                    selected_segment_rule="post_4sec",
                    selected_segment_start_sec=4.0,
                    selected_segment_end_sec=8.0,
                    selected_segment_duration_sec=4.0,
                )
            )
        db.session.commit()

        feature_path = Path(self.temp_dir.name) / "features.csv"
        fieldnames = [
            "song_id", "window_start", "window_end", "rms",
            "low_peaks", "middle_peaks", "high_peaks", "super_high_peaks",
            "spectral_centroids", "spectral_rolloff", "spectral_bandwidth",
            *[f"chroma_{index}" for index in range(1, 13)],
        ]
        with feature_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for index in range(1, 16):
                song_id = f"main_{index:02d}"
                row = {
                    "song_id": song_id,
                    "window_start": 4.0,
                    "window_end": 8.0,
                    "rms": index,
                    "low_peaks": index,
                    "middle_peaks": index * 2,
                    "high_peaks": index * 3,
                    "super_high_peaks": index * 4,
                    "spectral_centroids": index * 100,
                    "spectral_rolloff": index * 200,
                    "spectral_bandwidth": index * 50,
                }
                row.update(
                    {
                        f"chroma_{chroma_index}": (
                            index if chroma_index == 1 else 1.0
                        )
                        for chroma_index in range(1, 13)
                    }
                )
                writer.writerow(row)
        self.app.config["AUDIO_FEATURES_PATH"] = str(feature_path)

        profile = PreferenceProfileService().generate(participant)
        self.assertTrue(profile["acoustic_available"])
        self.assertEqual(2, profile["selected_segment_count"])
        self.assertNotIn("recommendations", profile)
        self.assertEqual(5, len(profile["trait_cards"]))
        self.assertEqual(
            ["energy", "rhythm", "brightness", "spread", "harmony"],
            [trait["key"] for trait in profile["trait_cards"]],
        )
        self.assertTrue(all(0 <= trait["score"] <= 100 for trait in profile["trait_cards"]))
        self.assertIn("あなたが惹かれやすいのは", profile["title"])
        with self.app.test_request_context():
            html = render_template(
                "complete.html",
                participant=participant,
                profile=profile,
                total_trials=6,
                button_press_count=2,
                rating_count=6,
            )
        self.assertIn("好きになりやすい音の特徴", html)
        self.assertIn("リズムの動き", html)
        for trait_key in ("energy", "rhythm", "brightness", "spread", "harmony"):
            self.assertIn(f"trait-{trait_key}", html)
        self.assertIn("スコアが34未満", html)
        self.assertNotIn("次に聴いてみてほしい曲", html)

    def test_nearest_window_uses_last_full_window_near_track_end(self):
        rows = [
            {"song_id": "main_01", "window_start": 27.9},
            {"song_id": "main_01", "window_start": 28.0},
        ]
        selections = [
            SimpleNamespace(song_id="main_01", selected_segment_start_sec=31.0)
        ]

        matched = PreferenceProfileService._nearest_rows_for_selections(rows, selections)

        self.assertEqual(28.0, matched[0]["window_start"])

    def test_profile_without_selection_uses_non_destructive_empty_state(self):
        participant = self.create_participant()
        for assignment in [item for item in participant.assignments if not item.is_practice]:
            db.session.add(
                ImpressionRating(
                    participant_id=participant.participant_id,
                    song_id=assignment.song.song_id,
                    is_practice=False,
                    **RATING_VALUES,
                )
            )
        participant.experiment_completed = True
        db.session.commit()
        feature_path = Path(self.temp_dir.name) / "features.csv"
        feature_path.touch()
        self.app.config["AUDIO_FEATURES_PATH"] = str(feature_path)
        service = PreferenceProfileService()
        service._load_feature_dataset = lambda path: ([{}], {})

        profile = service.generate(participant)

        self.assertFalse(profile["acoustic_available"])
        self.assertIn("最終選択がなかった", profile["acoustic_message"])
        self.assertEqual(5, ImpressionRating.query.filter_by(is_practice=False).count())

    def test_broken_feature_csv_falls_back_without_changing_answers(self):
        participant = self.create_participant()
        for assignment in [item for item in participant.assignments if not item.is_practice]:
            db.session.add(
                ImpressionRating(
                    participant_id=participant.participant_id,
                    song_id=assignment.song.song_id,
                    is_practice=False,
                    **RATING_VALUES,
                )
            )
        participant.experiment_completed = True
        db.session.commit()
        feature_path = Path(self.temp_dir.name) / "broken.csv"
        feature_path.write_text("song_id,window_start\nmain_01,0\n", encoding="utf-8")
        self.app.config["AUDIO_FEATURES_PATH"] = str(feature_path)

        profile = PreferenceProfileService().generate(participant)

        self.assertFalse(profile["acoustic_available"])
        self.assertIn("読み込めなかった", profile["acoustic_message"])
        self.assertEqual(5, ImpressionRating.query.filter_by(is_practice=False).count())


if __name__ == "__main__":
    unittest.main()
