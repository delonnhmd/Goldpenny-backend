export type OnboardingStatus = 'not_started' | 'in_progress' | 'completed' | 'skipped' | string;

export interface OnboardingUnlockItem {
  module_key: string;
  unlock_condition: string;
  unlock_status: boolean;
  unlock_reason: string;
  debug_meta?: Record<string, unknown>;
}

export interface OnboardingStateResponse {
  player_id: string;
  as_of_date: string;
  onboarding_status: OnboardingStatus;
  current_step_key: string;
  current_step_index: number;
  current_step_title: string;
  current_step_body: string;
  progress_label: string;
  first_session_day_count: number;
  guided_experience_active: boolean;
  guided_day_number: number;
  guided_phase?: string | null;
  guided_label?: string | null;
  visible_modules: string[];
  unlocked_modules: string[];
  completed_step_keys: string[];
  debug_meta?: Record<string, unknown>;
}

export interface OnboardingGuidanceResponse {
  player_id: string;
  as_of_date: string;
  onboarding_status: OnboardingStatus;
  guided_experience_active: boolean;
  guided_day_number: number;
  guided_phase?: string | null;
  guided_label?: string | null;
  step_key: string;
  title: string;
  body: string;
  highlight_target: string;
  required_action_key?: string | null;
  optional_action_key?: string | null;
  completion_condition: string;
  blocker_reason?: string | null;
  can_skip: boolean;
  debug_meta?: Record<string, unknown>;
}

export interface OnboardingBlockedAction {
  action_key: string;
  reason: string;
}

export interface OnboardingDashboardConfigResponse {
  player_id: string;
  as_of_date: string;
  onboarding_status: OnboardingStatus;
  guided_experience_active: boolean;
  guided_day_number: number;
  guided_phase?: string | null;
  guided_label?: string | null;
  visible_sections: string[];
  collapsed_sections: string[];
  hidden_sections: string[];
  highlighted_section?: string | null;
  highlighted_action_key?: string | null;
  allowed_actions: string[];
  blocked_actions_for_onboarding: OnboardingBlockedAction[];
  debug_meta?: Record<string, unknown>;
}

export interface OnboardingUnlockScheduleResponse {
  player_id: string;
  as_of_date: string;
  onboarding_status: OnboardingStatus;
  items: OnboardingUnlockItem[];
  debug_meta?: Record<string, unknown>;
}

export interface OnboardingAdvanceRequest {
  action_key?: string | null;
  step_key?: string | null;
  force?: boolean;
}

export interface OnboardingActionResultResponse {
  player_id: string;
  as_of_date: string;
  message: string;
  state: OnboardingStateResponse;
  guidance: OnboardingGuidanceResponse;
  dashboard_config: OnboardingDashboardConfigResponse;
  unlock_schedule: OnboardingUnlockScheduleResponse;
  debug_meta?: Record<string, unknown>;
}
