// Gold Penny — Playtest instrumentation context (Step 67).
// Wraps the gameplay loop to emit events, track screen time, funnel steps,
// balance telemetry, and friction signals without touching gameplay logic.

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import { AppState, AppStateStatus } from 'react-native';

import {
  buildPlaytestReport,
  Day1BalanceTelemetry,
  emitPlaytestEvent,
  FrictionSignals,
  generateSessionId,
  incrementLongIdleCount,
  markFunnelCheckpoint,
  PlaytestEvent,
  PlaytestReport,
  recordEndingStats,
  recordScreenTime,
  recordStartingStats,
  recordTimeToFirstAction,
  registerSession,
  updateFrictionSignal,
} from '@/lib/playtestAnalytics';

// ─── Long-idle threshold ──────────────────────────────────────────────────────
// Flag a friction idle if the app is backgrounded for longer than this.
const LONG_IDLE_THRESHOLD_MS = 90_000; // 90 seconds

// ─── Context value ─────────────────────────────────────────────────────────────

export interface PlaytestContextValue {
  sessionId: string;
  sessionStartedAt: string;
  /** Call when a screen becomes visible. Handles funnel + event + timing. */
  trackScreenView: (screen: string) => void;
  /** Call after a successful work action. */
  trackWorkAction: (properties?: Record<string, unknown>) => void;
  /** Call when onboarding starts. */
  trackOnboardingStarted: () => void;
  /** Call when onboarding is skipped. */
  trackOnboardingSkipped: () => void;
  /** Call when onboarding completes. */
  trackOnboardingCompleted: () => void;
  /** Call when the current gameplay day session begins (after hydration). */
  trackSessionStarted: (gameDay: number, startingStats: StartingStats) => void;
  /** Call when end-of-day settlement completes. */
  trackDayCompleted: (gameDay: number, endingStats: EndingStats) => void;
  /** Call when the app goes to background / user force-quits during play. */
  trackSessionAbandoned: () => void;
  /** Load the full report for the dev panel. */
  loadReport: () => Promise<PlaytestReport | null>;
}

export interface StartingStats {
  cash: number | null;
  stress: number | null;
  health: number | null;
  expensePressure: string | null;
  opportunityFlagsSurfaced: number;
}

export interface EndingStats {
  cash: number | null;
  stress: number | null;
  health: number | null;
  incomeEarned: number | null;
  expensePressure: string | null;
}

const PlaytestContext = createContext<PlaytestContextValue | null>(null);

// ─── Provider ─────────────────────────────────────────────────────────────────

export function PlaytestProvider({
  playerId,
  children,
}: {
  playerId: string;
  children: React.ReactNode;
}) {
  const sessionIdRef = useRef(generateSessionId());
  const sessionStartedAtRef = useRef(new Date().toISOString());
  const gameDayRef = useRef(1);
  const hasTrackedSessionRef = useRef(false);
  const hasTrackedFirstActionRef = useRef(false);
  const activeScreenRef = useRef<string | null>(null);
  const screenEnteredAtRef = useRef<number>(Date.now());
  const appBgAtRef = useRef<number | null>(null);

  const sessionId = sessionIdRef.current;
  const sessionStartedAt = sessionStartedAtRef.current;

  // ─── App-state idle tracking ────────────────────────────────────────────────
  useEffect(() => {
    const handleAppStateChange = async (nextState: AppStateStatus) => {
      if (nextState === 'background' || nextState === 'inactive') {
        appBgAtRef.current = Date.now();
      } else if (nextState === 'active' && appBgAtRef.current !== null) {
        const idleMs = Date.now() - appBgAtRef.current;
        appBgAtRef.current = null;
        if (idleMs >= LONG_IDLE_THRESHOLD_MS) {
          await incrementLongIdleCount(sessionId, playerId);
        }
      }
    };

    const subscription = AppState.addEventListener('change', handleAppStateChange);
    return () => subscription.remove();
  }, [playerId, sessionId]);

  // ─── Helpers ────────────────────────────────────────────────────────────────

  const emit = useCallback(
    (
      eventName: PlaytestEvent['eventName'],
      properties?: Record<string, unknown>,
    ) => {
      void emitPlaytestEvent({
        eventName,
        sessionId,
        playerId,
        gameDay: gameDayRef.current,
        properties,
      });
    },
    [playerId, sessionId],
  );

  const flushActiveScreenTime = useCallback(() => {
    const screen = activeScreenRef.current;
    if (!screen) return;
    const durationMs = Date.now() - screenEnteredAtRef.current;
    void recordScreenTime(sessionId, playerId, gameDayRef.current, {
      screen,
      enteredAt: new Date(screenEnteredAtRef.current).toISOString(),
      durationMs,
    });
  }, [playerId, sessionId]);

  // ─── Public API ──────────────────────────────────────────────────────────────

  const trackScreenView = useCallback(
    (screen: string) => {
      // Flush previous screen time first
      flushActiveScreenTime();
      activeScreenRef.current = screen;
      screenEnteredAtRef.current = Date.now();

      // Emit event
      const eventMap: Record<string, PlaytestEvent['eventName']> = {
        brief: 'brief_viewed',
        dashboard: 'dashboard_viewed',
        market: 'market_viewed',
        business: 'business_viewed',
        summary: 'summary_viewed',
      };
      const eventName = eventMap[screen];
      if (eventName) {
        emit(eventName);
      }

      // Update funnel
      const funnelMap: Record<string, Parameters<typeof markFunnelCheckpoint>[3]> = {
        brief: 'briefSeenAt',
        dashboard: 'dashboardSeenAt',
        market: 'marketSeenAt',
        summary: 'summarySeenAt',
      };
      const checkpoint = funnelMap[screen];
      if (checkpoint) {
        void markFunnelCheckpoint(
          sessionId,
          playerId,
          gameDayRef.current,
          checkpoint,
        );
      }

      // Update friction signals
      const frictionClearMap: Record<
        string,
        Parameters<typeof updateFrictionSignal>[2]
      > = {
        market: 'noMarketVisit',
        business: 'noBusinessVisit',
        summary: 'exitedBeforeSummary',
      };
      const frictionKey = frictionClearMap[screen];
      if (frictionKey) {
        void updateFrictionSignal(sessionId, playerId, frictionKey, false);
      }
    },
    [emit, flushActiveScreenTime, playerId, sessionId],
  );

  const trackWorkAction = useCallback(
    (properties?: Record<string, unknown>) => {
      emit('work_action_taken', properties);

      if (!hasTrackedFirstActionRef.current) {
        hasTrackedFirstActionRef.current = true;
        void recordTimeToFirstAction(
          sessionId,
          playerId,
          gameDayRef.current,
          sessionStartedAt,
        );
        void markFunnelCheckpoint(
          sessionId,
          playerId,
          gameDayRef.current,
          'firstWorkActionAt',
        );
        void updateFrictionSignal(sessionId, playerId, 'noWorkActionTaken', false);
      }
    },
    [emit, playerId, sessionId, sessionStartedAt],
  );

  const trackOnboardingStarted = useCallback(() => {
    emit('onboarding_started');
  }, [emit]);

  const trackOnboardingSkipped = useCallback(() => {
    emit('onboarding_skipped');
    void updateFrictionSignal(sessionId, playerId, 'onboardingSkipped', true);
  }, [emit, playerId, sessionId]);

  const trackOnboardingCompleted = useCallback(() => {
    emit('onboarding_completed');
  }, [emit]);

  const trackSessionStarted = useCallback(
    (gameDay: number, startingStats: StartingStats) => {
      if (hasTrackedSessionRef.current) return;
      hasTrackedSessionRef.current = true;
      gameDayRef.current = gameDay;

      emit('session_started', { gameDay });
      void markFunnelCheckpoint(sessionId, playerId, gameDay, 'sessionStartedAt');
      void registerSession({
        sessionId,
        playerId,
        startedAt: sessionStartedAt,
        gameDay,
      });
      void recordStartingStats(sessionId, playerId, gameDay, startingStats);
    },
    [emit, playerId, sessionId, sessionStartedAt],
  );

  const trackDayCompleted = useCallback(
    (gameDay: number, endingStats: EndingStats) => {
      emit('day_completed', { gameDay });
      void markFunnelCheckpoint(sessionId, playerId, gameDay, 'dayCompletedAt');
      void recordEndingStats(sessionId, playerId, gameDay, endingStats);
      // Clear the "exited before summary" friction signal on successful completion
      void updateFrictionSignal(sessionId, playerId, 'exitedBeforeSummary', false);
    },
    [emit, playerId, sessionId],
  );

  const trackSessionAbandoned = useCallback(() => {
    // Flush active screen time before abandoning
    flushActiveScreenTime();
    emit('session_abandoned');
  }, [emit, flushActiveScreenTime]);

  const loadReport = useCallback(async (): Promise<PlaytestReport | null> => {
    try {
      // Flush current screen before loading
      flushActiveScreenTime();
      return await buildPlaytestReport(playerId, sessionId, gameDayRef.current);
    } catch {
      return null;
    }
  }, [flushActiveScreenTime, playerId, sessionId]);

  const value: PlaytestContextValue = {
    sessionId,
    sessionStartedAt,
    trackScreenView,
    trackWorkAction,
    trackOnboardingStarted,
    trackOnboardingSkipped,
    trackOnboardingCompleted,
    trackSessionStarted,
    trackDayCompleted,
    trackSessionAbandoned,
    loadReport,
  };

  return (
    <PlaytestContext.Provider value={value}>
      {children}
    </PlaytestContext.Provider>
  );
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function usePlaytest(): PlaytestContextValue {
  const ctx = useContext(PlaytestContext);
  if (!ctx) {
    throw new Error('usePlaytest must be used inside PlaytestProvider');
  }
  return ctx;
}
