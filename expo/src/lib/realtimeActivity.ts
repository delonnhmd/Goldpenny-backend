import { BALANCE } from '@/lib/balanceConfig';

export type TimedActivityType =
  | 'watch_tv'
  | 'watch_movie'
  | 'read_book'
  | 'jogging'
  | 'eat_meal'
  | 'skill_training';

export type MealType = 'breakfast' | 'lunch' | 'dinner';

export interface TimedActivityState {
  currentActivity: TimedActivityType | null;
  currentMealType: MealType | null;
  activityElapsedMinutes: number;
  unitProgressMinutes: number;
  idleRecoveryBufferMinutes: number;
  activeRecoveryBufferMinutes: number;
  joggingHealthBufferMinutes: number;
  trainingProgressBufferMinutes: number;
  trainingUnitsThisSession: number;
  sessionUnitsConsumed: number;
  stressRecoveredToday: number;
  healthGainedToday: number;
  skillProgressGainedToday: number;
  sessionStressRecovered: number;
  sessionHealthGained: number;
  sessionSkillProgress: number;
  mealLocked: boolean;
  lastProcessedAtIso: string | null;
  lastInteractionTimeIso: string | null;
  lastActivityStartedAtIso: string | null;
  lastActivityStoppedAtIso: string | null;
}

export interface TimedActivityGuard {
  allowed: boolean;
  reason: string | null;
}

export interface TimedActivityTickResult {
  nextState: TimedActivityState;
  processedMinutes: number;
  unitsConsumed: number;
  stressRecovered: number;
  healthGained: number;
  skillProgressGained: number;
  mealAutoCompleted: boolean;
  forcedStop: boolean;
}

const MINUTES_PER_UNIT = BALANCE.REALTIME.MINUTES_PER_UNIT;
const IDLE_STRESS_RECOVERY_MINUTES = BALANCE.REALTIME.IDLE_STRESS_RECOVERY_MINUTES;
const ACTIVE_STRESS_RECOVERY_MINUTES = BALANCE.REALTIME.ACTIVE_STRESS_RECOVERY_MINUTES;
const MEAL_MIN_MINUTES = BALANCE.REALTIME.MEAL_MIN_MINUTES;
const JOGGING_HEALTH_INTERVAL_MINUTES = BALANCE.REALTIME.JOGGING_HEALTH_INTERVAL_MINUTES;
const JOGGING_HEALTH_GAIN = BALANCE.REALTIME.JOGGING_HEALTH_GAIN;
const TRAINING_SKILL_GAIN_PER_UNIT = BALANCE.REALTIME.TRAINING_SKILL_GAIN_PER_UNIT;
const TRAINING_BONUS_THRESHOLD_UNITS = BALANCE.REALTIME.TRAINING_BONUS_THRESHOLD_UNITS;
const TRAINING_BONUS_SKILL_GAIN_PER_UNIT = BALANCE.REALTIME.TRAINING_BONUS_SKILL_GAIN_PER_UNIT;

const ACTIVE_STRESS_RECOVERY_ACTIVITIES = new Set<TimedActivityType>([
  'watch_tv',
  'watch_movie',
  'read_book',
  'jogging',
]);

export function isTimedActivityActionKey(actionKey: string): actionKey is TimedActivityType {
  return [
    'watch_tv',
    'watch_movie',
    'read_book',
    'jogging',
    'eat_meal',
    'skill_training',
  ].includes(String(actionKey || '').trim().toLowerCase());
}

export function formatTimedActivityName(
  activity: TimedActivityType | null,
  mealType: MealType | null = null,
): string {
  if (activity === 'watch_tv') return 'Watch TV';
  if (activity === 'watch_movie') return 'Watch Movie';
  if (activity === 'read_book') return 'Read Book';
  if (activity === 'jogging') return 'Jogging';
  if (activity === 'skill_training') return 'Skill Training';
  if (activity === 'eat_meal') {
    if (mealType === 'breakfast') return 'Breakfast';
    if (mealType === 'lunch') return 'Lunch';
    return 'Dinner';
  }
  return 'No activity';
}

export function createDefaultTimedActivityState(nowIso = new Date().toISOString()): TimedActivityState {
  return {
    currentActivity: null,
    currentMealType: null,
    activityElapsedMinutes: 0,
    unitProgressMinutes: 0,
    idleRecoveryBufferMinutes: 0,
    activeRecoveryBufferMinutes: 0,
    joggingHealthBufferMinutes: 0,
    trainingProgressBufferMinutes: 0,
    trainingUnitsThisSession: 0,
    sessionUnitsConsumed: 0,
    stressRecoveredToday: 0,
    healthGainedToday: 0,
    skillProgressGainedToday: 0,
    sessionStressRecovered: 0,
    sessionHealthGained: 0,
    sessionSkillProgress: 0,
    mealLocked: false,
    lastProcessedAtIso: nowIso,
    lastInteractionTimeIso: nowIso,
    lastActivityStartedAtIso: null,
    lastActivityStoppedAtIso: null,
  };
}

function clampNonNegativeNumber(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, value);
}

function availableTimedMinutes(state: TimedActivityState, remainingUnits: number): number {
  return Math.max(0, remainingUnits * MINUTES_PER_UNIT - state.unitProgressMinutes);
}

export function getTimedActivityGuard(
  state: TimedActivityState,
  activity: TimedActivityType,
  options: {
    remainingUnits: number;
    sessionStatus: 'active' | 'ended';
  },
): TimedActivityGuard {
  if (options.sessionStatus !== 'active') {
    return { allowed: false, reason: 'Day already ended. Start next day to continue.' };
  }
  if (state.currentActivity) {
    return {
      allowed: false,
      reason: `${formatTimedActivityName(state.currentActivity, state.currentMealType)} is already running.`,
    };
  }
  if (options.remainingUnits <= 0 || availableTimedMinutes(state, options.remainingUnits) <= 0) {
    return { allowed: false, reason: 'No time units left today.' };
  }
  if (activity === 'eat_meal' && availableTimedMinutes(state, options.remainingUnits) < MEAL_MIN_MINUTES) {
    return { allowed: false, reason: 'Not enough time left today for a meal.' };
  }
  return { allowed: true, reason: null };
}

export function startTimedActivity(
  state: TimedActivityState,
  activity: TimedActivityType,
  nowIso = new Date().toISOString(),
  mealType: MealType | null = null,
): TimedActivityState {
  return {
    ...state,
    currentActivity: activity,
    currentMealType: activity === 'eat_meal' ? (mealType || 'dinner') : null,
    activityElapsedMinutes: 0,
    activeRecoveryBufferMinutes: 0,
    joggingHealthBufferMinutes: 0,
    trainingProgressBufferMinutes: 0,
    trainingUnitsThisSession: 0,
    sessionUnitsConsumed: 0,
    sessionStressRecovered: 0,
    sessionHealthGained: 0,
    sessionSkillProgress: 0,
    mealLocked: activity === 'eat_meal',
    lastProcessedAtIso: nowIso,
    lastInteractionTimeIso: nowIso,
    lastActivityStartedAtIso: nowIso,
    lastActivityStoppedAtIso: state.lastActivityStoppedAtIso,
  };
}

export function stopTimedActivity(
  state: TimedActivityState,
  nowIso = new Date().toISOString(),
): { nextState: TimedActivityState; blocked: boolean } {
  if (state.currentActivity === 'eat_meal' && state.activityElapsedMinutes < MEAL_MIN_MINUTES) {
    return { nextState: state, blocked: true };
  }
  return {
    blocked: false,
    nextState: {
      ...state,
      currentActivity: null,
      currentMealType: null,
      activityElapsedMinutes: 0,
      activeRecoveryBufferMinutes: 0,
      joggingHealthBufferMinutes: 0,
      trainingProgressBufferMinutes: 0,
      trainingUnitsThisSession: 0,
      sessionUnitsConsumed: 0,
      sessionStressRecovered: 0,
      sessionHealthGained: 0,
      sessionSkillProgress: 0,
      mealLocked: false,
      lastProcessedAtIso: nowIso,
      lastInteractionTimeIso: nowIso,
      lastActivityStoppedAtIso: nowIso,
    },
  };
}

export function applyIdleRecoveryMinutes(
  state: TimedActivityState,
  deltaMinutes: number,
): TimedActivityTickResult {
  const nextState = { ...state };
  let stressRecovered = 0;

  nextState.idleRecoveryBufferMinutes += clampNonNegativeNumber(deltaMinutes);
  while (nextState.idleRecoveryBufferMinutes >= IDLE_STRESS_RECOVERY_MINUTES) {
    nextState.idleRecoveryBufferMinutes -= IDLE_STRESS_RECOVERY_MINUTES;
    nextState.stressRecoveredToday += 1;
    stressRecovered += 1;
  }

  return {
    nextState,
    processedMinutes: clampNonNegativeNumber(deltaMinutes),
    unitsConsumed: 0,
    stressRecovered,
    healthGained: 0,
    skillProgressGained: 0,
    mealAutoCompleted: false,
    forcedStop: false,
  };
}

export function applyTimedActivityMinutes(
  state: TimedActivityState,
  deltaMinutes: number,
  remainingUnits: number,
): TimedActivityTickResult {
  const nextState = { ...state };
  if (!nextState.currentActivity) {
    return {
      nextState,
      processedMinutes: 0,
      unitsConsumed: 0,
      stressRecovered: 0,
      healthGained: 0,
      skillProgressGained: 0,
      mealAutoCompleted: false,
      forcedStop: false,
    };
  }

  const processableMinutes = Math.min(
    clampNonNegativeNumber(deltaMinutes),
    availableTimedMinutes(nextState, remainingUnits),
  );
  let unitsConsumed = 0;
  let stressRecovered = 0;
  let healthGained = 0;
  let skillProgressGained = 0;
  let mealAutoCompleted = false;
  let forcedStop = false;

  nextState.activityElapsedMinutes += processableMinutes;
  nextState.unitProgressMinutes += processableMinutes;

  if (ACTIVE_STRESS_RECOVERY_ACTIVITIES.has(nextState.currentActivity)) {
    nextState.activeRecoveryBufferMinutes += processableMinutes;
    while (nextState.activeRecoveryBufferMinutes >= ACTIVE_STRESS_RECOVERY_MINUTES) {
      nextState.activeRecoveryBufferMinutes -= ACTIVE_STRESS_RECOVERY_MINUTES;
      nextState.stressRecoveredToday += 1;
      nextState.sessionStressRecovered += 1;
      stressRecovered += 1;
    }
  }

  if (nextState.currentActivity === 'jogging') {
    nextState.joggingHealthBufferMinutes += processableMinutes;
    while (nextState.joggingHealthBufferMinutes >= JOGGING_HEALTH_INTERVAL_MINUTES) {
      nextState.joggingHealthBufferMinutes -= JOGGING_HEALTH_INTERVAL_MINUTES;
      nextState.healthGainedToday += JOGGING_HEALTH_GAIN;
      nextState.sessionHealthGained += JOGGING_HEALTH_GAIN;
      healthGained += JOGGING_HEALTH_GAIN;
    }
  }

  if (nextState.currentActivity === 'skill_training') {
    nextState.trainingProgressBufferMinutes += processableMinutes;
    while (nextState.trainingProgressBufferMinutes >= MINUTES_PER_UNIT) {
      nextState.trainingProgressBufferMinutes -= MINUTES_PER_UNIT;
      nextState.trainingUnitsThisSession += 1;
      const unitGain = TRAINING_SKILL_GAIN_PER_UNIT
        + (nextState.trainingUnitsThisSession >= TRAINING_BONUS_THRESHOLD_UNITS
          ? TRAINING_BONUS_SKILL_GAIN_PER_UNIT
          : 0);
      nextState.skillProgressGainedToday += unitGain;
      nextState.sessionSkillProgress += unitGain;
      skillProgressGained += unitGain;
    }
  }

  while (nextState.unitProgressMinutes >= MINUTES_PER_UNIT && unitsConsumed < remainingUnits) {
    nextState.unitProgressMinutes -= MINUTES_PER_UNIT;
    unitsConsumed += 1;
    nextState.sessionUnitsConsumed += 1;
  }

  if (nextState.currentActivity === 'eat_meal' && nextState.activityElapsedMinutes >= MEAL_MIN_MINUTES) {
    mealAutoCompleted = true;
    nextState.currentActivity = null;
    nextState.currentMealType = null;
    nextState.activityElapsedMinutes = 0;
    nextState.activeRecoveryBufferMinutes = 0;
    nextState.joggingHealthBufferMinutes = 0;
    nextState.trainingProgressBufferMinutes = 0;
    nextState.trainingUnitsThisSession = 0;
    nextState.sessionUnitsConsumed = 0;
    nextState.sessionStressRecovered = 0;
    nextState.sessionHealthGained = 0;
    nextState.sessionSkillProgress = 0;
    nextState.mealLocked = false;
  }

  if (!mealAutoCompleted && availableTimedMinutes(nextState, remainingUnits - unitsConsumed) <= 0) {
    forcedStop = true;
    nextState.currentActivity = null;
    nextState.currentMealType = null;
    nextState.activityElapsedMinutes = 0;
    nextState.activeRecoveryBufferMinutes = 0;
    nextState.joggingHealthBufferMinutes = 0;
    nextState.trainingProgressBufferMinutes = 0;
    nextState.trainingUnitsThisSession = 0;
    nextState.sessionUnitsConsumed = 0;
    nextState.sessionStressRecovered = 0;
    nextState.sessionHealthGained = 0;
    nextState.sessionSkillProgress = 0;
    nextState.mealLocked = false;
  }

  return {
    nextState,
    processedMinutes: processableMinutes,
    unitsConsumed,
    stressRecovered,
    healthGained,
    skillProgressGained,
    mealAutoCompleted,
    forcedStop,
  };
}

export function sanitizeTimedActivityState(value: unknown): TimedActivityState {
  const fallback = createDefaultTimedActivityState();
  if (!value || typeof value !== 'object' || Array.isArray(value)) return fallback;
  const candidate = value as Partial<TimedActivityState>;
  const currentActivity = isTimedActivityActionKey(String(candidate.currentActivity || '').trim().toLowerCase())
    ? String(candidate.currentActivity).trim().toLowerCase() as TimedActivityType
    : null;
  const currentMealType = ['breakfast', 'lunch', 'dinner'].includes(String(candidate.currentMealType || ''))
    ? String(candidate.currentMealType) as MealType
    : null;

  return {
    currentActivity,
    currentMealType,
    activityElapsedMinutes: clampNonNegativeNumber(Number(candidate.activityElapsedMinutes || 0)),
    unitProgressMinutes: Math.min(MINUTES_PER_UNIT - 0.001, clampNonNegativeNumber(Number(candidate.unitProgressMinutes || 0))),
    idleRecoveryBufferMinutes: clampNonNegativeNumber(Number(candidate.idleRecoveryBufferMinutes || 0)),
    activeRecoveryBufferMinutes: clampNonNegativeNumber(Number(candidate.activeRecoveryBufferMinutes || 0)),
    joggingHealthBufferMinutes: clampNonNegativeNumber(Number(candidate.joggingHealthBufferMinutes || 0)),
    trainingProgressBufferMinutes: clampNonNegativeNumber(Number(candidate.trainingProgressBufferMinutes || 0)),
    trainingUnitsThisSession: Math.max(0, Math.round(Number(candidate.trainingUnitsThisSession || 0))),
    sessionUnitsConsumed: Math.max(0, Math.round(Number(candidate.sessionUnitsConsumed || 0))),
    stressRecoveredToday: Math.max(0, Math.round(Number(candidate.stressRecoveredToday || 0))),
    healthGainedToday: Math.max(0, Math.round(Number(candidate.healthGainedToday || 0))),
    skillProgressGainedToday: Math.max(0, Math.round(Number(candidate.skillProgressGainedToday || 0))),
    sessionStressRecovered: Math.max(0, Math.round(Number(candidate.sessionStressRecovered || 0))),
    sessionHealthGained: Math.max(0, Math.round(Number(candidate.sessionHealthGained || 0))),
    sessionSkillProgress: Math.max(0, Math.round(Number(candidate.sessionSkillProgress || 0))),
    mealLocked: Boolean(candidate.mealLocked && currentActivity === 'eat_meal'),
    lastProcessedAtIso: typeof candidate.lastProcessedAtIso === 'string' ? candidate.lastProcessedAtIso : fallback.lastProcessedAtIso,
    lastInteractionTimeIso: typeof candidate.lastInteractionTimeIso === 'string' ? candidate.lastInteractionTimeIso : fallback.lastInteractionTimeIso,
    lastActivityStartedAtIso: typeof candidate.lastActivityStartedAtIso === 'string' ? candidate.lastActivityStartedAtIso : null,
    lastActivityStoppedAtIso: typeof candidate.lastActivityStoppedAtIso === 'string' ? candidate.lastActivityStoppedAtIso : null,
  };
}

export function getNextUnitCountdownMinutes(state: TimedActivityState): number {
  return Math.max(0, MINUTES_PER_UNIT - state.unitProgressMinutes);
}

export function isTimedActivityInterruptible(state: TimedActivityState): boolean {
  if (!state.currentActivity) return false;
  if (state.currentActivity === 'eat_meal') {
    return state.activityElapsedMinutes >= MEAL_MIN_MINUTES;
  }
  return true;
}
