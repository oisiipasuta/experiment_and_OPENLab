"""Create the experiment schema and CloudWorks quality tables.

Revision ID: 0001_cloudworks_quality
Revises: None
"""
from alembic import op
import sqlalchemy as sa

from models import db


revision = "0001_cloudworks_quality"
down_revision = None
branch_labels = None
depends_on = None


def _add_missing_columns(bind, table_name, columns):
    inspector = sa.inspect(bind)
    existing = {item["name"] for item in inspector.get_columns(table_name)}
    for column in columns:
        if column.name not in existing:
            op.add_column(table_name, column)


def upgrade():
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    db.metadata.create_all(bind=bind, checkfirst=True)

    if "participants" in existing_tables:
        _add_missing_columns(
            bind,
            "participants",
            [
                sa.Column("attention_check_trial_1", sa.Integer(), nullable=True),
                sa.Column("attention_check_trial_2", sa.Integer(), nullable=True),
            ],
        )
    if "songs" in existing_tables:
        _add_missing_columns(
            bind,
            "songs",
            [
                sa.Column("file_size_bytes", sa.Integer(), nullable=True),
                sa.Column("content_sha256", sa.String(length=64), nullable=True),
                sa.Column("duration_seconds", sa.Numeric(12, 6), nullable=True),
            ],
        )


def downgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    for table_name in (
        "admin_login_attempts",
        "resume_attempts",
        "quality_flags",
        "trial_telemetry",
        "attention_checks",
        "participant_credentials",
    ):
        if table_name in tables:
            op.drop_table(table_name)
