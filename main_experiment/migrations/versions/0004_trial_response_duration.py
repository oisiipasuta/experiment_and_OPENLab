"""Track elapsed time from trial playback page to final response.

Revision ID: 0004_trial_response_duration
Revises: 0003_preassigned_stimulus_sets
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_trial_response_duration"
down_revision = "0003_preassigned_stimulus_sets"
branch_labels = None
depends_on = None


def _add_column_if_missing(table_name, column):
    bind = op.get_bind()
    existing = {item["name"] for item in sa.inspect(bind).get_columns(table_name)}
    if column.name not in existing:
        op.add_column(table_name, column)


def upgrade():
    _add_column_if_missing(
        "trial_telemetry",
        sa.Column("trial_submitted_at", sa.DateTime(), nullable=True),
    )
    _add_column_if_missing(
        "trial_telemetry",
        sa.Column("trial_response_ms", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("trial_telemetry", "trial_response_ms")
    op.drop_column("trial_telemetry", "trial_submitted_at")
