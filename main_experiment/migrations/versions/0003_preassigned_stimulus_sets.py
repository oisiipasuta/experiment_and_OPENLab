"""Add preassigned stimulus sets to participants and songs.

Revision ID: 0003_preassigned_stimulus_sets
Revises: 0002_fix_pre_press_segments
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_preassigned_stimulus_sets"
down_revision = "0002_fix_pre_press_segments"
branch_labels = None
depends_on = None


def _add_column_if_missing(table_name, column):
    bind = op.get_bind()
    existing = {item["name"] for item in sa.inspect(bind).get_columns(table_name)}
    if column.name not in existing:
        op.add_column(table_name, column)


def upgrade():
    _add_column_if_missing(
        "participants", sa.Column("stimulus_set_id", sa.Integer(), nullable=True)
    )
    _add_column_if_missing(
        "songs",
        sa.Column("is_common", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    _add_column_if_missing(
        "songs", sa.Column("stimulus_set_id", sa.Integer(), nullable=True)
    )


def downgrade():
    op.drop_column("songs", "stimulus_set_id")
    op.drop_column("songs", "is_common")
    op.drop_column("participants", "stimulus_set_id")
