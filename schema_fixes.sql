-- schema_fixes.sql
-- Run in Supabase SQL Editor (PostgreSQL).
-- Adds missing UNIQUE and FK constraints in an idempotent way.

-- 1) UNIQUE constraints on logical-key columns

DO $$
BEGIN
    IF to_regclass('public.sector_stocks') IS NOT NULL
       AND NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'uq_sector_stocks_stock_id'
              AND conrelid = 'public.sector_stocks'::regclass
       ) THEN
        BEGIN
            ALTER TABLE public.sector_stocks
                ADD CONSTRAINT uq_sector_stocks_stock_id UNIQUE (stock_id);
        EXCEPTION
            WHEN unique_violation THEN
                RAISE WARNING 'Skipped uq_sector_stocks_stock_id: duplicate stock_id values exist.';
        END;
    END IF;
END $$;

DO $$
BEGIN
    IF to_regclass('public.business_types') IS NOT NULL
       AND NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'uq_business_types_business_id'
              AND conrelid = 'public.business_types'::regclass
       ) THEN
        BEGIN
            ALTER TABLE public.business_types
                ADD CONSTRAINT uq_business_types_business_id UNIQUE (business_id);
        EXCEPTION
            WHEN unique_violation THEN
                RAISE WARNING 'Skipped uq_business_types_business_id: duplicate business_id values exist.';
        END;
    END IF;
END $$;

DO $$
BEGIN
    IF to_regclass('public.housing_regions') IS NOT NULL
       AND NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'uq_housing_regions_region_id'
              AND conrelid = 'public.housing_regions'::regclass
       ) THEN
        BEGIN
            ALTER TABLE public.housing_regions
                ADD CONSTRAINT uq_housing_regions_region_id UNIQUE (region_id);
        EXCEPTION
            WHEN unique_violation THEN
                RAISE WARNING 'Skipped uq_housing_regions_region_id: duplicate region_id values exist.';
        END;
    END IF;
END $$;

-- 2) Missing FK: debt_accounts -> players

DO $$
BEGIN
    IF to_regclass('public.debt_accounts') IS NOT NULL
       AND to_regclass('public.players') IS NOT NULL
       AND NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'debt_accounts_player_id_fkey'
              AND conrelid = 'public.debt_accounts'::regclass
       ) THEN
        BEGIN
            ALTER TABLE public.debt_accounts
                ADD CONSTRAINT debt_accounts_player_id_fkey
                FOREIGN KEY (player_id) REFERENCES public.players(id);
        EXCEPTION
            WHEN foreign_key_violation THEN
                RAISE WARNING 'Skipped debt_accounts_player_id_fkey: orphan debt_accounts.player_id rows exist.';
        END;
    END IF;
END $$;

-- 3) Missing FKs: firm layer tables -> firms

DO $$
BEGIN
    IF to_regclass('public.firm_balance_snapshots') IS NOT NULL
       AND to_regclass('public.firms') IS NOT NULL
       AND NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'firm_balance_snapshots_firm_id_fkey'
              AND conrelid = 'public.firm_balance_snapshots'::regclass
       ) THEN
        BEGIN
            ALTER TABLE public.firm_balance_snapshots
                ADD CONSTRAINT firm_balance_snapshots_firm_id_fkey
                FOREIGN KEY (firm_id) REFERENCES public.firms(id);
        EXCEPTION
            WHEN foreign_key_violation THEN
                RAISE WARNING 'Skipped firm_balance_snapshots_firm_id_fkey: orphan firm_id rows exist.';
        END;
    END IF;
END $$;

DO $$
BEGIN
    IF to_regclass('public.firm_capacities') IS NOT NULL
       AND to_regclass('public.firms') IS NOT NULL
       AND NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'firm_capacities_firm_id_fkey'
              AND conrelid = 'public.firm_capacities'::regclass
       ) THEN
        BEGIN
            ALTER TABLE public.firm_capacities
                ADD CONSTRAINT firm_capacities_firm_id_fkey
                FOREIGN KEY (firm_id) REFERENCES public.firms(id);
        EXCEPTION
            WHEN foreign_key_violation THEN
                RAISE WARNING 'Skipped firm_capacities_firm_id_fkey: orphan firm_id rows exist.';
        END;
    END IF;
END $$;

DO $$
BEGIN
    IF to_regclass('public.firm_ledger_entries') IS NOT NULL
       AND to_regclass('public.firms') IS NOT NULL
       AND NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'firm_ledger_entries_firm_id_fkey'
              AND conrelid = 'public.firm_ledger_entries'::regclass
       ) THEN
        BEGIN
            ALTER TABLE public.firm_ledger_entries
                ADD CONSTRAINT firm_ledger_entries_firm_id_fkey
                FOREIGN KEY (firm_id) REFERENCES public.firms(id);
        EXCEPTION
            WHEN foreign_key_violation THEN
                RAISE WARNING 'Skipped firm_ledger_entries_firm_id_fkey: orphan firm_id rows exist.';
        END;
    END IF;
END $$;

DO $$
BEGIN
    IF to_regclass('public.firm_policies') IS NOT NULL
       AND to_regclass('public.firms') IS NOT NULL
       AND NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'firm_policies_firm_id_fkey'
              AND conrelid = 'public.firm_policies'::regclass
       ) THEN
        BEGIN
            ALTER TABLE public.firm_policies
                ADD CONSTRAINT firm_policies_firm_id_fkey
                FOREIGN KEY (firm_id) REFERENCES public.firms(id);
        EXCEPTION
            WHEN foreign_key_violation THEN
                RAISE WARNING 'Skipped firm_policies_firm_id_fkey: orphan firm_id rows exist.';
        END;
    END IF;
END $$;

DO $$
BEGIN
    IF to_regclass('public.employment_contracts') IS NOT NULL
       AND to_regclass('public.firms') IS NOT NULL
       AND NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'employment_contracts_firm_id_fkey'
              AND conrelid = 'public.employment_contracts'::regclass
       ) THEN
        BEGIN
            ALTER TABLE public.employment_contracts
                ADD CONSTRAINT employment_contracts_firm_id_fkey
                FOREIGN KEY (firm_id) REFERENCES public.firms(id);
        EXCEPTION
            WHEN foreign_key_violation THEN
                RAISE WARNING 'Skipped employment_contracts_firm_id_fkey: orphan firm_id rows exist.';
        END;
    END IF;
END $$;

DO $$
BEGIN
    IF to_regclass('public.job_openings') IS NOT NULL
       AND to_regclass('public.firms') IS NOT NULL
       AND NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'job_openings_firm_id_fkey'
              AND conrelid = 'public.job_openings'::regclass
       ) THEN
        BEGIN
            ALTER TABLE public.job_openings
                ADD CONSTRAINT job_openings_firm_id_fkey
                FOREIGN KEY (firm_id) REFERENCES public.firms(id);
        EXCEPTION
            WHEN foreign_key_violation THEN
                RAISE WARNING 'Skipped job_openings_firm_id_fkey: orphan firm_id rows exist.';
        END;
    END IF;
END $$;

-- 4) Missing FKs: co-op tables -> coop_deals

DO $$
BEGIN
    IF to_regclass('public.coop_deal_participants') IS NOT NULL
       AND to_regclass('public.coop_deals') IS NOT NULL
       AND NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'coop_deal_participants_deal_id_fkey'
              AND conrelid = 'public.coop_deal_participants'::regclass
       ) THEN
        BEGIN
            ALTER TABLE public.coop_deal_participants
                ADD CONSTRAINT coop_deal_participants_deal_id_fkey
                FOREIGN KEY (deal_id) REFERENCES public.coop_deals(id);
        EXCEPTION
            WHEN foreign_key_violation THEN
                RAISE WARNING 'Skipped coop_deal_participants_deal_id_fkey: orphan deal_id rows exist.';
        END;
    END IF;
END $$;

DO $$
BEGIN
    IF to_regclass('public.coop_deal_payouts') IS NOT NULL
       AND to_regclass('public.coop_deals') IS NOT NULL
       AND NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'coop_deal_payouts_deal_id_fkey'
              AND conrelid = 'public.coop_deal_payouts'::regclass
       ) THEN
        BEGIN
            ALTER TABLE public.coop_deal_payouts
                ADD CONSTRAINT coop_deal_payouts_deal_id_fkey
                FOREIGN KEY (deal_id) REFERENCES public.coop_deals(id);
        EXCEPTION
            WHEN foreign_key_violation THEN
                RAISE WARNING 'Skipped coop_deal_payouts_deal_id_fkey: orphan deal_id rows exist.';
        END;
    END IF;
END $$;
