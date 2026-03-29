export type EventSeverity = 'low' | 'medium' | 'high';

export type EventCategory = 'expense' | 'income' | 'debt' | 'life';

export interface RandomEventDefinition {
  eventId: string;
  category: EventCategory;
  title: string;
  description: string;
  /** Short string shown in the card, e.g. "-75 xgp cash". */
  effectSummary: string;
  /** One-time cash delta (negative = player loses cash, positive = player gains). */
  cashDelta: number;
  /** Recurring expense delta (positive = higher expenses going forward). Currently informational. */
  expenseDelta: number;
  /** Debt delta (positive = more debt, negative = debt reduced). */
  debtDelta: number;
  severity: EventSeverity;
}

export interface ActiveRandomEvent extends RandomEventDefinition {
  sourceDay: number;
  isResolved: boolean;
}

export interface RecoveryActionDefinition {
  recoveryActionId: string;
  label: string;
  /** Short description of what this action does. */
  effectSummary: string;
  /** Cash the player must spend to take this action. */
  cashCost: number;
  /** Immediate cash gain from taking this action. */
  cashGain: number;
  /** Immediate debt reduction from taking this action. */
  debtReduction: number;
  /** Minimum cash balance required before this action is offered. */
  minCashRequired: number;
}

/** Minimal state persisted to AsyncStorage for event continuity across reloads. */
export interface RandomEventPersistedState {
  eventId: string;
  sourceDay: number;
  isResolved: boolean;
}
