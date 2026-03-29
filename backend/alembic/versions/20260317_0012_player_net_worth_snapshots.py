"""player_net_worth_snapshots table.

Revision ID: 20260317_0012_net_worth
Revises: 20260317_0011_player_gender
Create Date: 2026-03-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260317_0012_net_worth"
down_revision: Union[str, Sequence[str], None] = "20260317_0011_player_gender"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_net_worth_snapshots",
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
        sa.Column("cash_xgp", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("bank_savings_xgp", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("stock_market_value_xgp", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("business_value_xgp", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total_assets_xgp", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("debt_xgp", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("net_worth_xgp", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("allocation_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("player_id", "day", name="uq_player_net_worth_snapshot_player_day"),
    )

    op.create_index(
        "ix_player_net_worth_snapshots_player_id",
        "player_net_worth_snapshots",
        ["player_id"],
    )
    op.create_index("ix_player_net_worth_snapshots_day", "player_net_worth_snapshots", ["day"])

    op.execute("ALTER TABLE player_net_worth_snapshots ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.drop_index("ix_player_net_worth_snapshots_day", table_name="player_net_worth_snapshots")
    op.drop_index("ix_player_net_worth_snapshots_player_id", table_name="player_net_worth_snapshots")
    op.drop_table("player_net_worth_snapshots")
