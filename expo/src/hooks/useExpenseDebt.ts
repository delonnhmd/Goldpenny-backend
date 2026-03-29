// Gold Penny — minimal expense/debt runtime contract for gameplay
import { useMemo } from 'react';

import { formatMoney } from '@/lib/gameplayFormatters';
import { GameplayCanonicalState } from '@/lib/gameplayRuntimeState';
import { DebtPressureLevel, EconomyStatus } from '@/types/economy';
import { deriveGameplayEconomyState } from '@/hooks/useEconomyState';

export interface ExpenseDebtContract {
  /** Daily expense total in xgp from end-of-day settlement. Null during an active day. */
  expenseAmount: number | null;
  /** Formatted expense label: "1,200.00 xgp" or "Pending". */
  expenseLabel: string;
  /** Current outstanding game debt in xgp from the latest dashboard snapshot. */
  debtAmount: number;
  /** Formatted debt amount label. */
  debtLabel: string;
  /** Debt pressure classification based on debt-to-cash and net worth ratios. */
  debtPressure: DebtPressureLevel;
  /** True when debt pressure is 'high' or 'critical'. */
  debtWarning: boolean;
  /** Net cash flow after income and expenses for the settled day. Null during an active day. */
  netCashFlow: number | null;
  /** Formatted net cash flow label: "+1,200.00 xgp", "-500.00 xgp", or "Pending". */
  netCashFlowLabel: string;
  /** Overall financial stress level — stable | watch | strained | critical. */
  financialStressLevel: EconomyStatus;
  /** True when financial stress is 'strained' or 'critical'. */
  financialStressWarning: boolean;
  /** Active economy warnings derived from dashboard risks and debt pressure. */
  economyWarnings: string[];
  /** Tomorrow-facing warnings from the most recent end-of-day settlement. */
  tomorrowWarnings: string[];
  /** Human-readable financial summary line — safe for UI labels and status displays. */
  financialSummary: string;
}

const DEFAULT_EXPENSE_DEBT: ExpenseDebtContract = {
  expenseAmount: null,
  expenseLabel: 'Pending',
  debtAmount: 0,
  debtLabel: '0.00 xgp',
  debtPressure: 'low',
  debtWarning: false,
  netCashFlow: null,
  netCashFlowLabel: 'Pending',
  financialStressLevel: 'stable',
  financialStressWarning: false,
  economyWarnings: [],
  tomorrowWarnings: [],
  financialSummary: 'Financial data pending.',
};

function deriveExpenseDebtState(
  state: GameplayCanonicalState,
): ExpenseDebtContract {
  if (!state.hasDashboardSnapshot) return DEFAULT_EXPENSE_DEBT;

  const economy = deriveGameplayEconomyState(state);

  const expenseLabel = economy.expenseAmount == null ? 'Pending' : formatMoney(economy.expenseAmount);
  const debtWarning = economy.debtPressure === 'high' || economy.debtPressure === 'critical';
  const financialStressWarning = economy.economyStatus === 'strained' || economy.economyStatus === 'critical';
  const tomorrowWarnings = state.tomorrowWarnings;

  return {
    expenseAmount: economy.expenseAmount,
    expenseLabel,
    debtAmount: economy.debtAmount,
    debtLabel: formatMoney(economy.debtAmount),
    debtPressure: economy.debtPressure,
    debtWarning,
    netCashFlow: economy.netCashFlow,
    netCashFlowLabel: economy.cashFlowLabel,
    financialStressLevel: economy.economyStatus,
    financialStressWarning,
    economyWarnings: economy.economyWarnings,
    tomorrowWarnings,
    financialSummary: economy.summaryLine,
  };
}

export function useExpenseDebt(
  state: GameplayCanonicalState,
): ExpenseDebtContract {
  return useMemo(() => deriveExpenseDebtState(state), [state]);
}
