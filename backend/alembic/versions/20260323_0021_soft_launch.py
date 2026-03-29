"""Step 70: Soft launch tables

Creates 4 new tables:
  soft_launch_access   — Pre-provisioned invite codes
  soft_launch_members  — User-to-cohort membership
  player_feedback      — In-game feedback submissions
  issue_reports        — Bug / friction / issue reports

Revision ID: 20260323_0021_soft_launch
Revises: 20260323_0020_retention_engine
Create Date: 2026-03-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260323_0021_soft_launch"
down_revision: Union[str, Sequence[str], None] = "20260323_0020_retention_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "soft_launch_access",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("invite_code", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("cohort_tag", sa.String(40), nullable=False, server_default="soft_launch_v1"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("max_uses", sa.Integer, nullable=False, server_default="1"),
        sa.Column("use_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "soft_launch_members",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
            index=True,
        ),
        sa.Column("invite_code_used", sa.String(64), nullable=True),
        sa.Column("cohort_tag", sa.String(40), nullable=False, server_default="soft_launch_v1"),
        sa.Column("is_approved", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("notes", sa.Text, nullable=True),
    )

    op.create_table(
        "player_feedback",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "player_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("game_day", sa.Integer, nullable=False, server_default="1"),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("response_confusing", sa.Text, nullable=True),
        sa.Column("response_hard", sa.Text, nullable=True),
        sa.Column("response_interesting", sa.Text, nullable=True),
        sa.Column("cohort_tag", sa.String(40), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "issue_reports",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "player_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("game_day", sa.Integer, nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("category", sa.String(40), nullable=True),
        sa.Column("severity", sa.String(20), nullable=True),
        sa.Column("extra_context_json", sa.Text, nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("issue_reports")
    op.drop_table("player_feedback")
    op.drop_table("soft_launch_members")
    op.drop_table("soft_launch_access")
