export type ConfidenceLabel = 'high' | 'moderate' | 'low' | string;
export type LiquidityRiskLabel = 'low' | 'moderate' | 'high' | string;
export type PressureLevel = 'low' | 'moderate' | 'high' | string;

export interface PlanOptionItem {
  plan_key: string;
  title: string;
  short_description: string;
  likely_upside: string;
  likely_downside: string;
  primary_tradeoff: string;
  suggested_duration_days: number;
  confidence_label: ConfidenceLabel;
  debug_meta?: Record<string, unknown>;
}

export interface ShortHorizonPlansResponse {
  player_id: string;
  as_of_date: string;
  options: PlanOptionItem[];
  debug_meta?: Record<string, unknown>;
}

export interface HousingTradeoffResponse {
  player_id: string;
  as_of_date: string;
  current_region: string;
  current_commute_burden: string;
  closer_housing_cost_pressure: string;
  expected_stress_delta_label: string;
  expected_time_delta_label: string;
  opportunity_access_label: string;
  short_recommendation: string;
  debug_meta?: Record<string, unknown>;
}

export interface DebtVsGrowthItem {
  option_key: string;
  option_label: string;
  defensive_score: number;
  growth_score: number;
  liquidity_risk: LiquidityRiskLabel;
  distress_impact_label: string;
  recommendation_note: string;
  debug_meta?: Record<string, unknown>;
}

export interface DebtVsGrowthResponse {
  player_id: string;
  as_of_date: string;
  items: DebtVsGrowthItem[];
  debug_meta?: Record<string, unknown>;
}

export interface BusinessPlanItem {
  business_key: string;
  business_present: boolean;
  current_mode: string;
  demand_outlook: string;
  input_cost_outlook: string;
  margin_stability: string;
  recommendation_over_horizon: string;
  key_watch_item: string;
  debug_meta?: Record<string, unknown>;
}

export interface BusinessPlanResponse {
  player_id: string;
  as_of_date: string;
  items: BusinessPlanItem[];
  debug_meta?: Record<string, unknown>;
}

export interface RecoveryVsPushResponse {
  player_id: string;
  as_of_date: string;
  current_pressure_level: PressureLevel;
  push_case: string;
  recovery_case: string;
  likely_near_term_cost: string;
  likely_near_term_benefit: string;
  recommendation_summary: string;
  debug_meta?: Record<string, unknown>;
}

export interface StrategyRecommendationResponse {
  player_id: string;
  as_of_date: string;
  recommended_plan_key: string;
  recommended_plan_title: string;
  biggest_risk: string;
  biggest_opportunity: string;
  defensive_move: string;
  growth_move: string;
  avoid_warning: string;
  recommendation_reason: string;
  debug_meta?: Record<string, unknown>;
}

export interface FuturePreparationItem {
  path_key: string;
  title: string;
  why_it_matters_now: string;
  current_preparation_signal: string;
  unlock_status: 'locked' | string;
  category: string;
  debug_meta?: Record<string, unknown>;
}

export interface FuturePreparationResponse {
  player_id: string;
  as_of_date: string;
  items: FuturePreparationItem[];
  debug_meta?: Record<string, unknown>;
}

export interface StrategicPlanningSummaryResponse {
  player_id: string;
  as_of_date: string;
  plans: ShortHorizonPlansResponse;
  housing_tradeoff: HousingTradeoffResponse;
  debt_vs_growth: DebtVsGrowthResponse;
  business_plan: BusinessPlanResponse;
  recovery_vs_push: RecoveryVsPushResponse;
  recommendation: StrategyRecommendationResponse;
  future_preparation: FuturePreparationResponse;
  debug_meta?: Record<string, unknown>;
}
