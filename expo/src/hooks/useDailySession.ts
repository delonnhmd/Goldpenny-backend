import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

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

// Constants sourced from BALANCE so all tuning is centralised in balanceConfig.
const DEFAULT_TOTAL_TIME_UNITS = BALANCE.DEFAULT_TOTAL_TIME_UNITS;
const MIN_TOTAL_TIME_UNITS = BALANCE.MIN_TOTAL_TIME_UNITS;
const MAX_TOTAL_TIME_UNITS = BALANCE.MAX_TOTAL_TIME_UNITS;
const DEFAULT_ACTION_TIME_COST: Record<string, number> = BALANCE.ACTION_TIME_COST;
const DEFAULT_ACTION_CAPS: Record<string, number> = BALANCE.ACTION_CAPS;

const MAX_PERSISTED_ACTION_COUNT = 99;

function normalizeActionKey(key: GameplayActionKey): string {
  const raw = String(key || '').toLowerCase().trim();
  if (!raw) return '';
  if (raw === 'switch_job' || (raw.includes('switch') && raw.includes('job'))) return 'switch_job';
  if (raw === 'change_region' || ((raw.includes('change') || raw.includes('move')) && raw.includes('region'))) {
    return 'change_region';
  }
  if (raw === 'recovery_action' || (raw.includes('recovery') && raw.includes('action'))) return 'recovery_action';
  if (raw.includes('business') && raw.includes('operate')) return 'operate_business';
  if (raw.includes('inventory') || raw.includes('stock')) return 'buy_inventory';
  if (raw.includes('ride') || raw.includes('delivery') || raw.includes('side_income')) return 'side_income';
  if (raw.includes('work') || raw.includes('shift')) return 'work_shift';
  if (raw.includes('study') || raw.includes('train') || raw.includes('cert')) return 'study';
  if (raw.includes('debt') || raw.includes('payment')) return 'debt_payment';
  if (raw.includes('housing') || raw.includes('region') || raw.includes('move')) return 'change_region';
  if (raw.includes('rest') || raw.includes('recover') || raw.includes('sleep')) return 'rest';
  return raw.slice(0, 64);
}

function clampTotalUnits(value: number | undefined): number {
  return normalizeTimeUnits(value, {
    fallback: DEFAULT_TOTAL_TIME_UNITS,
    min: MIN_TOTAL_TIME_UNITS,
    max: MAX_TOTAL_TIME_UNITS,
  });
}

export function useDailySession(playerId: string) {
  const [currentDay, setCurrentDay] = useState<number | null>(null);
  const [totalTimeUnits, setTotalTimeUnits] = useState<number>(DEFAULT_TOTAL_TIME_UNITS);
  const [remainingTimeUnits, setRemainingTimeUnits] = useState<number>(DEFAULT_TOTAL_TIME_UNITS);
  const [actionsTakenToday, setActionsTakenToday] = useState<DailyActionHistoryEntry[]>([]);
  const [sessionStatus, setSessionStatus] = useState<DailySessionStatus>('active');
  const [pendingExecution, setPendingExecution] = useState<boolean>(false);
  // Canonical once-per-day action markers survive reloads and drive cap enforcement.
  const [actionCounts, setActionCounts] = useState<Record<string, number>>({});

  // Prevents concurrent initializeDay calls while a storage read is in flight.
  const initializingRef = useRef(false);

  const sanitizeActionCounts = useCallback((value: unknown): Record<string, number> => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};

    const next: Record<string, number> = {};
    for (const [key, rawValue] of Object.entries(value as Record<string, unknown>)) {
      const normalizedKey = normalizeActionKey(key as GameplayActionKey);
      const parsedCount = Number(rawValue);
      if (!normalizedKey || !Number.isFinite(parsedCount)) continue;
      const cap = DEFAULT_ACTION_CAPS[normalizedKey];
      const upperBound = Number.isFinite(cap) ? Math.max(1, cap) : MAX_PERSISTED_ACTION_COUNT;
      next[normalizedKey] = Math.max(0, Math.min(upperBound, Math.round(parsedCount)));
    }
    return next;
  }, []);

  // Persist key session state so a mid-day reload cannot reset time units or action caps.
  useEffect(() => {
    if (currentDay == null || !playerId) return;
    const snapshot: PersistedGameplaySessionState = {
      currentDay,
      remainingTimeUnits,
      actionCounts: { ...actionCounts },
      sessionStatus,
      totalTimeUnits,
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
        },
        error,
      });
    });
  }, [
    actionCounts,
    actionsTakenToday.length,
    currentDay,
    remainingTimeUnits,
    sessionStatus,
    totalTimeUnits,
    playerId,
  ]);

  const initializeDay = useCallback((nextDay: number, suggestedTotalUnits?: number) => {
    const normalizedDay = Math.max(1, Math.round(Number(nextDay) || 0));
    if (!Number.isFinite(normalizedDay) || normalizedDay < 1) return;
    if (normalizedDay === currentDay) return;
    if (initializingRef.current) return;
    initializingRef.current = true;

    const clamped = clampTotalUnits(suggestedTotalUnits);

    const freshInit = (dayNumber: number, units: number) => {
      setCurrentDay(dayNumber);
      setTotalTimeUnits(units);
      setRemainingTimeUnits(units);
      setActionCounts({});
      setActionsTakenToday([]);
      setSessionStatus('active');
      setPendingExecution(false);
    };

    if (!playerId) {
      freshInit(normalizedDay, clamped);
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
          const restoredStatus: DailySessionStatus =
            persistedSession.sessionStatus === 'ended' ? 'ended' : 'active';
          const restoredCounts = sanitizeActionCounts(persistedSession.actionCounts);
          setCurrentDay(normalizedDay);
          setTotalTimeUnits(restoredTotal);
          setRemainingTimeUnits(restoredUnits);
          setActionCounts(restoredCounts);
          setActionsTakenToday([]);
          setSessionStatus(restoredStatus);
          setPendingExecution(false);
          recordInfo('dailySession', 'Restored persisted session snapshot.', {
            action: 'initialize_day',
            context: {
              currentDay: normalizedDay,
              restoredRemainingTimeUnits: restoredUnits,
              restoredStatus,
              restoredActionTypes: Object.keys(restoredCounts).length,
            },
          });
          initializingRef.current = false;
          return;
        }

        freshInit(normalizedDay, clamped);
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
        freshInit(normalizedDay, clamped);
        initializingRef.current = false;
      });
  }, [currentDay, playerId, sanitizeActionCounts]);

  const estimateTimeCost = useCallback(
    (actionKey: GameplayActionKey, explicitCost?: number): number => {
      if (Number.isFinite(explicitCost)) {
        return Math.max(1, Math.min(4, Number(explicitCost)));
      }
      const normalized = normalizeActionKey(actionKey);
      const mapped = DEFAULT_ACTION_TIME_COST[normalized] ?? 2;
      return Math.max(1, Math.min(4, mapped));
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

  const canExecuteAction = useCallback(
    (action: DailyActionItem | { action_key: GameplayActionKey; status?: string; blockers?: string[] }, explicitCost?: number): ActionExecutionGuard => {
      const timeCostUnits = estimateTimeCost(action.action_key, explicitCost);
      if (currentDay == null) {
        return { allowed: false, reason: 'Gameplay is still restoring your saved day.', timeCostUnits };
      }
      if (pendingExecution) {
        return { allowed: false, reason: 'Another action is already in progress.', timeCostUnits };
      }
      if (sessionStatus !== 'active') {
        return { allowed: false, reason: 'Day already ended. Start next day to continue.', timeCostUnits };
      }
      if (action.status === 'blocked') {
        const blockedReason = Array.isArray(action.blockers) && action.blockers.length > 0
          ? action.blockers[0]
          : 'Action is currently blocked.';
        return { allowed: false, reason: blockedReason, timeCostUnits };
      }
      const normalized = normalizeActionKey(action.action_key);
      const cap = DEFAULT_ACTION_CAPS[normalized];
      if (cap && getActionCount(normalized) >= cap) {
        return { allowed: false, reason: 'You already used this action enough times today.', timeCostUnits };
      }
      if (remainingTimeUnits < timeCostUnits) {
        return { allowed: false, reason: 'Not enough time today.', timeCostUnits };
      }
      return { allowed: true, reason: null, timeCostUnits };
    },
    [currentDay, estimateTimeCost, getActionCount, pendingExecution, remainingTimeUnits, sessionStatus],
  );

  const consumeTime = useCallback((amount: number) => {
    const delta = Math.max(0, Number(amount) || 0);
    setRemainingTimeUnits((prev) => Math.max(0, prev - delta));
  }, []);

  const addActionToHistory = useCallback((entry: Omit<DailyActionHistoryEntry, 'id' | 'order' | 'executed_at'>) => {
    if (entry.success) {
      const normalized = normalizeActionKey(entry.action_key);
      if (normalized) {
        setActionCounts((prev) => ({
          ...prev,
          [normalized]: (prev[normalized] || 0) + 1,
        }));
      }
    }
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

  const endDay = useCallback(() => {
    setSessionStatus('ended');
    setPendingExecution(false);
  }, []);

  const resetSession = useCallback((options?: { totalUnits?: number; nextDay?: number }) => {
    const clamped = clampTotalUnits(options?.totalUnits ?? totalTimeUnits);
    if (Number.isFinite(options?.nextDay)) {
      setCurrentDay(Math.max(1, Math.round(Number(options?.nextDay))));
    }
    setTotalTimeUnits(clamped);
    setRemainingTimeUnits(clamped);
    setActionCounts({});
    setActionsTakenToday([]);
    setSessionStatus('active');
    setPendingExecution(false);
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
  };
}
