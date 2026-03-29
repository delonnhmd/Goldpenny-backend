"""enable row level security on core public tables

Revision ID: 20260316_0002_enable_rls
Revises: 20260316_0001
Create Date: 2026-03-16 00:02:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260316_0002_enable_rls"
down_revision = "20260316_0001"
branch_labels = None
depends_on = None


CORE_PUBLIC_TABLES = (
    "alembic_version",
    "users",
    "players",
    "player_daily_states",
    "player_stock_holdings",
    "daily_settlement_logs",
    "macro_daily_states",
    "basket_daily_prices",
    "stock_daily_prices",
    "player_employment_states",
    "job_definitions",
    "stock_trade_logs",
)


def upgrade() -> None:
    """Enable deny-by-default RLS posture for core public schema tables."""
    for table_name in CORE_PUBLIC_TABLES:
        op.execute(f'ALTER TABLE IF EXISTS public."{table_name}" ENABLE ROW LEVEL SECURITY;')


def downgrade() -> None:
    """Disable RLS for rollback scenarios."""
    for table_name in CORE_PUBLIC_TABLES:
        op.execute(f'ALTER TABLE IF EXISTS public."{table_name}" DISABLE ROW LEVEL SECURITY;')
