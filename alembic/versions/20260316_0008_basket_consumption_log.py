"""basket_consumption_logs table.

Revision ID: 20260316_0008_basket_consumption
Revises: 20260316_0007_job_market
Create Date: 2026-03-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260316_0008_basket_consumption"
down_revision: Union[str, Sequence[str], None] = "20260316_0007_job_market"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "basket_consumption_logs",
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
            nullable=False,
        ),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("essentials_spend_xgp", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("protein_spend_xgp", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("produce_spend_xgp", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("convenience_spend_xgp", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_spend_xgp", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("budget_pressure_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("stress_spend_modifier", sa.Numeric(8, 4), nullable=False, server_default="1"),
        sa.Column("nutrition_pressure_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("notes_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "player_id", "day", name="uq_basket_consumption_log_player_day"
        ),
    )
    op.create_index(
        "ix_basket_consumption_logs_player_id",
        "basket_consumption_logs",
        ["player_id"],
    )
    op.create_index(
        "ix_basket_consumption_logs_day",
        "basket_consumption_logs",
        ["day"],
    )

    # Enable RLS so Supabase row-level policies can be applied later.
    op.execute("ALTER TABLE basket_consumption_logs ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.drop_index("ix_basket_consumption_logs_day", table_name="basket_consumption_logs")
    op.drop_index("ix_basket_consumption_logs_player_id", table_name="basket_consumption_logs")
    op.drop_table("basket_consumption_logs")
