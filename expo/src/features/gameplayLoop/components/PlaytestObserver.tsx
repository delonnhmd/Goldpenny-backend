// Gold Penny — PlaytestObserver (Step 67).
// A zero-UI component mounted inside the gameplay loop scaffold that reactively
// observes onboarding and gameplay state and fires playtest events via
// usePlaytest. This keeps all instrumentation concerns outside the gameplay
// and onboarding contexts.

import { useEffect, useRef } from 'react';

import { useOnboarding } from '@/features/onboarding';
import { usePlaytest } from '@/features/playtest';
import { readPersistedOnboardingState } from '@/lib/onboardingPersistence';
import { updateFrictionSignal } from '@/lib/playtestAnalytics';

import { useGameplayLoop } from '../context';

export function PlaytestObserver() {
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();
  const {
    sessionId,
    trackSessionStarted,
    trackDayCompleted,
    trackOnboardingStarted,
    trackOnboardingSkipped,
    trackOnboardingCompleted,
    trackWorkAction,
  } = usePlaytest();

  const playerId = loop.bundle?.playerId ?? '';

  // ─── Session started ────────────────────────────────────────────────────────
  const sessionTrackedRef = useRef(false);

  useEffect(() => {
    if (sessionTrackedRef.current) return;
    const { isHydrated } = loop.dailyProgression;
    if (!isHydrated) return;
    const stats = loop.dashboard?.stats;
    if (!stats) return;

    sessionTrackedRef.current = true;

    const opportunityCount =
      (loop.economySummary?.player_opportunities?.length ?? 0) +
      (loop.dashboard?.top_opportunities?.length ?? 0);

    trackSessionStarted(loop.dailyProgression.currentGameDay, {
      cash: stats.cash_xgp ?? null,
      stress: stats.stress ?? null,
      health: stats.health ?? null,
      expensePressure: loop.expenseDebt.debtPressure ?? null,
      opportunityFlagsSurfaced: opportunityCount,
    });
  }, [
    loop.dashboard?.stats,
    loop.dailyProgression,
    loop.economySummary?.player_opportunities?.length,
    loop.dashboard?.top_opportunities?.length,
    loop.expenseDebt.debtPressure,
    trackSessionStarted,
  ]);

  // ─── Day completed ──────────────────────────────────────────────────────────
  const dayCompletedTrackedRef = useRef<number | null>(null);

  useEffect(() => {
    const summary = loop.endOfDaySummary;
    if (!summary) return;
    const gameDay = loop.dailyProgression.currentGameDay;
    if (dayCompletedTrackedRef.current === gameDay) return;
    dayCompletedTrackedRef.current = gameDay;

    const stats = loop.dashboard?.stats;
    trackDayCompleted(gameDay, {
      cash: stats?.cash_xgp ?? null,
      stress: stats?.stress ?? null,
      health: stats?.health ?? null,
      incomeEarned: summary.total_earned_xgp ?? null,
      expensePressure: loop.expenseDebt.debtPressure ?? null,
    });

    // Trigger soft launch feedback prompt after Day 1 or Day 2 settlement.
    if (gameDay === 1 || gameDay === 2) {
      loop.requestFeedbackPrompt(gameDay);
    }
  }, [
    loop.endOfDaySummary,
    loop.dailyProgression.currentGameDay,
    loop.dashboard?.stats,
    loop.expenseDebt.debtPressure,
    loop.requestFeedbackPrompt,
    trackDayCompleted,
  ]);

  // ─── Work action taken ──────────────────────────────────────────────────────
  const actionCountRef = useRef(0);

  useEffect(() => {
    const actions = loop.dailySession.actionsTakenToday;
    const successCount = actions.filter((a) => a.success).length;
    if (successCount > actionCountRef.current) {
      actionCountRef.current = successCount;
      const lastAction = [...actions].reverse().find((a) => a.success);
      trackWorkAction({
        actionKey: lastAction?.action_key,
        title: lastAction?.title,
        cashDelta: lastAction?.impact_snapshot?.cash_delta_xgp,
        stressDelta: lastAction?.impact_snapshot?.stress_delta,
      });
    }
  }, [loop.dailySession.actionsTakenToday, trackWorkAction]);

  // ─── Onboarding started ─────────────────────────────────────────────────────
  const onboardingStartedRef = useRef(false);

  useEffect(() => {
    if (!onboarding.isHydrated) return;
    if (onboardingStartedRef.current) return;
    if (!onboarding.isActive) return;
    onboardingStartedRef.current = true;
    trackOnboardingStarted();
  }, [onboarding.isHydrated, onboarding.isActive, trackOnboardingStarted]);

  // ─── Onboarding completed / skipped ────────────────────────────────────────
  // Detect the isActive transition true → false; read persisted state to
  // distinguish skip vs complete for correct funnel/friction signal.
  const wasOnboardingActiveRef = useRef<boolean | null>(null);

  useEffect(() => {
    if (!onboarding.isHydrated) return;

    const prev = wasOnboardingActiveRef.current;
    const current = onboarding.isActive;

    if (prev === null) {
      wasOnboardingActiveRef.current = current;
      return;
    }

    if (prev === true && current === false) {
      wasOnboardingActiveRef.current = false;
      if (!onboarding.isFirstSession || !playerId) return;

      void readPersistedOnboardingState(playerId).then((persisted) => {
        if (persisted?.status === 'skipped') {
          trackOnboardingSkipped();
          void updateFrictionSignal(sessionId, playerId, 'onboardingSkipped', true);
        } else {
          trackOnboardingCompleted();
        }
      });
    } else {
      wasOnboardingActiveRef.current = current;
    }
  }, [
    onboarding.isHydrated,
    onboarding.isActive,
    onboarding.isFirstSession,
    playerId,
    sessionId,
    trackOnboardingCompleted,
    trackOnboardingSkipped,
  ]);

  return null;
}
