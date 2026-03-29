// Gold Penny — random event pool, recovery action pool, and generation logic.
// All event definitions live here so logic stays off UI files.
// Numeric values reference BALANCE constants — tune them in balanceConfig.ts.

import { BALANCE } from '@/lib/balanceConfig';
import { clampDeltaRange, normalizeMoneyValue } from '@/lib/economySafety';
import { RandomEventDefinition, RecoveryActionDefinition } from '@/types/randomEvent';

function sanitizeRandomEventDefinition(definition: RandomEventDefinition): RandomEventDefinition {
  return {
    ...definition,
    cashDelta: clampDeltaRange(definition.cashDelta),
    expenseDelta: clampDeltaRange(definition.expenseDelta, { min: 0, fallback: 0 }),
    debtDelta: clampDeltaRange(definition.debtDelta),
  };
}

function sanitizeRecoveryActionDefinition(action: RecoveryActionDefinition): RecoveryActionDefinition {
  const cashCost = normalizeMoneyValue(action.cashCost, { fallback: 0, allowNegative: false });
  return {
    ...action,
    cashCost,
    cashGain: normalizeMoneyValue(action.cashGain, { fallback: 0, allowNegative: false }),
    debtReduction: normalizeMoneyValue(action.debtReduction, { fallback: 0, allowNegative: false }),
    minCashRequired: normalizeMoneyValue(action.minCashRequired, {
      fallback: cashCost,
      allowNegative: false,
      min: cashCost,
    }),
  };
}

// ─── Event pool ───────────────────────────────────────────────────────────────

const RANDOM_EVENT_DEFINITIONS: RandomEventDefinition[] = [
  {
    eventId: 'unexpected_bill',
    category: 'expense',
    title: 'Unexpected Bill',
    description: "An unplanned bill arrived — a charge you didn't budget for.",
    effectSummary: `-${BALANCE.EVENT.UNEXPECTED_BILL_LOSS} xgp cash`,
    cashDelta: -BALANCE.EVENT.UNEXPECTED_BILL_LOSS,
    expenseDelta: 0,
    debtDelta: 0,
    severity: 'medium',
  },
  {
    eventId: 'extra_shift',
    category: 'income',
    title: 'Extra Shift Bonus',
    description: 'You picked up an extra shift and earned a small bonus on top of regular income.',
    effectSummary: `+${BALANCE.EVENT.EXTRA_SHIFT_GAIN} xgp cash`,
    cashDelta: BALANCE.EVENT.EXTRA_SHIFT_GAIN,
    expenseDelta: 0,
    debtDelta: 0,
    severity: 'low',
  },
  {
    eventId: 'minor_debt_fee',
    category: 'debt',
    title: 'Minor Debt Fee',
    description: 'A small processing fee was added to one of your outstanding debts.',
    effectSummary: `+${BALANCE.EVENT.MINOR_DEBT_FEE} xgp debt`,
    cashDelta: 0,
    expenseDelta: 0,
    debtDelta: BALANCE.EVENT.MINOR_DEBT_FEE,
    severity: 'low',
  },
  {
    eventId: 'car_repair',
    category: 'expense',
    title: 'Car Repair',
    description: 'Your vehicle needed an unexpected repair today.',
    effectSummary: `-${BALANCE.EVENT.CAR_REPAIR_LOSS} xgp cash`,
    cashDelta: -BALANCE.EVENT.CAR_REPAIR_LOSS,
    expenseDelta: 0,
    debtDelta: 0,
    severity: 'high',
  },
  {
    eventId: 'grocery_spike',
    category: 'expense',
    title: 'Grocery Price Spike',
    description: 'Grocery prices spiked this week and caught you short.',
    effectSummary: `-${BALANCE.EVENT.GROCERY_SPIKE_LOSS} xgp cash`,
    cashDelta: -BALANCE.EVENT.GROCERY_SPIKE_LOSS,
    expenseDelta: 0,
    debtDelta: 0,
    severity: 'low',
  },
  {
    eventId: 'side_income_surprise',
    category: 'income',
    title: 'Side Income Surprise',
    description: 'A small unexpected windfall from a past gig came through.',
    effectSummary: `+${BALANCE.EVENT.SIDE_INCOME_GAIN} xgp cash`,
    cashDelta: BALANCE.EVENT.SIDE_INCOME_GAIN,
    expenseDelta: 0,
    debtDelta: 0,
    severity: 'low',
  },
  {
    eventId: 'missed_opportunity',
    category: 'life',
    title: 'Missed Opportunity',
    description: 'Low energy today — a good opportunity slipped past you.',
    effectSummary: `-${BALANCE.EVENT.MISSED_OPPORTUNITY_LOSS} xgp cash`,
    cashDelta: -BALANCE.EVENT.MISSED_OPPORTUNITY_LOSS,
    expenseDelta: 0,
    debtDelta: 0,
    severity: 'low',
  },
  {
    eventId: 'financial_relief',
    category: 'debt',
    title: 'Financial Relief',
    description: 'A small credit or relief payment reduced your outstanding balance.',
    effectSummary: `-${BALANCE.EVENT.FINANCIAL_RELIEF} xgp debt`,
    cashDelta: 0,
    expenseDelta: 0,
    debtDelta: -BALANCE.EVENT.FINANCIAL_RELIEF,
    severity: 'low',
  },
];

export const RANDOM_EVENT_POOL: RandomEventDefinition[] = RANDOM_EVENT_DEFINITIONS.map(sanitizeRandomEventDefinition);

// ─── Recovery action pool ─────────────────────────────────────────────────────

const RECOVERY_ACTION_DEFINITIONS: RecoveryActionDefinition[] = [
  {
    recoveryActionId: 'cut_spending',
    label: 'Cut Spending',
    effectSummary: `Skip optional spending today. Recover +${BALANCE.RECOVERY.CUT_SPENDING_GAIN} xgp.`,
    cashCost: 0,
    cashGain: BALANCE.RECOVERY.CUT_SPENDING_GAIN,
    debtReduction: 0,
    minCashRequired: 0,
  },
  {
    recoveryActionId: 'rest',
    label: 'Rest',
    effectSummary: 'Rest and recover. No immediate cash change — keeps energy up.',
    cashCost: 0,
    cashGain: 0,
    debtReduction: 0,
    minCashRequired: 0,
  },
  {
    recoveryActionId: 'debt_payment',
    label: 'Debt Payment',
    effectSummary: `Pay ${BALANCE.RECOVERY.DEBT_PAYMENT_COST} xgp toward debt, reducing balance by ${BALANCE.RECOVERY.DEBT_PAYMENT_REDUCTION} xgp.`,
    cashCost: BALANCE.RECOVERY.DEBT_PAYMENT_COST,
    cashGain: 0,
    debtReduction: BALANCE.RECOVERY.DEBT_PAYMENT_REDUCTION,
    minCashRequired: BALANCE.RECOVERY.DEBT_PAYMENT_MIN_CASH,
  },
  {
    recoveryActionId: 'quick_side_hustle',
    label: 'Quick Side Hustle',
    effectSummary: `Take on a quick task and earn +${BALANCE.RECOVERY.SIDE_HUSTLE_GAIN} xgp.`,
    cashCost: 0,
    cashGain: BALANCE.RECOVERY.SIDE_HUSTLE_GAIN,
    debtReduction: 0,
    minCashRequired: 0,
  },
  {
    recoveryActionId: 'skip_optional_expense',
    label: 'Skip Optional Expense',
    effectSummary: `Skip one discretionary expense. Recover +${BALANCE.RECOVERY.SKIP_EXPENSE_GAIN} xgp.`,
    cashCost: 0,
    cashGain: BALANCE.RECOVERY.SKIP_EXPENSE_GAIN,
    debtReduction: 0,
    minCashRequired: 0,
  },
];

export const RECOVERY_ACTION_POOL: RecoveryActionDefinition[] = RECOVERY_ACTION_DEFINITIONS.map(sanitizeRecoveryActionDefinition);

// ─── Logic ────────────────────────────────────────────────────────────────────

/**
 * Roll a deterministic event for a given player + game day.
 * Uses a non-cryptographic hash so the same player+day always produces the same roll.
 * Returns an event (~50% of days) or null.
 *
 * The hash bit determines whether an event fires at all.
 * The upper bits pick which event from the pool.
 */
export function rollDailyEvent(
  playerId: string,
  gameDay: number,
): RandomEventDefinition | null {
  const seed = `${playerId}:${gameDay}`;
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = ((hash * 31) + seed.charCodeAt(i)) >>> 0;
  }
  // Lowest bit determines whether an event fires (~50% chance).
  if ((hash & 1) === 0) return null;
  const index =
    ((hash >>> 1) % RANDOM_EVENT_POOL.length + RANDOM_EVENT_POOL.length) %
    RANDOM_EVENT_POOL.length;
  const rolled = RANDOM_EVENT_POOL[index];
  if (gameDay <= 3 && rolled?.severity === 'high') return null;
  return rolled;
}

/**
 * Return recovery actions the player can currently afford.
 * Actions requiring more cash than `cashOnHand` are excluded.
 */
export function getAvailableRecoveryActions(
  cashOnHand: number,
): RecoveryActionDefinition[] {
  const safeCashOnHand = normalizeMoneyValue(cashOnHand, { fallback: 0, allowNegative: true });
  return RECOVERY_ACTION_POOL.filter(
    (action) => safeCashOnHand >= action.minCashRequired,
  );
}
