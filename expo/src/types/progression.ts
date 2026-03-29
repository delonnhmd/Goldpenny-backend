export type ProgressStatus = 'not_started' | 'in_progress' | 'completed' | 'failed';

export type ProgressUrgency = 'low' | 'medium' | 'high';

export interface DailyGoalItem {
  goal_key: string;
  title: string;
  description: string;
  status: ProgressStatus;
  progress_current: number;
  progress_target: number;
  reward_summary: string;
  urgency: ProgressUrgency | string;
  expires_on?: string | null;
  debug_meta?: Record<string, unknown>;
}

export interface WeeklyMissionItem {
  mission_key: string;
  title: string;
  description: string;
  status: ProgressStatus;
  progress_current: number;
  progress_target: number;
  reward_summary: string;
  week_start: string;
  week_end: string;
  category: string;
  debug_meta?: Record<string, unknown>;
}

export interface StreakItem {
  streak_key: string;
  title: string;
  current_count: number;
  best_count: number;
  status: string;
  last_credited_on?: string | null;
  reset_risk: string;
  next_credit_condition: string;
  debug_meta?: Record<string, unknown>;
}

export interface DailyGoalsResponse {
  player_id: string;
  as_of_date: string;
  daily_goals: DailyGoalItem[];
  debug_meta?: Record<string, unknown>;
}

export interface WeeklyMissionsResponse {
  player_id: string;
  as_of_date: string;
  weekly_missions: WeeklyMissionItem[];
  debug_meta?: Record<string, unknown>;
}

export interface StreaksResponse {
  player_id: string;
  as_of_date: string;
  streaks: StreakItem[];
  debug_meta?: Record<string, unknown>;
}

export interface RecentlyCompletedItem {
  scope: string;
  key: string;
  title: string;
  credited_on: string;
  reward_summary: string;
}

export interface ProgressionSummaryResponse {
  player_id: string;
  as_of_date: string;
  daily_goals: DailyGoalItem[];
  weekly_missions: WeeklyMissionItem[];
  streaks: StreakItem[];
  recently_completed: RecentlyCompletedItem[];
  suggested_focus: string[];
  motivational_summary: string;
  debug_meta?: Record<string, unknown>;
}
