export interface WealthProfileResponse {
  player_id: string;
  day_number: number;
  as_of_date: string;
  cash_reserve_xgp: number;
  savings_reserve_xgp: number;
  investable_surplus_xgp: number;
  debt_drag_xgp: number;
  net_worth_xgp: number;
  liquid_asset_value_xgp: number;
  market_asset_value_xgp: number;
  business_equity_xgp: number;
  total_asset_value_xgp: number;
  total_debt_xgp: number;
  wealth_momentum_score: number;
  stability_before_growth_score: number;
  buffer_days: number;
  wealth_phase_label: string;
  asset_growth_trend: string;
  safe_to_save_label: string;
  safe_to_invest_label: string;
  experience_phase: string;
  days_in_phase: number;
  softening_active: boolean;
  top_growth_driver: string;
  top_drag_driver: string;
  false_growth_detected: boolean;
  false_growth_warnings: string[];
  planning_insights: string[];
  debug_meta?: Record<string, unknown>;
}

export interface SavingsCapacityStateResponse {
  player_id: string;
  day_number: number;
  as_of_date: string;
  safe_to_save_label: string;
  safe_to_invest_label: string;
  recommended_buffer_days: number;
  current_buffer_days: number;
  daily_obligations_xgp: number;
  investable_surplus_xgp: number;
  excess_cash_label: string;
  short_summary: string;
  debug_meta?: Record<string, unknown>;
}

export interface AssetProgressionStateResponse {
  player_id: string;
  day_number: number;
  as_of_date: string;
  liquid_asset_value_xgp: number;
  market_asset_value_xgp: number;
  business_equity_xgp: number;
  total_asset_value_xgp: number;
  total_debt_xgp: number;
  asset_growth_trend: string;
  asset_quality_label: string;
  diversification_label: string;
  asset_to_debt_ratio: number;
  strong_business_trend: boolean;
  debug_meta?: Record<string, unknown>;
}

export interface WealthActionEvaluationItem {
  action_key: string;
  evaluation_label: string;
  reasoning: string;
}

export interface WealthActionsEvaluationResponse {
  player_id: string;
  day_number: number;
  as_of_date: string;
  evaluations: WealthActionEvaluationItem[];
  buffer_days: number;
  delinquency_stage: string;
  spiral_label: string;
  investable_surplus_xgp: number;
  debug_meta?: Record<string, unknown>;
}

export interface NetWorthSummaryResponse {
  player_id: string;
  day_number: number;
  as_of_date: string;
  net_worth_xgp: number;
  net_worth_direction: string;
  net_worth_delta_xgp: number;
  wealth_phase_label: string;
  growth_quality_label: string;
  false_growth_detected: boolean;
  false_growth_warnings: string[];
  top_growth_driver: string;
  top_drag_driver: string;
  debt_drag_xgp: number;
  debt_drag_ratio: number;
  total_asset_value_xgp: number;
  practical_current_actions: string[];
  short_recommendation: string;
  planning_insights: string[];
  debug_meta?: Record<string, unknown>;
}

export interface WealthMomentumSummaryResponse {
  player_id: string;
  day_number: number;
  as_of_date: string;
  wealth_phase_label: string;
  wealth_momentum_score: number;
  momentum_direction: string;
  stability_before_growth_score: number;
  net_worth_xgp: number;
  buffer_days: number;
  safe_to_save_label: string;
  safe_to_invest_label: string;
  experience_phase: string;
  days_in_phase: number;
  softening_active: boolean;
  softening_modifiers: Record<string, unknown>;
  false_growth_detected: boolean;
  false_growth_warnings: string[];
  asset_growth_trend: string;
  market_asset_value_xgp: number;
  business_equity_xgp: number;
  liquid_asset_value_xgp: number;
  debt_drag_xgp: number;
  top_growth_driver: string;
  top_drag_driver: string;
  phase_advisory: string[];
  planning_insights: string[];
  savings_capacity_summary: string;
  asset_quality_label: string;
  diversification_label: string;
  debug_meta?: Record<string, unknown>;
}
