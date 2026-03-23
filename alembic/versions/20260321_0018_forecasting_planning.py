"""Step 42 — Forecasting, Planning Intelligence, and Forward Projection Layer.

Revision ID:  20260321_0018_forecasting_planning
Revises:      20260321_0017_contract_timing
Create Date:  2026-03-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260321_0018_forecasting_planning"
down_revision = "20260321_0017_contract_timing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_forecast_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("forecast_horizon_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("generated_on_day", sa.Integer(), nullable=True),
        sa.Column("generated_on_date", sa.Date(), nullable=True),
        sa.Column("overall_outlook_label", sa.String(20), nullable=False, server_default="stable"),
        sa.Column("near_term_risk_label", sa.String(20), nullable=False, server_default="low"),
        sa.Column("delinquency_risk_label", sa.String(20), nullable=False, server_default="low"),
        sa.Column("cash_gap_risk_label", sa.String(20), nullable=False, server_default="none"),
        sa.Column("debt_spiral_risk_label", sa.String(20), nullable=False, server_default="low"),
        sa.Column("liquidity_low_point_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("projected_delinquency_risk_day", sa.Integer(), nullable=True),
        sa.Column("days_until_next_problem", sa.Integer(), nullable=True),
        sa.Column("confidence_level", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("guidance_label", sa.String(30), nullable=False, server_default="monitor"),
        sa.Column("top_recommendation", sa.String(120), nullable=True),
        sa.Column("avoid_action", sa.String(120), nullable=True),
        sa.Column("next_major_risk_event", sa.String(80), nullable=True),
        sa.Column("best_stabilizing_action", sa.String(120), nullable=True),
        sa.Column("projected_cash_curve_json", sa.Text(), nullable=True),
        sa.Column("risk_signals_json", sa.Text(), nullable=True),
        sa.Column("debug_json", sa.Text(), nullable=True),
        sa.Column("last_updated_on", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", name="uq_pfs_player"),
    )
    op.create_index("ix_pfs_player_id", "player_forecast_snapshots", ["player_id"])
    op.create_index("ix_pfs_generated_on_day", "player_forecast_snapshots", ["generated_on_day"])


def downgrade() -> None:
    op.drop_index("ix_pfs_generated_on_day", table_name="player_forecast_snapshots")
    op.drop_index("ix_pfs_player_id", table_name="player_forecast_snapshots")
    op.drop_table("player_forecast_snapshots")
