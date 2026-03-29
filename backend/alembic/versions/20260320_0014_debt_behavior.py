"""Create player_debt_behavior_states and player_debt_trend_history tables (Step 38).

Revision ID: 20260320_0014_debt_behavior
Revises: 20260317_0013_event_chains
Create Date: 2026-03-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260320_0014_debt_behavior"
down_revision: Union[str, Sequence[str], None] = "20260317_0013_event_chains"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # player_debt_behavior_states — rolling per-player snapshot
    op.create_table(
        "player_debt_behavior_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("debt_dependency_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("payment_stack_pressure_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("borrowing_frequency_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("financial_stability_score", sa.Numeric(8, 4), nullable=False, server_default="100"),
        sa.Column("trend_direction", sa.String(20), nullable=False, server_default="stable"),
        sa.Column("debt_state_label", sa.String(30), nullable=False, server_default="controlled"),
        sa.Column("spiral_risk_label", sa.String(20), nullable=False, server_default="low"),
        sa.Column("recovery_stage", sa.String(20), nullable=False, server_default="none"),
        sa.Column("top_risk_driver", sa.String(80), nullable=True),
        sa.Column("top_recovery_driver", sa.String(80), nullable=True),
        sa.Column("planning_warnings_json", sa.Text(), nullable=True),
        sa.Column("debug_json", sa.Text(), nullable=True),
        sa.Column("last_updated_on", sa.Integer(), nullable=True),
        sa.Column("last_updated_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", name="uq_pdbs_player"),
    )
    op.create_index("ix_pdbs_player_id", "player_debt_behavior_states", ["player_id"])

    # player_debt_trend_history — append-only daily rows
    op.create_table(
        "player_debt_trend_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("debt_dependency_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("payment_stack_pressure_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("borrowing_frequency_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("financial_stability_score", sa.Numeric(8, 4), nullable=False, server_default="100"),
        sa.Column("trend_direction", sa.String(20), nullable=False, server_default="stable"),
        sa.Column("debt_state_label", sa.String(30), nullable=False, server_default="controlled"),
        sa.Column("spiral_risk_label", sa.String(20), nullable=False, server_default="low"),
        sa.Column("recovery_stage", sa.String(20), nullable=False, server_default="none"),
        sa.Column("composite_risk_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("trigger_signals_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pdth_player_id", "player_debt_trend_history", ["player_id"])
    op.create_index("ix_pdth_day", "player_debt_trend_history", ["day"])


def downgrade() -> None:
    op.drop_index("ix_pdth_day", table_name="player_debt_trend_history")
    op.drop_index("ix_pdth_player_id", table_name="player_debt_trend_history")
    op.drop_table("player_debt_trend_history")
    op.drop_index("ix_pdbs_player_id", table_name="player_debt_behavior_states")
    op.drop_table("player_debt_behavior_states")
