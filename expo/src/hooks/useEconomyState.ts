import { useMemo } from 'react';

import { formatMoney } from '@/lib/gameplayFormatters';
import { GameplayCanonicalState } from '@/lib/gameplayRuntimeState';
import { BALANCE } from '@/lib/balanceConfig';
import { normalizeMoneyValue, normalizePercentageStat, safeNetCashFlowCalculation } from '@/lib/economySafety';
import { DebtPressureLevel, EconomyStatus, GameplayEconomyState } from '@/types/economy';

const DEFAULT_ECONOMY_STATE: GameplayEconomyState = {
  cashOnHand: 0,
  incomeAmount: null,
  expenseAmount: null,
  debtAmount: 0,
  netWorthAmount: 0,
  netCashFlow: null,
  debtPressure: 'low',
  economyStatus: 'stable',
  economyWarnings: [],
  cashFlowLabel: 'Pending',
  statusLabel: 'Stable',
  summaryLine: 'Cash 0.00 xgp. Cash flow pending. Debt pressure low.',
};

function toLabel(value: string): string {
  const normalized = String(value || '').trim();
  if (!normalized) return 'Unknown';
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function describeSignal(input: { title?: string; description?: string } | null | undefined): string | null {
  if (!input) return null;
  const title = String(input.title || '').trim();
  const description = String(input.description || '').trim();
  return title || description || null;
}

function deriveDebtPressure(cashOnHand: number, debtAmount: number, netWorthAmount: number): DebtPressureLevel {
  if (debtAmount <= 0) return 'low';
  if (cashOnHand <= 0 || netWorthAmount < 0) return 'critical';

  const debtToCashRatio = debtAmount / cashOnHand;
  if (debtToCashRatio >= BALANCE.THRESHOLDS.DEBT_CRITICAL_RATIO * 2) return 'critical';
  if (debtToCashRatio >= BALANCE.THRESHOLDS.DEBT_CRITICAL_RATIO) return 'high';
  if (debtToCashRatio >= BALANCE.THRESHOLDS.DEBT_HIGH_RATIO) return 'moderate';
  return 'low';
}

function deriveEconomyStatus(
  debtPressure: DebtPressureLevel,
  netCashFlow: number | null,
  stress: number,
  health: number,
): EconomyStatus {
  if (debtPressure === 'critical' || stress >= 80 || health <= 30) return 'critical';
  if (debtPressure === 'high' || (netCashFlow != null && netCashFlow < 0) || stress >= 60 || health <= 45) return 'strained';
  if (debtPressure === 'moderate' || stress >= 45 || health <= 60) return 'watch';
  return 'stable';
}

function deriveWarnings(
  state: GameplayCanonicalState,
  cashOnHand: number,
  debtAmount: number,
  debtPressure: DebtPressureLevel,
  netCashFlow: number | null,
): string[] {
  const warnings: string[] = [];

  if (cashOnHand <= BALANCE.THRESHOLDS.LOW_CASH_WARNING_XGP) {
    warnings.push('Cash buffer is thin. One weak day can force borrowing or missed payments.');
  }

  if (debtPressure === 'critical') {
    warnings.push('Debt pressure is critical and needs immediate attention.');
  } else if (debtPressure === 'high') {
    warnings.push('Debt payments are putting heavy pressure on available cash.');
  } else if (debtPressure === 'moderate') {
    warnings.push('Debt pressure is rising and should be monitored closely.');
  }

  if (netCashFlow != null && netCashFlow < 0) {
    warnings.push('Current cash flow is negative after today\'s settlement.');
  }

  if (debtAmount > 0 && cashOnHand > 0 && debtAmount >= cashOnHand * 2) {
    warnings.push('Debt is more than double your liquid cash, so recovery gets harder each day.');
  }

  for (const signal of state.topRisks) {
    const next = describeSignal(signal);
    if (next && !warnings.includes(next)) warnings.push(next);
    if (warnings.length >= 3) break;
  }

  return warnings;
}

export function deriveGameplayEconomyState(
  state: GameplayCanonicalState,
): GameplayEconomyState {
  if (!state.hasDashboardSnapshot) return DEFAULT_ECONOMY_STATE;

  const cashOnHand = normalizeMoneyValue(state.cashOnHand, { fallback: 0, allowNegative: true });
  const debtAmount = normalizeMoneyValue(state.debtAmount, { fallback: 0, allowNegative: false });
  const netWorthAmount = normalizeMoneyValue(state.netWorthAmount, { fallback: 0, allowNegative: true });
  const incomeAmount = state.incomeAmount == null
    ? null
    : normalizeMoneyValue(state.incomeAmount, { fallback: 0, allowNegative: false });
  const expenseAmount = state.expenseAmount == null
    ? null
    : normalizeMoneyValue(state.expenseAmount, { fallback: 0, allowNegative: false });
  const netCashFlow = incomeAmount == null || expenseAmount == null
    ? null
    : safeNetCashFlowCalculation(incomeAmount, expenseAmount, state.netCashFlow);
  const debtPressure = deriveDebtPressure(cashOnHand, debtAmount, netWorthAmount);
  const economyStatus = deriveEconomyStatus(
    debtPressure,
    netCashFlow,
    normalizePercentageStat(state.stress, 0),
    normalizePercentageStat(state.health, 100),
  );
  const economyWarnings = deriveWarnings(state, cashOnHand, debtAmount, debtPressure, netCashFlow);
  const cashFlowLabel = netCashFlow == null ? 'Pending' : `${netCashFlow > 0 ? '+' : ''}${formatMoney(netCashFlow)}`;
  const liquidityLabel = cashOnHand <= 0
    ? 'Cash exhausted'
    : cashOnHand <= BALANCE.THRESHOLDS.LOW_CASH_WARNING_XGP
      ? 'Cash buffer thin'
      : 'Cash buffer holding';
  const summaryLine = [
    `Cash ${formatMoney(cashOnHand)}`,
    liquidityLabel,
    netCashFlow == null ? 'Cash flow pending' : `Cash flow ${cashFlowLabel}`,
    `Debt pressure ${debtPressure}`,
  ].join('. ') + '.';

  return {
    cashOnHand,
    incomeAmount,
    expenseAmount,
    debtAmount,
    netWorthAmount,
    netCashFlow,
    debtPressure,
    economyStatus,
    economyWarnings,
    cashFlowLabel,
    statusLabel: toLabel(economyStatus),
    summaryLine,
  };
}

export function useEconomyState(
  state: GameplayCanonicalState,
): GameplayEconomyState {
  return useMemo(() => deriveGameplayEconomyState(state), [state]);
}