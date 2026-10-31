"""Scenario topic skills and narrative growth/fall navigation.

Revision ID: 31c0d2e4f5a6
Revises: 15f0a1b2c3d4
Create Date: 2026-10-31
"""

from alembic import op
import sqlalchemy as sa


revision = "31c0d2e4f5a6"
down_revision = "15f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scenario_topic_skill_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["skill_id"], ["skill_modules.id"]),
        sa.ForeignKeyConstraint(["topic_id"], ["scenario_topics.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("topic_id", "skill_id"),
    )
    with op.batch_alter_table("scenario_topic_skill_memberships") as batch_op:
        batch_op.create_index(
            "ix_scenario_topic_skill_memberships_skill_id", ["skill_id"]
        )
        batch_op.create_index(
            "ix_scenario_topic_skill_memberships_topic_id", ["topic_id"]
        )

    op.execute(
        """
        INSERT INTO scenario_topic_skill_memberships (topic_id, skill_id, sort_order)
        SELECT topic_id, target_skill_id, 0
        FROM scenario_topic_profiles
        WHERE target_skill_id IS NOT NULL
        """
    )

    with op.batch_alter_table("scenario_narratives") as batch_op:
        batch_op.add_column(sa.Column("previous_narrative_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("growth_next_narrative_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("fall_next_narrative_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_scenario_narratives_previous",
            "scenario_narratives",
            ["previous_narrative_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_scenario_narratives_growth_next",
            "scenario_narratives",
            ["growth_next_narrative_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_scenario_narratives_fall_next",
            "scenario_narratives",
            ["fall_next_narrative_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_scenario_narratives_previous_narrative_id", ["previous_narrative_id"]
        )
        batch_op.create_index(
            "ix_scenario_narratives_growth_next_narrative_id", ["growth_next_narrative_id"]
        )
        batch_op.create_index(
            "ix_scenario_narratives_fall_next_narrative_id", ["fall_next_narrative_id"]
        )


def downgrade():
    with op.batch_alter_table("scenario_narratives") as batch_op:
        batch_op.drop_index("ix_scenario_narratives_fall_next_narrative_id")
        batch_op.drop_index("ix_scenario_narratives_growth_next_narrative_id")
        batch_op.drop_index("ix_scenario_narratives_previous_narrative_id")
        batch_op.drop_constraint("fk_scenario_narratives_fall_next", type_="foreignkey")
        batch_op.drop_constraint("fk_scenario_narratives_growth_next", type_="foreignkey")
        batch_op.drop_constraint("fk_scenario_narratives_previous", type_="foreignkey")
        batch_op.drop_column("fall_next_narrative_id")
        batch_op.drop_column("growth_next_narrative_id")
        batch_op.drop_column("previous_narrative_id")
    op.drop_table("scenario_topic_skill_memberships")
