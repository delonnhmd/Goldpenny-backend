export type SeverityLevel = 'info' | 'low' | 'medium' | 'high' | 'critical';

export type GameplayActionKey =
  | 'work_shift'
  | 'side_income'
  | 'operate_business'
  | 'buy_inventory'
  | 'rest'
  | 'study'
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
  region_key?: string | null;
}

export interface JobProgressSnapshot {
  job_key: string;
  job_level: number;
  skill_level: number;
  job_xp: number;
  job_xp_to_next_level: number;
  max_job_level: number;
  monthly_pay_xgp: number;
  employer_company_symbol?: string | null;
  employer_company_name?: string | null;
  position_title?: string | null;
  shift_type?: string | null;
}

export interface CompletedShiftSnapshot {
  earned_cash_xgp: number;
  xp_gained: number;
  stress_change: number;
  health_change: number;
}

export interface WorkStateSnapshot {
  player_id: string;
  current_houston_time: string;
  current_game_day: number;
  day_of_week?: string;
  is_weekend?: boolean;
  day_settled: boolean;
  shift_status: 'idle' | 'active' | 'completed' | string;
  main_shift_active_flag: boolean;
  shift_started_at?: string | null;
  shift_ends_at?: string | null;
  shift_completed_at?: string | null;
  shift_job_name?: string | null;
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
  recovery_hours_today: number;
  total_time_used_today: number;
  did_work_today?: boolean;
  salary_earned_today?: number;
  missed_penalty_today?: number;
  missed_shift_today?: boolean;
  missed_shift_health_delta?: number;
  missed_shift_stress_delta?: number;
  survival_penalty_today?: boolean;
  survival_health_delta?: number;
  survival_stress_delta?: number;
  meals_recorded_today?: number;
  last_completed_shift: CompletedShiftSnapshot;
  rideshare_unlocked: boolean;
  rideshare_available: boolean;
  rideshare_unlock_time_label?: string | null;
  remaining_side_income_hours_today: number;
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
