export interface RegionPopulationStateResponse {
  player_id: string;
  as_of_date: string;
  region_key: string;
  heat_level: string;
  active_population_score: number;
  opportunity_density_score: number;
  congestion_score: number;
  housing_pressure_score: number;
  business_competition_score: number;
  consumer_flow_score: number;
  recent_growth_direction: string;
  last_updated_on: number;
  last_updated_date?: string | null;
  memory_window_start?: string | null;
  memory_window_end?: string | null;
  short_summary?: string | null;
  practical_current_responses?: string[];
  future_locked_response_options?: string[];
  debug_meta?: Record<string, unknown>;
}

export interface LocalOpportunityPressureResponse {
  player_id: string;
  as_of_date: string;
  region_key: string;
  opportunity_density_label: string;
  job_access_label: string;
  business_demand_label: string;
  local_advantage_summary: string;
  local_friction_summary: string;
  debug_meta?: Record<string, unknown>;
}

export interface LocalCompetitionStateResponse {
  player_id: string;
  as_of_date: string;
  region_key: string;
  competition_level: string;
  business_competition_label: string;
  demand_share_pressure: number;
  short_summary: string;
  debug_meta?: Record<string, unknown>;
}

export interface RegionHeatSummaryResponse {
  player_id: string;
  as_of_date: string;
  region_key: string;
  heat_level: string;
  dominant_upside: string;
  dominant_friction: string;
  housing_tradeoff_summary: string;
  business_climate_summary: string;
  commute_summary: string;
  debug_meta?: Record<string, unknown>;
}

export interface PopulationResponseSummaryResponse {
  player_id: string;
  as_of_date: string;
  region_key: string;
  current_pressure_summary: string;
  practical_current_responses: string[];
  short_recommendation: string;
  future_locked_response_options: string[];
  debug_meta?: Record<string, unknown>;
}

export interface PopulationPressureSummaryResponse {
  player_id: string;
  as_of_date: string;
  region_state: RegionPopulationStateResponse;
  opportunity_pressure: LocalOpportunityPressureResponse;
  competition_state: LocalCompetitionStateResponse;
  region_heat: RegionHeatSummaryResponse;
  response_summary: PopulationResponseSummaryResponse;
  debug_meta?: Record<string, unknown>;
}
