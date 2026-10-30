"""Stage 15 operations, queue and performance indexes.

Revision ID: 15f0a1b2c3d4
Revises: 08de7b3ceefe
Create Date: 2026-10-30
"""

from alembic import op
import sqlalchemy as sa


revision = "15f0a1b2c3d4"
down_revision = "08de7b3ceefe"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=700), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("background_jobs") as batch_op:
        batch_op.create_index("ix_background_jobs_idempotency_key", ["idempotency_key"], unique=True)
        batch_op.create_index("ix_background_jobs_job_type", ["job_type"])
        batch_op.create_index("ix_background_jobs_next_attempt_at", ["next_attempt_at"])
        batch_op.create_index("ix_background_jobs_status", ["status"])
    with op.batch_alter_table("form_responses") as batch_op:
        batch_op.create_index(
            "ix_form_response_family_timeline", ["user_id", "child_id", "created_at"]
        )
        batch_op.create_index("ix_form_response_form_status", ["form_id", "status"])


def downgrade():
    with op.batch_alter_table("form_responses") as batch_op:
        batch_op.drop_index("ix_form_response_form_status")
        batch_op.drop_index("ix_form_response_family_timeline")
    with op.batch_alter_table("background_jobs") as batch_op:
        batch_op.drop_index("ix_background_jobs_status")
        batch_op.drop_index("ix_background_jobs_next_attempt_at")
        batch_op.drop_index("ix_background_jobs_job_type")
        batch_op.drop_index("ix_background_jobs_idempotency_key")
    op.drop_table("background_jobs")
