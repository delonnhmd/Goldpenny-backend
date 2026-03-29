export type WorldPatternCategory = 'macro' | 'commute' | 'business' | 'life' | 'region' | string;
export type WorldPatternDirection = 'rising' | 'falling' | 'stable' | string;
export type WorldPatternSeverity = 'low' | 'moderate' | 'high' | string;
export type WorldPatternConfidence = 'low' | 'moderate' | 'high' | string;
export type WorldPatternStatus = 'active' | 'fading' | 'resolved' | string;

export interface WorldPatternItem {
  pattern_key: string;
  category: WorldPatternCategory;
  title: string;
  short_description: string;
  direction: WorldPatternDirection;
  consecutive_days: number;
  persistence_score: number;
  severity: WorldPatternSeverity;
  confidence: WorldPatternConfidence;
  affected_systems: string[];
  current_status: WorldPatternStatus;
  recommended_response: string;
  future_locked_response?: string | null;
  debug_meta?: Record<string, unknown>;
}

export interface WorldPatternsResponse {
  player_id: string;
  as_of_date: string;
  items: WorldPatternItem[];
  debug_meta?: Record<string, unknown>;
}

export interface WorldNarrativeResponse {
  player_id: string;
  as_of_date: string;
  headline: string;
  body: string;
  key_active_patterns: string[];
  what_is_persisting: string[];
  what_is_fading: string[];
  what_to_watch_next: string[];
  recommended_short_response: string;
  future_locked_long_response: string;
  debug_meta?: Record<string, unknown>;
}

export interface LocalPressureSummaryResponse {
  player_id: string;
  as_of_date: string;
  region_key: string;
  local_pressure_level: 'low' | 'moderate' | 'high' | string;
  congestion_label: 'low' | 'moderate' | 'high' | string;
  opportunity_label: 'low' | 'moderate' | 'high' | string;
  cost_pressure_label: 'low' | 'moderate' | 'high' | string;
  business_climate_label: 'supportive' | 'mixed' | 'pressured' | string;
  short_summary: string;
  practical_response_options: string[];
  future_locked_solution_teasers: string[];
  debug_meta?: Record<string, unknown>;
}

export interface PlayerPatternSummaryResponse {
  player_id: string;
  as_of_date: string;
  dominant_player_pattern: string;
  supporting_patterns: string[];
  risk_patterns: string[];
  improving_patterns: string[];
  summary: string;
  suggested_correction: string;
  debug_meta?: Record<string, unknown>;
}

export interface RegionMemorySummaryResponse {
  player_id: string;
  as_of_date: string;
  region_key: string;
  region_identity_trend: string;
  dominant_region_pressures: string[];
  dominant_region_opportunities: string[];
  recent_change_summary: string;
  current_tradeoff_identity: string;
  debug_meta?: Record<string, unknown>;
}

export interface WorldMemorySnapshotResponse {
  player_id: string;
  as_of_date?: string | null;
  region_key: string;
  memory_window_start?: string | null;
  memory_window_end?: string | null;
  macro_pressure_score: number;
  commute_pressure_score: number;
  business_pressure_score: number;
  life_pressure_score: number;
  opportunity_score: number;
  dominant_patterns: WorldPatternItem[];
  narrative_state: Record<string, unknown>;
  local_pressure_summary: Record<string, unknown>;
  player_pattern_summary: Record<string, unknown>;
  region_memory_summary: Record<string, unknown>;
  debug_meta?: Record<string, unknown>;
}

export interface WorldMemoryHistoryItem {
  pattern_key: string;
  category: WorldPatternCategory;
  title: string;
  first_seen_on?: string | null;
  last_seen_on?: string | null;
  consecutive_days: number;
  persistence_score: number;
  severity: WorldPatternSeverity;
  direction: WorldPatternDirection;
  status: WorldPatternStatus;
  summary: string;
  recommended_response?: string | null;
  future_locked_response?: string | null;
  debug_meta?: Record<string, unknown>;
}

export interface WorldMemoryHistoryResponse {
  player_id: string;
  as_of_date: string;
  entries: WorldMemoryHistoryItem[];
  debug_meta?: Record<string, unknown>;
}

export interface WorldMemorySummaryResponse {
  player_id: string;
  as_of_date: string;
  snapshot: WorldMemorySnapshotResponse;
  patterns: WorldPatternsResponse;
  narrative: WorldNarrativeResponse;
  local_pressure: LocalPressureSummaryResponse;
  player_patterns: PlayerPatternSummaryResponse;
  region_memory: RegionMemorySummaryResponse;
  debug_meta?: Record<string, unknown>;
}
