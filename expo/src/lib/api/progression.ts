import { fetchApiWithFallback } from '@/lib/apiClient';
import {
  DailyGoalItem,
  DailyGoalsResponse,
  ProgressionSummaryResponse,
  StreakItem,
  StreaksResponse,
  WeeklyMissionItem,
  WeeklyMissionsResponse,
} from '@/types/progression';


function toNumber(value: unknown, fallback = 0): number {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function toString(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value;
  if (value == null) return fallback;
  return String(value);
}

function toStatus(value: unknown): DailyGoalItem['status'] {
  const normalized = toString(value, 'not_started').toLowerCase();
  if (normalized === 'completed') return 'completed';
  if (normalized === 'in_progress') return 'in_progress';
  if (normalized === 'failed') return 'failed';
  return 'not_started';
}

function normalizeDailyGoals(raw: Record<string, unknown>, playerId: string): DailyGoalsResponse {
  const list = Array.isArray(raw.daily_goals) ? raw.daily_goals : [];
  return {
    player_id: toString(raw.player_id, playerId),
    as_of_date: toString(raw.as_of_date, ''),
    daily_goals: list.map((entry, index) => {
      const item = (entry || {}) as Record<string, unknown>;
      return {
        goal_key: toString(item.goal_key, `goal_${index}`),
        title: toString(item.title, 'Goal'),
        description: toString(item.description, ''),
        status: toStatus(item.status),
        progress_current: toNumber(item.progress_current),
        progress_target: Math.max(1, toNumber(item.progress_target, 1)),
        reward_summary: toString(item.reward_summary, ''),
        urgency: toString(item.urgency, 'medium'),
        expires_on: toString(item.expires_on, ''),
        debug_meta: (item.debug_meta as Record<string, unknown>) || {},
      };
    }),
    debug_meta: (raw.debug_meta as Record<string, unknown>) || {},
  };
}

function normalizeWeeklyMissions(raw: Record<string, unknown>, playerId: string): WeeklyMissionsResponse {
  const list = Array.isArray(raw.weekly_missions) ? raw.weekly_missions : [];
  return {
    player_id: toString(raw.player_id, playerId),
    as_of_date: toString(raw.as_of_date, ''),
    weekly_missions: list.map((entry, index) => {
      const item = (entry || {}) as Record<string, unknown>;
      return {
        mission_key: toString(item.mission_key, `mission_${index}`),
        title: toString(item.title, 'Mission'),
        description: toString(item.description, ''),
        status: toStatus(item.status),
        progress_current: toNumber(item.progress_current),
        progress_target: Math.max(1, toNumber(item.progress_target, 1)),
        reward_summary: toString(item.reward_summary, ''),
        week_start: toString(item.week_start, ''),
        week_end: toString(item.week_end, ''),
        category: toString(item.category, 'weekly'),
        debug_meta: (item.debug_meta as Record<string, unknown>) || {},
      };
    }),
    debug_meta: (raw.debug_meta as Record<string, unknown>) || {},
  };
}

function normalizeStreaks(raw: Record<string, unknown>, playerId: string): StreaksResponse {
  const list = Array.isArray(raw.streaks) ? raw.streaks : [];
  return {
    player_id: toString(raw.player_id, playerId),
    as_of_date: toString(raw.as_of_date, ''),
    streaks: list.map((entry, index) => {
      const item = (entry || {}) as Record<string, unknown>;
      return {
        streak_key: toString(item.streak_key, `streak_${index}`),
        title: toString(item.title, 'Streak'),
        current_count: Math.max(0, Math.round(toNumber(item.current_count))),
        best_count: Math.max(0, Math.round(toNumber(item.best_count))),
        status: toString(item.status, 'idle'),
        last_credited_on: toString(item.last_credited_on, ''),
        reset_risk: toString(item.reset_risk, 'high'),
        next_credit_condition: toString(item.next_credit_condition, ''),
        debug_meta: (item.debug_meta as Record<string, unknown>) || {},
      };
    }),
    debug_meta: (raw.debug_meta as Record<string, unknown>) || {},
  };
}

function normalizeSummary(raw: Record<string, unknown>, playerId: string): ProgressionSummaryResponse {
  const daily = normalizeDailyGoals(raw, playerId).daily_goals;
  const weekly = normalizeWeeklyMissions(raw, playerId).weekly_missions;
  const streaks = normalizeStreaks(raw, playerId).streaks;
  const recentlyCompleted = Array.isArray(raw.recently_completed)
    ? raw.recently_completed.map((entry) => {
      const item = (entry || {}) as Record<string, unknown>;
      return {
        scope: toString(item.scope, ''),
        key: toString(item.key, ''),
        title: toString(item.title, ''),
        credited_on: toString(item.credited_on, ''),
        reward_summary: toString(item.reward_summary, ''),
      };
    })
    : [];
  return {
    player_id: toString(raw.player_id, playerId),
    as_of_date: toString(raw.as_of_date, ''),
    daily_goals: daily,
    weekly_missions: weekly,
    streaks,
    recently_completed: recentlyCompleted,
    suggested_focus: Array.isArray(raw.suggested_focus)
      ? raw.suggested_focus.map((entry) => toString(entry)).filter(Boolean)
      : [],
    motivational_summary: toString(raw.motivational_summary, ''),
    debug_meta: (raw.debug_meta as Record<string, unknown>) || {},
  };
}

export async function getDailyGoals(playerId: string): Promise<DailyGoalsResponse> {
  const raw = await fetchApiWithFallback<Record<string, unknown>>([
    `/progression/player/${playerId}/daily-goals`,
  ]);
  return normalizeDailyGoals(raw, playerId);
}

export async function getWeeklyMissions(playerId: string): Promise<WeeklyMissionsResponse> {
  const raw = await fetchApiWithFallback<Record<string, unknown>>([
    `/progression/player/${playerId}/weekly-missions`,
  ]);
  return normalizeWeeklyMissions(raw, playerId);
}

export async function getPlayerStreaks(playerId: string): Promise<StreaksResponse> {
  const raw = await fetchApiWithFallback<Record<string, unknown>>([
    `/progression/player/${playerId}/streaks`,
  ]);
  return normalizeStreaks(raw, playerId);
}

export async function getProgressionSummary(playerId: string): Promise<ProgressionSummaryResponse> {
  const raw = await fetchApiWithFallback<Record<string, unknown>>([
    `/progression/player/${playerId}/summary`,
  ]);
  return normalizeSummary(raw, playerId);
}

export async function refreshProgression(playerId: string): Promise<ProgressionSummaryResponse> {
  const raw = await fetchApiWithFallback<Record<string, unknown>>(
    [
      `/progression/player/${playerId}/refresh`,
    ],
    {
      method: 'POST',
      body: '{}',
    },
  );
  return normalizeSummary(raw, playerId);
}
