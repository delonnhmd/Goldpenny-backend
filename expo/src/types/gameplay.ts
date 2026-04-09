export type SeverityLevel = 'info' | 'low' | 'medium' | 'high' | 'critical';

export type GameplayActionKey =
  | 'work_shift'
  | 'side_income'
  | 'operate_business'
  | 'buy_inventory'
  | 'rest'
  | 'study'
  | 'start_training'
  | 'debt_payment'
  | string;

export type DashboardSectionState = 'idle' | 'loading' | 'ready' | 'empty' | 'error';

export type ActionRecommendationState = 'recommended' | 'available' | 'blocked';

export type TrendDirection = 'up' | 'down' | 'flat' | 'mixed';

export type ConfidenceLevel = 'high' | 'medium' | 'low' | 'unknown';

export interface DashboardStatSnapshot {
  cash_xgp: number;
  debt_xgp: number;
  net_worth_xgp: number;
  stress: number;
  health: number;
  credit_score: number;
  current_job?: string | null;
  current_job_display?: string | null;
  region_key?: string | null;
}

export interface JobProgressSnapshot {
  job_key: string;
  job_level: number;
  skill_level: number;
  xp_total?: number;
  job_xp: number;
  job_xp_to_next_level: number;
  max_job_level: number;
  monthly_pay_xgp: number;
  promotion_tier?: string;
  shifts_completed?: number;
  estimated_current_monthly_salary_xgp?: number;
  estimated_next_level_monthly_salary_xgp?: number;
  next_level_salary_increase_pct?: number;
  salary_preview_note?: string;
  employer_company_symbol?: string | null;
  employer_company_name?: string | null;
  position_title?: string | null;
  shift_type?: string | null;
}

export interface JobProgressionTrackSnapshot {
  job_key: string;
  display_name?: string | null;
  status?: 'locked' | 'available' | 'current' | string;
  locked?: boolean;
  requires_certification?: boolean;
  certification_key?: string | null;
  certification_name?: string | null;
  requirement_label?: string | null;
  has_progression?: boolean;
  job_level: number;
  promotion_tier: string;
  job_xp: number;
  job_xp_to_next_level: number;
  shifts_completed: number;
  estimated_current_monthly_salary_xgp: number;
  estimated_next_level_monthly_salary_xgp: number;
  next_level_salary_increase_pct: number;
  salary_preview_note?: string | null;
  last_worked_at?: string | null;
}

export interface JobProgressionFeedbackSnapshot {
  job_key: string;
  xp_gained: number;
  level_before: number;
  level_after: number;
  promotion_tier_before?: string | null;
  promotion_tier_after?: string | null;
  leveled_up: boolean;
  tier_changed?: boolean;
  feedback_message?: string | null;
  progression?: JobProgressSnapshot | null;
}

export interface CompletedShiftSnapshot {
  earned_cash_xgp: number;
  xp_gained: number;
  stress_change: number;
  health_change: number;
  salary_payment_status?: string | null;
  salary_transaction_id?: string | null;
  salary_posted_at?: string | null;
  transaction_confirmed?: boolean;
  job_key?: string | null;
  job_display_name?: string | null;
}

export interface ShiftSalaryAuditSnapshot {
  audit_id: string;
  player_id: string;
  day_number: number;
  shift_token: string;
  shift_id: string;
  job_key: string;
  job_display_name: string;
  shift_started_at?: string | null;
  shift_ends_at?: string | null;
  shift_completed_at?: string | null;
  shift_type?: string | null;
  shift_number: number;
  hours_worked: number;
  trigger?: string | null;
  payment_status: string;
  failure_reason?: string | null;
  base_monthly_salary: number;
  pay_snapshot_used: number;
  base_hourly_pay: number;
  productivity_multiplier: number;
  income_multiplier: number;
  job_level_multiplier: number;
  gross_shift_pay: number;
  final_salary_paid: number;
  xp_gained: number;
  stress_change: number;
  health_change: number;
  fatigue_change: number;
  overtime_penalty_applied: boolean;
  salary_transaction_id?: string | null;
  xgp_transaction_id?: string | null;
  player_transaction_log_id?: string | null;
  salary_posted_at?: string | null;
  cash_before: number;
  cash_after: number;
  transaction_confirmed: boolean;
}

export interface RideshareStateSnapshot {
  can_rideshare: boolean;
  status: 'available' | 'shift_active' | 'limit_reached' | 'not_enough_time' | 'location_restricted' | string;
  reason: string;
  trips_today: number;
  max_trips: number;
  remaining_trips: number;
  hours_remaining_today: number;
  mode: 'morning_peak' | 'midday' | 'evening_peak' | 'night' | string;
  time_cost_per_trip_units?: number;
  current_location_key?: string;
  current_location_label?: string;
  current_location_region?: string;
  location_tier?: string;
  rideshare_allowed_here?: boolean;
  location_label?: string;
  demand_bonus_pct?: number;
  stress_delta_modifier?: number;
  estimated_pay_min_per_trip?: number;
  estimated_pay_max_per_trip?: number;
}

export interface CityMapNodeSnapshot {
  key: string;
  label: string;
  region: string;
  node_type: string;
  opportunity_tier: string;
  rideshare_quality: string;
  is_current_location: boolean;
}

export interface TravelOptionSnapshot {
  from_key: string;
  from_label: string;
  destination_key: string;
  destination_label: string;
  destination_region: string;
  destination_node_type: string;
  destination_opportunity_tier: string;
  time_cost_units: number;
  stress_delta: number;
  cash_cost_xgp: number;
  route_label: string;
  rideshare_quality: string;
  rideshare_allowed: boolean;
  rideshare_demand_bonus_pct: number;
}

export interface WorkStateSnapshot {
  player_id: string;
  current_houston_time: string;
  current_houston_time_label?: string | null;
  current_game_day: number;
  day_of_week?: string;
  is_weekend?: boolean;
  day_settled: boolean;
  day_rollover_timezone?: string | null;
  day_rollover_time_label?: string | null;
  next_day_rollover_time?: string | null;
  main_job_key?: string | null;
  authoritative_current_job_id?: string | null;
  current_job_display_name?: string | null;
  current_job_level?: number;
  current_job_progression?: JobProgressSnapshot | null;
  career_job_progression?: JobProgressionTrackSnapshot[];
  job_progression_feedback?: JobProgressionFeedbackSnapshot | null;
  scheduled_shift_job_id?: string | null;
  active_shift_job_id?: string | null;
  pay_calculation_job_id?: string | null;
  ui_job_id?: string | null;
  job_truth_mismatch_detected?: boolean;
  job_truth_sources?: Record<string, string>;
  job_sync_status?: string | null;
  job_sync_warning_message?: string | null;
  job_sync_repair_source?: string | null;
  job_sync_auto_repaired?: boolean;
  job_market?: WorkJobMarketSnapshot | null;
  shift_status: 'idle' | 'active' | 'completed' | string;
  main_shift_active_flag: boolean;
  shift_started_at?: string | null;
  shift_ends_at?: string | null;
  shift_completed_at?: string | null;
  shift_start_time_label?: string | null;
  shift_end_time_label?: string | null;
  shift_completed_time_label?: string | null;
  shift_job_name?: string | null;
  shift_job_display_name?: string | null;
  shift_type?: string | null;
  shift_hours: number;
  shift_number: number;
  shift_expired: boolean;
  shift_found: boolean;
  shift_completed_today?: boolean;
  shift_required_today?: boolean;
  no_shift_scheduled?: boolean;
  scheduled_shift_start?: string | null;
  scheduled_shift_end?: string | null;
  scheduled_shift_start_label?: string | null;
  scheduled_shift_end_label?: string | null;
  scheduled_shift_window_label?: string | null;
  hours_available: number;
  main_shift_hours_today: number;
  side_income_hours_today: number;
  rideshare_time_today?: number;
  rideshare_earned_today?: number;
  recovery_hours_today: number;
  total_time_used_today: number;
  did_work_today?: boolean;
  salary_earned_today?: number;
  salary_earned_yesterday?: number;
  pay_model?: 'daily_after_shift_completion' | string;
  pay_model_label?: string;
  salary_pending_until_completion?: boolean;
  salary_payment_status?: string | null;
  salary_status_label?: string | null;
  salary_status_message?: string | null;
  salary_posting_pending?: boolean;
  salary_transaction_id?: string | null;
  salary_posted_at?: string | null;
  salary_transaction_confirmed?: boolean;
  current_shift_salary_audit?: ShiftSalaryAuditSnapshot | null;
  last_salary_posted?: ShiftSalaryAuditSnapshot | null;
  recent_salary_audits?: ShiftSalaryAuditSnapshot[];
  missed_penalty_today?: number;
  missed_shift_today?: boolean;
  missed_shift_health_delta?: number;
  missed_shift_stress_delta?: number;
  survival_penalty_today?: boolean;
  survival_health_delta?: number;
  survival_stress_delta?: number;
  meals_recorded_today?: number;
  current_location_key?: string;
  current_location_label?: string;
  current_location_region?: string;
  city_map?: {
    current_location_key: string;
    current_location_label: string;
    current_location_region: string;
    current_location_node_type: string;
    nodes: CityMapNodeSnapshot[];
    travel_options: TravelOptionSnapshot[];
  } | null;
  travel_options?: TravelOptionSnapshot[];
  dinner_resolved_today?: boolean;
  dinner_mode_today?: string;
  dinner_cost_today?: number;
  food_debt_added_today?: number;
  needs_dinner_reminder?: boolean;
  dinner_reminder_message?: string | null;
  night_eat_reminder_shown?: boolean;
  last_completed_shift: CompletedShiftSnapshot;
  rideshare_state?: RideshareStateSnapshot | null;
  rideshare_unlocked: boolean;
  rideshare_available: boolean;
  rideshare_unlock_time_label?: string | null;
  remaining_side_income_hours_today: number;
  auto_day_rollover?: {
    applied_days: number;
    missed_days: number;
    truncated_days: number;
    previous_sync_date?: string;
    today_date?: string;
    settlement_days?: number[];
    triggered?: boolean;
  } | null;
  auto_finalized_previous_day?: boolean;
  auto_finalized_days_count?: number;
  new_day_started_houston_time?: boolean;
  auto_rollover_recap_lines?: string[];
  offline_survival_catchup?: {
    applied_days: number;
    missed_days: number;
    truncated_days: number;
    current_day_after?: number;
    sync_date_updated?: boolean;
    processed_days?: Array<Record<string, unknown>>;
  } | null;
}

export interface JobMarketJobSnapshot {
  job_key: string;
  display_name: string;
  tier: string;
  base_salary_xgp: number;
  stress_level: string;
  status: 'locked' | 'available' | 'current' | string;
  is_current_job: boolean;
  is_future_unlock: boolean;
  requires_certification: boolean;
  certification_key?: string | null;
  certification_name?: string | null;
  certification_completed?: boolean;
  requirement_label?: string | null;
  can_start_training?: boolean;
  can_switch?: boolean;
  training_in_progress?: boolean;
  training_days_completed?: number;
  training_days_required?: number;
  progression?: JobProgressSnapshot | null;
  is_locked?: boolean;
  is_unlocked?: boolean;
}

export interface JobMarketCertificationSnapshot {
  certification_key: string;
  display_name: string;
  unlocks_job?: string | null;
  duration_days: number;
  cost_xgp: number;
  completed: boolean;
  in_progress: boolean;
  progress_days: number;
  days_remaining: number;
}

export interface WorkJobMarketSnapshot {
  current_job_key: string;
  current_job_display_name: string;
  has_main_job: boolean;
  job_sync_status?: string | null;
  job_sync_warning_message?: string | null;
  jobs: JobMarketJobSnapshot[];
  certifications: JobMarketCertificationSnapshot[];
  training_active: boolean;
  training_certification_key?: string | null;
  training_certification_name?: string | null;
  training_days_completed?: number;
  training_days_required?: number;
  training_days_remaining?: number;
  completed_certification_keys?: string[];
  career_progression?: JobProgressionTrackSnapshot[];
}

export interface EconomySignalChip {
  key: string;
  label: string;
  level: 'low' | 'moderate' | 'high' | 'critical' | string;
  value_text?: string;
  trend?: string;
}

export interface EconomyRiskOverview {
  macro_conditions: EconomySignalChip[];
  opportunity_signals: EconomySignalChip[];
  risk_badges: EconomySignalChip[];
  summary_line: string;
}

export interface DashboardStateCard {
  title: string;
  summary: string;
  key_metrics?: { label: string; value: string | number }[];
}

export interface DashboardSignalItem {
  key: string;
  title: string;
  description: string;
  severity?: SeverityLevel;
  value?: number;
  category?: string;
}

export interface ActionRecommendation {
  action_key: GameplayActionKey;
  title: string;
  reason: string;
}

export interface PlayerDashboardResponse {
  player_id: string;
  as_of_date: string;
  headline: string;
  daily_brief: string;
  stats: DashboardStatSnapshot;
  state_cards?: DashboardStateCard[];
  top_opportunities: DashboardSignalItem[];
  top_risks: DashboardSignalItem[];
  economy_risk_overview?: EconomyRiskOverview | null;
  recommended_actions: ActionRecommendation[];
  job_progress?: JobProgressSnapshot | null;
  work_state?: WorkStateSnapshot | null;
  debug_meta?: Record<string, unknown>;
}

export interface DailyActionItem {
  action_key: GameplayActionKey;
  title: string;
  description: string;
  status: ActionRecommendationState;
  blockers?: string[];
  blocker_text?: string | null;
  tradeoffs?: string[];
  warnings?: string[];
  confidence_level?: ConfidenceLevel;
  parameters?: Record<string, unknown>;
  debug_meta?: Record<string, unknown>;
}

export interface DailyActionHubResponse {
  player_id: string;
  as_of_date: string;
  recommended_actions: DailyActionItem[];
  available_actions: DailyActionItem[];
  blocked_actions: DailyActionItem[];
  top_tradeoffs: string[];
  next_risk_warnings: string[];
  work_state?: WorkStateSnapshot | null;
  debug_meta?: Record<string, unknown>;
}

export interface ActionPreviewRequest {
  action_key: GameplayActionKey;
  parameters?: Record<string, unknown>;
}

export interface ActionImpact {
  label: string;
  direction: TrendDirection;
  amount?: number;
  text?: string;
}

export interface ActionPreviewResponse {
  player_id: string;
  action_key: GameplayActionKey;
  summary: string;
  expected_cash_impact: ActionImpact;
  expected_stress_impact: ActionImpact;
  expected_health_impact: ActionImpact;
  expected_time_impact: ActionImpact;
  expected_career_impact: ActionImpact;
  expected_distress_impact: ActionImpact;
  blockers: string[];
  warnings: string[];
  confidence_level: ConfidenceLevel;
  debug_meta?: Record<string, unknown>;
}

export interface EndOfDaySummaryResponse {
  player_id: string;
  day_number?: number;
  as_of_date: string;
  total_earned_xgp: number;
  total_spent_xgp: number;
  net_change_xgp: number;
  guided_day_number?: number;
  guided_learning_title?: string | null;
  guided_earned_summary?: string | null;
  guided_spent_summary?: string | null;
  guided_change_summary?: string | null;
  guided_watch_tomorrow?: string | null;
  biggest_gain: string;
  biggest_loss: string;
  stress_delta: number;
  health_delta: number;
  skill_delta: number;
  credit_score_delta: number;
  distress_state: string;
  tomorrow_warnings: string[];
  debug_meta?: Record<string, unknown>;
}

export interface TransactionHistoryItem {
  id: string;
  player_id: string;
  day: number;
  type: string;
  category: string;
  amount: number;
  description: string;
  timestamp: string | null;
}

export interface TransactionHistoryResponse {
  player_id: string;
  day: number;
  transactions: TransactionHistoryItem[];
  total_income: number;
  total_expense: number;
  net: number;
}

export interface WeeklyIncomeMixItem {
  source: string;
  amount_xgp: number;
}

export interface WeeklyPlayerSummaryResponse {
  player_id: string;
  week_start: string;
  week_end: string;
  weekly_income_mix: WeeklyIncomeMixItem[];
  top_pressure: string;
  strongest_opportunity: string;
  strategy_classification: string;
  risk_trend: string;
  growth_trend: string;
  suggested_next_moves: string[];
  notable_event_chain: string;
  debug_meta?: Record<string, unknown>;
}

export interface PlayerNotificationItem {
  id: string;
  severity: SeverityLevel;
  category: string;
  title: string;
  body: string;
  suggested_action?: string | null;
  created_at?: string | null;
  read?: boolean;
}

export interface PlayerNotificationResponse {
  player_id: string;
  as_of_date: string;
  notifications: PlayerNotificationItem[];
  debug_meta?: Record<string, unknown>;
}

export type DailySessionStatus = 'active' | 'ended';

export interface DailyActionHistoryEntry {
  id: string;
  order: number;
  action_key: GameplayActionKey;
  title: string;
  description: string;
  result_summary?: string;
  time_cost_units: number;
  executed_at: string;
  success: boolean;
  error_message?: string;
  impact_snapshot?: {
    cash_delta_xgp?: number;
    stress_delta?: number;
    health_delta?: number;
  };
  raw_result?: Record<string, unknown>;
}

export interface ActionExecutionResponse {
  player_id: string;
  action_key: GameplayActionKey;
  success: boolean;
  message: string;
  result_summary: string;
  time_cost_units: number;
  cash_delta_xgp?: number;
  stress_delta?: number;
  health_delta?: number;
  raw_result?: Record<string, unknown>;
}

export interface EndDayResponse {
  player_id: string;
  settled_day: number;
  message: string;
  summary_headline?: string;
  summary?: string;
  ending_cash_xgp?: number;
  stress_change?: number;
  health_change?: number;
  raw_result?: Record<string, unknown>;
}
