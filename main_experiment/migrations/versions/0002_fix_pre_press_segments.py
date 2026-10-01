"""Ensure pre-press segments never include audio after the press.

Revision ID: 0002_fix_pre_press_segments
Revises: 0001_cloudworks_quality
"""
from decimal import Decimal

from alembic import op
import sqlalchemy as sa


revision = "0002_fix_pre_press_segments"
down_revision = "0001_cloudworks_quality"
branch_labels = None
depends_on = None


FOUR_SECONDS = Decimal("4.000000")
ZERO_SECONDS = Decimal("0.000000")


def _correct_segment(audio_time):
    audio_time = Decimal(str(audio_time)).quantize(Decimal("0.000001"))
    start = max(ZERO_SECONDS, audio_time - FOUR_SECONDS)
    return start, audio_time, audio_time - start, audio_time < FOUR_SECONDS


def upgrade():
    bind = op.get_bind()
    metadata = sa.MetaData()
    press_events = sa.Table("press_events", metadata, autoload_with=bind)
    button_presses = sa.Table("button_presses", metadata, autoload_with=bind)

    event_rows = bind.execute(
        sa.select(press_events.c.id, press_events.c.audio_time_sec)
    ).mappings().all()
    for row in event_rows:
        start, end, duration, clipped = _correct_segment(row["audio_time_sec"])
        bind.execute(
            press_events.update()
            .where(press_events.c.id == row["id"])
            .values(
                segment_start_sec=start,
                segment_end_sec=end,
                segment_duration_sec=duration,
                segment_clipped_start=clipped,
            )
        )

    press_rows = bind.execute(
        sa.select(
            button_presses.c.id,
            button_presses.c.pressed_time,
            button_presses.c.selected_audio_time_sec,
        ).where(button_presses.c.selected_segment_rule == "pre_4sec")
    ).mappings().all()
    for row in press_rows:
        audio_time = (
            row["selected_audio_time_sec"]
            if row["selected_audio_time_sec"] is not None
            else row["pressed_time"]
        )
        start, end, duration, _ = _correct_segment(audio_time)
        bind.execute(
            button_presses.update()
            .where(button_presses.c.id == row["id"])
            .values(
                selected_segment_start_sec=start,
                selected_segment_end_sec=end,
                selected_segment_duration_sec=duration,
            )
        )


def downgrade():
    bind = op.get_bind()
    metadata = sa.MetaData()
    press_events = sa.Table("press_events", metadata, autoload_with=bind)
    button_presses = sa.Table("button_presses", metadata, autoload_with=bind)

    event_rows = bind.execute(
        sa.select(press_events.c.id, press_events.c.audio_time_sec)
    ).mappings().all()
    for row in event_rows:
        audio_time = Decimal(str(row["audio_time_sec"])).quantize(
            Decimal("0.000001")
        )
        start = max(ZERO_SECONDS, audio_time - FOUR_SECONDS)
        bind.execute(
            press_events.update()
            .where(press_events.c.id == row["id"])
            .values(
                segment_start_sec=start,
                segment_end_sec=start + FOUR_SECONDS,
                segment_duration_sec=FOUR_SECONDS,
                segment_clipped_start=audio_time < FOUR_SECONDS,
            )
        )

    press_rows = bind.execute(
        sa.select(
            button_presses.c.id,
            button_presses.c.pressed_time,
            button_presses.c.selected_audio_time_sec,
        ).where(button_presses.c.selected_segment_rule == "pre_4sec")
    ).mappings().all()
    for row in press_rows:
        audio_time_value = (
            row["selected_audio_time_sec"]
            if row["selected_audio_time_sec"] is not None
            else row["pressed_time"]
        )
        audio_time = Decimal(str(audio_time_value)).quantize(Decimal("0.000001"))
        start = max(ZERO_SECONDS, audio_time - FOUR_SECONDS)
        bind.execute(
            button_presses.update()
            .where(button_presses.c.id == row["id"])
            .values(
                selected_segment_start_sec=start,
                selected_segment_end_sec=start + FOUR_SECONDS,
                selected_segment_duration_sec=FOUR_SECONDS,
            )
        )
