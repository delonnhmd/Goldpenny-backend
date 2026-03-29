// Step 42: Forecasting, Planning Intelligence, and Forward Projection Layer — TypeScript type definitions.
// Auto-generated from app/schemas/forecasting.py

export interface ProjectedCashEntry {
  day: number;
  cash_xgp: number;
  daily_net_xgp: number;
}

export interface ProjectedObligationHit {
  obligation_key: string;
  family: string;
  type: string;
  amount_xgp: number;
  due_on_day: number;
  days_away: number;
  status: string;
}

export interface ProjectedIncomeEvent {
  income_key: string;
  type: string;
  amount_xgp: number;
  due_on_day: number;
  days_away: number;
  status: string;
}

export interface ShortTermForecastResponse {
  player_id: string;
  day: number;
  forecast_horizon_days: number;
  projected_cash_curve: ProjectedCashEntry[];
  projected_obligation_hits: ProjectedObligationHit[];
  projected_income_events: ProjectedIncomeEvent[];
  projected_liquidity_low_point: number;
  projected_liquidity_low_day: number;
  projected_delinquency_risk_day: number | null;
  projected_stress_trend: string;
  projected_debt_trend: string;
  confidence_level: string;
  short_summary: string;
  debug_meta?: Record<string, unknown> | null;
}

export interface RiskProjectionResponse {
  player_id: string;
  day: number;
  near_term_risk_label: string;
  delinquency_risk_label: string;
  cash_gap_risk_label: string;
  debt_spiral_risk_projection: string;
  timing_collision_risk: string;
  composite_risk_score: number;
  projected_liquidity_low_point_xgp: number;
  projected_delinquency_risk_day: number | null;
  short_summary: string;
  debug_meta?: Record<string, unknown> | null;
}

export interface ForecastSummaryResponse {
  player_id: string;
  day: number;
  overall_outlook_label: string;
  next_major_risk_event: string;
  days_until_next_problem: number | null;
  best_stabilizing_action: string;
  worst_action_to_take: string;
  projected_liquidity_low_point_xgp: number;
  confidence_level: string;
  short_summary: string;
  debug_meta?: Record<string, unknown> | null;
}

export interface SimulationRequest {
  action: string;
  horizon_days?: number;
}

export interface SimulationBaseline {
  projected_liquidity_low_point: number;
  liquidity_low_day: number;
  delinquency_risk_day: number | null;
  end_cash_xgp: number;
  outcome_label: string;
}

export interface SimulationSimulated {
  projected_cash_curve: ProjectedCashEntry[];
  projected_liquidity_low_point: number;
  liquidity_low_day: number;
  delinquency_risk_day: number | null;
  end_cash_xgp: number;
  outcome_label: string;
  risk_label: string;
  stability_label: string;
}

export interface SimulationNetEffect {
  cash_change_end_xgp: number;
  delinquency_risk_change: string;
  stability_change: string;
}

export interface SimulationResponse {
  player_id: string;
  day: number;
  action: string;
  action_note: string;
  baseline: SimulationBaseline;
  simulated: SimulationSimulated;
  net_effect: SimulationNetEffect;
  projected_obligations: ProjectedObligationHit[];
  projected_income: ProjectedIncomeEvent[];
  debug_meta?: Record<string, unknown> | null;
}

export interface ScenarioComparisonRequest {
  actions: string[];
  horizon_days?: number;
}

export interface ScenarioOption {
  option_key: string;
  action_note: string;
  short_term_outcome_label: string;
  medium_term_outcome_label: string;
  risk_label: string;
  stability_label: string;
  net_effect_summary: string;
  projected_end_cash_xgp: number;
  liquidity_low_point_xgp: number;
  delinquency_risk_day: number | null;
}

export interface ScenarioComparisonResponse {
  player_id: string;
  day: number;
  horizon_days: number;
  options: ScenarioOption[];
  recommended_option_key: string;
  recommendation_reason: string;
  debug_meta?: Record<string, unknown> | null;
}

export interface DecisionGuidanceResponse {
  player_id: string;
  day: number;
  guidance_label: string;
  top_recommendation: string;
  avoid_action: string;
  confidence_label: string;
  reasoning_summary: string;
  debug_meta?: Record<string, unknown> | null;
}

export interface ForecastSnapshotResponse {
  player_id: string;
  snapshot_id: string;
  day: number;
  overall_outlook_label: string;
  composite_risk_score: number;
  projected_liquidity_low_point_xgp: number;
  projected_delinquency_risk_day: number | null;
  days_until_next_problem: number | null;
  near_term_risk_label: string;
  delinquency_risk_label: string;
  cash_gap_risk_label: string;
  debt_spiral_risk_label: string;
  guidance_label: string;
  top_recommendation: string;
  avoid_action: string;
  confidence_level: string;
  debug_meta?: Record<string, unknown> | null;
}
