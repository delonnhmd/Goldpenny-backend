"""Add event chain columns to daily_economy_events (Step 19.5).

Revision ID: 20260317_0013_event_chains
Revises: 20260317_0012_net_worth
Create Date: 2026-03-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260317_0013_event_chains"
down_revision: Union[str, Sequence[str], None] = "20260317_0012_net_worth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("daily_economy_events", sa.Column("chain_id", sa.String(80), nullable=True))
    op.add_column("daily_economy_events", sa.Column("chain_position", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("daily_economy_events", sa.Column("chain_length_expected", sa.Integer(), nullable=True))
    op.add_column("daily_economy_events", sa.Column("chain_stage", sa.String(20), nullable=True))
    op.add_column("daily_economy_events", sa.Column("parent_event_key", sa.String(80), nullable=True))
    op.add_column("daily_economy_events", sa.Column("continuation_probability", sa.Numeric(6, 4), nullable=True))
    op.add_column("daily_economy_events", sa.Column("decay_factor", sa.Numeric(6, 4), nullable=True))
    op.add_column("daily_economy_events", sa.Column("chain_debug_json", sa.Text(), nullable=True))
    op.create_index("ix_daily_economy_events_chain_id", "daily_economy_events", ["chain_id"])


def downgrade() -> None:
    op.drop_index("ix_daily_economy_events_chain_id", table_name="daily_economy_events")
    op.drop_column("daily_economy_events", "chain_debug_json")
    op.drop_column("daily_economy_events", "decay_factor")
    op.drop_column("daily_economy_events", "continuation_probability")
    op.drop_column("daily_economy_events", "parent_event_key")
    op.drop_column("daily_economy_events", "chain_stage")
    op.drop_column("daily_economy_events", "chain_length_expected")
    op.drop_column("daily_economy_events", "chain_position")
    op.drop_column("daily_economy_events", "chain_id")
