import { SupplyChainStoryResponse, SupplyChainSummaryResponse } from '@/types/supplyChain';

export type MarketMood = 'supportive' | 'mixed' | 'pressured' | string;
export type TrendLabel = 'rising' | 'falling' | 'stable' | string;
export type VolatilityLabel = 'calm' | 'moderate' | 'high' | string;
export type MarginOutlook = 'favorable' | 'mixed' | 'pressured' | string;
export type DemandOutlook = 'supportive' | 'stable' | 'soft' | string;
export type CostPressure = 'low' | 'moderate' | 'high' | string;
export type CommutePressureLevel = 'low' | 'moderate' | 'high' | string;

export interface MarketOverviewResponse {
  player_id: string;
  as_of_date: string;
  current_market_mood: MarketMood;
  headline_drivers: string[];
  top_winners: string[];
  top_losers: string[];
  macro_trend_labels: Record<string, string>;
  basket_pressure_labels: Record<string, string>;
  short_explainer: string;
  debug_meta?: Record<string, unknown>;
}

export interface PriceTrendItem {
  basket_key: string;
  current_level: number;
  short_term_trend: TrendLabel;
  volatility_label: VolatilityLabel;
  primary_driver: string;
  player_impact_summary: string;
  debug_meta?: Record<string, unknown>;
}

export interface PriceTrendsResponse {
  player_id: string;
  as_of_date: string;
  items: PriceTrendItem[];
  debug_meta?: Record<string, unknown>;
}

export interface BusinessMarginItem {
  business_key: string;
  margin_outlook: MarginOutlook;
  demand_outlook: DemandOutlook;
  cost_pressure: CostPressure;
  risk_factors: string[];
  opportunity_factors: string[];
  short_explainer: string;
  debug_meta?: Record<string, unknown>;
}

export interface BusinessMarginsResponse {
  player_id: string;
  as_of_date: string;
  items: BusinessMarginItem[];
  debug_meta?: Record<string, unknown>;
}

export interface CommutePressureResponse {
  player_id: string;
  as_of_date: string;
  region_key: string;
  commute_pressure_level: CommutePressureLevel;
  estimated_commute_burden: string;
  stress_impact_label: string;
  time_impact_label: string;
  housing_tradeoff_summary: string;
  suggested_current_responses: string[];
  future_locked_solutions: string[];
  debug_meta?: Record<string, unknown>;
}

export interface PlayerEconomyExplainerResponse {
  player_id: string;
  as_of_date: string;
  why_costs_changed: string;
  why_business_changed: string;
  why_commute_changed: string;
  why_stress_changed: string;
  this_week_focus: string;
  suggested_defensive_move: string;
  suggested_growth_move: string;
  debug_meta?: Record<string, unknown>;
}

export interface FutureOpportunityTeaser {
  teaser_key: string;
  title: string;
  body: string;
  unlock_status: 'locked' | string;
  category: string;
  debug_meta?: Record<string, unknown>;
}

export interface FutureOpportunityTeasersResponse {
  player_id: string;
  as_of_date: string;
  teasers: FutureOpportunityTeaser[];
  debug_meta?: Record<string, unknown>;
}

export interface DailyEconomyBriefResponse {
  as_of_date: string;
  day: number;
  headline: string;
  summary_lines: string[];
  top_bottlenecks: string[];
  top_basket_movers: string[];
  top_job_changes: string[];
  debug_meta?: Record<string, unknown>;
}

export interface DailySettlementDigestResponse {
  day_number: number;
  income_xgp: number;
  expenses_xgp: number;
  net_change_xgp: number;
  cash_after_xgp: number;
  stress_change: number;
  health_change: number;
  debug_meta?: Record<string, unknown>;
}

export interface EconomyPresentationSummaryResponse {
  player_id: string;
  as_of_date: string;
  current_day: number;
  market_overview: MarketOverviewResponse;
  price_trends: PriceTrendsResponse;
  business_margins: BusinessMarginsResponse;
  commute_pressure: CommutePressureResponse;
  explainer: PlayerEconomyExplainerResponse;
  future_teasers: FutureOpportunityTeasersResponse;
  daily_brief: DailyEconomyBriefResponse;
  supply_chain_summary: SupplyChainSummaryResponse;
  supply_chain_story: SupplyChainStoryResponse;
  settlement_summary?: DailySettlementDigestResponse | null;
  player_warnings: string[];
  player_opportunities: string[];
  debug_meta?: Record<string, unknown>;
}
