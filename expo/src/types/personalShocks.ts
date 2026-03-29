export interface PersonalShockProfileResponse {
  player_id: string;
  as_of_date: string;
  day_number: number;
  shock_risk_score: number;
  financial_fragility_score: number;
  health_fragility_score: number;
  work_disruption_risk_score: number;
  recovery_capacity_score: number;
  recent_pressure_direction: string;
  recent_negative_streak: number;
  recent_recovery_support: number;
  last_updated_on: number;
  last_updated_date: string;
  debug_meta?: Record<string, unknown>;
}

export interface PersonalRiskStateResponse {
  player_id: string;
  as_of_date: string;
  day_number: number;
  shock_risk_label: string;
  event_roll_chance: number;
  severity_weights: Record<string, number>;
  major_event_probability: number;
  repeat_shock_protection_active: boolean;
  debug_meta?: Record<string, unknown>;
}

export interface PersonalLifeEventResponse {
  event_triggered: boolean;
  event_key?: string | null;
  event_family?: string | null;
  headline: string;
  severity_band: string;
  as_of_date?: string | null;
  day_number?: number | null;
  cash_impact_xgp: number;
  stress_impact_delta: number;
  health_impact_delta: number;
  time_impact_hours: number;
  work_income_impact: number;
  business_impact: number;
  side_income_impact: number;
  duration_days: number;
  recovery_hint: string;
  trigger_tags: string[];
  impact: Record<string, unknown>;
  debug_meta?: Record<string, unknown>;
}

export interface RecoveryStateResponse {
  player_id?: string | null;
  recovery_days_remaining: number;
  temporary_stress_modifier: number;
  temporary_health_modifier: number;
  temporary_income_modifier: number;
  temporary_business_modifier: number;
  temporary_time_modifier: number;
  recovery_status_label: string;
  source_event_key?: string | null;
  source_event_severity?: string | null;
  last_applied_day?: number | null;
  next_expire_day?: number | null;
  short_summary: string;
  debug_meta?: Record<string, unknown>;
}

export interface PlayerResilienceSummaryResponse {
  player_id: string;
  as_of_date: string;
  resilience_label: string;
  cash_buffer_label: string;
  stress_load_label: string;
  recovery_capacity_label: string;
  top_risk_driver: string;
  top_stabilizer: string;
  short_summary: string;
  debug_meta?: Record<string, unknown>;
}

export interface PersonalShockSummaryResponse {
  player_id: string;
  as_of_date: string;
  current_shock_risk_label: string;
  recent_event_summary: string;
  active_recovery_summary: string;
  practical_current_actions: string[];
  short_recommendation: string;
  debug_meta?: Record<string, unknown>;
}

export interface PersonalShockSystemSummaryResponse {
  player_id: string;
  as_of_date: string;
  shock_profile: PersonalShockProfileResponse;
  risk_state: PersonalRiskStateResponse;
  recent_event: PersonalLifeEventResponse;
  recovery_state: RecoveryStateResponse;
  resilience_summary: PlayerResilienceSummaryResponse;
  shock_summary: PersonalShockSummaryResponse;
  debug_meta?: Record<string, unknown>;
}

