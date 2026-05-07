import os

import logging

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import text

# Load environment variables from the project root `.env` file at app import/startup time.
load_dotenv()

from app.api import admin_realworld, auth, baskets, briefs, business, career, daily, debt, economy, economy_presentation, events, finance, financial_survival, game_time, gameplay, health, housing, jobs, macro, market, notifications, onboarding, player, portfolio, progression, side_income, stocks
from app.core.security import load_jwt_secret
from app.db.database import Base, engine, SessionLocal, log_database_schema_diagnostics
from app import models  # noqa: F401

logger = logging.getLogger(__name__)


def load_app_config() -> dict[str, str | int]:
    # Centralized MVP config loader. These values are sourced from `.env`.
    return {
        "DATABASE_URL": os.getenv("DATABASE_URL", ""),
        "SECRET_KEY": load_jwt_secret(),
        "ALGORITHM": os.getenv("ALGORITHM", "HS256"),
        "ACCESS_TOKEN_EXPIRE_MINUTES": int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")),
    }


def _run_schema_migrations() -> None:
    """Apply lightweight additive column migrations for iterative dev.

    These are safe to run on every startup — each statement is wrapped in its
    own try/except so an already-existing column is silently ignored.
    """
    migrations = [
        # Step 95C: ensure auth-account metadata columns exist on legacy prod
        # databases that haven't yet run the 20260414_0027 alembic migration.
        # Without these, /auth/register INSERTs raise a raw OperationalError
        # and the client sees "Internal Server Error" with no JSON body.
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(50) NOT NULL DEFAULT 'password'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(50) NOT NULL DEFAULT 'active'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP",
        # Step 95E: Supabase Auth ids live outside this DB. Legacy schemas had
        # players.user_id as UUID + FK to users, which breaks lookup when the
        # mobile app sends a Supabase UUID string.
        "ALTER TABLE players DROP CONSTRAINT IF EXISTS players_user_id_fkey",
        "ALTER TABLE players DROP CONSTRAINT IF EXISTS fk_players_user_id_users",
        "ALTER TABLE players DROP CONSTRAINT IF EXISTS uq_players_user_id",
        "ALTER TABLE players DROP CONSTRAINT IF EXISTS players_user_id_key",
        "DROP INDEX IF EXISTS ix_players_user_id",
        "ALTER TABLE players ALTER COLUMN user_id DROP NOT NULL",
        "ALTER TABLE players ALTER COLUMN user_id TYPE TEXT USING user_id::text",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_players_user_id ON players (user_id) WHERE user_id IS NOT NULL",
        # Step 71I: ensure onboarding can persist gender on legacy prod schemas.
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS gender VARCHAR(20)",
        # Step 5: track which day the economy engine last processed.
        "ALTER TABLE game_states ADD COLUMN economy_processed_for_day INTEGER",
        # Step 6: expanded stock columns and new tables.
        "ALTER TABLE stocks ADD COLUMN company_name VARCHAR(120)",
        "ALTER TABLE stocks ADD COLUMN sector VARCHAR(40) NOT NULL DEFAULT 'consumer'",
        "ALTER TABLE stocks ADD COLUMN base_price NUMERIC(12,2) NOT NULL DEFAULT 50",
        "ALTER TABLE stocks ADD COLUMN volatility FLOAT NOT NULL DEFAULT 0.5",
        "ALTER TABLE stocks ADD COLUMN growth_bias FLOAT NOT NULL DEFAULT 0.0",
        # Step 7: player region for business demand modifiers.
        "ALTER TABLE players ADD COLUMN region VARCHAR(40) NOT NULL DEFAULT 'suburban'",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS current_location_key VARCHAR(80) NOT NULL DEFAULT 'home'",
        # Onboarding MVP: basic player profile field.
        "ALTER TABLE players ADD COLUMN bank_savings_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN debt_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN credit_score INTEGER NOT NULL DEFAULT 650",
        "ALTER TABLE players ADD COLUMN display_name VARCHAR(80)",
        "ALTER TABLE players ADD COLUMN gender VARCHAR(20)",
        # Step 7b: business balancing fields.
        "ALTER TABLE businesses ADD COLUMN consecutive_profitable_days INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE businesses ADD COLUMN consecutive_loss_days INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE businesses ADD COLUMN lifetime_units_sold INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE businesses ADD COLUMN lifetime_spoiled_units INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE businesses ADD COLUMN demand_reputation FLOAT NOT NULL DEFAULT 1.0",
        "ALTER TABLE businesses ADD COLUMN current_margin_modifier FLOAT NOT NULL DEFAULT 1.0",
        "ALTER TABLE businesses ADD COLUMN last_snapshot_day INTEGER",
        # Step 7b: balance analytics on business actions.
        "ALTER TABLE business_actions ADD COLUMN demand_factor FLOAT",
        "ALTER TABLE business_actions ADD COLUMN efficiency_factor FLOAT",
        "ALTER TABLE business_actions ADD COLUMN margin_modifier FLOAT",
        "ALTER TABLE business_actions ADD COLUMN economy_pressure FLOAT",
        "ALTER TABLE business_actions ADD COLUMN player_condition_penalty FLOAT",
        # Step 8: Housing and Debt System — player fields.
        "ALTER TABLE players ADD COLUMN net_worth NUMERIC(14,2) NOT NULL DEFAULT 1000",
        "ALTER TABLE players ADD COLUMN housing_stability INTEGER NOT NULL DEFAULT 100",
        "ALTER TABLE players ADD COLUMN has_active_housing BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE players ADD COLUMN account_created_day INTEGER",
        "ALTER TABLE players ADD COLUMN lifetime_xgp_earned FLOAT NOT NULL DEFAULT 0.0",
        # Step 8b: player_housing pressure tracking.
        "ALTER TABLE player_housings ADD COLUMN affordability_pressure FLOAT NOT NULL DEFAULT 1.0",
        "ALTER TABLE player_housings ADD COLUMN cumulative_housing_paid NUMERIC(12,2) NOT NULL DEFAULT 0",
        "ALTER TABLE player_housings ADD COLUMN cumulative_property_tax_paid NUMERIC(12,2) NOT NULL DEFAULT 0",
        "ALTER TABLE player_housings ADD COLUMN cumulative_maintenance_paid NUMERIC(12,2) NOT NULL DEFAULT 0",
        "ALTER TABLE player_housings ADD COLUMN cumulative_debt_paid NUMERIC(12,2) NOT NULL DEFAULT 0",
        "ALTER TABLE player_housings ADD COLUMN consecutive_missed_housing_days INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE player_housings ADD COLUMN region_pressure_modifier FLOAT NOT NULL DEFAULT 1.0",
        "ALTER TABLE player_housings ADD COLUMN last_snapshot_day INTEGER",
        # Step 8b: debt_account delinquency tracking.
        "ALTER TABLE debt_accounts ADD COLUMN cumulative_interest_paid NUMERIC(12,2) NOT NULL DEFAULT 0",
        "ALTER TABLE debt_accounts ADD COLUMN cumulative_principal_paid NUMERIC(12,2) NOT NULL DEFAULT 0",
        "ALTER TABLE debt_accounts ADD COLUMN consecutive_missed_payments INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE debt_accounts ADD COLUMN penalty_rate_modifier FLOAT NOT NULL DEFAULT 1.0",
        "ALTER TABLE debt_accounts ADD COLUMN last_delinquency_day INTEGER",
        # Step 2 (gameplay loop): job assignment field on players.
        # main_job already exists in the Player model; this migration guard ensures
        # any DB that pre-dates the column creation will get it safely.
        "ALTER TABLE players ADD COLUMN main_job VARCHAR(120)",
        "ALTER TABLE players ADD COLUMN side_job VARCHAR(120)",
        # Step 3 (daily lifecycle): new player field and GameState columns.
        # last_settled_day enforces the one-settlement-per-day idempotency rule.
        "ALTER TABLE players ADD COLUMN last_settled_day INTEGER",
        # Step 73: one-time end-of-day summary acknowledgment checkpoint.
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS last_seen_settlement_day INTEGER",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS main_shift_active_flag BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS main_shift_status VARCHAR(20) NOT NULL DEFAULT 'idle'",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS main_shift_started_at TIMESTAMPTZ",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS main_shift_ends_at TIMESTAMPTZ",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS main_shift_completed_at TIMESTAMPTZ",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS main_shift_job_name VARCHAR(120)",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS main_shift_shift_type VARCHAR(40)",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS main_shift_hours INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS main_shift_number INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS main_shift_last_cash_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS main_shift_last_xp_gained INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS main_shift_last_stress_delta INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS main_shift_last_health_delta INTEGER NOT NULL DEFAULT 0",
        # Phase 3-C Step 3: run lifecycle metadata for bankruptcy/retirement endings.
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS run_status VARCHAR(20) NOT NULL DEFAULT 'active'",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS run_ended_at TIMESTAMPTZ",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS run_end_day INTEGER",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS run_end_reason VARCHAR(80)",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS run_end_summary_json TEXT",
        # Phase 3-C Player Absence Handling: live schemas can miss these even
        # when the model has already started selecting them through the ORM.
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS last_settlement_at TIMESTAMPTZ",
        # day_status and day_started_at extend the existing game_states table.
        "ALTER TABLE game_states ADD COLUMN day_status VARCHAR(20) NOT NULL DEFAULT 'open'",
        "ALTER TABLE game_states ADD COLUMN day_started_at TIMESTAMPTZ",
        # Step 4 (goods baskets): daily basket consumption fields on player_daily_states.
        # Accumulate during the day; reset when a new daily state row is created.
        "ALTER TABLE player_daily_states ADD COLUMN essentials_units NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN protein_units NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN produce_units NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN convenience_units NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN total_spent_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS did_work BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS missed_shift BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS shift_start TIMESTAMPTZ",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS shift_end TIMESTAMPTZ",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS salary_earned NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS salary_transaction_id TEXT",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS salary_posted_at TIMESTAMPTZ",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS missed_penalty NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS meals_recorded INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS survival_penalty_applied BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS dinner_resolved BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS dinner_mode TEXT",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS dinner_cost NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS food_debt_added NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS night_eat_reminder_shown BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS dinner_resolved_at TIMESTAMPTZ",
        # Step 5 (macro economy): sensitivity columns on goods_baskets.
        # These drive the deterministic basket price formula in macro_engine.py.
        "ALTER TABLE goods_baskets ADD COLUMN inflation_sensitivity NUMERIC(6,4) NOT NULL DEFAULT 0.6",
        "ALTER TABLE goods_baskets ADD COLUMN oil_sensitivity NUMERIC(6,4) NOT NULL DEFAULT 0.3",
        "ALTER TABLE goods_baskets ADD COLUMN confidence_sensitivity NUMERIC(6,4) NOT NULL DEFAULT 0.1",
        "ALTER TABLE goods_baskets ADD COLUMN supply_chain_sensitivity NUMERIC(6,4) NOT NULL DEFAULT 0.4",
        "ALTER TABLE goods_baskets ADD COLUMN seasonality_factor NUMERIC(6,4) NOT NULL DEFAULT 0.1",
        # Step 6 (daily needs quality): evaluation fields on player_daily_states.
        "ALTER TABLE player_daily_states ADD COLUMN needs_score NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN needs_tier TEXT",
        "ALTER TABLE player_daily_states ADD COLUMN needs_evaluated BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE player_daily_states ADD COLUMN food_quality_score NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN survival_coverage_score NUMERIC(8,4) NOT NULL DEFAULT 0",
        # Step 6: needs-quality output fields on daily_settlement_logs.
        "ALTER TABLE daily_settlement_logs ADD COLUMN needs_score NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN needs_tier TEXT",
        "ALTER TABLE daily_settlement_logs ADD COLUMN food_quality_modifier INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN stress_penalty_from_needs INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN health_modifier_from_needs INTEGER NOT NULL DEFAULT 0",
        # Step 7 (housing region cost layer): player housing assignment.
        "ALTER TABLE players ADD COLUMN housing_region_id VARCHAR(40)",
        # Step 7: housing cost snapshot on player_daily_states.
        "ALTER TABLE player_daily_states ADD COLUMN housing_cost_paid NUMERIC(10,2) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN housing_region_id TEXT",
        # Step 8: side-income daily totals on player_daily_states.
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS main_shift_hours_today NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN side_income_hours NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN side_income_gross_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN side_income_fuel_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN side_income_net_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        # Step 7: housing audit fields on daily_settlement_logs.
        "ALTER TABLE daily_settlement_logs ADD COLUMN housing_region_id TEXT",
        "ALTER TABLE daily_settlement_logs ADD COLUMN housing_cost_paid NUMERIC(10,2) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN housing_stress_modifier INTEGER NOT NULL DEFAULT 0",
        # Step 8: side-income snapshot fields on daily_settlement_logs.
        "ALTER TABLE daily_settlement_logs ADD COLUMN side_income_hours NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN side_income_net_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        # Step 16: job-market pressure + employment event tracking.
        "ALTER TABLE player_employment_states ADD COLUMN job_status VARCHAR(20) NOT NULL DEFAULT 'employed'",
        "ALTER TABLE player_employment_states ADD COLUMN promotion_eligible_flag BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE player_employment_states ADD COLUMN promotion_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE player_employment_states ADD COLUMN last_raise_pct NUMERIC(6,2) NOT NULL DEFAULT 0",
        "ALTER TABLE player_employment_states ADD COLUMN last_employment_event VARCHAR(40)",
        "ALTER TABLE player_employment_states ADD COLUMN opportunity_score NUMERIC(8,4) NOT NULL DEFAULT 1.0",
        "ALTER TABLE player_employment_states ADD COLUMN layoff_event_flag BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE player_employment_states ADD COLUMN promotion_chance_pct NUMERIC(6,2) NOT NULL DEFAULT 0",
        "ALTER TABLE player_employment_states ADD COLUMN wage_adjustment_pct NUMERIC(6,2) NOT NULL DEFAULT 0",
        "ALTER TABLE player_employment_states ADD COLUMN employment_evaluated_flag BOOLEAN NOT NULL DEFAULT FALSE",
        # Step 73: company-linked and shift foundation metadata.
        "ALTER TABLE player_employment_states ADD COLUMN IF NOT EXISTS employer_company_symbol VARCHAR(40)",
        "ALTER TABLE player_employment_states ADD COLUMN IF NOT EXISTS employer_company_name VARCHAR(120)",
        "ALTER TABLE player_employment_states ADD COLUMN IF NOT EXISTS position_title VARCHAR(120)",
        "ALTER TABLE player_employment_states ADD COLUMN IF NOT EXISTS shift_type VARCHAR(40)",
        "ALTER TABLE player_employment_states ADD COLUMN IF NOT EXISTS job_level_xp INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE player_employment_states ADD COLUMN IF NOT EXISTS job_level_xp_to_next INTEGER NOT NULL DEFAULT 100",
        # Step 11: business balancing metadata on business_types.
        "ALTER TABLE business_types ADD COLUMN fixed_overhead_xgp NUMERIC(10,2) NOT NULL DEFAULT 0",
        "ALTER TABLE business_types ADD COLUMN base_demand_factor NUMERIC(8,4) NOT NULL DEFAULT 1.0",
        "ALTER TABLE business_types ADD COLUMN saturation_penalty_rate NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE business_types ADD COLUMN confidence_sensitivity NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE business_types ADD COLUMN unemployment_sensitivity NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE business_types ADD COLUMN oil_margin_sensitivity NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE business_types ADD COLUMN input_cost_pressure_weight NUMERIC(8,4) NOT NULL DEFAULT 0",
        # Step 11: daily saturation counter + lifetime counter on player_businesses.
        "ALTER TABLE player_businesses ADD COLUMN times_operated_today INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE player_businesses ADD COLUMN lifetime_business_runs INTEGER NOT NULL DEFAULT 0",
        # Step 15: business daily operations MVP columns on player_businesses.
        "ALTER TABLE player_businesses DROP CONSTRAINT IF EXISTS uq_pb_player",
        "ALTER TABLE player_businesses ADD COLUMN region VARCHAR(40) NOT NULL DEFAULT 'suburban'",
        "ALTER TABLE player_businesses ADD COLUMN reputation INTEGER NOT NULL DEFAULT 50",
        "ALTER TABLE player_businesses ADD COLUMN cash_reserve_xgp NUMERIC(14,2)",
        "ALTER TABLE player_businesses ADD COLUMN business_name VARCHAR(120)",
        "ALTER TABLE player_businesses ADD COLUMN level_key VARCHAR(40) NOT NULL DEFAULT 'starter'",
        "ALTER TABLE player_businesses ADD COLUMN cash_invested_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_businesses ADD COLUMN inventory_produce_units NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_businesses ADD COLUMN inventory_essentials_units NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_businesses ADD COLUMN inventory_protein_units NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_businesses ADD COLUMN inventory_items_json TEXT",
        "ALTER TABLE player_businesses ADD COLUMN fruit_markup_pct NUMERIC(8,4) NOT NULL DEFAULT 0.20",
        "ALTER TABLE player_businesses ADD COLUMN operating_mode VARCHAR(40)",
        "ALTER TABLE player_businesses ADD COLUMN upgrades_json TEXT",
        "ALTER TABLE player_businesses ADD COLUMN last_operated_on DATE",
        "ALTER TABLE business_daily_logs ADD COLUMN as_of_date DATE",
        "ALTER TABLE business_daily_logs ADD COLUMN business_type VARCHAR(40)",
        "ALTER TABLE business_daily_logs ADD COLUMN region_key VARCHAR(40)",
        "ALTER TABLE business_daily_logs ADD COLUMN labor_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE business_daily_logs ADD COLUMN maintenance_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE business_daily_logs ADD COLUMN units_sold INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE business_daily_logs ADD COLUMN inventory_start_units NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE business_daily_logs ADD COLUMN inventory_end_units NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE business_daily_logs ADD COLUMN demand_signal NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE business_daily_logs ADD COLUMN reputation_before INTEGER",
        "ALTER TABLE business_daily_logs ADD COLUMN reputation_after INTEGER",
        "ALTER TABLE business_daily_logs ADD COLUMN debug_json TEXT",
        "ALTER TABLE player_net_worth_snapshots ADD COLUMN inventory_value_xgp NUMERIC(14,2) NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN rideshare_reliability NUMERIC(8,4) NOT NULL DEFAULT 0.95",
        "ALTER TABLE players ADD COLUMN productivity_modifier NUMERIC(8,4) NOT NULL DEFAULT 1.0",
        "ALTER TABLE players ADD COLUMN base_productivity_modifier NUMERIC(8,4) NOT NULL DEFAULT 1.0",
        "ALTER TABLE players ADD COLUMN burnout_risk NUMERIC(8,4) NOT NULL DEFAULT 0.0",
        "ALTER TABLE players ADD COLUMN medical_event_risk NUMERIC(8,4) NOT NULL DEFAULT 0.0",
        "ALTER TABLE player_daily_states ADD COLUMN side_income_wear_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN side_income_maintenance_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN total_hours_used NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN job_hours NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN business_hours NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN commute_hours NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN sleep_hours NUMERIC(12,4) NOT NULL DEFAULT 7",
        "ALTER TABLE player_daily_states ADD COLUMN recovery_hours NUMERIC(12,4) NOT NULL DEFAULT 1",
        "ALTER TABLE player_daily_states ADD COLUMN overtime_hours NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN stress_delta INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN health_delta INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN productivity_modifier NUMERIC(8,4) NOT NULL DEFAULT 1",
        "ALTER TABLE player_daily_states ADD COLUMN burnout_risk NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN medical_event_risk NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN medical_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN missed_work_penalty_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN life_debug_json TEXT",
        "ALTER TABLE side_income_actions ADD COLUMN wear_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE side_income_actions ADD COLUMN maintenance_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE side_income_actions ADD COLUMN demand_multiplier NUMERIC(8,4) NOT NULL DEFAULT 1",
        "ALTER TABLE side_income_actions ADD COLUMN gross_per_hour_xgp NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE side_income_actions ADD COLUMN gas_price_per_unit_xgp NUMERIC(10,4) NOT NULL DEFAULT 0",
        "ALTER TABLE side_income_actions ADD COLUMN wear_cost_per_hour_xgp NUMERIC(10,4) NOT NULL DEFAULT 0",
        "ALTER TABLE side_income_actions ADD COLUMN net_per_hour_xgp NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE side_income_actions ADD COLUMN reliability_before NUMERIC(8,4) NOT NULL DEFAULT 1",
        "ALTER TABLE side_income_actions ADD COLUMN reliability_after NUMERIC(8,4) NOT NULL DEFAULT 1",
        "ALTER TABLE daily_settlement_logs ADD COLUMN business_revenue_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN business_cogs_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN business_overhead_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN business_spoilage_loss_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN business_fuel_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN business_maintenance_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN business_net_profit_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN total_hours_used NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN overtime_hours NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN sleep_hours NUMERIC(12,4) NOT NULL DEFAULT 7",
        "ALTER TABLE daily_settlement_logs ADD COLUMN recovery_hours NUMERIC(12,4) NOT NULL DEFAULT 1",
        "ALTER TABLE daily_settlement_logs ADD COLUMN productivity_modifier NUMERIC(8,4) NOT NULL DEFAULT 1",
        "ALTER TABLE daily_settlement_logs ADD COLUMN burnout_risk NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN medical_event_risk NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN medical_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN missed_work_penalty_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        # Step 17: housing-region full integration fields.
        "ALTER TABLE player_housing_states ADD COLUMN monthly_housing_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 540",
        "ALTER TABLE player_housing_states ADD COLUMN monthly_utilities_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 105",
        "ALTER TABLE player_housing_states ADD COLUMN monthly_transport_base_xgp NUMERIC(14,4) NOT NULL DEFAULT 165",
        "ALTER TABLE player_housing_states ADD COLUMN commute_mode VARCHAR(20) NOT NULL DEFAULT 'car'",
        "ALTER TABLE player_housing_states ADD COLUMN business_demand_modifier NUMERIC(8,4) NOT NULL DEFAULT 1.0",
        "ALTER TABLE player_housing_states ADD COLUMN side_income_modifier NUMERIC(8,4) NOT NULL DEFAULT 1.0",
        "ALTER TABLE player_housing_states ADD COLUMN networking_modifier NUMERIC(8,4) NOT NULL DEFAULT 0.0",
        "ALTER TABLE housing_daily_logs ADD COLUMN as_of_date DATE",
        "ALTER TABLE housing_daily_logs ADD COLUMN utilities_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE housing_daily_logs ADD COLUMN commute_hours NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE housing_daily_logs ADD COLUMN commute_fuel_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE housing_daily_logs ADD COLUMN region_stress_delta NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE housing_daily_logs ADD COLUMN region_opportunity_modifier NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE housing_daily_logs ADD COLUMN region_business_demand_modifier NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE housing_daily_logs ADD COLUMN region_side_income_modifier NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE housing_daily_logs ADD COLUMN networking_modifier NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE housing_daily_logs ADD COLUMN opportunity_quality_signal NUMERIC(8,4) NOT NULL DEFAULT 1",
        "ALTER TABLE housing_daily_logs ADD COLUMN housing_debug_json TEXT",
        "ALTER TABLE player_daily_states ADD COLUMN region_key TEXT",
        "ALTER TABLE player_daily_states ADD COLUMN housing_cost_daily_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN utilities_cost_daily_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN commute_fuel_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN region_stress_delta NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN region_opportunity_modifier NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN region_business_demand_modifier NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN region_side_income_modifier NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN networking_modifier NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN opportunity_quality_signal NUMERIC(8,4) NOT NULL DEFAULT 1",
        "ALTER TABLE player_daily_states ADD COLUMN housing_debug_json TEXT",
        "ALTER TABLE daily_settlement_logs ADD COLUMN region_key TEXT",
        "ALTER TABLE daily_settlement_logs ADD COLUMN housing_cost_daily_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN utilities_cost_daily_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN commute_hours NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN commute_fuel_cost_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN region_stress_delta NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN region_opportunity_modifier NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN region_business_demand_modifier NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN region_side_income_modifier NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN networking_modifier NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN opportunity_quality_signal NUMERIC(8,4) NOT NULL DEFAULT 1",
        # Step 11: balancing audit fields on business_operations.
        "ALTER TABLE business_operations ADD COLUMN fixed_overhead_xgp NUMERIC(12,4) NOT NULL DEFAULT 0",
        "ALTER TABLE business_operations ADD COLUMN demand_multiplier NUMERIC(8,4) NOT NULL DEFAULT 1.0",
        "ALTER TABLE business_operations ADD COLUMN saturation_penalty_multiplier NUMERIC(8,4) NOT NULL DEFAULT 1.0",
        "ALTER TABLE business_operations ADD COLUMN macro_margin_modifier NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE business_operations ADD COLUMN final_margin_multiplier NUMERIC(8,4) NOT NULL DEFAULT 1.0",
        # Step 12: abstract marketplace listing columns on market_listings.
        "ALTER TABLE market_listings ADD COLUMN listing_type VARCHAR(20)",
        "ALTER TABLE market_listings ADD COLUMN item_id VARCHAR(40)",
        "ALTER TABLE market_listings ADD COLUMN listing_fee_xgp NUMERIC(10,2) NOT NULL DEFAULT 0",
        # Step 12: marketplace reputation / trade tracking on players.
        "ALTER TABLE players ADD COLUMN completed_trades_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN marketplace_rating_score FLOAT NOT NULL DEFAULT 0.0",
        # Step 13: co-op deal collaboration tracking on players.
        "ALTER TABLE players ADD COLUMN successful_coop_deals_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN failed_coop_deals_count INTEGER NOT NULL DEFAULT 0",
        # Step 18: career progression tables (created via Base.metadata.create_all)
        # These additive guards handle any column additions to existing tables.
        # The player_career_states and career_progress_logs tables are new and
        # created by SQLAlchemy metadata, so no ALTER TABLE needed for them.
        # Step 20: financial distress + recovery arc fields.
        "ALTER TABLE players ADD COLUMN required_daily_debt_payment_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN debt_utilization_ratio NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN missed_payment_streak INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN on_payment_plan BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE players ADD COLUMN distress_state VARCHAR(20) NOT NULL DEFAULT 'stable'",
        "ALTER TABLE players ADD COLUMN distress_score NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN last_missed_payment_date DATE",
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS last_survival_resolved_date DATE",
        "ALTER TABLE players ADD COLUMN borrowing_cost_modifier NUMERIC(8,4) NOT NULL DEFAULT 1.0",
        "ALTER TABLE players ADD COLUMN opportunity_access_penalty NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN business_risk_penalty NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN career_progress_penalty NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE players ADD COLUMN credit_debug_json TEXT",
        "ALTER TABLE players ADD COLUMN recovery_actions_json TEXT",
        "ALTER TABLE player_daily_states ADD COLUMN debt_payment_due_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN debt_payment_paid_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN debt_payment_missed BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE player_daily_states ADD COLUMN late_fee_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN accrued_interest_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN credit_score_before INTEGER NOT NULL DEFAULT 650",
        "ALTER TABLE player_daily_states ADD COLUMN credit_score_after INTEGER NOT NULL DEFAULT 650",
        "ALTER TABLE player_daily_states ADD COLUMN credit_score_delta INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN distress_state_before TEXT NOT NULL DEFAULT 'stable'",
        "ALTER TABLE player_daily_states ADD COLUMN distress_state_after TEXT NOT NULL DEFAULT 'stable'",
        "ALTER TABLE player_daily_states ADD COLUMN distress_score_before NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN distress_score_after NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN borrowing_cost_modifier NUMERIC(8,4) NOT NULL DEFAULT 1",
        "ALTER TABLE player_daily_states ADD COLUMN opportunity_access_penalty NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN business_risk_penalty NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN career_progress_penalty NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE player_daily_states ADD COLUMN distress_driver_json TEXT",
        "ALTER TABLE player_daily_states ADD COLUMN recovery_actions_json TEXT",
        # Step 69: retention engine carryover fields.
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS retention_flags_json TEXT",
        "ALTER TABLE player_daily_states ADD COLUMN IF NOT EXISTS carryover_opportunities_json TEXT",
        "ALTER TABLE daily_settlement_logs ADD COLUMN debt_payment_due_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN debt_payment_paid_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN debt_payment_missed BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE daily_settlement_logs ADD COLUMN late_fee_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN accrued_interest_xgp NUMERIC(14,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN credit_score_before INTEGER NOT NULL DEFAULT 650",
        "ALTER TABLE daily_settlement_logs ADD COLUMN credit_score_after INTEGER NOT NULL DEFAULT 650",
        "ALTER TABLE daily_settlement_logs ADD COLUMN credit_score_delta INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN distress_state_before TEXT NOT NULL DEFAULT 'stable'",
        "ALTER TABLE daily_settlement_logs ADD COLUMN distress_state_after TEXT NOT NULL DEFAULT 'stable'",
        "ALTER TABLE daily_settlement_logs ADD COLUMN distress_score_before NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN distress_score_after NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN borrowing_cost_modifier NUMERIC(8,4) NOT NULL DEFAULT 1",
        "ALTER TABLE daily_settlement_logs ADD COLUMN opportunity_access_penalty NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN business_risk_penalty NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN career_progress_penalty NUMERIC(8,4) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_settlement_logs ADD COLUMN recovery_actions_applied_json TEXT",
        "ALTER TABLE daily_settlement_logs ADD COLUMN distress_driver_json TEXT",
    ]
    for stmt in migrations:
        try:
            # Execute each statement in an isolated transaction so one failure
            # does not abort the entire schema-guard sequence.
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception as exc:
            logger.debug(
                "startup schema guard skipped statement",
                extra={"statement": stmt, "error": str(exc)},
            )


def create_app() -> FastAPI:
    application = FastAPI(
        title="Gold Penny Backend",
        description="Backend API for the Gold Penny financial simulation game.",
        version="0.1.0",
    )

    application.include_router(health.router)
    application.include_router(auth.router, prefix="/auth", tags=["auth"])
    application.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
    application.include_router(player.router, prefix="/player", tags=["player"])
    application.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
    application.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
    application.include_router(briefs.router, prefix="/briefs", tags=["briefs"])
    application.include_router(debt.router, prefix="/debt", tags=["debt"])
    application.include_router(finance.router, prefix="/finance", tags=["finance"])
    application.include_router(financial_survival.router, prefix="/financial", tags=["Financial Survival"])
    application.include_router(economy.router, prefix="/economy", tags=["economy"])
    application.include_router(market.router, prefix="/market", tags=["market"])
    application.include_router(stocks.router, prefix="/stocks", tags=["stocks"])
    application.include_router(business.router, prefix="/business", tags=["business"])
    application.include_router(housing.router, prefix="/housing", tags=["housing"])
    application.include_router(daily.router, prefix="/daily", tags=["Daily"])
    application.include_router(side_income.router)
    application.include_router(baskets.router, prefix="/baskets", tags=["Baskets"])
    application.include_router(macro.router, prefix="/macro", tags=["Macro"])
    application.include_router(career.router, prefix="/career", tags=["Career"])
    application.include_router(events.router, prefix="/events", tags=["Events"])
    application.include_router(progression.router, prefix="/progression", tags=["Progression"])
    application.include_router(economy_presentation.router, prefix="/economy-presentation", tags=["Economy Presentation"])
    application.include_router(game_time.router, tags=["Game Time"])
    application.include_router(gameplay.router, prefix="/gameplay", tags=["Gameplay"])
    application.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
    application.include_router(admin_realworld.router, prefix="/admin", tags=["Admin · Real-World"])
    return application


app = create_app()


@app.exception_handler(StarletteHTTPException)
def _http_exception_to_json(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if exc.detail is not None else "Request failed."
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error_code": f"http_{exc.status_code}",
            "message": str(detail),
            "detail": detail,
        },
        headers=getattr(exc, "headers", None) or None,
    )


@app.exception_handler(RequestValidationError)
def _validation_error_to_json(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error_code": "validation_error",
            "message": "Request body was invalid.",
            "detail": exc.errors(),
        },
    )


@app.exception_handler(Exception)
def _unhandled_exception_to_json(request: Request, exc: Exception) -> JSONResponse:
    # Never leak raw framework error pages to the mobile client — always JSON.
    logger.exception(
        "unhandled_server_error",
        extra={"path": str(request.url.path), "method": request.method, "error_type": type(exc).__name__},
    )
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error_code": "internal_server_error",
            "message": "The server hit an unexpected error. Please try again.",
            "detail": "Internal Server Error",
        },
    )


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "goldpenny-backend",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }


@app.on_event("startup")
def on_startup() -> None:
    # Make resolved settings available via app state for future services/routes.
    app.state.config = load_app_config()
    # Create all new tables declared in models (existing tables are untouched).
    Base.metadata.create_all(bind=engine)
    # Additive column migrations for tables that already exist.
    _run_schema_migrations()
    # Step 71K: emit DB target/schema diagnostics to reconcile Render vs Supabase.
    log_database_schema_diagnostics()
    # Seed the 4 default goods baskets if they do not yet exist.
    _seed_default_baskets()
    # Backfill basket sensitivity values for any existing rows that predate Step 5.
    _backfill_basket_sensitivities()
    # Step 7: seed 2 default housing regions (suburban, downtown) if missing.
    _seed_default_housing_regions()
    # Step 9: seed 10 default SectorStocks if they do not yet exist.
    _seed_default_sector_stocks()
    # Step 13: seed 4 default DealTemplates if they do not yet exist.
    _seed_default_deal_templates()
    # Step 14: seed 4 default NPC firms (2 regions × 2 firm types) if missing.
    _seed_npc_firms()
    # Step 10: seed 2 default BusinessTypes if they do not yet exist.
    _seed_default_business_types()
    # Step 11: backfill Step 11 balancing columns for any BusinessType rows
    # that existed before Step 11 and still have neutral/zero values.
    _backfill_business_type_balancing()


def _seed_default_baskets() -> None:
    """Ensure the 4 default GoodsBasket rows exist. Safe to call repeatedly."""
    from app.engine.basket_engine import get_or_seed_default_baskets
    db = SessionLocal()
    try:
        get_or_seed_default_baskets(db)
    finally:
        db.close()


def _backfill_basket_sensitivities() -> None:
    """
    Ensure existing GoodsBasket rows have correct sensitivity values for Step 5.

    Runs on every startup.  Safe to call repeatedly — only updates rows where
    the sensitivity values still match the old pre-Step-5 defaults, or where
    all sensitivity columns are at their migration-guard DEFAULT (0.6/0.3/0.1/0.4/0.1).
    We identify a row needing backfill by checking whether its sensitivities
    exactly match the column-level defaults (i.e. all baskets got the same values
    from the ALTER TABLE DEFAULT).  If any basket already has differentiated values
    (e.g. produce's supply_chain_sensitivity=0.7), skip it.

    The authoritative sensitivity values per basket are defined in DEFAULT_BASKETS
    inside goods_basket.py.
    """
    from app.models.goods_basket import GoodsBasket, DEFAULT_BASKETS

    SENSITIVITY_DEFAULTS = {
        "inflation_sensitivity": 0.6,
        "oil_sensitivity": 0.3,
        "confidence_sensitivity": 0.1,
        "supply_chain_sensitivity": 0.4,
        "seasonality_factor": 0.1,
    }

    db = SessionLocal()
    try:
        for row_data in DEFAULT_BASKETS:
            basket_id = row_data["basket_id"]
            basket = db.query(GoodsBasket).filter(GoodsBasket.id == basket_id).first()
            if basket is None:
                continue  # get_or_seed_default_baskets will add it separately

            # Check whether all five sensitivity fields still hold the migration default.
            needs_backfill = all(
                abs(float(getattr(basket, field, default)) - default) < 0.001
                for field, default in SENSITIVITY_DEFAULTS.items()
            )
            if not needs_backfill:
                continue  # Already differentiated — do not overwrite

            basket.inflation_sensitivity = row_data["inflation_sensitivity"]
            basket.oil_sensitivity = row_data["oil_sensitivity"]
            basket.confidence_sensitivity = row_data["confidence_sensitivity"]
            basket.supply_chain_sensitivity = row_data["supply_chain_sensitivity"]
            basket.seasonality_factor = row_data["seasonality_factor"]

        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _seed_default_housing_regions() -> None:
    """Ensure the 2 default HousingRegion rows exist.  Safe to call repeatedly."""
    from app.engine.housing_engine import get_or_seed_default_housing_regions
    db = SessionLocal()
    try:
        get_or_seed_default_housing_regions(db)
    finally:
        db.close()


def _seed_default_sector_stocks() -> None:
    """Ensure the 10 default SectorStock rows exist.  Safe to call repeatedly."""
    from app.engine.stock_engine import get_or_seed_default_sector_stocks
    db = SessionLocal()
    try:
        get_or_seed_default_sector_stocks(db)
    finally:
        db.close()


def _seed_default_business_types() -> None:
    """Ensure the 2 default BusinessType rows exist.  Safe to call repeatedly."""
    from app.engine.business_engine import get_or_seed_business_types
    db = SessionLocal()
    try:
        get_or_seed_business_types(db)
    finally:
        db.close()


def _seed_default_deal_templates() -> None:
    """Ensure the 4 default DealTemplate rows exist.  Safe to call repeatedly."""
    from app.engine.coop_deal_engine import get_or_seed_default_deal_templates
    db = SessionLocal()
    try:
        get_or_seed_default_deal_templates(db)
    finally:
        db.close()


def _seed_npc_firms() -> None:
    """Ensure the 4 default NPC firms exist (2 regions × 2 firm types).  Safe to call repeatedly."""
    from app.engine.firm_engine import get_or_seed_npc_firms
    db = SessionLocal()
    try:
        get_or_seed_npc_firms(db)
    finally:
        db.close()


def _backfill_business_type_balancing() -> None:
    """Backfill Step 11 balancing columns for BusinessType rows created before Step 11.

    Identifies rows where the Step 11 columns still hold zero/default values —
    a sign the row was seeded by Step 10 before Step 11 columns were added.
    Only rows matching a known DEFAULT_BUSINESS_TYPES entry are updated.
    Safe to call repeatedly; already-correct rows are skipped.
    """
    from app.models.business_type import BusinessType, DEFAULT_BUSINESS_TYPES

    # Build a lookup of canonical Step 11 values keyed by business_id.
    _S11_FIELDS = (
        "fixed_overhead_xgp",
        "base_demand_factor",
        "saturation_penalty_rate",
        "confidence_sensitivity",
        "unemployment_sensitivity",
        "oil_margin_sensitivity",
        "input_cost_pressure_weight",
    )
    canonical: dict[str, dict] = {
        spec["business_id"]: spec
        for spec in DEFAULT_BUSINESS_TYPES
        if any(f in spec for f in _S11_FIELDS)
    }

    db = SessionLocal()
    try:
        for business_id, spec in canonical.items():
            row = db.query(BusinessType).filter(BusinessType.business_id == business_id).first()
            if row is None:
                continue
            # Only backfill when all Step 11 columns are still at zero (migration default).
            needs_backfill = float(getattr(row, "fixed_overhead_xgp", 0) or 0) < 0.01
            if not needs_backfill:
                continue
            for field in _S11_FIELDS:
                if field in spec:
                    setattr(row, field, spec[field])
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
