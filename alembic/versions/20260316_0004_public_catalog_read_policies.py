"""Add SELECT policies for public catalog and game-state tables.

Revision ID: 20260316_0004
Revises: 20260316_0003
Create Date: 2026-03-16 00:00:00.000000

Security design
---------------
RLS is already ENABLED on every table.  With RLS on and zero policies Postgres
denies all rows to anon/authenticated — that is the CORRECT secure default for
private tables.  We add SELECT policies only for the subset of tables that are
genuinely public: static catalog data (stocks, baskets, housing, business types,
deals) and shared game-state data (economy, sector indices, firms, listings).

Tables that get public SELECT (anon + authenticated):
  Catalog / reference
    goods_baskets         — basket definitions (essentials, protein, …)
    sector_stocks         — stock definitions (GP Energy, GP Tech, …)
    housing_regions       — housing zone catalog
    business_types        — business type catalog
    deal_templates        — co-op deal template catalog
    job_openings          — public job board (firms posting open positions)

  Game / economy state (read-only, non-sensitive)
    economy_state         — current macro economy snapshot
    economy_events        — public economic event log
    economy_history       — historical economy snapshots
    game_states           — game-wide state flags
    day_logs              — daily game log (settlements, events)
    sector_index          — sector performance indices
    macro_states          — legacy macro state (kept until table is dropped)

  Public market / firm data
    firms                 — public firm directory
    coop_deals            — public co-op deal listings
    market_listings       — active marketplace listings
    market_share_states   — public market-share data

Tables intentionally LEFT locked (no policy = deny all):
  Player-private data
    users, players, player_daily_states, player_stock_holdings,
    player_employment_states, daily_settlement_logs, stock_trade_logs,
    stock_trades, debt_accounts, employment_contracts, player_housings,
    player_businesses, player_inventory, player_reward_scores,
    purchase_actions, housing_actions, job_actions, contribution_events,
    contribution_snapshots, wallet_links, token_claims, token_claim_history,
    token_claim_allowances, xgp_transactions, claim_balances, claim_ledger,
    claim_windows, reward_ledgers, reward_epochs, reward_pools,
    side_income_actions, basket_purchases, business_daily_snapshots,
    housing_daily_snapshots, housing_payments, business_inventory,
    business_operations, firm_balance_snapshots, firm_ledger_entries,
    firm_capacities, firm_policies, coop_deal_participants,
    coop_deal_payouts, market_fee_logs, market_trades, market_transactions

  Legacy tables (scheduled for DROP via drop_legacy_tables.sql)
    baskets, stocks, portfolios, trades, basket_price_history,
    stock_price_histories, business_actions

  System table — never expose
    alembic_version
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# ---------------------------------------------------------------------------
revision: str = "20260316_0004"
down_revision: Union[str, Sequence[str], None] = "20260316_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
# ---------------------------------------------------------------------------

# Only tables that are genuinely public — catalog / reference / game-state.
_PUBLIC_READ_TABLES = [
    # --- static catalog / reference data ---
    "goods_baskets",
    "sector_stocks",
    "housing_regions",
    "business_types",
    "deal_templates",
    "job_openings",
    # --- game / economy state ---
    "economy_state",
    "economy_events",
    "economy_history",
    "game_states",
    "day_logs",
    "sector_index",
    "macro_states",
    # --- public market / firm data ---
    "firms",
    "coop_deals",
    "market_listings",
    "market_share_states",
]


def _policy_name(table: str) -> str:
    return f"public read {table}"


def _policy_exists(conn, table: str, name: str) -> bool:
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_policies "
            "WHERE schemaname = 'public' "
            "  AND tablename  = :tbl "
            "  AND policyname = :pol"
        ),
        {"tbl": table, "pol": name},
    ).fetchone()
    return row is not None


def _create_policy_if_not_exists(conn, table: str) -> None:
    name = _policy_name(table)
    if _policy_exists(conn, table, name):
        print(f"  [skip] already exists: {name!r} on {table}")
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
    print(f"  [ok]   created: {name!r} on {table}")


def _drop_policy_if_exists(conn, table: str) -> None:
    name = _policy_name(table)
    if not _policy_exists(conn, table, name):
        print(f"  [skip] not found: {name!r} on {table}")
        return
    conn.execute(sa.text(f'DROP POLICY "{name}" ON public.{table}'))
    print(f"  [ok]   dropped: {name!r} on {table}")


def upgrade() -> None:
    conn = op.get_bind()
    for table in _PUBLIC_READ_TABLES:
        _create_policy_if_not_exists(conn, table)


def downgrade() -> None:
    conn = op.get_bind()
    for table in reversed(_PUBLIC_READ_TABLES):
        _drop_policy_if_exists(conn, table)
