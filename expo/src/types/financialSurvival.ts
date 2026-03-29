export interface PlayerObligationProfileResponse {
  player_id: string;
  as_of_date: string;
  day_number: number;
  required_monthly_obligation_xgp: number;
  required_daily_burden_xgp: number;
  debt_minimum_obligation_xgp: number;
  housing_obligation_xgp: number;
  business_overhead_obligation_xgp: number;
  loan_obligation_xgp?: number;
  insurance_basic_obligation_xgp: number;
  obligation_load_ratio: number;
  liquidity_buffer_days: number;
  payment_pressure_label: string;
  last_updated_on: number;
  debug_meta?: Record<string, unknown>;
}

export interface PaymentRiskStateResponse {
  player_id: string;
  as_of_date: string;
  day_number: number;
  due_obligations: Array<Record<string, unknown>>;
  full_pay_feasible: boolean;
  partial_pay_feasible: boolean;
  likely_stress_impact: string;
  late_fee_exposure_xgp: number;
  delinquency_exposure: string;
  short_recommendation: string;
  debug_meta?: Record<string, unknown>;
}

export interface DelinquencyStateResponse {
  player_id: string;
  as_of_date: string;
  day_number: number;
  current_delinquency_stage: string;
  survival_status_label: string;
  missed_payment_count_30d: number;
  late_payment_count_30d: number;
  days_under_payment_stress: number;
  last_missed_obligation_type?: string | null;
  credit_pressure_score: number;
  credit_pressure_label: string;
  financial_distress_score: number;
  last_updated_on?: number | null;
  last_updated_date?: string | null;
  debug_meta?: Record<string, unknown>;
}

export interface CreditImpactSummaryResponse {
  credit_score_before: number;
  credit_score_after: number;
  credit_delta: number;
  impact_label: string;
  primary_driver: string;
  future_borrowing_pressure_label: string;
  short_summary: string;
  debug_meta?: Record<string, unknown>;
}

export interface FinancialSurvivalSummaryResponse {
  player_id: string;
  as_of_date: string;
  survival_status_label: string;
  payment_pressure_label: string;
  credit_pressure_label: string;
  liquidity_buffer_label: string;
  top_distress_driver: string;
  top_stabilizer: string;
  practical_current_actions: string[];
  short_summary: string;
  debug_meta?: Record<string, unknown>;
}

export interface FinancialSurvivalPaymentHistoryResponse {
  player_id: string;
  as_of_date: string;
  entries: Array<Record<string, unknown>>;
  trailing_7d_missed_payments: number;
  trailing_7d_late_payments: number;
  trailing_7d_avg_obligation_load_ratio: number;
  trailing_7d_avg_liquidity_buffer_days: number;
  trailing_7d_credit_change: number;
  debug_meta?: Record<string, unknown>;
}

export interface FinancialSurvivalSystemSummaryResponse {
  player_id: string;
  as_of_date: string;
  day_number: number;
  obligation_profile: PlayerObligationProfileResponse;
  payment_risk_state: PaymentRiskStateResponse;
  delinquency_state: DelinquencyStateResponse;
  credit_impact: CreditImpactSummaryResponse;
  survival_summary: FinancialSurvivalSummaryResponse;
  payment_history: FinancialSurvivalPaymentHistoryResponse;
  recent_payment: Record<string, unknown>;
  debug_meta?: Record<string, unknown>;
}
