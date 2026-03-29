-- drop_legacy_tables.sql
-- ============================================================
-- LEGACY TABLE CLEANUP — REVIEW CAREFULLY BEFORE RUNNING
-- ============================================================
-- These tables are superseded by newer equivalents.
-- Each table was replaced as the schema evolved during dev.
--
-- SAFETY CHECKS — run these first to confirm all are empty:
--
--   SELECT 'baskets',           COUNT(*) FROM public.baskets;
--   SELECT 'stocks',            COUNT(*) FROM public.stocks;
--   SELECT 'portfolios',        COUNT(*) FROM public.portfolios;
--   SELECT 'trades',            COUNT(*) FROM public.trades;
--   SELECT 'market_transactions',COUNT(*) FROM public.market_transactions;
--   SELECT 'stock_trade_logs',  COUNT(*) FROM public.stock_trade_logs;
--   SELECT 'business_actions',  COUNT(*) FROM public.business_actions;
--
-- If any are non-empty, migrate the data before dropping.
-- ============================================================

-- Old stock-holdings system (Step 6 era)
-- Superseded by: player_stock_holdings
DROP TABLE IF EXISTS public.baskets CASCADE;

-- Old stock-definition table (Step 6 era)
-- Superseded by: sector_stocks
DROP TABLE IF EXISTS public.stocks CASCADE;

-- Old portfolio tracker (Step 6 era)
-- Superseded by: player_stock_holdings
DROP TABLE IF EXISTS public.portfolios CASCADE;

-- Old stock-trade log (Step 6 era)
-- Superseded by: stock_trades
DROP TABLE IF EXISTS public.trades CASCADE;

-- Old marketplace trade log (Step 8 era)
-- Superseded by: market_trades
DROP TABLE IF EXISTS public.market_transactions CASCADE;

-- Old stock-trade detail log (Step 10 era)
-- Superseded by: stock_trades (merged schema)
DROP TABLE IF EXISTS public.stock_trade_logs CASCADE;

-- Old business-operation log (Step 9 era)
-- Superseded by: business_operations
DROP TABLE IF EXISTS public.business_actions CASCADE;
