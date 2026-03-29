"""daily_brief_logs table.

Revision ID: 20260317_0010_daily_brief
Revises: 20260317_0009_debt_credit
Create Date: 2026-03-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260317_0010_daily_brief"
down_revision: Union[str, Sequence[str], None] = "20260317_0009_debt_credit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_brief_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("headline", sa.String(length=220), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("macro_tags_json", sa.Text(), nullable=True),
        sa.Column("player_impact_json", sa.Text(), nullable=True),
        sa.Column("action_hints_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("player_id", "day", name="uq_daily_brief_log_player_day"),
    )

    op.create_index("ix_daily_brief_logs_player_id", "daily_brief_logs", ["player_id"])
    op.create_index("ix_daily_brief_logs_day", "daily_brief_logs", ["day"])

    # Optional global brief support: at most one player-null row per day.
    op.create_index(
        "ux_daily_brief_logs_global_day",
        "daily_brief_logs",
        ["day"],
        unique=True,
        postgresql_where=sa.text("player_id IS NULL"),
    )

    op.execute("ALTER TABLE daily_brief_logs ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.drop_index("ux_daily_brief_logs_global_day", table_name="daily_brief_logs")
    op.drop_index("ix_daily_brief_logs_day", table_name="daily_brief_logs")
    op.drop_index("ix_daily_brief_logs_player_id", table_name="daily_brief_logs")
    op.drop_table("daily_brief_logs")
