import { fetchApiWithFallback } from '@/lib/apiClient';
import {
  OnboardingActionResultResponse,
  OnboardingAdvanceRequest,
  OnboardingDashboardConfigResponse,
  OnboardingGuidanceResponse,
  OnboardingStateResponse,
  OnboardingUnlockScheduleResponse,
} from '@/types/onboarding';


function toString(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value;
  if (value == null) return fallback;
  return String(value);
}

function toBoolean(value: unknown, fallback = false): boolean {
  if (typeof value === 'boolean') return value;
  if (value === 'true') return true;
  if (value === 'false') return false;
  return fallback;
}

function toNumber(value: unknown, fallback = 0): number {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

function toRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((entry) => toString(entry)).filter(Boolean);
}

export interface PlayablePlayerSummary {
  player_id: string;
  display_name: string | null;
  region: string | null;
  load_ready: boolean | null;
}

export interface CreatePlayablePlayerRequest {
  player_id?: string;
  display_name: string;
  gender: 'male' | 'female';
  region?: 'suburban' | 'downtown';
  starter_job_code?: string;
}

function normalizePlayablePlayerSummary(raw: unknown): PlayablePlayerSummary {
  const obj = toRecord(raw);
  return {
    player_id: toString(obj.player_id),
    display_name: obj.display_name == null ? null : toString(obj.display_name),
    region: obj.region == null ? null : toString(obj.region),
    load_ready: obj.load_ready == null ? null : toBoolean(obj.load_ready, false),
  };
}

export async function getPlayablePlayerSummary(playerId: string): Promise<PlayablePlayerSummary> {
  const raw = await fetchApiWithFallback<unknown>([
    `/onboarding/player/${playerId}`,
  ]);
  return normalizePlayablePlayerSummary(raw);
}

export async function createPlayablePlayer(
  request: CreatePlayablePlayerRequest,
): Promise<PlayablePlayerSummary> {
  const normalizedPlayerId = toString(request.player_id || request.display_name).trim();
  const body = {
    player_id: normalizedPlayerId,
    display_name: normalizedPlayerId,
    gender: request.gender,
    region: request.region || 'suburban',
    starter_job_code: request.starter_job_code || 'retail_worker',
  };
  const raw = await fetchApiWithFallback<unknown>(
    ['/onboarding/new-player'],
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  );
  return normalizePlayablePlayerSummary(raw);
}


function normalizeState(raw: unknown): OnboardingStateResponse {
  const obj = toRecord(raw);
  return {
    player_id: toString(obj.player_id),
    as_of_date: toString(obj.as_of_date),
    onboarding_status: toString(obj.onboarding_status, 'not_started'),
    current_step_key: toString(obj.current_step_key),
    current_step_index: toNumber(obj.current_step_index, 1),
    current_step_title: toString(obj.current_step_title),
    current_step_body: toString(obj.current_step_body),
    progress_label: toString(obj.progress_label),
    first_session_day_count: toNumber(obj.first_session_day_count, 0),
    guided_experience_active: toBoolean(obj.guided_experience_active, false),
    guided_day_number: toNumber(obj.guided_day_number, 0),
    guided_phase: obj.guided_phase != null ? toString(obj.guided_phase) : null,
    guided_label: obj.guided_label != null ? toString(obj.guided_label) : null,
    visible_modules: toStringList(obj.visible_modules),
    unlocked_modules: toStringList(obj.unlocked_modules),
    completed_step_keys: toStringList(obj.completed_step_keys),
    debug_meta: toRecord(obj.debug_meta),
  };
}

function normalizeGuidance(raw: unknown): OnboardingGuidanceResponse {
  const obj = toRecord(raw);
  return {
    player_id: toString(obj.player_id),
    as_of_date: toString(obj.as_of_date),
    onboarding_status: toString(obj.onboarding_status, 'not_started'),
    guided_experience_active: toBoolean(obj.guided_experience_active, false),
    guided_day_number: toNumber(obj.guided_day_number, 0),
    guided_phase: obj.guided_phase != null ? toString(obj.guided_phase) : null,
    guided_label: obj.guided_label != null ? toString(obj.guided_label) : null,
    step_key: toString(obj.step_key),
    title: toString(obj.title),
    body: toString(obj.body),
    highlight_target: toString(obj.highlight_target),
    required_action_key: obj.required_action_key != null ? toString(obj.required_action_key) : null,
    optional_action_key: obj.optional_action_key != null ? toString(obj.optional_action_key) : null,
    completion_condition: toString(obj.completion_condition),
    blocker_reason: obj.blocker_reason != null ? toString(obj.blocker_reason) : null,
    can_skip: toBoolean(obj.can_skip, true),
    debug_meta: toRecord(obj.debug_meta),
  };
}

function normalizeDashboardConfig(raw: unknown): OnboardingDashboardConfigResponse {
  const obj = toRecord(raw);
  const blockedRaw = Array.isArray(obj.blocked_actions_for_onboarding)
    ? obj.blocked_actions_for_onboarding
    : [];
  return {
    player_id: toString(obj.player_id),
    as_of_date: toString(obj.as_of_date),
    onboarding_status: toString(obj.onboarding_status, 'not_started'),
    guided_experience_active: toBoolean(obj.guided_experience_active, false),
    guided_day_number: toNumber(obj.guided_day_number, 0),
    guided_phase: obj.guided_phase != null ? toString(obj.guided_phase) : null,
    guided_label: obj.guided_label != null ? toString(obj.guided_label) : null,
    visible_sections: toStringList(obj.visible_sections),
    collapsed_sections: toStringList(obj.collapsed_sections),
    hidden_sections: toStringList(obj.hidden_sections),
    highlighted_section: obj.highlighted_section != null ? toString(obj.highlighted_section) : null,
    highlighted_action_key: obj.highlighted_action_key != null ? toString(obj.highlighted_action_key) : null,
    allowed_actions: toStringList(obj.allowed_actions),
    blocked_actions_for_onboarding: blockedRaw.map((entry) => {
      const row = toRecord(entry);
      return {
        action_key: toString(row.action_key),
        reason: toString(row.reason),
      };
    }),
    debug_meta: toRecord(obj.debug_meta),
  };
}

function normalizeUnlockSchedule(raw: unknown): OnboardingUnlockScheduleResponse {
  const obj = toRecord(raw);
  const itemRaw = Array.isArray(obj.items) ? obj.items : [];
  return {
    player_id: toString(obj.player_id),
    as_of_date: toString(obj.as_of_date),
    onboarding_status: toString(obj.onboarding_status, 'not_started'),
    items: itemRaw.map((entry) => {
      const row = toRecord(entry);
      return {
        module_key: toString(row.module_key),
        unlock_condition: toString(row.unlock_condition),
        unlock_status: toBoolean(row.unlock_status, false),
        unlock_reason: toString(row.unlock_reason),
        debug_meta: toRecord(row.debug_meta),
      };
    }),
    debug_meta: toRecord(obj.debug_meta),
  };
}

function normalizeActionResult(raw: unknown): OnboardingActionResultResponse {
  const obj = toRecord(raw);
  return {
    player_id: toString(obj.player_id),
    as_of_date: toString(obj.as_of_date),
    message: toString(obj.message),
    state: normalizeState(obj.state),
    guidance: normalizeGuidance(obj.guidance),
    dashboard_config: normalizeDashboardConfig(obj.dashboard_config),
    unlock_schedule: normalizeUnlockSchedule(obj.unlock_schedule),
    debug_meta: toRecord(obj.debug_meta),
  };
}

export async function getOnboardingState(playerId: string): Promise<OnboardingStateResponse> {
  const raw = await fetchApiWithFallback<unknown>([
    `/onboarding/player/${playerId}/state`,
  ]);
  return normalizeState(raw);
}

export async function getOnboardingGuidance(playerId: string): Promise<OnboardingGuidanceResponse> {
  const raw = await fetchApiWithFallback<unknown>([
    `/onboarding/player/${playerId}/guidance`,
  ]);
  return normalizeGuidance(raw);
}

export async function getOnboardingDashboardConfig(playerId: string): Promise<OnboardingDashboardConfigResponse> {
  const raw = await fetchApiWithFallback<unknown>([
    `/onboarding/player/${playerId}/dashboard-config`,
  ]);
  return normalizeDashboardConfig(raw);
}

export async function getOnboardingUnlockSchedule(playerId: string): Promise<OnboardingUnlockScheduleResponse> {
  const raw = await fetchApiWithFallback<unknown>([
    `/onboarding/player/${playerId}/unlock-schedule`,
  ]);
  return normalizeUnlockSchedule(raw);
}

export async function advanceOnboarding(
  playerId: string,
  payload: OnboardingAdvanceRequest = {},
): Promise<OnboardingActionResultResponse> {
  const raw = await fetchApiWithFallback<unknown>(
    [`/onboarding/player/${playerId}/advance`],
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
  return normalizeActionResult(raw);
}

export async function skipOnboarding(playerId: string): Promise<OnboardingActionResultResponse> {
  const raw = await fetchApiWithFallback<unknown>(
    [`/onboarding/player/${playerId}/skip`],
    {
      method: 'POST',
      body: JSON.stringify({}),
    },
  );
  return normalizeActionResult(raw);
}

export async function completeOnboarding(playerId: string): Promise<OnboardingActionResultResponse> {
  const raw = await fetchApiWithFallback<unknown>(
    [`/onboarding/player/${playerId}/complete`],
    {
      method: 'POST',
      body: JSON.stringify({}),
    },
  );
  return normalizeActionResult(raw);
}

export async function refreshOnboarding(
  playerId: string,
  payload: OnboardingAdvanceRequest = {},
): Promise<OnboardingActionResultResponse> {
  const raw = await fetchApiWithFallback<unknown>(
    [`/onboarding/player/${playerId}/refresh`],
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
  return normalizeActionResult(raw);
}
