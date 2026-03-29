export type DebtPressureLevel = 'low' | 'moderate' | 'high' | 'critical';

export type EconomyStatus = 'stable' | 'watch' | 'strained' | 'critical';

export interface GameplayEconomyState {
  cashOnHand: number;
  incomeAmount: number | null;
  expenseAmount: number | null;
  debtAmount: number;
  netWorthAmount: number;
  netCashFlow: number | null;
  debtPressure: DebtPressureLevel;
  economyStatus: EconomyStatus;
  economyWarnings: string[];
  cashFlowLabel: string;
  statusLabel: string;
  summaryLine: string;
}