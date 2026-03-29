import {
  DailySessionStatus,
  DashboardSignalItem,
  EndOfDaySummaryResponse,
  PlayerDashboardResponse,
} from '@/types/gameplay';
import {
  normalizeCurrentDay,
  normalizeJobName,
  normalizeMoneyValue,
  normalizeOptionalMoneyValue,
  normalizePercentageStat,
  safeNetCashFlowCalculation,
} from '@/lib/economySafety';
import { ActiveRandomEvent } from '@/types/randomEvent';

export interface GameplayCanonicalState {
  playerId: string;
  currentDay: number;
  sessionStatus: DailySessionStatus;
  hasDashboardSnapshot: boolean;
  hasSettledEndOfDay: boolean;
  cashOnHand: number;
  debtAmount: number;
  netWorthAmount: number;
  stress: number;
  health: number;
  currentJob: string | null;
  incomeAmount: number | null;
  expenseAmount: number | null;
  netCashFlow: number | null;
  incomeSource: string | null;
  tomorrowWarnings: string[];
  topRisks: DashboardSignalItem[];
  activeEventId: string | null;
  activeEventSourceDay: number | null;
}

interface CreateGameplayCanonicalStateArgs {
  playerId: string;
  currentDay: number;
  sessionStatus: DailySessionStatus;
  dashboard: PlayerDashboardResponse | null;
  endOfDay: EndOfDaySummaryResponse | null;
}

// toNullableJob replaced by the shared normalizeJobName helper from economySafety.

export function resolveSettledEndOfDay(
  sessionStatus: DailySessionStatus,
  endOfDay: EndOfDaySummaryResponse | null,
): EndOfDaySummaryResponse | null {
  if (sessionStatus !== 'ended') return null;
  return endOfDay || null;
}

export function createGameplayCanonicalState({
  playerId,
  currentDay,
  sessionStatus,
  dashboard,
  endOfDay,
}: CreateGameplayCanonicalStateArgs): GameplayCanonicalState {
  const settledEndOfDay = resolveSettledEndOfDay(sessionStatus, endOfDay);
  const incomeAmount = settledEndOfDay
    ? normalizeOptionalMoneyValue(settledEndOfDay.total_earned_xgp, { allowNegative: false, fallback: 0 })
    : null;
  const expenseAmount = settledEndOfDay
    ? normalizeOptionalMoneyValue(settledEndOfDay.total_spent_xgp, { allowNegative: false, fallback: 0 })
    : null;
  const netCashFlow = settledEndOfDay
    ? safeNetCashFlowCalculation(incomeAmount, expenseAmount, settledEndOfDay.net_change_xgp)
    : null;

  return {
    playerId,
    currentDay: normalizeCurrentDay(currentDay, 1),
    sessionStatus,
    hasDashboardSnapshot: Boolean(dashboard),
    hasSettledEndOfDay: Boolean(settledEndOfDay),
    cashOnHand: normalizeMoneyValue(dashboard?.stats.cash_xgp, { fallback: 0, allowNegative: true }),
    debtAmount: normalizeMoneyValue(dashboard?.stats.debt_xgp, { fallback: 0, allowNegative: false }),
    netWorthAmount: normalizeMoneyValue(dashboard?.stats.net_worth_xgp, { fallback: 0, allowNegative: true }),
    stress: normalizePercentageStat(dashboard?.stats.stress, 0),
    health: normalizePercentageStat(dashboard?.stats.health, 100),
    currentJob: normalizeJobName(dashboard?.stats.current_job),
    incomeAmount,
    expenseAmount,
    netCashFlow,
    incomeSource: normalizeJobName(settledEndOfDay?.biggest_gain),
    tomorrowWarnings: Array.isArray(settledEndOfDay?.tomorrow_warnings)
      ? settledEndOfDay.tomorrow_warnings
      : [],
    topRisks: Array.isArray(dashboard?.top_risks) ? dashboard.top_risks : [],
    activeEventId: null,
    activeEventSourceDay: null,
  };
}

export function attachGameplayEventState(
  state: GameplayCanonicalState,
  activeEvent: ActiveRandomEvent | null,
): GameplayCanonicalState {
  if (!activeEvent) {
    return {
      ...state,
      activeEventId: null,
      activeEventSourceDay: null,
    };
  }

  return {
    ...state,
    activeEventId: activeEvent.eventId,
    activeEventSourceDay: activeEvent.sourceDay,
  };
}