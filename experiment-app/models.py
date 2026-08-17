from datetime import datetime, timedelta, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, UniqueConstraint


db = SQLAlchemy()


def utcnow():
    jst = timezone(timedelta(hours=9))
    return datetime.now(jst).replace(tzinfo=None)


class Participant(db.Model):
    __tablename__ = "participants"

    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.String(100), unique=True, nullable=False)
    age = db.Column(db.Integer, nullable=True)
    gender = db.Column(db.String(50), nullable=True)
    music_experience = db.Column(db.String(100), nullable=True)
    music_experience_years = db.Column(db.Integer, nullable=True)
    music_experience_type = db.Column(db.Text, nullable=True)
    listening_environment = db.Column(db.String(50), nullable=True)
    listening_environment_note = db.Column(db.Text, nullable=True)
    experiment_browser = db.Column(db.String(50), nullable=True)
    experiment_browser_note = db.Column(db.Text, nullable=True)
    listening_device = db.Column(db.String(50), nullable=True)
    listening_device_note = db.Column(db.Text, nullable=True)
    practice_volume_impression = db.Column(db.String(50), nullable=True)
    practice_volume_level = db.Column(db.Integer, nullable=True)
    practice_volume_confirmed_at = db.Column(db.DateTime, nullable=True)
    consent_given = db.Column(db.Boolean, nullable=False, default=False)
    consented_at = db.Column(db.DateTime, nullable=True)
    current_assignment_index = db.Column(db.Integer, nullable=False, default=0)
    current_phase = db.Column(db.String(20), nullable=False, default="playback")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    assignments = db.relationship(
        "ParticipantSongOrder",
        back_populates="participant",
        cascade="all, delete-orphan",
        order_by="ParticipantSongOrder.order_index",
    )
    button_presses = db.relationship(
        "ButtonPress",
        back_populates="participant",
        cascade="all, delete-orphan",
    )
    press_events = db.relationship(
        "PressEvent",
        back_populates="participant",
        cascade="all, delete-orphan",
    )
    impression_ratings = db.relationship(
        "ImpressionRating",
        back_populates="participant",
        cascade="all, delete-orphan",
    )


class Song(db.Model):
    __tablename__ = "songs"

    id = db.Column(db.Integer, primary_key=True)
    song_id = db.Column(db.String(100), unique=True, nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    is_practice = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    assignments = db.relationship(
        "ParticipantSongOrder",
        back_populates="song",
        cascade="all, delete-orphan",
    )
    press_events = db.relationship("PressEvent", back_populates="song")
    candidate_presses = db.relationship("ButtonPressCandidate", back_populates="song")
    button_presses = db.relationship("ButtonPress", back_populates="song")
    impression_ratings = db.relationship("ImpressionRating", back_populates="song")


class ParticipantSongOrder(db.Model):
    __tablename__ = "participant_song_orders"
    __table_args__ = (
        UniqueConstraint("participant_id", "order_index", name="uq_participant_order"),
    )

    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(
        db.Integer,
        db.ForeignKey("participants.id", ondelete="CASCADE"),
        nullable=False,
    )
    song_id = db.Column(
        db.Integer,
        db.ForeignKey("songs.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_index = db.Column(db.Integer, nullable=False)
    is_practice = db.Column(db.Boolean, nullable=False, default=False)
    press_count = db.Column(db.Integer, nullable=False, default=0)
    has_press = db.Column(db.Boolean, nullable=False, default=False)
    all_press_audio_times = db.Column(db.Text, nullable=True)
    selected_press_event_id = db.Column(db.Integer, nullable=True)

    participant = db.relationship("Participant", back_populates="assignments")
    song = db.relationship("Song", back_populates="assignments")
    press_events = db.relationship(
        "PressEvent",
        back_populates="assignment",
        cascade="all, delete-orphan",
    )


class PressEvent(db.Model):
    __tablename__ = "press_events"
    __table_args__ = (
        CheckConstraint("press_index >= 1", name="ck_press_event_index_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(
        db.Integer,
        db.ForeignKey("participant_song_orders.id", ondelete="CASCADE"),
        nullable=True,
    )
    participant_id = db.Column(
        db.String(100),
        db.ForeignKey("participants.participant_id", ondelete="CASCADE"),
        nullable=False,
    )
    song_id = db.Column(
        db.String(100),
        db.ForeignKey("songs.song_id", ondelete="CASCADE"),
        nullable=False,
    )
    is_practice = db.Column(db.Boolean, nullable=False, default=False)
    press_index = db.Column(db.Integer, nullable=False)
    audio_time_sec = db.Column(db.Numeric(12, 6), nullable=False)
    performance_time_ms = db.Column(db.Numeric(14, 6), nullable=True)
    client_timestamp = db.Column(db.String(64), nullable=True)
    server_received_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    segment_rule = db.Column(db.String(20), nullable=False, default="pre_4sec")
    segment_start_sec = db.Column(db.Numeric(12, 6), nullable=False)
    segment_end_sec = db.Column(db.Numeric(12, 6), nullable=False)
    segment_duration_sec = db.Column(db.Numeric(12, 6), nullable=False)
    segment_clipped_start = db.Column(db.Boolean, nullable=False, default=False)
    is_selected = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    assignment = db.relationship("ParticipantSongOrder", back_populates="press_events")
    participant = db.relationship("Participant", back_populates="press_events")
    song = db.relationship("Song", back_populates="press_events")


class ButtonPress(db.Model):
    __tablename__ = "button_presses"
    __table_args__ = (
        CheckConstraint("press_order >= 1", name="ck_press_order_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(
        db.String(100),
        db.ForeignKey("participants.participant_id", ondelete="CASCADE"),
        nullable=False,
    )
    song_id = db.Column(
        db.String(100),
        db.ForeignKey("songs.song_id", ondelete="CASCADE"),
        nullable=False,
    )
    assignment_id = db.Column(db.Integer, nullable=True)
    press_event_id = db.Column(
        db.Integer,
        db.ForeignKey("press_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_practice = db.Column(db.Boolean, nullable=False, default=False)
    press_order = db.Column(db.Integer, nullable=False)
    pressed_time = db.Column(db.Numeric(12, 6), nullable=False)
    selected_audio_time_sec = db.Column(db.Numeric(12, 6), nullable=True)
    selected_segment_rule = db.Column(db.String(20), nullable=True)
    selected_segment_start_sec = db.Column(db.Numeric(12, 6), nullable=True)
    selected_segment_end_sec = db.Column(db.Numeric(12, 6), nullable=True)
    selected_segment_duration_sec = db.Column(db.Numeric(12, 6), nullable=True)
    selection_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    participant = db.relationship("Participant", back_populates="button_presses")
    song = db.relationship("Song", back_populates="button_presses")
    press_event = db.relationship("PressEvent")


class ButtonPressCandidate(db.Model):
    __tablename__ = "button_press_candidates"
    __table_args__ = (
        CheckConstraint("press_order >= 1", name="ck_candidate_press_order_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(
        db.String(100),
        db.ForeignKey("participants.participant_id", ondelete="CASCADE"),
        nullable=False,
    )
    song_id = db.Column(
        db.String(100),
        db.ForeignKey("songs.song_id", ondelete="CASCADE"),
        nullable=False,
    )
    assignment_id = db.Column(db.Integer, nullable=True)
    press_event_id = db.Column(
        db.Integer,
        db.ForeignKey("press_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_practice = db.Column(db.Boolean, nullable=False, default=False)
    press_order = db.Column(db.Integer, nullable=False)
    pressed_time = db.Column(db.Numeric(12, 6), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    participant = db.relationship("Participant")
    song = db.relationship("Song", back_populates="candidate_presses")
    press_event = db.relationship("PressEvent")


class ImpressionRating(db.Model):
    __tablename__ = "impression_ratings"
    __table_args__ = (
        UniqueConstraint(
            "participant_id",
            "song_id",
            "is_practice",
            name="uq_impression_per_song",
        ),
        CheckConstraint("bright_dark BETWEEN 1 AND 7", name="ck_bright_dark_range"),
        CheckConstraint("smooth_rough BETWEEN 1 AND 7", name="ck_smooth_rough_range"),
        CheckConstraint("rich_thin BETWEEN 1 AND 7", name="ck_rich_thin_range"),
        CheckConstraint("clear_muddy BETWEEN 1 AND 7", name="ck_clear_muddy_range"),
        CheckConstraint("intense_calm BETWEEN 1 AND 7", name="ck_intense_calm_range"),
        CheckConstraint("heavy_light BETWEEN 1 AND 7", name="ck_heavy_light_range"),
        CheckConstraint("soft_hard BETWEEN 1 AND 7", name="ck_soft_hard_range"),
        CheckConstraint("thick_thin BETWEEN 1 AND 7", name="ck_thick_thin_range"),
        CheckConstraint("like_dislike BETWEEN 1 AND 7", name="ck_like_dislike_range"),
    )

    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(
        db.String(100),
        db.ForeignKey("participants.participant_id", ondelete="CASCADE"),
        nullable=False,
    )
    song_id = db.Column(
        db.String(100),
        db.ForeignKey("songs.song_id", ondelete="CASCADE"),
        nullable=False,
    )
    is_practice = db.Column(db.Boolean, nullable=False, default=False)
    bright_dark = db.Column(db.Integer, nullable=False)
    smooth_rough = db.Column(db.Integer, nullable=False)
    rich_thin = db.Column(db.Integer, nullable=False)
    clear_muddy = db.Column(db.Integer, nullable=False)
    intense_calm = db.Column(db.Integer, nullable=False)
    heavy_light = db.Column(db.Integer, nullable=False)
    soft_hard = db.Column(db.Integer, nullable=False)
    thick_thin = db.Column(db.Integer, nullable=False)
    like_dislike = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    participant = db.relationship("Participant", back_populates="impression_ratings")
    song = db.relationship("Song", back_populates="impression_ratings")
