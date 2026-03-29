"""Add public read-only RLS policies for market data tables.

Revision ID: 20260316_0003
Revises: 85854026afad
Create Date: 2026-03-16 00:00:00.000000

Context
-------
Row Level Security (RLS) is already ENABLED on all public tables via the
preceding migration.  Supabase reports "RLS enabled but no policy" warnings for
tables that have RLS on but zero policies — Postgres therefore denies every row
to every non-superuser role by default.

This migration adds **read-only SELECT policies** for the four market-data
tables that are intentionally public:

  macro_daily_states  — macro-economic daily snapshots (interest, inflation …)
  basket_daily_prices — goods-basket inflation history
  stock_daily_prices  — sector stock OHLC history
  job_definitions     — static job catalogue (title, pay, stress …)

Design decisions
----------------
* Only SELECT is granted — INSERT/UPDATE/DELETE remain blocked for anon/
  authenticated roles; the FastAPI backend (postgres superuser) still writes
  freely because superusers bypass RLS entirely.
* Player/account tables (users, players, player_daily_states,
  player_stock_holdings, player_employment_states, daily_settlement_logs,
  stock_trade_logs …) are intentionally left without policies so they remain
  inaccessible over the PostgREST/anon path.  All player data must be read
  through the authenticated FastAPI routes.
* Policies are created with IF NOT EXISTS semantics via a helper that checks
  pg_policies first — safe to re-run if the migration has already been applied
  manually.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "20260316_0003"
down_revision: Union[str, Sequence[str], None] = "85854026afad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# Tables that get public SELECT policies
# ---------------------------------------------------------------------------
_PUBLIC_READ_TABLES = [
    "macro_daily_states",
    "basket_daily_prices",
    "stock_daily_prices",
    "job_definitions",
]


def _policy_name(table: str) -> str:
    return f"public read {table}"


def _create_policy_if_not_exists(conn, table: str) -> None:
    """Create a SELECT policy only when it does not already exist.

    Checks pg_policies so the migration is safe to run even if the policy was
    previously added manually (e.g. via Supabase SQL Editor).
    """
    name = _policy_name(table)
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_policies "
            "WHERE schemaname = 'public' "
            "  AND tablename  = :tbl "
            "  AND policyname = :pol"
        ),
        {"tbl": table, "pol": name},
    ).fetchone()

    if exists:
        print(f"  [skip] policy already exists: {name!r} on {table}")
        return

    conn.execute(
        sa.text(
            f'CREATE POLICY "{name}" '
            f"ON public.{table} "
            f"FOR SELECT "
            f"TO anon, authenticated "
            f"USING (true)"
        )
    )
    print(f"  [ok]   created policy: {name!r} on {table}")


def _drop_policy_if_exists(conn, table: str) -> None:
    """Drop the SELECT policy only when it exists."""
    name = _policy_name(table)
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_policies "
            "WHERE schemaname = 'public' "
            "  AND tablename  = :tbl "
            "  AND policyname = :pol"
        ),
        {"tbl": table, "pol": name},
    ).fetchone()

    if not exists:
        print(f"  [skip] policy not found (already removed?): {name!r} on {table}")
        return

    conn.execute(sa.text(f'DROP POLICY "{name}" ON public.{table}'))
    print(f"  [ok]   dropped policy: {name!r} on {table}")


# ---------------------------------------------------------------------------
# Upgrade / downgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    """Add public read-only SELECT policies for market data tables."""
    conn = op.get_bind()
    for table in _PUBLIC_READ_TABLES:
        _create_policy_if_not_exists(conn, table)


def downgrade() -> None:
    """Remove the public read-only SELECT policies added in upgrade()."""
    conn = op.get_bind()
    for table in reversed(_PUBLIC_READ_TABLES):
        _drop_policy_if_exists(conn, table)
