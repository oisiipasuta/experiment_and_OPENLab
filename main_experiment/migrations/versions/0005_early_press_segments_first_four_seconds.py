"""Use the opening four seconds for presses before second four.

Revision ID: 0005_early_press_segments_first_four_seconds
Revises: 0004_trial_response_duration
"""
from decimal import Decimal

from alembic import op
import sqlalchemy as sa


revision = "0005_early_press_segments_first_four_seconds"
down_revision = "0004_trial_response_duration"
branch_labels = None
depends_on = None

FOUR_SECONDS = Decimal("4.000000")
ZERO_SECONDS = Decimal("0.000000")


def _rewrite_press_events(table, bind, opening_interval):
    rows = bind.execute(
        sa.select(table.c.id, table.c.audio_time_sec).where(
            table.c.audio_time_sec < FOUR_SECONDS,
            table.c.segment_rule == "pre_4sec",
        )
    ).mappings().all()
    for row in rows:
        audio_time = Decimal(str(row["audio_time_sec"])).quantize(
            Decimal("0.000001")
        )
        end = FOUR_SECONDS if opening_interval else audio_time
        bind.execute(
            table.update()
            .where(table.c.id == row["id"])
            .values(
                segment_start_sec=ZERO_SECONDS,
                segment_end_sec=end,
                segment_duration_sec=end,
                segment_clipped_start=True,
            )
        )


def _rewrite_selected_presses(table, bind, opening_interval):
    rows = bind.execute(
        sa.select(
            table.c.id,
            table.c.pressed_time,
            table.c.selected_audio_time_sec,
        ).where(table.c.selected_segment_rule == "pre_4sec")
    ).mappings().all()
    for row in rows:
        selected_time = (
            row["selected_audio_time_sec"]
            if row["selected_audio_time_sec"] is not None
            else row["pressed_time"]
        )
        audio_time = Decimal(str(selected_time)).quantize(Decimal("0.000001"))
        if audio_time >= FOUR_SECONDS:
            continue
        end = FOUR_SECONDS if opening_interval else audio_time
        bind.execute(
            table.update()
            .where(table.c.id == row["id"])
            .values(
                selected_segment_start_sec=ZERO_SECONDS,
                selected_segment_end_sec=end,
                selected_segment_duration_sec=end,
            )
        )


def upgrade():
    bind = op.get_bind()
    metadata = sa.MetaData()
    press_events = sa.Table("press_events", metadata, autoload_with=bind)
    button_presses = sa.Table("button_presses", metadata, autoload_with=bind)
    _rewrite_press_events(press_events, bind, opening_interval=True)
    _rewrite_selected_presses(button_presses, bind, opening_interval=True)


def downgrade():
    bind = op.get_bind()
    metadata = sa.MetaData()
    press_events = sa.Table("press_events", metadata, autoload_with=bind)
    button_presses = sa.Table("button_presses", metadata, autoload_with=bind)
    _rewrite_press_events(press_events, bind, opening_interval=False)
    _rewrite_selected_presses(button_presses, bind, opening_interval=False)
