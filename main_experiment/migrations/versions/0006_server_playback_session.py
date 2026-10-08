"""Track server time and resume position for playback validation.

Revision ID: 0006_server_playback_session
Revises: 0005_early_press_segments_first_four_seconds
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_server_playback_session"
down_revision = "0005_early_press_segments_first_four_seconds"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = {item["name"] for item in sa.inspect(bind).get_columns("trial_telemetry")}
    if "playback_session_started_at" not in existing:
        op.add_column(
            "trial_telemetry",
            sa.Column("playback_session_started_at", sa.DateTime(), nullable=True),
        )
    if "playback_session_start_sec" not in existing:
        op.add_column(
            "trial_telemetry",
            sa.Column("playback_session_start_sec", sa.Numeric(12, 6), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    existing = {item["name"] for item in sa.inspect(bind).get_columns("trial_telemetry")}
    if "playback_session_start_sec" in existing:
        op.drop_column("trial_telemetry", "playback_session_start_sec")
    if "playback_session_started_at" in existing:
        op.drop_column("trial_telemetry", "playback_session_started_at")
