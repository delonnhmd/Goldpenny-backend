// Gold Penny — minimal job/income runtime contract for gameplay
import { useMemo } from 'react';

import { formatMoney } from '@/lib/gameplayFormatters';
import { GameplayCanonicalState } from '@/lib/gameplayRuntimeState';

export interface JobIncomeContract {
  /** Current job title from the latest dashboard snapshot. Null if not yet loaded or unassigned. */
  currentJob: string | null;
  /** True if the player has an active job assignment. */
  hasActiveJob: boolean;
  /**
   * Reflects the player's work state:
   * - 'pending': dashboard data not yet loaded
   * - 'working': player has an active job
   * - 'unemployed': dashboard loaded but no job assigned
   */
  workStatus: 'working' | 'unemployed' | 'pending';
  /** Daily earned amount in xgp from end-of-day settlement. Null during an active day. */
  incomeAmount: number | null;
  /** Primary income source label from end-of-day data (biggest_gain). Null when unavailable. */
  incomeSource: string | null;
  /** Formatted income label for display: "+1,200.00 xgp", "0.00 xgp", or "Pending". */
  dailyIncomeLabel: string;
  /** Human-readable one-liner summarising job + income state — safe for UI labels and feedback. */
  incomeSummary: string;
}

const DEFAULT_JOB_INCOME: JobIncomeContract = {
  currentJob: null,
  hasActiveJob: false,
  workStatus: 'pending',
  incomeAmount: null,
  incomeSource: null,
  dailyIncomeLabel: 'Pending',
  incomeSummary: 'Income data pending.',
};

function deriveJobIncomeState(
  state: GameplayCanonicalState,
): JobIncomeContract {
  if (!state.hasDashboardSnapshot) return DEFAULT_JOB_INCOME;

  const currentJob = state.currentJob;
  const hasActiveJob = Boolean(currentJob);
  const workStatus: JobIncomeContract['workStatus'] = hasActiveJob ? 'working' : 'unemployed';

  const incomeAmount = state.incomeAmount;
  const incomeSource = state.incomeSource;

  const dailyIncomeLabel =
    incomeAmount == null
      ? 'Pending'
      : incomeAmount > 0
        ? `+${formatMoney(incomeAmount)}`
        : formatMoney(incomeAmount);

  let incomeSummary: string;
  if (!hasActiveJob && incomeAmount == null) {
    incomeSummary = 'No active job. Income depends on side work.';
  } else if (!hasActiveJob && incomeAmount != null) {
    const sourceNote = incomeSource ? ` via ${incomeSource}` : '';
    incomeSummary = `Side income${sourceNote}: ${dailyIncomeLabel} today.`;
  } else if (incomeAmount == null) {
    incomeSummary = `Working as ${currentJob}. Income available after end of day.`;
  } else if (incomeAmount > 0) {
    const sourceNote = incomeSource ? ` via ${incomeSource}` : '';
    incomeSummary = `Working as ${currentJob}${sourceNote} — earned ${dailyIncomeLabel} today.`;
  } else {
    incomeSummary = `Working as ${currentJob} — no income recorded today.`;
  }

  return {
    currentJob,
    hasActiveJob,
    workStatus,
    incomeAmount,
    incomeSource,
    dailyIncomeLabel,
    incomeSummary,
  };
}

/**
 * Derives a minimal, stable job/income contract from the latest dashboard and
 * end-of-day snapshots. Safe with null/missing data — returns a pending default
 * until both sources are loaded.
 */
export function useJobIncome(
  state: GameplayCanonicalState,
): JobIncomeContract {
  return useMemo(() => deriveJobIncomeState(state), [state]);
}
