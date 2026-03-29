"""Create player_reputation_states and player_reputation_history tables (Step 40).

Revision ID: 20260321_0016_reputation_trust
Revises: 20260321_0015_wealth_progression
Create Date: 2026-03-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260321_0016_reputation_trust"
down_revision: Union[str, Sequence[str], None] = "20260321_0015_wealth_progression"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # player_reputation_states — rolling per-player reputation profile (upsert)
    op.create_table(
        "player_reputation_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reputation_score", sa.Numeric(8, 4), nullable=False, server_default="50"),
        sa.Column("trust_score", sa.Numeric(8, 4), nullable=False, server_default="50"),
        sa.Column("financial_reliability_score", sa.Numeric(8, 4), nullable=False, server_default="50"),
        sa.Column("work_reliability_score", sa.Numeric(8, 4), nullable=False, server_default="50"),
        sa.Column("business_reliability_score", sa.Numeric(8, 4), nullable=False, server_default="50"),
        sa.Column("opportunity_readiness_score", sa.Numeric(8, 4), nullable=False, server_default="50"),
        sa.Column("overall_trust_label", sa.String(20), nullable=False, server_default="mixed"),
        sa.Column("reputation_direction", sa.String(20), nullable=False, server_default="stable"),
        sa.Column("payment_signal_label", sa.String(20), nullable=False, server_default="mixed"),
        sa.Column("borrowing_signal_label", sa.String(20), nullable=False, server_default="mixed"),
        sa.Column("work_signal_label", sa.String(20), nullable=False, server_default="mixed"),
        sa.Column("business_signal_label", sa.String(20), nullable=False, server_default="mixed"),
        sa.Column("stability_signal_label", sa.String(20), nullable=False, server_default="mixed"),
        sa.Column("opportunity_access_label", sa.String(20), nullable=False, server_default="standard"),
        sa.Column("top_reputation_driver", sa.String(100), nullable=True),
        sa.Column("top_reputation_drag", sa.String(100), nullable=True),
        sa.Column("practical_actions_json", sa.Text(), nullable=True),
        sa.Column("planning_insights_json", sa.Text(), nullable=True),
        sa.Column("debug_json", sa.Text(), nullable=True),
        sa.Column("last_updated_on", sa.Integer(), nullable=True),
        sa.Column("last_updated_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", name="uq_prs_player"),
    )
    op.create_index("ix_prs_player_id", "player_reputation_states", ["player_id"])

    # player_reputation_history — append-only daily snapshot rows
    op.create_table(
        "player_reputation_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("reputation_score", sa.Numeric(8, 4), nullable=False, server_default="50"),
        sa.Column("trust_score", sa.Numeric(8, 4), nullable=False, server_default="50"),
        sa.Column("financial_reliability_score", sa.Numeric(8, 4), nullable=False, server_default="50"),
        sa.Column("work_reliability_score", sa.Numeric(8, 4), nullable=False, server_default="50"),
        sa.Column("business_reliability_score", sa.Numeric(8, 4), nullable=False, server_default="50"),
        sa.Column("opportunity_readiness_score", sa.Numeric(8, 4), nullable=False, server_default="50"),
        sa.Column("overall_trust_label", sa.String(20), nullable=False, server_default="mixed"),
        sa.Column("opportunity_access_label", sa.String(20), nullable=False, server_default="standard"),
        sa.Column("reputation_direction", sa.String(20), nullable=False, server_default="stable"),
        sa.Column("false_growth_suppressed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("delinquency_drag_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("recovery_boost_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", "day", name="uq_prh_player_day"),
    )
    op.create_index("ix_prh_player_id", "player_reputation_history", ["player_id"])
    op.create_index("ix_prh_day", "player_reputation_history", ["day"])
    op.create_index("ix_prh_player_day", "player_reputation_history", ["player_id", "day"])


def downgrade() -> None:
    op.drop_index("ix_prh_player_day", table_name="player_reputation_history")
    op.drop_index("ix_prh_day", table_name="player_reputation_history")
    op.drop_index("ix_prh_player_id", table_name="player_reputation_history")
    op.drop_table("player_reputation_history")

    op.drop_index("ix_prs_player_id", table_name="player_reputation_states")
    op.drop_table("player_reputation_states")
