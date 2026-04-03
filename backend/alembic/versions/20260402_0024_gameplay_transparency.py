"""Step 83: gameplay transparency ledger and work tracking fields.

Revision ID: 20260402_0024_gameplay_transparency
Revises: 20260325_0023_settlement_txn_shift_foundation
Create Date: 2026-04-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260402_0024_gameplay_transparency"
down_revision: Union[str, Sequence[str], None] = "20260325_0023_settlement_txn_shift_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gameplay_transactions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "player_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("amount", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_gameplay_transactions_player_id", "gameplay_transactions", ["player_id"])
    op.create_index("ix_gameplay_transactions_day", "gameplay_transactions", ["day"])
    op.create_index("ix_gameplay_transactions_type", "gameplay_transactions", ["type"])
    op.create_index("ix_gameplay_transactions_category", "gameplay_transactions", ["category"])
    op.create_index("ix_gameplay_transactions_timestamp", "gameplay_transactions", ["timestamp"])

    op.add_column(
        "player_daily_states",
        sa.Column("did_work", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "player_daily_states",
        sa.Column("shift_start", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "player_daily_states",
        sa.Column("shift_end", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "player_daily_states",
        sa.Column("salary_earned", sa.Numeric(14, 4), nullable=False, server_default="0"),
    )
    op.add_column(
        "player_daily_states",
        sa.Column("missed_penalty", sa.Numeric(14, 4), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("player_daily_states", "missed_penalty")
    op.drop_column("player_daily_states", "salary_earned")
    op.drop_column("player_daily_states", "shift_end")
    op.drop_column("player_daily_states", "shift_start")
    op.drop_column("player_daily_states", "did_work")

    op.drop_index("ix_gameplay_transactions_timestamp", table_name="gameplay_transactions")
    op.drop_index("ix_gameplay_transactions_category", table_name="gameplay_transactions")
    op.drop_index("ix_gameplay_transactions_type", table_name="gameplay_transactions")
    op.drop_index("ix_gameplay_transactions_day", table_name="gameplay_transactions")
    op.drop_index("ix_gameplay_transactions_player_id", table_name="gameplay_transactions")
    op.drop_table("gameplay_transactions")
