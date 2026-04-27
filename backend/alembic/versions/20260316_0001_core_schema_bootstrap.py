"""core schema bootstrap

Revision ID: 20260316_0001
Revises:
Create Date: 2026-03-16 00:01:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260316_0001"
down_revision = None
branch_labels = None
depends_on = None


def _inspector(bind):
    return sa.inspect(bind)


def _table_exists(bind, table_name: str) -> bool:
    return table_name in _inspector(bind).get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return column_name in {c["name"] for c in _inspector(bind).get_columns(table_name)}


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return any(ix["name"] == index_name for ix in _inspector(bind).get_indexes(table_name))


def _fk_exists(bind, table_name: str, fk_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return any(fk["name"] == fk_name for fk in _inspector(bind).get_foreign_keys(table_name))


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    if _table_exists(bind, table_name) and not _column_exists(bind, table_name, column.name):
        op.add_column(table_name, column)


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # Core base tables for clean-slate Supabase databases.
    # ------------------------------------------------------------------
    if not _table_exists(bind, "users"):
        op.create_table(
            "users",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("hashed_password", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("email", name="uq_users_email"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if not _table_exists(bind, "players"):
        op.create_table(
            "players",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("display_name", sa.String(length=80), nullable=True),
            sa.Column("region", sa.String(length=40), nullable=False, server_default="suburban"),
            sa.Column("cash", sa.Numeric(12, 2), nullable=False, server_default="1000"),
            sa.Column("bank_savings_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("debt_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("credit_score", sa.Integer(), nullable=False, server_default="650"),
            sa.Column("net_worth", sa.Numeric(14, 2), nullable=False, server_default="1000"),
            sa.Column("health", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("stress", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("hours_available", sa.Integer(), nullable=False, server_default="16"),
            sa.Column("reputation", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("fatigue", sa.Float(), nullable=False, server_default="0"),
            sa.Column("skill_level", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("main_job", sa.String(length=120), nullable=True),
            sa.Column("side_job", sa.String(length=120), nullable=True),
            sa.Column("main_job_hours_today", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("side_job_hours_today", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_hours_worked_today", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("work_actions_today", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_worked_day", sa.Integer(), nullable=True),
            sa.Column("last_settled_day", sa.Integer(), nullable=True),
            sa.Column("housing_region_id", sa.String(length=40), nullable=True),
            sa.Column("housing_stability", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("has_active_housing", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("account_created_day", sa.Integer(), nullable=True),
            sa.Column("lifetime_xgp_earned", sa.Float(), nullable=False, server_default="0"),
            sa.Column("completed_trades_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("marketplace_rating_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("successful_coop_deals_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_coop_deals_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("user_id", name="uq_players_user_id"),
        )
        op.create_index("ix_players_user_id", "players", ["user_id"], unique=True)

    if not _table_exists(bind, "player_daily_states"):
        op.create_table(
            "player_daily_states",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("day_number", sa.Integer(), nullable=False),
            sa.Column("worked_hours", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("gross_income_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("side_income_hours", sa.Numeric(12, 4), nullable=False, server_default="0"),
            sa.Column("side_income_gross_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("side_income_fuel_cost_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("side_income_net_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("total_spent_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("debt_payment_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("stock_realized_pnl_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("cash_end", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("stress_end", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("health_end", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("hours_available_start", sa.Integer(), nullable=False, server_default="24"),
            sa.Column("hours_available_end", sa.Integer(), nullable=False, server_default="24"),
            sa.Column("worked_main_job", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("did_settlement", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("stress_start", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("health_start", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("cash_start", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("essentials_units", sa.Numeric(12, 4), nullable=False, server_default="0"),
            sa.Column("protein_units", sa.Numeric(12, 4), nullable=False, server_default="0"),
            sa.Column("produce_units", sa.Numeric(12, 4), nullable=False, server_default="0"),
            sa.Column("convenience_units", sa.Numeric(12, 4), nullable=False, server_default="0"),
            sa.Column("needs_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
            sa.Column("needs_tier", sa.Text(), nullable=True),
            sa.Column("needs_evaluated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("food_quality_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
            sa.Column("survival_coverage_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
            sa.Column("housing_cost_paid", sa.Numeric(10, 2), nullable=False, server_default="0"),
            sa.Column("housing_region_id", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("player_id", "day_number", name="uq_player_daily_state_player_day"),
        )
        op.create_index("ix_player_daily_states_player_id", "player_daily_states", ["player_id"], unique=False)
        op.create_index("ix_player_daily_states_day_number", "player_daily_states", ["day_number"], unique=False)

    if not _table_exists(bind, "player_stock_holdings"):
        op.create_table(
            "player_stock_holdings",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("stock_id", sa.String(length=40), nullable=False),
            sa.Column("shares_owned", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("average_cost_basis", sa.Numeric(12, 4), nullable=False, server_default="0"),
            sa.Column("total_cost_basis", sa.Numeric(12, 4), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("player_id", "stock_id", name="uq_psh_player_stock"),
        )
        op.create_index("ix_player_stock_holdings_player_id", "player_stock_holdings", ["player_id"], unique=False)
        op.create_index("ix_player_stock_holdings_stock_id", "player_stock_holdings", ["stock_id"], unique=False)

    if not _table_exists(bind, "daily_settlement_logs"):
        op.create_table(
            "daily_settlement_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("day_number", sa.Integer(), nullable=False),
            sa.Column("income_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("expenses_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("side_income_net_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("stock_pnl_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("debt_paid_xgp", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("health_change", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("stress_change", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cash_after", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("summary_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("hours_before_reset", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("hours_after_reset", sa.Integer(), nullable=False, server_default="24"),
            sa.Column("stress_before", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("stress_after", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("health_before", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("health_after", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("cash_before", sa.Numeric(14, 4), nullable=False, server_default="0"),
            sa.Column("recovery_applied", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("needs_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
            sa.Column("needs_tier", sa.Text(), nullable=True),
            sa.Column("food_quality_modifier", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("stress_penalty_from_needs", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("health_modifier_from_needs", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("housing_region_id", sa.Text(), nullable=True),
            sa.Column("housing_cost_paid", sa.Numeric(10, 2), nullable=False, server_default="0"),
            sa.Column("housing_stress_modifier", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("side_income_hours", sa.Numeric(12, 4), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_daily_settlement_logs_player_id", "daily_settlement_logs", ["player_id"], unique=False)
        op.create_index("ix_daily_settlement_logs_day_number", "daily_settlement_logs", ["day_number"], unique=False)

    # ------------------------------------------------------------------
    # Additive updates on existing core tables (safe for live projects).
    # ------------------------------------------------------------------
    _add_column_if_missing(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    _add_column_if_missing("players", sa.Column("display_name", sa.String(length=80), nullable=True))
    _add_column_if_missing(
        "players",
        sa.Column("bank_savings_xgp", sa.Numeric(14, 4), server_default="0", nullable=False),
    )
    _add_column_if_missing(
        "players",
        sa.Column("debt_xgp", sa.Numeric(14, 4), server_default="0", nullable=False),
    )
    _add_column_if_missing(
        "players",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    _add_column_if_missing(
        "player_daily_states",
        sa.Column("worked_hours", sa.Integer(), server_default="0", nullable=False),
    )
    _add_column_if_missing(
        "player_daily_states",
        sa.Column("gross_income_xgp", sa.Numeric(14, 4), server_default="0", nullable=False),
    )
    _add_column_if_missing(
        "player_daily_states",
        sa.Column("debt_payment_xgp", sa.Numeric(14, 4), server_default="0", nullable=False),
    )
    _add_column_if_missing(
        "player_daily_states",
        sa.Column("stock_realized_pnl_xgp", sa.Numeric(14, 4), server_default="0", nullable=False),
    )

    _add_column_if_missing(
        "daily_settlement_logs",
        sa.Column("income_xgp", sa.Numeric(14, 4), server_default="0", nullable=False),
    )
    _add_column_if_missing(
        "daily_settlement_logs",
        sa.Column("expenses_xgp", sa.Numeric(14, 4), server_default="0", nullable=False),
    )
    _add_column_if_missing(
        "daily_settlement_logs",
        sa.Column("stock_pnl_xgp", sa.Numeric(14, 4), server_default="0", nullable=False),
    )
    _add_column_if_missing(
        "daily_settlement_logs",
        sa.Column("debt_paid_xgp", sa.Numeric(14, 4), server_default="0", nullable=False),
    )
    _add_column_if_missing(
        "daily_settlement_logs",
        sa.Column("health_change", sa.Integer(), server_default="0", nullable=False),
    )
    _add_column_if_missing(
        "daily_settlement_logs",
        sa.Column("stress_change", sa.Integer(), server_default="0", nullable=False),
    )

    if (
        _table_exists(bind, "player_stock_holdings")
        and _table_exists(bind, "players")
        and not _fk_exists(bind, "player_stock_holdings", "fk_player_stock_holdings_player_id_players")
    ):
        op.create_foreign_key(
            "fk_player_stock_holdings_player_id_players",
            "player_stock_holdings",
            "players",
            ["player_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # ------------------------------------------------------------------
    # New core schema tables for MVP bootstrap.
    # ------------------------------------------------------------------
    if not _table_exists(bind, "macro_daily_states"):
        op.create_table(
            "macro_daily_states",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("day", sa.Integer(), nullable=False),
            sa.Column("inflation_rate", sa.Numeric(8, 4), nullable=False, server_default="2.0"),
            sa.Column("interest_rate", sa.Numeric(8, 4), nullable=False, server_default="4.0"),
            sa.Column("unemployment_rate", sa.Numeric(8, 4), nullable=False, server_default="5.0"),
            sa.Column("oil_index", sa.Numeric(10, 4), nullable=False, server_default="100.0"),
            sa.Column("consumer_confidence", sa.Numeric(8, 4), nullable=False, server_default="50.0"),
            sa.Column("supply_chain_stress", sa.Numeric(8, 4), nullable=False, server_default="0.0"),
            sa.Column("event_headline", sa.String(length=200), nullable=True),
            sa.Column("event_summary", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("day", name="uq_macro_daily_states_day"),
        )
        op.create_index("ix_macro_daily_states_day", "macro_daily_states", ["day"], unique=False)

    if not _table_exists(bind, "basket_daily_prices"):
        op.create_table(
            "basket_daily_prices",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("day", sa.Integer(), nullable=False),
            sa.Column("basket_type", sa.String(length=20), nullable=False),
            sa.Column("price_index", sa.Numeric(12, 4), nullable=False),
            sa.Column("daily_change_pct", sa.Numeric(8, 4), nullable=False, server_default="0"),
            sa.Column("supply_pressure", sa.Numeric(8, 4), nullable=False, server_default="1.0"),
            sa.Column("demand_pressure", sa.Numeric(8, 4), nullable=False, server_default="1.0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.CheckConstraint(
                "basket_type IN ('essentials','protein','produce','convenience')",
                name="ck_basket_daily_prices_basket_type",
            ),
            sa.UniqueConstraint("day", "basket_type", name="uq_basket_daily_price_day_type"),
        )
        op.create_index("ix_basket_daily_prices_day", "basket_daily_prices", ["day"], unique=False)
        op.create_index(
            "ix_basket_daily_prices_basket_type",
            "basket_daily_prices",
            ["basket_type"],
            unique=False,
        )

    if not _table_exists(bind, "stock_daily_prices"):
        op.create_table(
            "stock_daily_prices",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("day", sa.Integer(), nullable=False),
            sa.Column("ticker", sa.String(length=20), nullable=False),
            sa.Column("sector", sa.String(length=40), nullable=False),
            sa.Column("open_price", sa.Numeric(14, 4), nullable=False),
            sa.Column("close_price", sa.Numeric(14, 4), nullable=False),
            sa.Column("daily_change_pct", sa.Numeric(8, 4), nullable=False),
            sa.Column("macro_impact", sa.Numeric(8, 4), nullable=False, server_default="0"),
            sa.Column("noise_component", sa.Numeric(8, 4), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("day", "ticker", name="uq_stock_daily_price_day_ticker"),
        )
        op.create_index("ix_stock_daily_prices_day", "stock_daily_prices", ["day"], unique=False)
        op.create_index("ix_stock_daily_prices_ticker", "stock_daily_prices", ["ticker"], unique=False)

    if not _table_exists(bind, "job_definitions"):
        op.create_table(
            "job_definitions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("job_code", sa.String(length=60), nullable=False),
            sa.Column("title", sa.String(length=120), nullable=False),
            sa.Column("base_monthly_pay_xgp", sa.Numeric(14, 2), nullable=False),
            sa.Column("stability_pct", sa.Numeric(6, 2), nullable=False, server_default="0"),
            sa.Column("growth_pct", sa.Numeric(6, 2), nullable=False, server_default="0"),
            sa.Column("stress_pct", sa.Numeric(6, 2), nullable=False, server_default="0"),
            sa.Column("promotion_threshold", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("job_code", name="uq_job_definitions_job_code"),
        )
        op.create_index("ix_job_definitions_job_code", "job_definitions", ["job_code"], unique=True)

    if not _table_exists(bind, "player_employment_states"):
        op.create_table(
            "player_employment_states",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("day", sa.Integer(), nullable=False),
            sa.Column("current_job_code", sa.String(length=60), nullable=True),
            sa.Column("skill_level", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("monthly_pay_xgp", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("employed_flag", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("layoff_risk_pct", sa.Numeric(6, 2), nullable=False, server_default="0"),
            sa.Column("productivity_modifier", sa.Numeric(8, 4), nullable=False, server_default="1.0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["current_job_code"], ["job_definitions.job_code"], ondelete="SET NULL"),
        )
        op.create_index(
            "ix_player_employment_states_player_id",
            "player_employment_states",
            ["player_id"],
            unique=False,
        )
        op.create_index("ix_player_employment_states_day", "player_employment_states", ["day"], unique=False)
        op.create_index(
            "ix_player_employment_states_current_job_code",
            "player_employment_states",
            ["current_job_code"],
            unique=False,
        )

    if not _table_exists(bind, "stock_trade_logs"):
        op.create_table(
            "stock_trade_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("day", sa.Integer(), nullable=False),
            sa.Column("ticker", sa.String(length=20), nullable=False),
            sa.Column("side", sa.String(length=10), nullable=False),
            sa.Column("shares", sa.Integer(), nullable=False),
            sa.Column("price_per_share", sa.Numeric(14, 4), nullable=False),
            sa.Column("gross_amount_xgp", sa.Numeric(14, 4), nullable=False),
            sa.Column("fee_amount_xgp", sa.Numeric(14, 4), nullable=False),
            sa.Column("net_amount_xgp", sa.Numeric(14, 4), nullable=False),
            sa.Column("realized_pnl_xgp", sa.Numeric(14, 4), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.CheckConstraint("side IN ('buy','sell')", name="ck_stock_trade_logs_side"),
            sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_stock_trade_logs_player_id", "stock_trade_logs", ["player_id"], unique=False)
        op.create_index("ix_stock_trade_logs_day", "stock_trade_logs", ["day"], unique=False)
        op.create_index("ix_stock_trade_logs_ticker", "stock_trade_logs", ["ticker"], unique=False)
        op.create_index("ix_stock_trade_logs_side", "stock_trade_logs", ["side"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    for table_name in [
        "stock_trade_logs",
        "player_employment_states",
        "job_definitions",
        "stock_daily_prices",
        "basket_daily_prices",
        "macro_daily_states",
    ]:
        if _table_exists(bind, table_name):
            op.drop_table(table_name)

    # Drop additive columns if present.
    for table_name, column_name in [
        ("daily_settlement_logs", "stress_change"),
        ("daily_settlement_logs", "health_change"),
        ("daily_settlement_logs", "debt_paid_xgp"),
        ("daily_settlement_logs", "stock_pnl_xgp"),
        ("daily_settlement_logs", "expenses_xgp"),
        ("daily_settlement_logs", "income_xgp"),
        ("player_daily_states", "stock_realized_pnl_xgp"),
        ("player_daily_states", "debt_payment_xgp"),
        ("player_daily_states", "gross_income_xgp"),
        ("player_daily_states", "worked_hours"),
        ("players", "updated_at"),
        ("players", "debt_xgp"),
        ("players", "bank_savings_xgp"),
        ("players", "display_name"),
        ("users", "updated_at"),
    ]:
        if _column_exists(bind, table_name, column_name):
            op.drop_column(table_name, column_name)

    if _fk_exists(bind, "player_stock_holdings", "fk_player_stock_holdings_player_id_players"):
        op.drop_constraint(
            "fk_player_stock_holdings_player_id_players",
            "player_stock_holdings",
            type_="foreignkey",
        )
