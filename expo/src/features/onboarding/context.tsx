import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { router } from 'expo-router';

import { useGameplayLoop } from '@/features/gameplayLoop/context';
import { recordInfo, recordWarning } from '@/lib/logger';
import {
  PersistedOnboardingStatus,
  readPersistedOnboardingState,
  writePersistedOnboardingState,
} from '@/lib/onboardingPersistence';
import {
  emitPlaytestEvent,
} from '@/lib/playtestAnalytics';

export type OnboardingRouteKey =
  | 'brief'
  | 'dashboard'
  | 'work'
  | 'market'
  | 'business'
  | 'life'
  | 'summary';

type GuidedRouteKey = Exclude<OnboardingRouteKey, 'business' | 'life'>;

type OnboardingStepRequirement = 'manual_continue' | 'first_work_action' | 'settled_summary';

export interface OnboardingStepDefinition {
  key: string;
  route: GuidedRouteKey;
  title: string;
  body: string;
  highlightTarget: string;
  requirement: OnboardingStepRequirement;
  continueLabel?: string;
}

const ONBOARDING_STEPS: OnboardingStepDefinition[] = [
  {
    key: 'brief_daily_economy',
    route: 'brief',
    title: 'Read The Daily Economy',
    body: 'Signals first -> better actions next.',
    highlightTarget: 'brief-daily-economy',
    requirement: 'manual_continue',
    continueLabel: 'Next: Dashboard',
  },
  {
    key: 'dashboard_core_stats',
    route: 'dashboard',
    title: 'Watch Cash And Stress',
    body: 'Cash protects you -> stress increases mistakes.',
    highlightTarget: 'dashboard-core-stats',
    requirement: 'manual_continue',
    continueLabel: 'Next: Work',
  },
  {
    key: 'work_first_action',
    route: 'work',
    title: 'Do One Work Action',
    body: 'One action spends time -> cash and stress change.',
    highlightTarget: 'work-first-action',
    requirement: 'first_work_action',
  },
  {
    key: 'market_price_movement',
    route: 'market',
    title: 'Check Price Movement',
    body: 'Prices up -> your costs and margins move.',
    highlightTarget: 'market-price-movement',
    requirement: 'manual_continue',
    continueLabel: 'Next: Summary',
  },
  {
    key: 'summary_close_day',
    route: 'summary',
    title: 'Close Day 1',
    body: 'Settle day -> lock results and learn fast.',
    highlightTarget: 'summary-day-results',
    requirement: 'settled_summary',
  },
];

const ONBOARDING_ROUTE_LOCK_ENABLED =
  process.env.EXPO_PUBLIC_ONBOARDING_ROUTE_LOCK === 'true'
  || process.env.EXPO_PUBLIC_ONBOARDING_ROUTE_LOCK === '1';
const ONBOARDING_NAV_DIAGNOSTICS_ENABLED =
  __DEV__
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === 'true'
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === '1';

interface OnboardingContextValue {
  isHydrated: boolean;
  isFirstSession: boolean;
  isActive: boolean;
  isSimplifiedMode: boolean;
  currentStepIndex: number;
  totalSteps: number;
  progressLabel: string;
  currentStep: OnboardingStepDefinition | null;
  expectedRoute: GuidedRouteKey | null;
  highlightTarget: string | null;
  canContinueCurrentStep: boolean;
  continueLabel: string | null;
  requirementStatus: string | null;
  blockedNavigationMessage: string | null;
  hasCompletedWorkAction: boolean;
  hasSettledSummary: boolean;
  navigateTo: (route: OnboardingRouteKey) => boolean;
  canNavigateTo: (route: OnboardingRouteKey) => boolean;
  ensureRoute: (currentRoute: OnboardingRouteKey) => void;
  continueCurrentStep: () => Promise<void>;
  skipOnboarding: () => Promise<void>;
  clearBlockedNavigationMessage: () => void;
}

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

function clampStepIndex(value: number): number {
  const safe = Math.floor(Number(value) || 0);
  if (!Number.isFinite(safe)) return 0;
  return Math.max(0, Math.min(ONBOARDING_STEPS.length - 1, safe));
}

function stepRoutePath(playerId: string, route: OnboardingRouteKey): string {
  return `/gameplay/loop/${playerId}/${route}`;
}

function navLabel(route: OnboardingRouteKey): string {
  if (route === 'brief') return 'Brief';
  if (route === 'dashboard') return 'Dashboard';
  if (route === 'work') return 'Work';
  if (route === 'market') return 'Market';
  if (route === 'business') return 'Business';
  if (route === 'life') return 'Life';
  return 'Summary';
}

export function OnboardingProvider({
  playerId,
  children,
}: {
  playerId: string;
  children: React.ReactNode;
}) {
  const loop = useGameplayLoop();

  const [isHydrated, setIsHydrated] = useState(false);
  const [isFirstSession, setIsFirstSession] = useState(false);
  const [isActive, setIsActive] = useState(false);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [blockedNavigationMessage, setBlockedNavigationMessage] = useState<string | null>(null);

  const transitionGuardRef = useRef(false);

  const currentStep = isActive ? ONBOARDING_STEPS[clampStepIndex(currentStepIndex)] : null;
  const expectedRoute = currentStep?.route || null;

  const hasCompletedWorkAction = useMemo(
    () => loop.dailySession.actionsTakenToday.some((entry) => entry.success),
    [loop.dailySession.actionsTakenToday],
  );

  const hasSettledSummary = Boolean(loop.endOfDaySummary)
    && loop.dailySession.sessionStatus === 'ended';

  const isSimplifiedMode = isActive
    && isFirstSession
    && loop.dailyProgression.currentGameDay <= 1;

  const progressLabel = currentStep
    ? `${clampStepIndex(currentStepIndex) + 1}/${ONBOARDING_STEPS.length}`
    : `${ONBOARDING_STEPS.length}/${ONBOARDING_STEPS.length}`;

  const persistState = useCallback(async (
    status: PersistedOnboardingStatus,
    stepIndex: number,
  ) => {
    await writePersistedOnboardingState(playerId, {
      status,
      stepIndex: clampStepIndex(stepIndex),
    });
  }, [playerId]);

  const completeOnboarding = useCallback(async (status: 'completed' | 'skipped') => {
    if (transitionGuardRef.current) return;
    transitionGuardRef.current = true;
    try {
      await persistState(status, ONBOARDING_STEPS.length - 1);
      setIsActive(false);
      setBlockedNavigationMessage(null);
      recordInfo('onboarding', 'First-session onboarding finished.', {
        action: 'complete_onboarding',
        context: {
          playerId,
          status,
        },
      });
      // Emit playtest event for skip vs complete distinction.
      void emitPlaytestEvent({
        eventName: status === 'skipped' ? 'onboarding_skipped' : 'onboarding_completed',
        sessionId: 'onboarding',
        playerId,
        gameDay: 1,
      });
    } finally {
      transitionGuardRef.current = false;
    }
  }, [persistState, playerId]);

  const moveToStep = useCallback(async (nextStepIndex: number, autoNavigate = true) => {
    if (transitionGuardRef.current) return;
    transitionGuardRef.current = true;
    try {
      const safeIndex = clampStepIndex(nextStepIndex);
      setCurrentStepIndex(safeIndex);
      await persistState('in_progress', safeIndex);
      setBlockedNavigationMessage(null);

      if (autoNavigate) {
        const nextRoute = ONBOARDING_STEPS[safeIndex]?.route;
        if (nextRoute) {
          router.replace(stepRoutePath(playerId, nextRoute));
        }
      }
    } finally {
      transitionGuardRef.current = false;
    }
  }, [persistState, playerId]);

  const moveToNextStep = useCallback(async (autoNavigate = true) => {
    const nextStepIndex = clampStepIndex(currentStepIndex) + 1;
    if (nextStepIndex >= ONBOARDING_STEPS.length) {
      await completeOnboarding('completed');
      return;
    }
    await moveToStep(nextStepIndex, autoNavigate);
  }, [completeOnboarding, currentStepIndex, moveToStep]);

  useEffect(() => {
    if (!playerId || !loop.dailyProgression.isHydrated) return;

    let cancelled = false;
    setIsHydrated(false);

    async function hydrateOnboarding() {
      const firstSession = loop.dailyProgression.lastProcessedDay == null;
      const persisted = await readPersistedOnboardingState(playerId);
      if (cancelled) return;

      setIsFirstSession(firstSession);

      if (!firstSession) {
        setIsActive(false);
        setCurrentStepIndex(clampStepIndex(persisted?.stepIndex ?? ONBOARDING_STEPS.length - 1));
        setBlockedNavigationMessage(null);
        setIsHydrated(true);
        return;
      }

      if (persisted?.status === 'completed' || persisted?.status === 'skipped') {
        setIsActive(false);
        setCurrentStepIndex(clampStepIndex(persisted.stepIndex));
        setBlockedNavigationMessage(null);
        setIsHydrated(true);
        return;
      }

      const restoredStepIndex = clampStepIndex(persisted?.stepIndex ?? 0);
      setCurrentStepIndex(restoredStepIndex);
      setIsActive(true);
      setBlockedNavigationMessage(null);
      setIsHydrated(true);

      if (!persisted || persisted.status !== 'in_progress') {
        await persistState('in_progress', restoredStepIndex);
      }
    }

    void hydrateOnboarding();

    return () => {
      cancelled = true;
    };
  }, [
    loop.dailyProgression.isHydrated,
    loop.dailyProgression.lastProcessedDay,
    persistState,
    playerId,
  ]);

  useEffect(() => {
    if (!isHydrated || !isActive || !currentStep) return;
    if (currentStep.requirement !== 'first_work_action') return;
    if (!hasCompletedWorkAction) return;

    void moveToNextStep(true);
  }, [
    currentStep,
    hasCompletedWorkAction,
    isActive,
    isHydrated,
    moveToNextStep,
  ]);

  useEffect(() => {
    if (!isHydrated || !isActive || !currentStep) return;
    if (currentStep.requirement !== 'settled_summary') return;
    if (!hasSettledSummary) return;

    void completeOnboarding('completed');
  }, [
    completeOnboarding,
    currentStep,
    hasSettledSummary,
    isActive,
    isHydrated,
  ]);

  const canNavigateTo = useCallback((route: OnboardingRouteKey) => {
    if (!isActive || !expectedRoute) return true;
    if (!ONBOARDING_ROUTE_LOCK_ENABLED) return true;
    return route === expectedRoute;
  }, [expectedRoute, isActive]);

  const navigateTo = useCallback((route: OnboardingRouteKey) => {
    if (canNavigateTo(route)) {
      setBlockedNavigationMessage(null);
      if (ONBOARDING_NAV_DIAGNOSTICS_ENABLED) {
        recordInfo('onboarding', 'Navigation route accepted.', {
          action: 'navigate_to',
          context: {
            playerId,
            route,
            expectedRoute,
            routeLockEnabled: ONBOARDING_ROUTE_LOCK_ENABLED,
          },
        });
      }
      router.replace(stepRoutePath(playerId, route));
      return true;
    }

    const nextStepTitle = currentStep?.title || 'the guided step';
    const message = `Finish "${nextStepTitle}" before opening ${navLabel(route)}.`;
    setBlockedNavigationMessage(message);
    if (ONBOARDING_NAV_DIAGNOSTICS_ENABLED) {
      recordWarning('onboarding', 'Navigation route blocked by guided onboarding lock.', {
        action: 'navigate_to_blocked',
        context: {
          playerId,
          route,
          expectedRoute,
          currentStepTitle: currentStep?.title || null,
          routeLockEnabled: ONBOARDING_ROUTE_LOCK_ENABLED,
        },
      });
    }
    return false;
  }, [canNavigateTo, currentStep?.title, expectedRoute, playerId]);

  const ensureRoute = useCallback((currentRoute: OnboardingRouteKey) => {
    if (!ONBOARDING_ROUTE_LOCK_ENABLED) return;
    if (!isActive || !expectedRoute || currentRoute === expectedRoute) return;
    if (ONBOARDING_NAV_DIAGNOSTICS_ENABLED) {
      recordWarning('onboarding', 'Route mismatch corrected by onboarding lock.', {
        action: 'ensure_route',
        context: {
          playerId,
          currentRoute,
          expectedRoute,
        },
      });
    }
    router.replace(stepRoutePath(playerId, expectedRoute));
  }, [expectedRoute, isActive, playerId]);

  const canContinueCurrentStep = currentStep?.requirement === 'manual_continue';
  const continueLabel = canContinueCurrentStep
    ? currentStep?.continueLabel || 'Continue'
    : null;

  const continueCurrentStep = useCallback(async () => {
    if (!canContinueCurrentStep) return;
    await moveToNextStep(true);
  }, [canContinueCurrentStep, moveToNextStep]);

  const skipOnboarding = useCallback(async () => {
    await completeOnboarding('skipped');
  }, [completeOnboarding]);

  const requirementStatus = useMemo(() => {
    if (!currentStep) return null;
    if (currentStep.requirement === 'first_work_action' && !hasCompletedWorkAction) {
      return 'Required: complete 1 work action.';
    }
    if (currentStep.requirement === 'settled_summary' && !hasSettledSummary) {
      return 'Required: run end-of-day settlement.';
    }
    return null;
  }, [currentStep, hasCompletedWorkAction, hasSettledSummary]);

  const clearBlockedNavigationMessage = useCallback(() => {
    setBlockedNavigationMessage(null);
  }, []);

  const value = useMemo<OnboardingContextValue>(() => ({
    isHydrated,
    isFirstSession,
    isActive,
    isSimplifiedMode,
    currentStepIndex: clampStepIndex(currentStepIndex),
    totalSteps: ONBOARDING_STEPS.length,
    progressLabel,
    currentStep,
    expectedRoute,
    highlightTarget: currentStep?.highlightTarget || null,
    canContinueCurrentStep,
    continueLabel,
    requirementStatus,
    blockedNavigationMessage,
    hasCompletedWorkAction,
    hasSettledSummary,
    navigateTo,
    canNavigateTo,
    ensureRoute,
    continueCurrentStep,
    skipOnboarding,
    clearBlockedNavigationMessage,
  }), [
    blockedNavigationMessage,
    canContinueCurrentStep,
    canNavigateTo,
    clearBlockedNavigationMessage,
    continueCurrentStep,
    continueLabel,
    currentStep,
    currentStepIndex,
    ensureRoute,
    expectedRoute,
    hasCompletedWorkAction,
    hasSettledSummary,
    isActive,
    isFirstSession,
    isHydrated,
    isSimplifiedMode,
    navigateTo,
    progressLabel,
    requirementStatus,
    skipOnboarding,
  ]);

  return (
    <OnboardingContext.Provider value={value}>
      {children}
    </OnboardingContext.Provider>
  );
}

export function useOnboarding() {
  const context = useContext(OnboardingContext);
  if (!context) {
    throw new Error('useOnboarding must be used inside OnboardingProvider.');
  }
  return context;
}
