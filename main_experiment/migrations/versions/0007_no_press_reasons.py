"""Store reasons for trials without button presses.

Revision ID: 0007_no_press_reasons
Revises: 0006_server_playback_session
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_no_press_reasons"
down_revision = "0006_server_playback_session"
branch_labels = None
depends_on = None


def upgrade():
    existing = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("participant_song_orders")
    }
    for name, column_type in (
        ("no_press_reason_choices", sa.Text()),
        ("no_press_reason_note", sa.Text()),
        ("no_press_reason_submitted_at", sa.DateTime()),
    ):
        if name not in existing:
            op.add_column(
                "participant_song_orders", sa.Column(name, column_type, nullable=True)
            )


def downgrade():
    with op.batch_alter_table("participant_song_orders") as batch_op:
        batch_op.drop_column("no_press_reason_submitted_at")
        batch_op.drop_column("no_press_reason_note")
        batch_op.drop_column("no_press_reason_choices")
