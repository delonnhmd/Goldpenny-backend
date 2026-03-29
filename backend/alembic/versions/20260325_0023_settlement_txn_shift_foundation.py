"""Step 73: settlement summary ack, transaction history, company/shift employment fields.

Revision ID: 20260325_0023_settlement_txn_shift_foundation
Revises: 20260323_0022_merge_heads
Create Date: 2026-03-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260325_0023_settlement_txn_shift_foundation"
down_revision: Union[str, Sequence[str], None] = "20260323_0022_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("last_seen_settlement_day", sa.Integer(), nullable=True))

    op.add_column(
        "player_employment_states",
        sa.Column("employer_company_symbol", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "player_employment_states",
        sa.Column("employer_company_name", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "player_employment_states",
        sa.Column("position_title", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "player_employment_states",
        sa.Column("shift_type", sa.String(length=40), nullable=True),
    )

    op.create_table(
        "player_transaction_logs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "player_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Integer(), nullable=True),
        sa.Column("transaction_type", sa.String(length=40), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False, server_default="general"),
        sa.Column("asset_symbol", sa.String(length=40), nullable=True),
        sa.Column("quantity", sa.Numeric(14, 4), nullable=True),
        sa.Column("unit_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("gross_amount", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("fee_amount", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("net_cash_delta", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("resulting_cash_balance", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_player_transaction_logs_player_id", "player_transaction_logs", ["player_id"])
    op.create_index("ix_player_transaction_logs_day", "player_transaction_logs", ["day"])
    op.create_index(
        "ix_player_transaction_logs_transaction_type",
        "player_transaction_logs",
        ["transaction_type"],
    )
    op.create_index(
        "ix_player_transaction_logs_category",
        "player_transaction_logs",
        ["category"],
    )
    op.create_index(
        "ix_player_transaction_logs_asset_symbol",
        "player_transaction_logs",
        ["asset_symbol"],
    )
    op.create_index(
        "ix_player_transaction_logs_created_at",
        "player_transaction_logs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_player_transaction_logs_created_at", table_name="player_transaction_logs")
    op.drop_index("ix_player_transaction_logs_asset_symbol", table_name="player_transaction_logs")
    op.drop_index("ix_player_transaction_logs_category", table_name="player_transaction_logs")
    op.drop_index("ix_player_transaction_logs_transaction_type", table_name="player_transaction_logs")
    op.drop_index("ix_player_transaction_logs_day", table_name="player_transaction_logs")
    op.drop_index("ix_player_transaction_logs_player_id", table_name="player_transaction_logs")
    op.drop_table("player_transaction_logs")

    op.drop_column("player_employment_states", "shift_type")
    op.drop_column("player_employment_states", "position_title")
    op.drop_column("player_employment_states", "employer_company_name")
    op.drop_column("player_employment_states", "employer_company_symbol")
    op.drop_column("players", "last_seen_settlement_day")
