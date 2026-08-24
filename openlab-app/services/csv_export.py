import csv
import io

from flask import make_response

from constants import (
    EXPERIMENT_BROWSER_LABELS,
    GENDER_LABELS,
    LISTENING_DEVICE_LABELS,
    LISTENING_ENVIRONMENT_LABELS,
    MUSIC_EXPERIENCE_LABELS,
    MUSIC_EXPERIENCE_TYPE_LABELS,
    SD_ITEMS,
    VOLUME_IMPRESSION_LABELS,
)
from models import ButtonPress, ImpressionRating, Participant, PressEvent


class CsvExportService:
    """CSV ダウンロード用レスポンスを生成する。"""

    def __init__(self, analytics_service):
        self.analytics_service = analytics_service

    def export_participants(self):
        rows = [
            {
                "id": participant.id,
                "participant_id": participant.participant_id,
                "participant_group": participant.participant_group,
                "cohort_id": participant.cohort_id,
                "experiment_completed": participant.experiment_completed,
                "completed_at": self._format_datetime(participant.completed_at),
                "age": participant.age if participant.age is not None else "",
                "gender": GENDER_LABELS.get(participant.gender, participant.gender or ""),
                "music_experience": MUSIC_EXPERIENCE_LABELS.get(
                    participant.music_experience,
                    participant.music_experience or "",
                ),
                "music_experience_years": (
                    participant.music_experience_years
                    if participant.music_experience_years is not None
                    else ""
                ),
                "music_experience_type": self._format_music_experience_type(
                    participant.music_experience_type
                ),
                "listening_environment": LISTENING_ENVIRONMENT_LABELS.get(
                    participant.listening_environment,
                    participant.listening_environment or "",
                ),
                "listening_environment_note": (
                    participant.listening_environment_note or ""
                ),
                "experiment_browser": EXPERIMENT_BROWSER_LABELS.get(
                    participant.experiment_browser,
                    participant.experiment_browser or "",
                ),
                "experiment_browser_note": participant.experiment_browser_note or "",
                "listening_device": LISTENING_DEVICE_LABELS.get(
                    participant.listening_device,
                    participant.listening_device or "",
                ),
                "listening_device_note": participant.listening_device_note or "",
                "practice_volume_impression": VOLUME_IMPRESSION_LABELS.get(
                    participant.practice_volume_impression,
                    participant.practice_volume_impression or "",
                ),
                "practice_volume_level": (
                    participant.practice_volume_level
                    if participant.practice_volume_level is not None
                    else ""
                ),
                "practice_volume_confirmed_at": (
                    participant.practice_volume_confirmed_at.isoformat(
                        sep=" ",
                        timespec="seconds",
                    )
                    if participant.practice_volume_confirmed_at
                    else ""
                ),
                "consent_given": "yes" if participant.consent_given else "no",
                "consented_at": (
                    participant.consented_at.isoformat(sep=" ", timespec="seconds")
                    if participant.consented_at
                    else ""
                ),
                "current_assignment_index": participant.current_assignment_index,
                "current_phase": participant.current_phase,
                "created_at": participant.created_at.isoformat(
                    sep=" ", timespec="seconds"
                ),
            }
            for participant in Participant.query.order_by(Participant.created_at.asc()).all()
        ]

        return self._build_response(
            "participants.csv",
            [
                "id",
                "participant_id",
                "participant_group",
                "cohort_id",
                "experiment_completed",
                "completed_at",
                "age",
                "gender",
                "music_experience",
                "music_experience_years",
                "music_experience_type",
                "listening_environment",
                "listening_environment_note",
                "experiment_browser",
                "experiment_browser_note",
                "listening_device",
                "listening_device_note",
                "practice_volume_impression",
                "practice_volume_level",
                "practice_volume_confirmed_at",
                "consent_given",
                "consented_at",
                "current_assignment_index",
                "current_phase",
                "created_at",
            ],
            rows,
        )

    def export_button_presses(self):
        rows = [
            {
                "id": record.id,
                "participant_id": record.participant.participant_id,
                "song_id": record.song.song_id,
                "is_practice": record.is_practice,
                "assignment_id": record.assignment_id or "",
                "selected_press_id": record.press_event_id or "",
                "press_order": record.press_order,
                "pressed_time": self._format_decimal(record.pressed_time),
                "selected_audio_time_sec": self._format_decimal(
                    record.selected_audio_time_sec
                ),
                "selected_segment_rule": record.selected_segment_rule or "",
                "selected_segment_start_sec": self._format_decimal(
                    record.selected_segment_start_sec
                ),
                "selected_segment_end_sec": self._format_decimal(
                    record.selected_segment_end_sec
                ),
                "selected_segment_duration_sec": self._format_decimal(
                    record.selected_segment_duration_sec
                ),
                "selection_reason": record.selection_reason or "",
                "created_at": record.created_at.isoformat(sep=" ", timespec="seconds"),
            }
            for record in ButtonPress.query.order_by(ButtonPress.created_at.asc()).all()
        ]

        return self._build_response(
            "button_presses.csv",
            [
                "id",
                "participant_id",
                "song_id",
                "is_practice",
                "assignment_id",
                "selected_press_id",
                "press_order",
                "pressed_time",
                "selected_audio_time_sec",
                "selected_segment_rule",
                "selected_segment_start_sec",
                "selected_segment_end_sec",
                "selected_segment_duration_sec",
                "selection_reason",
                "created_at",
            ],
            rows,
        )

    def export_press_events(self):
        rows = []
        for record in PressEvent.query.order_by(
            PressEvent.server_received_at.asc(),
            PressEvent.id.asc(),
        ).all():
            assignment = record.assignment
            rows.append(
                {
                    "press_id": record.id,
                    "assignment_id": record.assignment_id or "",
                    "participant_id": record.participant_id,
                    "song_id": record.song_id,
                    "trial_index": (
                        assignment.order_index + 1 if assignment is not None else ""
                    ),
                    "is_practice": record.is_practice,
                    "stimulus_set": assignment.stimulus_set if assignment is not None else "",
                    "presentation_order": (
                        assignment.presentation_order if assignment is not None else ""
                    ),
                    "press_index": record.press_index,
                    "audio_time_sec": self._format_decimal(record.audio_time_sec),
                    "performance_time_ms": self._format_decimal(
                        record.performance_time_ms
                    ),
                    "client_timestamp": record.client_timestamp or "",
                    "server_received_at": self._format_datetime(record.server_received_at),
                    "segment_rule": record.segment_rule,
                    "segment_start_sec": self._format_decimal(record.segment_start_sec),
                    "segment_end_sec": self._format_decimal(record.segment_end_sec),
                    "segment_duration_sec": self._format_decimal(
                        record.segment_duration_sec
                    ),
                    "segment_clipped_start": (
                        "yes" if record.segment_clipped_start else "no"
                    ),
                    "segment_clipped_end": "yes" if record.segment_clipped_end else "no",
                    "audio_duration_sec": self._format_decimal(record.audio_duration_sec),
                    "is_selected": "yes" if record.is_selected else "no",
                    "quality_flags": assignment.quality_flags if assignment is not None else "",
                }
            )

        return self._build_response(
            "press_events.csv",
            [
                "press_id",
                "assignment_id",
                "participant_id",
                "song_id",
                "trial_index",
                "is_practice",
                "stimulus_set",
                "presentation_order",
                "press_index",
                "audio_time_sec",
                "performance_time_ms",
                "client_timestamp",
                "server_received_at",
                "segment_rule",
                "segment_start_sec",
                "segment_end_sec",
                "segment_duration_sec",
                "segment_clipped_start",
                "segment_clipped_end",
                "audio_duration_sec",
                "is_selected",
                "quality_flags",
            ],
            rows,
        )

    def export_impression_ratings(self):
        rows = []
        for record in ImpressionRating.query.order_by(ImpressionRating.created_at.asc()).all():
            assignment = next(
                (
                    item
                    for item in record.participant.assignments
                    if item.song.song_id == record.song_id
                    and item.is_practice == record.is_practice
                ),
                None,
            )
            row = {
                "id": record.id,
                "participant_id": record.participant.participant_id,
                "participant_group": record.participant.participant_group,
                "cohort_id": record.participant.cohort_id,
                "experiment_completed": record.participant.experiment_completed,
                "song_id": record.song.song_id,
                "is_practice": record.is_practice,
                "stimulus_set": assignment.stimulus_set if assignment is not None else "",
                "presentation_order": (
                    assignment.presentation_order if assignment is not None else ""
                ),
            }
            for item in SD_ITEMS:
                row[item["name"]] = getattr(record, item["name"])
            row["created_at"] = record.created_at.isoformat(sep=" ", timespec="seconds")
            rows.append(row)

        return self._build_response(
            "impression_ratings.csv",
            [
                "id",
                "participant_id",
                "participant_group",
                "cohort_id",
                "experiment_completed",
                "song_id",
                "is_practice",
                "stimulus_set",
                "presentation_order",
                *[item["name"] for item in SD_ITEMS],
                "created_at",
            ],
            rows,
        )

    def export_analysis_dataset(self):
        participants = Participant.query.order_by(Participant.created_at.asc()).all()
        button_presses = ButtonPress.query.order_by(ButtonPress.created_at.asc()).all()
        impression_ratings = ImpressionRating.query.order_by(
            ImpressionRating.created_at.asc()
        ).all()
        rows = self.analytics_service.build_flattened_export_rows(
            participants=participants,
            button_presses=button_presses,
            impression_ratings=impression_ratings,
        )

        return self._build_response(
            "analysis_dataset.csv",
            [
                "participant_id",
                "participant_group",
                "cohort_id",
                "experiment_completed",
                "consent_given",
                "consented_at",
                "gender",
                "age",
                "music_experience",
                "music_experience_years",
                "music_experience_type",
                "listening_environment",
                "listening_environment_note",
                "experiment_browser",
                "experiment_browser_note",
                "listening_device",
                "listening_device_note",
                "practice_volume_impression",
                "practice_volume_level",
                "practice_volume_confirmed_at",
                "song_id",
                "is_practice",
                "stimulus_set",
                "presentation_order",
                "playback_started_at",
                "playback_completed_at",
                "playback_elapsed_sec",
                "client_audio_duration_sec",
                "playback_completed",
                "quality_flags",
                "press_count",
                "has_press",
                "all_press_audio_times",
                "button_pressed_time",
                "selected_press_id",
                "selected_audio_time_sec",
                "selected_segment_rule",
                "selected_segment_start_sec",
                "selected_segment_end_sec",
                "selected_segment_duration_sec",
                *[item["name"] for item in SD_ITEMS],
                "button_selected_at",
                "selection_reason",
                "rating_created_at",
            ],
            rows,
        )

    @staticmethod
    def _format_decimal(value):
        if value is None:
            return ""
        return f"{float(value):.6f}"

    @staticmethod
    def _format_datetime(value):
        if not value:
            return ""
        return value.isoformat(sep=" ", timespec="seconds")

    @staticmethod
    def _format_music_experience_type(value):
        if not value:
            return ""
        labels = [
            MUSIC_EXPERIENCE_TYPE_LABELS.get(item, item)
            for item in value.split(";")
            if item
        ]
        return ";".join(labels)

    @staticmethod
    def _build_response(filename, fieldnames, rows):
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

        response = make_response(output.getvalue())
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
