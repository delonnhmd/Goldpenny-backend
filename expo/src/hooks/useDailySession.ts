import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AppState, AppStateStatus } from 'react-native';

import { BALANCE } from '@/lib/balanceConfig';
import { normalizeTimeUnits } from '@/lib/economySafety';
import {
  createEmptyPersistedGameplayState,
  PersistedGameplaySessionState,
  readPersistedGameplayState,
  updatePersistedGameplayState,
} from '@/lib/gameplayPersistence';
import { recordInfo, recordWarning } from '@/lib/logger';
import {
  applyIdleRecoveryMinutes,
  applyTimedActivityMinutes,
  createDefaultTimedActivityState,
  formatTimedActivityName,
  getNextUnitCountdownMinutes,
  getTimedActivityGuard,
  isTimedActivityActionKey,
  isTimedActivityInterruptible,
  MealType,
  sanitizeTimedActivityState,
  startTimedActivity as beginTimedActivity,
  stopTimedActivity as finishTimedActivity,
  TimedActivityGuard,
  TimedActivityState,
  TimedActivityType,
} from '@/lib/realtimeActivity';
import {
  DailyActionHistoryEntry,
  DailyActionItem,
  DailySessionStatus,
  GameplayActionKey,
} from '@/types/gameplay';

export interface ActionExecutionGuard {
  allowed: boolean;
  reason: string | null;
  timeCostUnits: number;
}

export interface TimedActivityStartResult {
  allowed: boolean;
  reason: string | null;
}

interface TimedActivityStartOptions {
  mealType?: MealType | null;
  recordHistory?: boolean;
}

// Constants sourced from BALANCE so tuning remains centralised.
const DEFAULT_TOTAL_TIME_UNITS = BALANCE.DEFAULT_TOTAL_TIME_UNITS;
const MIN_TOTAL_TIME_UNITS = BALANCE.MIN_TOTAL_TIME_UNITS;
const MAX_TOTAL_TIME_UNITS = BALANCE.MAX_TOTAL_TIME_UNITS;
const MIN_ACTION_TIME_COST_UNITS = BALANCE.SAFETY.MIN_TIME_COST_UNITS;
const MAX_ACTION_TIME_COST_UNITS = BALANCE.SAFETY.MAX_TIME_COST_UNITS;
const DEFAULT_ACTION_TIME_COST: Record<string, number> = BALANCE.ACTION_TIME_COST;
const DEFAULT_ACTION_CAPS: Record<string, number> = BALANCE.ACTION_CAPS;
const UI_TICK_INTERVAL_MS = BALANCE.REALTIME.UI_TICK_INTERVAL_MS;
const TRAINING_BONUS_THRESHOLD_UNITS = BALANCE.REALTIME.TRAINING_BONUS_THRESHOLD_UNITS;
const MEAL_MIN_MINUTES = BALANCE.REALTIME.MEAL_MIN_MINUTES;
const ZERO_TIME_ACTION_KEYS = new Set(['quick_loan', 'debt_payment', 'select_housing']);

const MAX_PERSISTED_ACTION_COUNT = 99;

function canRunDuringTimedMeal(actionKey: string, currentActivity: TimedActivityType | null): boolean {
  return currentActivity === 'eat_meal' && actionKey === 'debt_payment';
}

function normalizeActionKey(key: GameplayActionKey): string {
  const raw = String(key || '').toLowerCase().trim();
  if (!raw) return '';
  if (isTimedActivityActionKey(raw)) return raw;
  if (raw === 'switch_job' || (raw.includes('switch') && raw.includes('job'))) return 'switch_job';
  if (raw === 'change_region' || ((raw.includes('change') || raw.includes('move')) && raw.includes('region'))) {
    return 'change_region';
  }
  if (raw === 'recovery_action' || (raw.includes('recovery') && raw.includes('action'))) return 'recovery_action';
  if (raw.includes('business') && raw.includes('operate')) return 'operate_business';
  if (raw.includes('inventory') || raw.includes('stock')) return 'buy_inventory';
  if (raw.includes('ride') || raw.includes('delivery') || raw.includes('side_income')) return 'side_income';
  if (raw.includes('travel') || raw.includes('map_move')) return 'travel';
  if (raw.includes('work') || raw.includes('shift')) return 'work_shift';
  if (raw.includes('study') || raw.includes('train') || raw.includes('cert')) return 'study';
  if (raw.includes('meal') || raw.includes('eat')) return 'eat_meal';
  if (raw.includes('quick') && raw.includes('loan')) return 'quick_loan';
  if (raw.includes('debt') || raw.includes('payment')) return 'debt_payment';
  if (raw === 'select_housing' || raw.includes('select_housing')) return 'select_housing';
  if (raw.includes('housing') || raw.includes('region') || raw.includes('move')) return 'change_region';
  if (raw.includes('rest') || raw.includes('recover') || raw.includes('sleep')) return 'watch_tv';
  return raw.slice(0, 64);
}

function clampTotalUnits(value: number | undefined): number {
  return normalizeTimeUnits(value, {
    fallback: DEFAULT_TOTAL_TIME_UNITS,
    min: MIN_TOTAL_TIME_UNITS,
    max: MAX_TOTAL_TIME_UNITS,
  });
}

function clampRemainingUnits(value: number | undefined, totalUnits: number): number | null {
  if (!Number.isFinite(value)) return null;
  const boundedTotal = Math.max(0, Math.round(totalUnits || 0));
  return Math.max(0, Math.min(boundedTotal, Math.round(Number(value))));
}

function minutesFromIso(startIso: string | null | undefined, endDate = new Date()): number {
  if (!startIso) return 0;
  const startMs = new Date(startIso).getTime();
  if (!Number.isFinite(startMs)) return 0;
  const deltaMs = Math.max(0, endDate.getTime() - startMs);
  return deltaMs / 60000;
}

function formatSessionSummary(state: TimedActivityState): string {
  const elapsed = Math.max(0, Math.floor(state.activityElapsedMinutes));
  const unitSummary = `${state.sessionUnitsConsumed} unit${state.sessionUnitsConsumed === 1 ? '' : 's'} used`;
  if (state.currentActivity === 'skill_training') {
    const bonus = state.trainingUnitsThisSession >= TRAINING_BONUS_THRESHOLD_UNITS ? ' Efficiency bonus active.' : '';
    return `Training session ended after ${elapsed} min. ${unitSummary}. Skill progress +${state.sessionSkillProgress}.${bonus}`;
  }
  if (state.currentActivity === 'jogging') {
    return `Jogging session ended after ${elapsed} min. ${unitSummary}. Stress -${state.sessionStressRecovered}, Health +${state.sessionHealthGained}.`;
  }
  if (state.currentActivity === 'eat_meal') {
    return `${formatTimedActivityName('eat_meal', state.currentMealType)} completed after ${elapsed} min. ${unitSummary}.`;
  }
  return `${formatTimedActivityName(state.currentActivity, state.currentMealType)} ended after ${elapsed} min. ${unitSummary}. Stress -${state.sessionStressRecovered}.`;
}

function formatStartSummary(activity: TimedActivityType, mealType: MealType | null): string {
  if (activity === 'eat_meal') {
    return `${formatTimedActivityName(activity, mealType)} started. Minimum duration: ${MEAL_MIN_MINUTES} min.`;
  }
  if (activity === 'skill_training') {
    return `Skill training started. Time and progress now advance every ${BALANCE.REALTIME.MINUTES_PER_UNIT} minutes.`;
  }
  return `${formatTimedActivityName(activity, mealType)} started. Stress recovers while the activity runs.`;
}

export function useDailySession(playerId: string) {
  const [currentDay, setCurrentDay] = useState<number | null>(null);
  const [totalTimeUnits, setTotalTimeUnits] = useState<number>(DEFAULT_TOTAL_TIME_UNITS);
  const [remainingTimeUnits, setRemainingTimeUnits] = useState<number>(DEFAULT_TOTAL_TIME_UNITS);
  const [actionsTakenToday, setActionsTakenToday] = useState<DailyActionHistoryEntry[]>([]);
  const [sessionStatus, setSessionStatus] = useState<DailySessionStatus>('active');
  const [pendingExecution, setPendingExecution] = useState<boolean>(false);
  const [actionCounts, setActionCounts] = useState<Record<string, number>>({});
  const [timedActivity, setTimedActivity] = useState<TimedActivityState>(() => createDefaultTimedActivityState());

  const initializingRef = useRef(false);
  const timedActivityRef = useRef<TimedActivityState>(timedActivity);
  const remainingTimeUnitsRef = useRef<number>(remainingTimeUnits);
  const sessionStatusRef = useRef<DailySessionStatus>(sessionStatus);
  const appStateRef = useRef<AppStateStatus>(AppState.currentState);
  const tickIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    timedActivityRef.current = timedActivity;
  }, [timedActivity]);

  useEffect(() => {
    remainingTimeUnitsRef.current = remainingTimeUnits;
  }, [remainingTimeUnits]);

  useEffect(() => {
    sessionStatusRef.current = sessionStatus;
  }, [sessionStatus]);

  const updateTimedActivityState = useCallback((updater: (current: TimedActivityState) => TimedActivityState) => {
    setTimedActivity((current) => {
      const next = sanitizeTimedActivityState(updater(current));
      timedActivityRef.current = next;
      return next;
    });
  }, []);

  const sanitizeActionCounts = useCallback((value: unknown): Record<string, number> => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};

    const next: Record<string, number> = {};
    for (const [key, rawValue] of Object.entries(value as Record<string, unknown>)) {
      const normalizedKey = normalizeActionKey(key as GameplayActionKey);
      const parsedCount = Number(rawValue);
      if (!normalizedKey || !Number.isFinite(parsedCount) || isTimedActivityActionKey(normalizedKey)) continue;
      const cap = DEFAULT_ACTION_CAPS[normalizedKey];
      const upperBound = Number.isFinite(cap) ? Math.max(1, cap) : MAX_PERSISTED_ACTION_COUNT;
      next[normalizedKey] = Math.max(0, Math.min(upperBound, Math.round(parsedCount)));
    }
    return next;
  }, []);

  useEffect(() => {
    if (currentDay == null || !playerId) return;
    const snapshot: PersistedGameplaySessionState = {
      currentDay,
      remainingTimeUnits,
      actionCounts: { ...actionCounts },
      sessionStatus,
      totalTimeUnits,
      timedActivity,
    };
    updatePersistedGameplayState(playerId, (current) => ({
      ...(current || createEmptyPersistedGameplayState(playerId, currentDay)),
      currentDay,
      session: snapshot,
      randomEvent:
        current?.randomEvent && current.randomEvent.sourceDay === currentDay
          ? current.randomEvent
          : current?.randomEvent && current.randomEvent.isResolved && current.randomEvent.sourceDay === currentDay
            ? current.randomEvent
            : current?.randomEvent && current.randomEvent.sourceDay < currentDay
              ? null
              : current?.randomEvent || null,
    })).catch((error) => {
      recordWarning('dailySession', 'Failed to persist daily session snapshot.', {
        action: 'persist_snapshot',
        context: {
          currentDay,
          actionCount: actionsTakenToday.length,
          remainingTimeUnits,
          sessionStatus,
          currentActivity: timedActivity.currentActivity,
        },
        error,
      });
    });
  }, [
    actionCounts,
    actionsTakenToday.length,
    currentDay,
    playerId,
    remainingTimeUnits,
    sessionStatus,
    timedActivity,
    totalTimeUnits,
  ]);

  const appendHistoryEntry = useCallback((entry: Omit<DailyActionHistoryEntry, 'id' | 'order' | 'executed_at'>) => {
    setActionsTakenToday((prev) => {
      const nextOrder = prev.length + 1;
      const next: DailyActionHistoryEntry = {
        id: `${Date.now()}_${nextOrder}_${String(entry.action_key)}`,
        order: nextOrder,
        executed_at: new Date().toISOString(),
        ...entry,
      };
      return [next, ...prev];
    });
  }, []);

  const completeTimedActivity = useCallback((
    snapshot: TimedActivityState,
    reason: 'manual_stop' | 'auto_stop' | 'meal_complete',
  ) => {
    if (!snapshot.currentActivity) return;

    const title = reason === 'meal_complete'
      ? formatTimedActivityName('eat_meal', snapshot.currentMealType)
      : formatTimedActivityName(snapshot.currentActivity, snapshot.currentMealType);
    appendHistoryEntry({
      action_key: snapshot.currentActivity,
      title,
      description: `${title} session`,
      result_summary: formatSessionSummary(snapshot),
      time_cost_units: snapshot.sessionUnitsConsumed,
      success: true,
      impact_snapshot: {
        cash_delta_xgp: 0,
        stress_delta: snapshot.currentActivity === 'skill_training' ? 0 : -snapshot.sessionStressRecovered,
        health_delta: snapshot.sessionHealthGained,
      },
      raw_result: {
        current_activity: snapshot.currentActivity,
        meal_type: snapshot.currentMealType,
        session_units_consumed: snapshot.sessionUnitsConsumed,
        session_stress_recovered: snapshot.sessionStressRecovered,
        session_health_gained: snapshot.sessionHealthGained,
        session_skill_progress: snapshot.sessionSkillProgress,
        stop_reason: reason,
      },
    });
  }, [appendHistoryEntry]);

  const runTimedTick = useCallback((mode: 'active_session' | 'idle_away') => {
    const now = new Date();
    const current = timedActivityRef.current;
    const deltaMinutes = minutesFromIso(current.lastProcessedAtIso, now);
    const nowIso = now.toISOString();

    if (sessionStatusRef.current !== 'active') {
      updateTimedActivityState((state) => ({
        ...state,
        lastProcessedAtIso: nowIso,
      }));
      return;
    }

    if (mode === 'idle_away' && !current.currentActivity && deltaMinutes > 0) {
      const tick = applyIdleRecoveryMinutes(current, deltaMinutes);
      updateTimedActivityState((state) => ({
        ...tick.nextState,
        lastProcessedAtIso: nowIso,
      }));
      return;
    }

    if (!current.currentActivity || deltaMinutes <= 0) {
      updateTimedActivityState((state) => ({
        ...state,
        lastProcessedAtIso: nowIso,
      }));
      return;
    }

    const tick = applyTimedActivityMinutes(current, deltaMinutes, remainingTimeUnitsRef.current);
    const snapshotBeforeStop = tick.mealAutoCompleted || tick.forcedStop ? { ...current, ...tick.nextState } : null;

    if (tick.unitsConsumed > 0) {
      setRemainingTimeUnits((prev) => Math.max(0, prev - tick.unitsConsumed));
    }

    updateTimedActivityState((state) => ({
      ...tick.nextState,
      lastProcessedAtIso: nowIso,
    }));

    if (snapshotBeforeStop?.currentActivity) {
      completeTimedActivity(snapshotBeforeStop, tick.mealAutoCompleted ? 'meal_complete' : 'auto_stop');
    }
  }, [completeTimedActivity, updateTimedActivityState]);

  useEffect(() => {
    if (appStateRef.current !== 'active' || !timedActivity.currentActivity || sessionStatus !== 'active') {
      if (tickIntervalRef.current) {
        clearInterval(tickIntervalRef.current);
        tickIntervalRef.current = null;
      }
      return undefined;
    }

    tickIntervalRef.current = setInterval(() => {
      void runTimedTick('active_session');
    }, UI_TICK_INTERVAL_MS);

    return () => {
      if (tickIntervalRef.current) {
        clearInterval(tickIntervalRef.current);
        tickIntervalRef.current = null;
      }
    };
  }, [runTimedTick, sessionStatus, timedActivity.currentActivity]);

  useEffect(() => {
    const handleAppStateChange = (nextAppState: AppStateStatus) => {
      const previousState = appStateRef.current;
      appStateRef.current = nextAppState;

      if (previousState !== 'active' && nextAppState === 'active') {
        void runTimedTick(timedActivityRef.current.currentActivity ? 'active_session' : 'idle_away');
        return;
      }

      if ((nextAppState === 'background' || nextAppState === 'inactive') && currentDay != null) {
        updateTimedActivityState((state) => ({
          ...state,
          lastProcessedAtIso: new Date().toISOString(),
        }));
      }
    };

    const subscription = AppState.addEventListener('change', handleAppStateChange);
    return () => {
      subscription.remove();
    };
  }, [currentDay, runTimedTick, updateTimedActivityState]);

  useEffect(() => {
    if (currentDay == null || appStateRef.current !== 'active') return;
    void runTimedTick(timedActivityRef.current.currentActivity ? 'active_session' : 'idle_away');
  }, [currentDay, runTimedTick]);

  const initializeDay = useCallback((
    nextDay: number,
    suggestedTotalUnits?: number,
    suggestedRemainingUnits?: number,
  ) => {
    const normalizedDay = Math.max(1, Math.round(Number(nextDay) || 0));
    if (!Number.isFinite(normalizedDay) || normalizedDay < 1) return;
    if (normalizedDay === currentDay) return;
    if (initializingRef.current) return;
    initializingRef.current = true;

    const clamped = clampTotalUnits(suggestedTotalUnits);
    const suggestedRemaining = clampRemainingUnits(suggestedRemainingUnits, clamped);

    const freshInit = (dayNumber: number, units: number, remainingUnits?: number | null) => {
      const defaultTimedActivity = createDefaultTimedActivityState();
      const resolvedRemaining = remainingUnits == null ? units : remainingUnits;
      setCurrentDay(dayNumber);
      setTotalTimeUnits(units);
      setRemainingTimeUnits(resolvedRemaining);
      setActionCounts({});
      setActionsTakenToday([]);
      setSessionStatus('active');
      setPendingExecution(false);
      setTimedActivity(defaultTimedActivity);
      timedActivityRef.current = defaultTimedActivity;
    };

    if (!playerId) {
      freshInit(normalizedDay, clamped, suggestedRemaining);
      initializingRef.current = false;
      return;
    }

    readPersistedGameplayState(playerId)
      .then((persisted) => {
        const persistedSession = persisted?.session;
        const snapshotDay = persisted?.currentDay;
        if (persistedSession && snapshotDay === normalizedDay && persistedSession.currentDay === normalizedDay) {
          const restoredUnits = Math.max(
            0,
            Math.min(MAX_TOTAL_TIME_UNITS, Number(persistedSession.remainingTimeUnits) || 0),
          );
          const restoredTotal = clampTotalUnits(persistedSession.totalTimeUnits);
          const restoredSuggestedRemaining = clampRemainingUnits(suggestedRemainingUnits, restoredTotal);
          const resolvedRemainingUnits = restoredSuggestedRemaining == null
            ? restoredUnits
            : restoredSuggestedRemaining;
          const restoredStatus: DailySessionStatus =
            persistedSession.sessionStatus === 'ended' ? 'ended' : 'active';
          const restoredCounts = sanitizeActionCounts(persistedSession.actionCounts);
          const restoredTimedActivity = sanitizeTimedActivityState(persistedSession.timedActivity);
          setCurrentDay(normalizedDay);
          setTotalTimeUnits(restoredTotal);
          setRemainingTimeUnits(resolvedRemainingUnits);
          setActionCounts(restoredCounts);
          setActionsTakenToday([]);
          setSessionStatus(restoredStatus);
          setPendingExecution(false);
          setTimedActivity(restoredTimedActivity);
          timedActivityRef.current = restoredTimedActivity;
          recordInfo('dailySession', 'Restored persisted session snapshot.', {
            action: 'initialize_day',
            context: {
              currentDay: normalizedDay,
              restoredRemainingTimeUnits: resolvedRemainingUnits,
              restoredStatus,
              restoredActionTypes: Object.keys(restoredCounts).length,
              currentActivity: restoredTimedActivity.currentActivity,
            },
          });
          initializingRef.current = false;
          return;
        }

        freshInit(normalizedDay, clamped, suggestedRemaining);
        initializingRef.current = false;
      })
      .catch((error) => {
        recordWarning('dailySession', 'Failed to read persisted session snapshot.', {
          action: 'initialize_day',
          context: {
            currentDay: normalizedDay,
          },
          error,
        });
        freshInit(normalizedDay, clamped, suggestedRemaining);
        initializingRef.current = false;
      });
  }, [currentDay, playerId, sanitizeActionCounts]);

  const estimateTimeCost = useCallback(
    (actionKey: GameplayActionKey, explicitCost?: number): number => {
      const normalized = normalizeActionKey(actionKey);
      if (isTimedActivityActionKey(normalized)) return 0;
      if (ZERO_TIME_ACTION_KEYS.has(normalized)) {
        return 0;
      }
      if (Number.isFinite(explicitCost)) {
        if (Number(explicitCost) <= 0) return 0;
        return Math.max(MIN_ACTION_TIME_COST_UNITS, Math.min(MAX_ACTION_TIME_COST_UNITS, Number(explicitCost)));
      }
      const mapped = DEFAULT_ACTION_TIME_COST[normalized] ?? 2;
      return Math.max(MIN_ACTION_TIME_COST_UNITS, Math.min(MAX_ACTION_TIME_COST_UNITS, mapped));
    },
    [],
  );

  const getActionCount = useCallback(
    (actionKey: GameplayActionKey): number => {
      const normalized = normalizeActionKey(actionKey);
      return actionCounts[normalized] || 0;
    },
    [actionCounts],
  );

  const canStartTimedActivity = useCallback((
    activity: TimedActivityType,
    options?: TimedActivityStartOptions,
  ): TimedActivityGuard => {
    const guard = getTimedActivityGuard(timedActivityRef.current, activity, {
      remainingUnits: remainingTimeUnitsRef.current,
      sessionStatus: sessionStatusRef.current,
    });
    if (!guard.allowed) return guard;
    if (activity === 'eat_meal' && timedActivityRef.current.currentActivity === 'eat_meal') {
      return { allowed: false, reason: 'A meal is already in progress.' };
    }
    if (activity === 'eat_meal' && options?.mealType == null) {
      return { allowed: false, reason: 'Choose a meal before starting.' };
    }
    return guard;
  }, []);

  const canExecuteAction = useCallback(
    (action: DailyActionItem | { action_key: GameplayActionKey; status?: string; blockers?: string[] }, explicitCost?: number): ActionExecutionGuard => {
      const normalized = normalizeActionKey(action.action_key);
      if (isTimedActivityActionKey(normalized)) {
        const mealType = normalized === 'eat_meal'
          ? String((action as DailyActionItem).parameters?.meal_type || 'dinner').toLowerCase() as MealType
          : null;
        const guard = canStartTimedActivity(normalized, { mealType });
        return {
          allowed: guard.allowed,
          reason: guard.reason,
          timeCostUnits: 0,
        };
      }

      const actionRecord = action as Partial<DailyActionItem> & {
        parameters?: Record<string, unknown>;
        debug_meta?: Record<string, unknown>;
      };
      const inlineCost = Number(
        explicitCost
        ?? actionRecord.parameters?.time_cost_units
        ?? actionRecord.debug_meta?.time_cost_units,
      );
      const timeCostUnits = estimateTimeCost(
        action.action_key,
        Number.isFinite(inlineCost) ? inlineCost : undefined,
      );
      if (currentDay == null) {
        return { allowed: false, reason: 'Gameplay is still restoring your saved day.', timeCostUnits };
      }
      if (pendingExecution) {
        return { allowed: false, reason: 'Another action is already in progress.', timeCostUnits };
      }
      if (sessionStatus !== 'active') {
        return { allowed: false, reason: 'Day already ended. Start next day to continue.', timeCostUnits };
      }
      if (
        timedActivityRef.current.currentActivity
        && !canRunDuringTimedMeal(normalized, timedActivityRef.current.currentActivity)
      ) {
        return {
          allowed: false,
          reason: `Finish ${formatTimedActivityName(timedActivityRef.current.currentActivity, timedActivityRef.current.currentMealType)} first.`,
          timeCostUnits,
        };
      }
      if (action.status === 'blocked') {
        const blockedReason = Array.isArray(action.blockers) && action.blockers.length > 0
          ? action.blockers[0]
          : 'Action is currently blocked.';
        return { allowed: false, reason: blockedReason, timeCostUnits };
      }
      if (remainingTimeUnits < timeCostUnits) {
        return { allowed: false, reason: 'Not enough time today.', timeCostUnits };
      }
      return { allowed: true, reason: null, timeCostUnits };
    },
    [canStartTimedActivity, currentDay, estimateTimeCost, pendingExecution, remainingTimeUnits, sessionStatus],
  );

  const consumeTime = useCallback((amount: number) => {
    const delta = Math.max(0, Number(amount) || 0);
    setRemainingTimeUnits((prev) => Math.max(0, prev - delta));
    updateTimedActivityState((state) => ({
      ...state,
      lastInteractionTimeIso: new Date().toISOString(),
    }));
  }, [updateTimedActivityState]);

  const addActionToHistory = useCallback((entry: Omit<DailyActionHistoryEntry, 'id' | 'order' | 'executed_at'>) => {
    if (entry.success) {
      const normalized = normalizeActionKey(entry.action_key);
      const cap = DEFAULT_ACTION_CAPS[normalized];
      if (normalized && cap && !isTimedActivityActionKey(normalized)) {
        setActionCounts((prev) => ({
          ...prev,
          [normalized]: (prev[normalized] || 0) + 1,
        }));
      }
    }
    appendHistoryEntry(entry);
  }, [appendHistoryEntry]);

  const startTimedActivity = useCallback((
    activity: TimedActivityType,
    options?: TimedActivityStartOptions,
  ): TimedActivityStartResult => {
    const guard = canStartTimedActivity(activity, options);
    if (!guard.allowed) return guard;
    const nowIso = new Date().toISOString();
    const mealType = activity === 'eat_meal' ? (options?.mealType || 'dinner') : null;
    updateTimedActivityState((state) => beginTimedActivity(state, activity, nowIso, mealType));
    if (options?.recordHistory !== false) {
      appendHistoryEntry({
        action_key: activity,
        title: formatTimedActivityName(activity, mealType),
        description: `${formatTimedActivityName(activity, mealType)} session`,
        result_summary: formatStartSummary(activity, mealType),
        time_cost_units: 0,
        success: true,
        impact_snapshot: {
          cash_delta_xgp: 0,
          stress_delta: 0,
          health_delta: 0,
        },
        raw_result: {
          session_event: 'activity_started',
          meal_type: mealType,
        },
      });
    }
    return { allowed: true, reason: null };
  }, [appendHistoryEntry, canStartTimedActivity, updateTimedActivityState]);

  const stopTimedActivity = useCallback((): TimedActivityStartResult => {
    const snapshot = timedActivityRef.current;
    if (!snapshot.currentActivity) {
      return { allowed: false, reason: 'No timed activity is running.' };
    }
    const nowIso = new Date().toISOString();
    const result = finishTimedActivity(snapshot, nowIso);
    if (result.blocked) {
      return { allowed: false, reason: `Meals cannot be stopped before ${MEAL_MIN_MINUTES} minutes.` };
    }
    completeTimedActivity(snapshot, 'manual_stop');
    updateTimedActivityState(() => result.nextState);
    return { allowed: true, reason: null };
  }, [completeTimedActivity, updateTimedActivityState]);

  const endDay = useCallback(() => {
    if (timedActivityRef.current.currentActivity) {
      const stopped = finishTimedActivity(timedActivityRef.current, new Date().toISOString());
      if (!stopped.blocked) {
        completeTimedActivity(timedActivityRef.current, 'manual_stop');
        updateTimedActivityState(() => stopped.nextState);
      }
    }
    setSessionStatus('ended');
    setPendingExecution(false);
  }, [completeTimedActivity, updateTimedActivityState]);

  const resetSession = useCallback((options?: { totalUnits?: number; nextDay?: number }) => {
    const clamped = clampTotalUnits(options?.totalUnits ?? totalTimeUnits);
    if (Number.isFinite(options?.nextDay)) {
      setCurrentDay(Math.max(1, Math.round(Number(options?.nextDay))));
    }
    const defaultTimedActivity = createDefaultTimedActivityState();
    setTotalTimeUnits(clamped);
    setRemainingTimeUnits(clamped);
    setActionCounts({});
    setActionsTakenToday([]);
    setSessionStatus('active');
    setPendingExecution(false);
    setTimedActivity(defaultTimedActivity);
    timedActivityRef.current = defaultTimedActivity;
    recordInfo('dailySession', 'Session reset for new day.', {
      action: 'reset_session',
      context: {
        nextDay: options?.nextDay ?? currentDay,
        totalTimeUnits: clamped,
      },
    });
  }, [currentDay, totalTimeUnits]);

  const progress = useMemo(() => {
    if (totalTimeUnits <= 0) return 0;
    const used = totalTimeUnits - remainingTimeUnits;
    return Math.max(0, Math.min(1, used / totalTimeUnits));
  }, [remainingTimeUnits, totalTimeUnits]);

  const currentActivityName = useMemo(
    () => formatTimedActivityName(timedActivity.currentActivity, timedActivity.currentMealType),
    [timedActivity.currentActivity, timedActivity.currentMealType],
  );

  const nextUnitCountdownMinutes = useMemo(
    () => getNextUnitCountdownMinutes(timedActivity),
    [timedActivity],
  );

  const canStopCurrentActivity = useMemo(
    () => isTimedActivityInterruptible(timedActivity),
    [timedActivity],
  );

  const trainingEfficiencyBonusActive = useMemo(
    () => timedActivity.trainingUnitsThisSession >= TRAINING_BONUS_THRESHOLD_UNITS,
    [timedActivity.trainingUnitsThisSession],
  );

  return {
    currentDay,
    totalTimeUnits,
    remainingTimeUnits,
    actionsTakenToday,
    sessionStatus,
    pendingExecution,
    progress,
    initializeDay,
    estimateTimeCost,
    getActionCount,
    canExecuteAction,
    consumeTime,
    addActionToHistory,
    setPendingExecution,
    endDay,
    resetSession,
    currentActivity: timedActivity.currentActivity,
    currentActivityName,
    currentMealType: timedActivity.currentMealType,
    currentActivityElapsedMinutes: timedActivity.activityElapsedMinutes,
    unitProgressMinutes: timedActivity.unitProgressMinutes,
    nextUnitCountdownMinutes,
    mealLocked: timedActivity.mealLocked,
    hasActiveTimedActivity: Boolean(timedActivity.currentActivity),
    stressRecoveredToday: timedActivity.stressRecoveredToday,
    healthGainedToday: timedActivity.healthGainedToday,
    skillProgressGainedToday: timedActivity.skillProgressGainedToday,
    sessionStressRecovered: timedActivity.sessionStressRecovered,
    sessionHealthGained: timedActivity.sessionHealthGained,
    sessionSkillProgress: timedActivity.sessionSkillProgress,
    trainingUnitsThisSession: timedActivity.trainingUnitsThisSession,
    sessionUnitsConsumed: timedActivity.sessionUnitsConsumed,
    trainingEfficiencyBonusActive,
    lastInteractionTimeIso: timedActivity.lastInteractionTimeIso,
    lastProcessedAtIso: timedActivity.lastProcessedAtIso,
    canStopCurrentActivity,
    canStartTimedActivity,
    startTimedActivity,
    stopTimedActivity,
  };
}
