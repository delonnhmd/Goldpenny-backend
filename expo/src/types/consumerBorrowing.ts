export interface BorrowingEligibilityProfileResponse {
  player_id: string;
  as_of_date: string;
  day_number: number;
  borrowing_access_score: number;
  credit_access_tier: string;
  emergency_liquidity_label: string;
  max_safe_borrow_amount_xgp: number;
  estimated_risk_pricing_band: string;
  recent_distress_penalty: number;
  dependence_risk_score: number;
  active_loan_count: number;
  repeat_borrowing_count_30d: number;
  last_updated_on: number;
  debug_meta?: Record<string, unknown>;
}

export interface EmergencyLiquidityStateResponse {
  player_id: string;
  as_of_date: string;
  day_number: number;
  days_to_cash_stress: number;
  days_to_payment_failure: number;
  liquidity_gap_xgp: number;
  bridge_need_label: string;
  survival_borrowing_pressure_label: string;
  preferred_relief_type: string;
  short_summary: string;
  debug_meta?: Record<string, unknown>;
}

export interface BorrowingOfferResponse {
  offer_key: string;
  offer_family: string;
  headline: string;
  approval_likelihood_label: string;
  principal_offered_xgp: number;
  estimated_total_cost_xgp: number;
  estimated_repay_xgp: number;
  term_days: number;
  term_label: string;
  apr_pct: number;
  fee_pct: number;
  payment_burden_label: string;
  risk_label: string;
  emergency_usefulness_label: string;
  hidden_danger_summary: string;
  rollover_allowed: boolean;
  short_summary: string;
  locked: boolean;
  locked_reason?: string | null;
  debug_meta?: Record<string, unknown>;
}

export interface BorrowingOptionsResponse {
  player_id: string;
  as_of_date: string;
  day_number: number;
  items: BorrowingOfferResponse[];
  debug_meta?: Record<string, unknown>;
}

export interface BorrowingRiskSummaryResponse {
  player_id: string;
  as_of_date: string;
  risk_label: string;
  short_term_relief_label: string;
  future_burden_label: string;
  credit_protection_value_label: string;
  top_risk_driver: string;
  top_reason_to_avoid: string;
  top_reason_to_consider: string;
  short_summary: string;
  debug_meta?: Record<string, unknown>;
}

export interface BorrowingPressureSummaryResponse {
  player_id: string;
  as_of_date: string;
  current_liquidity_pressure_label: string;
  best_available_option_label: string;
  worst_trap_warning: string;
  practical_current_actions: string[];
  short_recommendation: string;
  future_locked_options: string[];
  debug_meta?: Record<string, unknown>;
}

export interface BorrowingDecisionRequest {
  offer_key: string;
  principal_requested_xgp?: number | null;
}

export interface BorrowingDecisionResponse {
  player_id: string;
  as_of_date: string;
  day_number: number;
  offer_key: string;
  offer_family: string;
  accepted: boolean;
  loan_account_id: string;
  cash_before_xgp: number;
  cash_after_xgp: number;
  debt_before_xgp: number;
  debt_after_xgp: number;
  principal_accepted_xgp: number;
  estimated_total_cost_xgp: number;
  scheduled_daily_payment_xgp: number;
  risk_label: string;
  short_term_relief_label: string;
  future_burden_label: string;
  eligibility_profile_after: BorrowingEligibilityProfileResponse;
  liquidity_state_after: EmergencyLiquidityStateResponse;
  risk_summary_after: BorrowingRiskSummaryResponse;
  debug_meta?: Record<string, unknown>;
}

export interface PlayerLoanAccountsResponse {
  player_id: string;
  entries: Array<Record<string, unknown>>;
  debug_meta?: Record<string, unknown>;
}

export interface PlayerBorrowingHistoryResponse {
  player_id: string;
  as_of_date: string;
  entries: Array<Record<string, unknown>>;
  debug_meta?: Record<string, unknown>;
}

export interface ConsumerBorrowingSystemSummaryResponse {
  player_id: string;
  as_of_date: string;
  day_number: number;
  eligibility_profile: BorrowingEligibilityProfileResponse;
  liquidity_state: EmergencyLiquidityStateResponse;
  options: BorrowingOptionsResponse;
  risk_summary: BorrowingRiskSummaryResponse;
  pressure_summary: BorrowingPressureSummaryResponse;
  loan_accounts: PlayerLoanAccountsResponse;
  history: PlayerBorrowingHistoryResponse;
  debug_meta?: Record<string, unknown>;
}
