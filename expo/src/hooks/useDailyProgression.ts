import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  createEmptyPersistedGameplayState,
  readPersistedGameplayState,
  updatePersistedGameplayState,
} from '@/lib/gameplayPersistence';
import { recordInfo, recordWarning } from '@/lib/logger';
import { DailySessionStatus } from '@/types/gameplay';

const DEFAULT_START_DAY = 1;

export interface DailyProgressionContract {
  /** Current game day number — starts at 1, increments each time a new day begins. */
  currentGameDay: number;
  /** True once persisted day state has been hydrated or safely defaulted. */
  isHydrated: boolean;
  /** The last game day confirmed as fully settled with the backend. Null until first end-of-day. */
  lastProcessedDay: number | null;
  /**
   * True when the player may safely end the current day.
   * Requires: session active, no action in flight, and today not yet processed.
   */
  canAdvanceDay: boolean;
  /** True while a day-advance persistence operation is in flight. */
  isAdvancingDay: boolean;
  /**
   * Record the current game day as settled.
   * Persists lastProcessedDay to storage.
   * Pass the backend-confirmed settled_day when available for accuracy.
   */
  markDayAdvanced: (settledDay?: number | null) => Promise<void>;
  /**
   * Start a new game day: increments currentGameDay, persists it asynchronously,
   * and returns the new day number synchronously so callers can use it immediately.
   */
  markDayStarted: () => Promise<number>;
}

export function useDailyProgression(
  playerId: string,
  sessionStatus: DailySessionStatus,
  actionInProgress: boolean,
): DailyProgressionContract {
  const [currentGameDay, setCurrentGameDay] = useState<number>(DEFAULT_START_DAY);
  const [isHydrated, setIsHydrated] = useState(false);
  const [lastProcessedDay, setLastProcessedDay] = useState<number | null>(null);
  const [isAdvancingDay, setIsAdvancingDay] = useState(false);

  // Ref mirrors so callbacks always read the latest values without stale closure issues.
  const currentGameDayRef = useRef(currentGameDay);
  currentGameDayRef.current = currentGameDay;

  // Prevents markDayStarted from advancing more than one day per button press.
  const markingDayRef = useRef(false);

  useEffect(() => {
    if (!playerId) {
      setCurrentGameDay(DEFAULT_START_DAY);
      currentGameDayRef.current = DEFAULT_START_DAY;
      setLastProcessedDay(null);
      setIsHydrated(true);
      return;
    }

    let cancelled = false;
    setIsHydrated(false);

    async function loadPersistedState() {
      try {
        const persisted = await readPersistedGameplayState(playerId);
        if (cancelled) return;

        const nextDay = persisted?.currentDay ?? DEFAULT_START_DAY;
        const nextLastProcessedDay = persisted?.lastProcessedDay ?? null;

        setCurrentGameDay(nextDay);
        currentGameDayRef.current = nextDay;
        setLastProcessedDay(nextLastProcessedDay);
      } catch (error) {
        if (cancelled) return;
        recordWarning('dailyProgression', 'Failed to hydrate persisted day state.', {
          action: 'load_persisted_state',
          context: {
            hasPlayerId: Boolean(playerId),
          },
          error,
        });
        setCurrentGameDay(DEFAULT_START_DAY);
        currentGameDayRef.current = DEFAULT_START_DAY;
        setLastProcessedDay(null);
      } finally {
        if (!cancelled) {
          setIsHydrated(true);
        }
      }
    }

    void loadPersistedState();

    return () => {
      cancelled = true;
    };
  }, [playerId]);

  const canAdvanceDay =
    isHydrated &&
    sessionStatus === 'active' &&
    !actionInProgress &&
    !isAdvancingDay &&
    currentGameDay !== lastProcessedDay;

  const markDayAdvanced = useCallback(async (settledDay?: number | null): Promise<void> => {
    setIsAdvancingDay(true);
    try {
      const processedDay =
        settledDay != null && Number.isFinite(settledDay) && settledDay > 0
          ? settledDay
          : currentGameDayRef.current;

      setLastProcessedDay(processedDay);
      await updatePersistedGameplayState(playerId, (current) => ({
        ...(current || createEmptyPersistedGameplayState(playerId, currentGameDayRef.current)),
        currentDay: current?.currentDay ?? currentGameDayRef.current,
        lastProcessedDay: processedDay,
      }));
      recordInfo('dailyProgression', 'Marked day as settled.', {
        action: 'mark_day_advanced',
        context: {
          processedDay,
        },
      });
    } catch (error) {
      recordWarning('dailyProgression', 'Failed to persist settled day.', {
        action: 'mark_day_advanced',
        context: {
          currentDay: currentGameDayRef.current,
        },
        error,
      });
      // Proceed even when persistence fails — in-memory update is applied.
    } finally {
      setIsAdvancingDay(false);
    }
  }, [playerId]);

  const markDayStarted = useCallback(async (): Promise<number> => {
    // Synchronous guard prevents double-advance on rapid double-tap of "Start Next Day".
    if (markingDayRef.current) return currentGameDayRef.current;
    markingDayRef.current = true;
    const nextDay = currentGameDayRef.current + 1;
    try {
      await updatePersistedGameplayState(playerId, (current) => ({
        ...(current || createEmptyPersistedGameplayState(playerId, nextDay)),
        currentDay: nextDay,
        session: null,
        randomEvent: null,
      }));
    } catch (error) {
      recordWarning('dailyProgression', 'Failed to persist current day.', {
        action: 'mark_day_started',
        context: {
          nextDay,
        },
        error,
      });
    }

    setCurrentGameDay(nextDay);
    currentGameDayRef.current = nextDay;
    recordInfo('dailyProgression', 'Started next day.', {
      action: 'mark_day_started',
      context: {
        nextDay,
      },
    });

    queueMicrotask(() => { markingDayRef.current = false; });
    return nextDay;
  }, [playerId]);

  return useMemo(
    () => ({
      currentGameDay,
      isHydrated,
      lastProcessedDay,
      canAdvanceDay,
      isAdvancingDay,
      markDayAdvanced,
      markDayStarted,
    }),
    [currentGameDay, isHydrated, lastProcessedDay, canAdvanceDay, isAdvancingDay, markDayAdvanced, markDayStarted],
  );
}
