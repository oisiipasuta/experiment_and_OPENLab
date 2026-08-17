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
from models import ButtonPress, ImpressionRating, Participant, PressEvent, Song


class AdminAnalyticsService:
    """管理画面向けの集計と可視化データを生成する。"""

    def build_dashboard_context(self):
        participants = Participant.query.order_by(Participant.created_at.desc()).all()
        songs = Song.query.order_by(
            Song.is_active.desc(),
            Song.is_practice.desc(),
            Song.display_order.asc(),
            Song.song_id.asc(),
        ).all()
        button_presses = ButtonPress.query.order_by(ButtonPress.created_at.desc()).all()
        press_events = PressEvent.query.order_by(PressEvent.server_received_at.desc()).all()
        impression_ratings = ImpressionRating.query.order_by(
            ImpressionRating.created_at.desc()
        ).all()

        participant_views, song_views = self.build_admin_views(
            participants=participants,
            songs=songs,
            button_presses=button_presses,
            impression_ratings=impression_ratings,
        )

        return {
            "participants": participants,
            "songs": songs,
            "button_presses": button_presses,
            "press_events": press_events,
            "impression_ratings": impression_ratings,
            "participant_views": participant_views,
            "song_views": song_views,
            "heatmap_rows": self.build_song_heatmap_rows(song_views),
            "flattened_rows": self.build_flattened_export_rows(
                participants=participants,
                button_presses=button_presses,
                impression_ratings=impression_ratings,
            ),
        }

    def build_admin_views(self, participants, songs, button_presses, impression_ratings):
        participant_lookup = {
            participant.participant_id: participant for participant in participants
        }
        press_index = {
            (press.participant_id, press.song_id, press.is_practice): press
            for press in button_presses
        }
        rating_index = {
            (rating.participant_id, rating.song_id, rating.is_practice): rating
            for rating in impression_ratings
        }

        participant_views = []
        for participant in participants:
            trial_rows = []
            for assignment in participant.assignments:
                key = (participant.participant_id, assignment.song.song_id, assignment.is_practice)
                press = press_index.get(key)
                rating = rating_index.get(key)
                if press is None and rating is None:
                    continue

                trial_rows.append(
                    {
                        "song": assignment.song,
                        "is_practice": assignment.is_practice,
                        "pressed_time": float(press.pressed_time) if press else None,
                        "press_order": press.press_order if press else None,
                        "selection_reason": press.selection_reason if press else None,
                        "selected_at": press.created_at if press else None,
                        "rating_values": self.build_rating_values(rating),
                        "rating_created_at": rating.created_at if rating else None,
                    }
                )

            participant_views.append(
                {
                    "participant": participant,
                    "trial_rows": trial_rows,
                    "press_count": sum(
                        1 for row in trial_rows if row["pressed_time"] is not None
                    ),
                    "rating_count": sum(1 for row in trial_rows if row["rating_values"]),
                }
            )

        song_views = []
        for song in songs:
            song_ratings = [
                rating
                for rating in impression_ratings
                if rating.song_id == song.song_id and rating.is_practice == song.is_practice
            ]
            song_presses = [
                press
                for press in button_presses
                if press.song_id == song.song_id and press.is_practice == song.is_practice
            ]

            response_rows = []
            for rating in song_ratings:
                key = (rating.participant_id, rating.song_id, rating.is_practice)
                press = press_index.get(key)
                response_rows.append(
                    {
                        "participant": participant_lookup.get(rating.participant_id),
                        "participant_id": rating.participant_id,
                        "pressed_time": float(press.pressed_time) if press else None,
                        "press_order": press.press_order if press else None,
                        "selection_reason": press.selection_reason if press else None,
                        "scores": {
                            item["name"]: getattr(rating, item["name"]) for item in SD_ITEMS
                        },
                        "rating_values": self.build_rating_values(rating),
                        "created_at": rating.created_at,
                    }
                )

            song_views.append(
                {
                    "song": song,
                    "response_count": len(song_ratings),
                    "press_count": len(song_presses),
                    "averages": self.build_average_rating_values(song_ratings),
                    "response_rows": response_rows,
                }
            )

        return participant_views, song_views

    def build_song_heatmap_rows(self, song_views):
        heatmap_rows = []
        for song_view in song_views:
            cells = []
            has_any_data = False

            for average in song_view["averages"]:
                value = average["average"]
                if value is not None:
                    has_any_data = True
                cells.append(
                    {
                        "label": average["label"],
                        "value": value,
                        "class_name": self.score_to_heatmap_class(value),
                    }
                )

            heatmap_rows.append(
                {
                    "song": song_view["song"],
                    "response_count": song_view["response_count"],
                    "cells": cells,
                    "has_any_data": has_any_data,
                }
            )

        return heatmap_rows

    def build_flattened_export_rows(self, participants, button_presses, impression_ratings):
        press_index = {
            (press.participant_id, press.song_id, press.is_practice): press
            for press in button_presses
        }
        rating_index = {
            (rating.participant_id, rating.song_id, rating.is_practice): rating
            for rating in impression_ratings
        }

        rows = []
        for participant in participants:
            for assignment in participant.assignments:
                key = (participant.participant_id, assignment.song.song_id, assignment.is_practice)
                press = press_index.get(key)
                rating = rating_index.get(key)

                if press is None and rating is None:
                    continue

                row = {
                    "participant_id": participant.participant_id,
                    "consent_given": participant.consent_given,
                    "consented_at": (
                        participant.consented_at.isoformat(sep=" ", timespec="seconds")
                        if participant.consented_at
                        else ""
                    ),
                    "gender": GENDER_LABELS.get(participant.gender, participant.gender or ""),
                    "age": participant.age if participant.age is not None else "",
                    "music_experience": MUSIC_EXPERIENCE_LABELS.get(
                        participant.music_experience,
                        participant.music_experience or "",
                    ),
                    "music_experience_years": (
                        participant.music_experience_years
                        if participant.music_experience_years is not None
                        else ""
                    ),
                    "music_experience_type": self.format_music_experience_type(
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
                    "song_id": assignment.song.song_id,
                    "is_practice": assignment.is_practice,
                    "press_count": assignment.press_count,
                    "has_press": assignment.has_press,
                    "all_press_audio_times": assignment.all_press_audio_times or "",
                    "button_pressed_time": (
                        f"{float(press.pressed_time):.6f}" if press else ""
                    ),
                    "selected_press_id": press.press_event_id if press else "",
                    "selected_audio_time_sec": (
                        f"{float(press.selected_audio_time_sec):.6f}"
                        if press and press.selected_audio_time_sec is not None
                        else ""
                    ),
                    "selected_segment_rule": press.selected_segment_rule if press else "",
                    "selected_segment_start_sec": (
                        f"{float(press.selected_segment_start_sec):.6f}"
                        if press and press.selected_segment_start_sec is not None
                        else ""
                    ),
                    "selected_segment_end_sec": (
                        f"{float(press.selected_segment_end_sec):.6f}"
                        if press and press.selected_segment_end_sec is not None
                        else ""
                    ),
                    "selected_segment_duration_sec": (
                        f"{float(press.selected_segment_duration_sec):.6f}"
                        if press and press.selected_segment_duration_sec is not None
                        else ""
                    ),
                    "button_selected_at": (
                        press.created_at.isoformat(sep=" ", timespec="seconds")
                        if press
                        else ""
                    ),
                    "selection_reason": press.selection_reason if press else "",
                    "rating_created_at": (
                        rating.created_at.isoformat(sep=" ", timespec="seconds")
                        if rating
                        else ""
                    ),
                }

                for item in SD_ITEMS:
                    row[item["name"]] = getattr(rating, item["name"]) if rating else ""

                rows.append(row)

        return rows

    def build_rating_values(self, rating):
        if rating is None:
            return []

        values = []
        for item in SD_ITEMS:
            score = getattr(rating, item["name"])
            values.append(
                {
                    "name": item["name"],
                    "label": f"{item['left']} / {item['right']}",
                    "value": score,
                    "percent": self.score_to_percent(score),
                }
            )
        return values

    def build_average_rating_values(self, ratings):
        averages = []
        for item in SD_ITEMS:
            values = [getattr(rating, item["name"]) for rating in ratings]
            average = round(sum(values) / len(values), 2) if values else None
            averages.append(
                {
                    "name": item["name"],
                    "label": f"{item['left']} / {item['right']}",
                    "left": item["left"],
                    "right": item["right"],
                    "average": average,
                    "percent": self.score_to_percent(average) if average is not None else 0,
                }
            )
        return averages

    @staticmethod
    def score_to_percent(score):
        if score is None:
            return 0
        return round(((float(score) - 1.0) / 6.0) * 100.0, 2)

    @staticmethod
    def score_to_heatmap_class(score):
        if score is None:
            return "heatmap-empty"

        numeric = float(score)
        if numeric < 2.0:
            return "heatmap-1"
        if numeric < 3.0:
            return "heatmap-2"
        if numeric < 4.0:
            return "heatmap-3"
        if numeric < 5.0:
            return "heatmap-4"
        if numeric < 6.0:
            return "heatmap-5"
        return "heatmap-6"

    @staticmethod
    def format_music_experience_type(value):
        if not value:
            return ""
        labels = [
            MUSIC_EXPERIENCE_TYPE_LABELS.get(item, item)
            for item in value.split(";")
            if item
        ]
        return ";".join(labels)
