import { BALANCE } from '@/lib/balanceConfig';

interface NumericNormalizationOptions {
  fallback?: number;
  min?: number;
  max?: number;
  round?: 'round' | 'floor' | 'ceil' | 'none';
}

interface MoneyNormalizationOptions extends NumericNormalizationOptions {
  allowNegative?: boolean;
}

const MAX_ABSOLUTE_XGP = BALANCE.SAFETY.MAX_ABSOLUTE_XGP;
const MAX_ABSOLUTE_DELTA_XGP = BALANCE.SAFETY.MAX_ABSOLUTE_DELTA_XGP;

function applyRounding(value: number, round: NumericNormalizationOptions['round'] = 'none'): number {
  if (round === 'round') return Math.round(value);
  if (round === 'floor') return Math.floor(value);
  if (round === 'ceil') return Math.ceil(value);
  return value;
}

export function normalizeFiniteNumber(
  value: unknown,
  {
    fallback = 0,
    min = -Number.MAX_SAFE_INTEGER,
    max = Number.MAX_SAFE_INTEGER,
    round = 'none',
  }: NumericNormalizationOptions = {},
): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;

  const rounded = applyRounding(parsed, round);
  return Math.min(max, Math.max(min, rounded));
}

export function normalizeMoneyValue(
  value: unknown,
  {
    fallback = 0,
    allowNegative = true,
    min,
    max = MAX_ABSOLUTE_XGP,
    round = 'none',
  }: MoneyNormalizationOptions = {},
): number {
  const resolvedMin = min ?? (allowNegative ? -MAX_ABSOLUTE_XGP : 0);
  return normalizeFiniteNumber(value, {
    fallback,
    min: resolvedMin,
    max,
    round,
  });
}

export function normalizeOptionalMoneyValue(
  value: unknown,
  options?: MoneyNormalizationOptions,
): number | null {
  if (value == null || value === '') return null;
  return normalizeMoneyValue(value, options);
}

export function clampDeltaRange(
  value: unknown,
  {
    fallback = 0,
    min = -MAX_ABSOLUTE_DELTA_XGP,
    max = MAX_ABSOLUTE_DELTA_XGP,
    round = 'none',
  }: NumericNormalizationOptions = {},
): number {
  return normalizeFiniteNumber(value, { fallback, min, max, round });
}

export function normalizePercentageStat(value: unknown, fallback: number): number {
  return normalizeFiniteNumber(value, {
    fallback,
    min: BALANCE.SAFETY.MIN_PERCENTAGE_STAT,
    max: BALANCE.SAFETY.MAX_PERCENTAGE_STAT,
  });
}

export function normalizeCreditScore(value: unknown, fallback = 650): number {
  return normalizeFiniteNumber(value, {
    fallback,
    min: BALANCE.SAFETY.MIN_CREDIT_SCORE,
    max: BALANCE.SAFETY.MAX_CREDIT_SCORE,
    round: 'round',
  });
}

export function normalizeCurrentDay(value: unknown, fallback = 1): number {
  return normalizeFiniteNumber(value, {
    fallback,
    min: 1,
    max: BALANCE.SAFETY.MAX_GAME_DAY,
    round: 'round',
  });
}

export function normalizeTimeUnits(
  value: unknown,
  {
    fallback = BALANCE.DEFAULT_TOTAL_TIME_UNITS,
    min = BALANCE.MIN_TOTAL_TIME_UNITS,
    max = BALANCE.MAX_TOTAL_TIME_UNITS,
    round = 'floor',
  }: NumericNormalizationOptions = {},
): number {
  return normalizeFiniteNumber(value, {
    fallback,
    min,
    max,
    round,
  });
}

export function normalizeTimeCostUnits(value: unknown, fallback = 2): number {
  return normalizeFiniteNumber(value, {
    fallback,
    min: BALANCE.SAFETY.MIN_TIME_COST_UNITS,
    max: BALANCE.SAFETY.MAX_TIME_COST_UNITS,
    round: 'round',
  });
}

/**
 * Normalizes a raw job name / key string to a clean non-empty value or null.
 * Rejects blank strings, literal "null"/"undefined" tokens, and values over 128 chars.
 * Used to validate job parameters before API calls.
 */
export function normalizeJobName(value: unknown): string | null {
  const s = String(value ?? '').trim();
  if (!s) return null;
  const lower = s.toLowerCase();
  if (lower === 'null' || lower === 'undefined') return null;
  return s.slice(0, 128);
}

export function safeNetCashFlowCalculation(
  incomeAmount: unknown,
  expenseAmount: unknown,
  reportedNetCashFlow?: unknown,
): number {
  const normalizedIncome = normalizeMoneyValue(incomeAmount, { allowNegative: false, fallback: 0 });
  const normalizedExpense = normalizeMoneyValue(expenseAmount, { allowNegative: false, fallback: 0 });
  const derived = normalizeMoneyValue(normalizedIncome - normalizedExpense, {
    allowNegative: true,
    fallback: 0,
  });

  if (reportedNetCashFlow == null || reportedNetCashFlow === '') {
    return derived;
  }

  const reported = normalizeMoneyValue(reportedNetCashFlow, {
    allowNegative: true,
    fallback: derived,
  });

  const mismatch = Math.abs(reported - derived);
  if (mismatch > BALANCE.SAFETY.MAX_NET_CASHFLOW_MISMATCH_XGP) {
    return derived;
  }

  return reported;
}