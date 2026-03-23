"""Create player_wealth_states and player_wealth_trend_history tables (Step 39).

Revision ID: 20260321_0015_wealth_progression
Revises: 20260320_0014_debt_behavior
Create Date: 2026-03-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260321_0015_wealth_progression"
down_revision: Union[str, Sequence[str], None] = "20260320_0014_debt_behavior"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # player_wealth_states — rolling per-player wealth profile
    op.create_table(
        "player_wealth_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cash_reserve_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("savings_reserve_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("investable_surplus_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("debt_drag_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("net_worth_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("liquid_asset_value_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("market_asset_value_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("business_equity_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("total_asset_value_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("total_debt_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("wealth_momentum_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("stability_before_growth_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("buffer_days", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("wealth_phase_label", sa.String(20), nullable=False, server_default="fragile"),
        sa.Column("asset_growth_trend", sa.String(20), nullable=False, server_default="stable"),
        sa.Column("safe_to_save_label", sa.String(30), nullable=False, server_default="not_safe"),
        sa.Column("safe_to_invest_label", sa.String(30), nullable=False, server_default="not_safe"),
        sa.Column("experience_phase", sa.String(20), nullable=False, server_default="onboarding"),
        sa.Column("days_in_phase", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("softening_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("top_growth_driver", sa.String(80), nullable=True),
        sa.Column("top_drag_driver", sa.String(80), nullable=True),
        sa.Column("false_growth_detected", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("false_growth_warnings_json", sa.Text(), nullable=True),
        sa.Column("planning_insights_json", sa.Text(), nullable=True),
        sa.Column("debug_json", sa.Text(), nullable=True),
        sa.Column("last_updated_on", sa.Integer(), nullable=True),
        sa.Column("last_updated_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", name="uq_player_wealth_state_player"),
    )
    op.create_index("ix_pws_player_id", "player_wealth_states", ["player_id"])

    # player_wealth_trend_history — daily snapshot rows
    op.create_table(
        "player_wealth_trend_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("net_worth_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("total_asset_value_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("total_debt_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("debt_drag_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("investable_surplus_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("market_asset_value_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("business_equity_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("wealth_momentum_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("stability_before_growth_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("buffer_days", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("wealth_phase_label", sa.String(20), nullable=False, server_default="fragile"),
        sa.Column("asset_growth_trend", sa.String(20), nullable=False, server_default="stable"),
        sa.Column("experience_phase", sa.String(20), nullable=False, server_default="onboarding"),
        sa.Column("false_growth_flag", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pwth_player_id", "player_wealth_trend_history", ["player_id"])
    op.create_index("ix_pwth_day", "player_wealth_trend_history", ["day"])
    op.create_index("ix_pwth_player_day", "player_wealth_trend_history", ["player_id", "day"])


def downgrade() -> None:
    op.drop_index("ix_pwth_player_day", table_name="player_wealth_trend_history")
    op.drop_index("ix_pwth_day", table_name="player_wealth_trend_history")
    op.drop_index("ix_pwth_player_id", table_name="player_wealth_trend_history")
    op.drop_table("player_wealth_trend_history")

    op.drop_index("ix_pws_player_id", table_name="player_wealth_states")
    op.drop_table("player_wealth_states")
