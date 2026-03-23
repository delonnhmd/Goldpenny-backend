-- enable_rls.sql
-- Run this in Supabase → SQL Editor.
--
-- Enables Row Level Security on every application table.
-- Your FastAPI backend connects as the `postgres` superuser, which bypasses
-- RLS entirely — so no policies are needed and nothing will break.
-- Supabase's anon / authenticated roles will have zero access by default,
-- which is exactly what we want for a server-side-only backend.

ALTER TABLE public.alembic_version              ENABLE ROW LEVEL SECURITY;

-- ── Auth / Identity ───────────────────────────────────────────────────────────
ALTER TABLE public.users                        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.players                      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wallet_links                 ENABLE ROW LEVEL SECURITY;

-- ── Player state ───────────────────────────────────────────────────────────────
ALTER TABLE public.player_daily_states          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_inventory             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_reward_scores         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portfolios                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.debt_accounts                ENABLE ROW LEVEL SECURITY;

-- ── Stocks ────────────────────────────────────────────────────────────────────
ALTER TABLE public.stocks                       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sector_stocks                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sector_index                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_stock_holdings        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stock_price_histories        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stock_trades                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stock_trade_logs             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trades                       ENABLE ROW LEVEL SECURITY;

-- ── Baskets / Economy ─────────────────────────────────────────────────────────
ALTER TABLE public.baskets                      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.goods_baskets                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.basket_purchases             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.basket_price_history         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.basket_daily_prices          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.purchase_actions             ENABLE ROW LEVEL SECURITY;

-- ── Macro / Economy state ─────────────────────────────────────────────────────
ALTER TABLE public.macro_states                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.macro_daily_states           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.economy_state                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.economy_events               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.economy_history              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.game_states                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.day_logs                     ENABLE ROW LEVEL SECURITY;

-- ── Market / Marketplace ──────────────────────────────────────────────────────
ALTER TABLE public.market_listings              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.market_transactions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.market_fee_logs              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.market_trades                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stock_daily_prices           ENABLE ROW LEVEL SECURITY;

-- ── Housing ───────────────────────────────────────────────────────────────────
ALTER TABLE public.housing_regions              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_housings              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.housing_actions              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.housing_daily_snapshots      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.housing_payments             ENABLE ROW LEVEL SECURITY;

-- ── Business ──────────────────────────────────────────────────────────────────
ALTER TABLE public.businesses                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.business_types               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.business_actions             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.business_inventory           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.business_daily_snapshots     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.business_operations          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_businesses            ENABLE ROW LEVEL SECURITY;

-- ── Jobs ──────────────────────────────────────────────────────────────────────
ALTER TABLE public.job_definitions              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_actions                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_employment_states     ENABLE ROW LEVEL SECURITY;

-- ── Co-op Deals ───────────────────────────────────────────────────────────────
ALTER TABLE public.deal_templates               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coop_deals                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coop_deal_participants       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coop_deal_payouts            ENABLE ROW LEVEL SECURITY;

-- ── Firms (NPC layer) ─────────────────────────────────────────────────────────
ALTER TABLE public.firms                        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.firm_capacities              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.firm_policies                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.firm_ledger_entries          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.firm_balance_snapshots       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.market_share_states          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_openings                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.employment_contracts         ENABLE ROW LEVEL SECURITY;

-- ── Rewards / Tokens ─────────────────────────────────────────────────────────
ALTER TABLE public.reward_pools                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reward_ledgers               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reward_epochs                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.token_claims                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.token_claim_history          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.token_claim_allowances       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.claim_balances               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.claim_windows                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.claim_ledger                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.xgp_transactions             ENABLE ROW LEVEL SECURITY;

-- ── Contributions / Side income ───────────────────────────────────────────────
ALTER TABLE public.contribution_events          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contribution_snapshots       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.side_income_actions          ENABLE ROW LEVEL SECURITY;

-- ── Settlement ────────────────────────────────────────────────────────────────
ALTER TABLE public.daily_settlement_logs        ENABLE ROW LEVEL SECURITY;
