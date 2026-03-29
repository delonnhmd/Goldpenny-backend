import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { useDailyProgression } from '@/hooks/useDailyProgression';
import { useDailySession } from '@/hooks/useDailySession';
import { useEconomyState } from '@/hooks/useEconomyState';
import { useExpenseDebt } from '@/hooks/useExpenseDebt';
import { useJobIncome } from '@/hooks/useJobIncome';
import {
  buyStock,
  sellStock,
} from '@/lib/api/stocks';
import {
  acknowledgeEndOfDaySummary,
  endDay as settleDay,
  executeAction as executeGameplayAction,
  getTransactionHistory,
} from '@/lib/api/gameplay';
import { createGameplayCanonicalState } from '@/lib/gameplayRuntimeState';
import { recordInfo, recordWarning } from '@/lib/logger';
import {
  ActionPreviewResponse,
  DailyActionItem,
  EndOfDaySummaryResponse,
  TransactionHistoryItem,
} from '@/types/gameplay';

import {
  loadActionPreviewWithFallback,
  loadEndOfDaySummaryWithFallback,
  loadGameplayLoopBundle,
} from './service';
import { GameplayLoopBundle, GameplayLoopDataMode } from './types';

type FeedbackTone = 'success' | 'error' | 'info';

interface FeedbackState {
  tone: FeedbackTone;
  message: string;
}

interface PendingTradeState {
  stockId: string;
  side: 'buy' | 'sell';
}

interface RefreshOptions {
  silent?: boolean;
  includeEndOfDaySummary?: boolean;
}

interface GameplayLoopContextValue {
  playerId: string;
  bundle: GameplayLoopBundle | null;
  dashboard: GameplayLoopBundle['dashboard'] | null;
  actionHub: GameplayLoopBundle['actionHub'] | null;
  economySummary: GameplayLoopBundle['economySummary'] | null;
  stockMarket: GameplayLoopBundle['stockMarket'] | null;
  businesses: GameplayLoopBundle['businesses'] | null;
  businessPlan: GameplayLoopBundle['businessPlan'] | null;
  endOfDaySummary: EndOfDaySummaryResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  sourceMode: GameplayLoopDataMode;
  sourceNotes: string[];
  lastSyncedAt: string | null;
  transactionHistory: TransactionHistoryItem[];
  feedbackPromptDay: number | null;
  requestFeedbackPrompt: (gameDay: number) => void;
  dismissFeedbackPrompt: () => void;
  summaryAutoOpenDay: number | null;
  consumeSummaryAutoOpen: () => void;
  acknowledgeSummarySeen: (dayNumber?: number | null) => Promise<void>;
  feedback: FeedbackState | null;
  setFeedback: (next: FeedbackState | null) => void;
  refresh: (options?: RefreshOptions) => Promise<void>;
  dailySession: ReturnType<typeof useDailySession>;
  dailyProgression: ReturnType<typeof useDailyProgression>;
  canonicalState: ReturnType<typeof createGameplayCanonicalState>;
  economyState: ReturnType<typeof useEconomyState>;
  jobIncome: ReturnType<typeof useJobIncome>;
  expenseDebt: ReturnType<typeof useExpenseDebt>;
  selectedPreviewAction: DailyActionItem | null;
  actionPreview: ActionPreviewResponse | null;
  previewLoading: boolean;
  previewError: string | null;
  openActionPreview: (action: DailyActionItem) => Promise<void>;
  closeActionPreview: () => void;
  executeSelectedAction: () => Promise<boolean>;
  executeAction: (action: DailyActionItem) => Promise<boolean>;
  executingAction: boolean;
  busyActionKey: string | null;
  operateBusinessAction: DailyActionItem | null;
  operateBusiness: () => Promise<boolean>;
  endingDay: boolean;
  endCurrentDay: () => Promise<boolean>;
  startNextDay: () => Promise<void>;
  pendingTrade: PendingTradeState | null;
  buyOneStock: (stockId: string) => Promise<void>;
  sellOneStock: (stockId: string) => Promise<void>;
  sellAllStock: (stockId: string, quantity: number) => Promise<void>;
  eatMeal: (mealType: 'breakfast' | 'lunch' | 'dinner') => Promise<boolean>;
  takeLoan: (amount: number) => Promise<boolean>;
  selectHousing: (housingType: 'suburban' | 'downtown') => Promise<boolean>;
}

const GameplayLoopContext = createContext<GameplayLoopContextValue | null>(null);

const INTERACTION_DIAGNOSTICS_ENABLED =
  __DEV__
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === 'true'
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === '1';

function normalizeError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

function canonicalActionKey(actionKey: string): string {
  const raw = String(actionKey || '').toLowerCase().trim();
  if (!raw) return '';
  if (raw === 'operate_business' || (raw.includes('operate') && raw.includes('business'))) return 'operate_business';
  if (raw === 'work_shift' || raw.includes('work') || raw.includes('shift')) return 'work_shift';
  if (raw === 'recovery_action' || raw.includes('recovery')) return 'recovery_action';
  if (raw === 'switch_job' || (raw.includes('switch') && raw.includes('job'))) return 'switch_job';
  if (raw.includes('stock') || raw.includes('market')) return 'stocks';
  return raw;
}

function deriveSuggestedTimeUnits(bundle: GameplayLoopBundle | null): number {
  if (!bundle) return 10;
  const debug = bundle.dashboard.debug_meta || {};
  const directUnits = Number(debug.daily_time_units ?? debug.time_units ?? debug.hours_available_units);
  if (Number.isFinite(directUnits)) return Math.max(6, Math.min(16, Math.round(directUnits)));
  const fromSummary = Number(bundle.economySummary.current_day);
  if (Number.isFinite(fromSummary) && fromSummary > 0 && fromSummary <= 3) return 8;
  return 10;
}

export function GameplayLoopProvider({
  playerId,
  children,
}: {
  playerId: string;
  children: React.ReactNode;
}) {
  const [bundle, setBundle] = useState<GameplayLoopBundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<FeedbackState | null>(null);
  const [feedbackPromptDay, setFeedbackPromptDay] = useState<number | null>(null);
  const [summaryAutoOpenDay, setSummaryAutoOpenDay] = useState<number | null>(null);
  const [transactionHistory, setTransactionHistory] = useState<TransactionHistoryItem[]>([]);

  const [selectedPreviewAction, setSelectedPreviewAction] = useState<DailyActionItem | null>(null);
  const [actionPreview, setActionPreview] = useState<ActionPreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [executingAction, setExecutingAction] = useState(false);
  const [busyActionKey, setBusyActionKey] = useState<string | null>(null);
  const [endingDay, setEndingDay] = useState(false);
  const [pendingTrade, setPendingTrade] = useState<PendingTradeState | null>(null);
  const hasBundleRef = useRef(false);
  const promptedFeedbackDaysRef = useRef<Set<number>>(new Set());
  const autoOpenedSummaryDaysRef = useRef<Set<number>>(new Set());

  const dailySession = useDailySession(playerId);
  const dailyProgression = useDailyProgression(
    playerId,
    dailySession.sessionStatus,
    dailySession.pendingExecution || executingAction || endingDay || Boolean(pendingTrade),
  );
  const { initializeDay } = dailySession;

  useEffect(() => {
    hasBundleRef.current = Boolean(bundle);
  }, [bundle]);

  useEffect(() => {
    if (!INTERACTION_DIAGNOSTICS_ENABLED) return;
    recordInfo('gameplayLoop', 'Loading state changed.', {
      action: 'loading_state',
      context: {
        playerId,
        loading,
        refreshing,
        hasBundle: Boolean(bundle),
        sourceMode: bundle?.source.mode || null,
        hasError: Boolean(error),
      },
    });
  }, [bundle, error, loading, playerId, refreshing]);

  const refresh = useCallback(async (options?: RefreshOptions) => {
    const silent = Boolean(options?.silent);
    const includeEndOfDaySummary = options?.includeEndOfDaySummary ?? dailySession.sessionStatus === 'ended';
    if (INTERACTION_DIAGNOSTICS_ENABLED) {
      recordInfo('gameplayLoop', 'Refreshing gameplay bundle.', {
        action: 'refresh_bundle_start',
        context: {
          playerId,
          silent,
          includeEndOfDaySummary,
          sessionStatus: dailySession.sessionStatus,
        },
      });
    }

    if (!silent && !hasBundleRef.current) {
      setLoading(true);
    }
    setRefreshing(true);
    setError(null);

    try {
      const [nextBundle, txHistory] = await Promise.all([
        loadGameplayLoopBundle(playerId, {
          includeEndOfDaySummary,
        }),
        getTransactionHistory(playerId, 80).catch((txError) => {
          recordWarning('gameplayLoop', 'Failed to load transaction history.', {
            action: 'transaction_history_load',
            context: { playerId },
            error: txError,
          });
          return null;
        }),
      ]);
      setBundle(nextBundle);
      if (txHistory) {
        setTransactionHistory(txHistory.transactions);
      }

      const summary = nextBundle.endOfDaySummary;
      const debug = summary?.debug_meta || {};
      const latestDay = Number(
        summary?.day_number
        ?? debug.latest_completed_day
        ?? 0,
      );
      const shouldAutoShow = Boolean(debug.should_auto_show_summary) && latestDay > 0;
      const alreadyOpened = autoOpenedSummaryDaysRef.current.has(latestDay);
      if (shouldAutoShow && !alreadyOpened) {
        autoOpenedSummaryDaysRef.current.add(latestDay);
        setSummaryAutoOpenDay(latestDay);
        if (INTERACTION_DIAGNOSTICS_ENABLED) {
          recordInfo('gameplayLoop', 'Auto summary trigger armed.', {
            action: 'summary_auto_show',
            context: {
              playerId,
              latestCompletedDay: latestDay,
              summarySeenDay: Number(debug.summary_seen_day ?? 0),
              reason: String(debug.summary_gate_reason || 'show_unseen_latest_settlement'),
            },
          });
        }
      } else if (INTERACTION_DIAGNOSTICS_ENABLED && latestDay > 0) {
        recordInfo('gameplayLoop', 'Auto summary trigger suppressed.', {
          action: 'summary_auto_suppressed',
          context: {
            playerId,
            latestCompletedDay: latestDay,
            alreadyOpened,
            shouldAutoShow,
            summarySeenDay: Number(debug.summary_seen_day ?? 0),
            reason: String(debug.summary_gate_reason || 'suppressed'),
          },
        });
      }
    } catch (loadError) {
      const message = normalizeError(loadError);
      setError(message);
      recordWarning('gameplayLoop', 'Failed to load gameplay loop bundle.', {
        action: 'refresh_bundle',
        context: { playerId },
        error: loadError,
      });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [dailySession.sessionStatus, playerId]);

  const consumeSummaryAutoOpen = useCallback(() => {
    setSummaryAutoOpenDay(null);
  }, []);

  const acknowledgeSummarySeen = useCallback(async (dayNumber?: number | null) => {
    const currentSummary = bundle?.endOfDaySummary;
    const debug = currentSummary?.debug_meta || {};
    const targetDay = Number(
      dayNumber
      ?? currentSummary?.day_number
      ?? debug.latest_completed_day
      ?? 0,
    );
    if (!targetDay || targetDay <= 0) return;

    try {
      await acknowledgeEndOfDaySummary(playerId, targetDay);
      autoOpenedSummaryDaysRef.current.add(targetDay);
      setSummaryAutoOpenDay((current) => (current === targetDay ? null : current));
      setBundle((current) => {
        if (!current?.endOfDaySummary) return current;
        const existingDebug = current.endOfDaySummary.debug_meta || {};
        return {
          ...current,
          endOfDaySummary: {
            ...current.endOfDaySummary,
            debug_meta: {
              ...existingDebug,
              summary_seen_day: targetDay,
              summary_seen_for_day: true,
              should_auto_show_summary: false,
              summary_gate_reason: 'acknowledged_by_player',
            },
          },
        };
      });
      if (INTERACTION_DIAGNOSTICS_ENABLED) {
        recordInfo('gameplayLoop', 'Summary acknowledged by player.', {
          action: 'summary_ack',
          context: {
            playerId,
            targetDay,
          },
        });
      }
    } catch (ackError) {
      recordWarning('gameplayLoop', 'Failed to acknowledge summary.', {
        action: 'summary_ack',
        context: {
          playerId,
          targetDay,
        },
        error: ackError,
      });
    }
  }, [bundle?.endOfDaySummary, playerId]);

  const requestFeedbackPrompt = useCallback((gameDay: number) => {
    const normalizedDay = Math.max(1, Math.round(Number(gameDay) || 0));
    if (promptedFeedbackDaysRef.current.has(normalizedDay)) {
      return;
    }
    promptedFeedbackDaysRef.current.add(normalizedDay);
    setFeedbackPromptDay(normalizedDay);
    if (INTERACTION_DIAGNOSTICS_ENABLED) {
      recordInfo('gameplayLoop', 'Feedback prompt armed for settlement day.', {
        action: 'feedback_prompt_arm',
        context: {
          playerId,
          gameDay: normalizedDay,
        },
      });
    }
  }, [playerId]);

  const dismissFeedbackPrompt = useCallback(() => {
    setFeedbackPromptDay(null);
  }, []);

  useEffect(() => {
    void refresh({ includeEndOfDaySummary: false });
  }, [playerId, refresh]);

  useEffect(() => {
    if (!bundle || !dailyProgression.isHydrated) return;
    const dayFromSummary = Number(bundle.economySummary.current_day);
    const sessionDay = Number.isFinite(dayFromSummary) && dayFromSummary > 0
      ? dayFromSummary
      : dailyProgression.currentGameDay;
    initializeDay(sessionDay, deriveSuggestedTimeUnits(bundle));
  }, [
    bundle,
    dailyProgression.currentGameDay,
    dailyProgression.isHydrated,
    initializeDay,
  ]);

  const canonicalState = useMemo(() => createGameplayCanonicalState({
    playerId,
    currentDay: dailyProgression.currentGameDay,
    sessionStatus: dailySession.sessionStatus,
    dashboard: bundle?.dashboard || null,
    endOfDay: bundle?.endOfDaySummary || null,
  }), [
    playerId,
    dailyProgression.currentGameDay,
    dailySession.sessionStatus,
    bundle?.dashboard,
    bundle?.endOfDaySummary,
  ]);

  const economyState = useEconomyState(canonicalState);
  const jobIncome = useJobIncome(canonicalState);
  const expenseDebt = useExpenseDebt(canonicalState);
  const newPlayerFirstSession = Boolean(
    bundle?.dashboard?.debug_meta?.new_player_first_session
    ?? bundle?.actionHub?.debug_meta?.new_player_first_session
    ?? false,
  );
  const hasSettledSummaryPayload = Boolean(bundle?.endOfDaySummary);

  useEffect(() => {
    if (!INTERACTION_DIAGNOSTICS_ENABLED || !bundle) return;
    recordInfo('gameplayLoop', 'First-session gate evaluated.', {
      action: 'first_session_gate',
      context: {
        playerId,
        newPlayerFirstSession,
        hasSettledSummaryPayload,
        sessionStatus: dailySession.sessionStatus,
      },
    });
  }, [bundle, dailySession.sessionStatus, hasSettledSummaryPayload, newPlayerFirstSession, playerId]);

  const allActions = useMemo(() => {
    if (!bundle) return [];
    return [
      ...(bundle.actionHub.recommended_actions || []),
      ...(bundle.actionHub.available_actions || []),
      ...(bundle.actionHub.blocked_actions || []),
    ];
  }, [bundle]);

  const operateBusinessAction = useMemo(
    () => allActions.find((action) => canonicalActionKey(action.action_key) === 'operate_business') || null,
    [allActions],
  );

  const executeAction = useCallback(async (action: DailyActionItem): Promise<boolean> => {
    const executionGuard = dailySession.canExecuteAction(action);
    if (!executionGuard.allowed) {
      setFeedback({
        tone: 'error',
        message: executionGuard.reason || 'This action is currently blocked.',
      });
      return false;
    }

    setExecutingAction(true);
    setBusyActionKey(String(action.action_key));
    dailySession.setPendingExecution(true);

    try {
      const result = await executeGameplayAction(
        playerId,
        action.action_key,
        (action.parameters || {}) as Record<string, unknown>,
      );
      dailySession.consumeTime(result.time_cost_units);
      dailySession.addActionToHistory({
        action_key: action.action_key,
        title: action.title,
        description: action.description,
        result_summary: result.result_summary,
        time_cost_units: result.time_cost_units,
        success: Boolean(result.success),
        impact_snapshot: {
          cash_delta_xgp: result.cash_delta_xgp,
          stress_delta: result.stress_delta,
          health_delta: result.health_delta,
        },
      });

      setFeedback({
        tone: 'success',
        message: result.result_summary || result.message || `${action.title} completed.`,
      });

      await refresh({ silent: true });
      return true;
    } catch (actionError) {
      setFeedback({
        tone: 'error',
        message: normalizeError(actionError),
      });
      return false;
    } finally {
      dailySession.setPendingExecution(false);
      setExecutingAction(false);
      setBusyActionKey(null);
    }
  }, [dailySession, playerId, refresh]);

  const openActionPreview = useCallback(async (action: DailyActionItem) => {
    setSelectedPreviewAction(action);
    setPreviewLoading(true);
    setPreviewError(null);
    setActionPreview(null);

    try {
      const { preview, usedMock, note } = await loadActionPreviewWithFallback(playerId, {
        action_key: action.action_key,
        parameters: (action.parameters || {}) as Record<string, unknown>,
      });
      setActionPreview(preview);
      if (usedMock && note) {
        setPreviewError('Preview is using local mock data because backend preview is unavailable.');
      }
    } catch (previewLoadError) {
      setPreviewError(normalizeError(previewLoadError));
    } finally {
      setPreviewLoading(false);
    }
  }, [playerId]);

  const closeActionPreview = useCallback(() => {
    setSelectedPreviewAction(null);
    setActionPreview(null);
    setPreviewError(null);
    setPreviewLoading(false);
  }, []);

  const executeSelectedAction = useCallback(async (): Promise<boolean> => {
    if (!selectedPreviewAction) return false;
    const ok = await executeAction(selectedPreviewAction);
    if (ok) closeActionPreview();
    return ok;
  }, [closeActionPreview, executeAction, selectedPreviewAction]);

  const endCurrentDay = useCallback(async (): Promise<boolean> => {
    if (!dailyProgression.canAdvanceDay) {
      setFeedback({
        tone: 'error',
        message: 'Complete your current in-flight action first, then end the day.',
      });
      return false;
    }

    setEndingDay(true);
    dailySession.setPendingExecution(true);

    try {
      const result = await settleDay(playerId);
      dailySession.endDay();
      await dailyProgression.markDayAdvanced(result.settled_day);
      const { summary, note } = await loadEndOfDaySummaryWithFallback(playerId);

      setBundle((current) => (current ? { ...current, endOfDaySummary: summary } : current));
      if (summary) {
        setFeedback({
          tone: 'success',
          message: result.summary_headline || result.summary || result.message || 'Day settled.',
        });
      } else {
        setFeedback({
          tone: 'info',
          message: `${result.summary_headline || result.summary || result.message || 'Day settled.'} Summary data is not ready yet.`,
        });
        if (note && INTERACTION_DIAGNOSTICS_ENABLED) {
          recordWarning('gameplayLoop', 'Summary payload missing after settlement.', {
            action: 'summary_missing_after_settlement',
            context: {
              playerId,
              note,
            },
          });
        }
      }

      await refresh({
        silent: true,
        includeEndOfDaySummary: true,
      });
      return true;
    } catch (endDayError) {
      setFeedback({
        tone: 'error',
        message: normalizeError(endDayError),
      });
      return false;
    } finally {
      dailySession.setPendingExecution(false);
      setEndingDay(false);
    }
  }, [dailyProgression, dailySession, playerId, refresh]);

  const startNextDay = useCallback(async () => {
    const nextDay = await dailyProgression.markDayStarted();
    dailySession.resetSession({ nextDay });
    setBundle((current) => (current ? { ...current, endOfDaySummary: null } : current));
    setSummaryAutoOpenDay(null);
    setFeedback({
      tone: 'info',
      message: `Day ${nextDay} started. New brief and markets loaded.`,
    });
    await refresh({
      silent: true,
      includeEndOfDaySummary: false,
    });
  }, [dailyProgression, dailySession, refresh]);

  const performTrade = useCallback(async (stockId: string, side: 'buy' | 'sell', shares = 1) => {
    setPendingTrade({ stockId, side });
    try {
      const result = side === 'buy'
        ? await buyStock(playerId, stockId, shares)
        : await sellStock(playerId, stockId, shares);
      setFeedback({
        tone: 'success',
        message: `${side === 'buy' ? 'Bought' : 'Sold'} ${result.shares} share${result.shares === 1 ? '' : 's'} of ${result.stock_id}.`,
      });
      await refresh({
        silent: true,
        includeEndOfDaySummary: dailySession.sessionStatus === 'ended',
      });
    } catch (tradeError) {
      setFeedback({
        tone: 'error',
        message: normalizeError(tradeError),
      });
    } finally {
      setPendingTrade(null);
    }
  }, [dailySession.sessionStatus, playerId, refresh]);

  const buyOneStock = useCallback(async (stockId: string) => {
    await performTrade(stockId, 'buy', 1);
  }, [performTrade]);

  const sellOneStock = useCallback(async (stockId: string) => {
    await performTrade(stockId, 'sell', 1);
  }, [performTrade]);

  const sellAllStock = useCallback(async (stockId: string, quantity: number) => {
    const safeQuantity = Math.max(1, Math.floor(Number(quantity) || 0));
    await performTrade(stockId, 'sell', safeQuantity);
  }, [performTrade]);

  const operateBusiness = useCallback(async () => {
    const fallbackAction: DailyActionItem = {
      action_key: 'operate_business',
      title: 'Operate Business',
      description: 'Run the active business operation.',
      status: 'available',
      blockers: [],
      warnings: [],
      tradeoffs: [],
      confidence_level: 'unknown',
      parameters: {},
    };
    return executeAction(operateBusinessAction || fallbackAction);
  }, [executeAction, operateBusinessAction]);

  const eatMeal = useCallback(async (mealType: 'breakfast' | 'lunch' | 'dinner'): Promise<boolean> => {
    const action: DailyActionItem = {
      action_key: 'eat_meal',
      title: `Eat ${mealType.charAt(0).toUpperCase() + mealType.slice(1)}`,
      description: `Eat ${mealType} to restore health and reduce stress (-6 XGP).`,
      status: 'available',
      blockers: [],
      warnings: [],
      tradeoffs: [],
      confidence_level: 'high',
      parameters: { meal_type: mealType },
    };
    return executeAction(action);
  }, [executeAction]);

  const takeLoan = useCallback(async (amount: number): Promise<boolean> => {
    const safeAmount = Math.max(100, Math.min(500, Math.round(amount)));
    const action: DailyActionItem = {
      action_key: 'quick_loan',
      title: `Borrow ${safeAmount} XGP`,
      description: `Quick loan of ${safeAmount} XGP at 15% interest.`,
      status: 'available',
      blockers: [],
      warnings: [],
      tradeoffs: [],
      confidence_level: 'medium',
      parameters: { loan_amount: safeAmount },
    };
    return executeAction(action);
  }, [executeAction]);

  const selectHousing = useCallback(async (housingType: 'suburban' | 'downtown'): Promise<boolean> => {
    const action: DailyActionItem = {
      action_key: 'select_housing',
      title: `Choose ${housingType.charAt(0).toUpperCase() + housingType.slice(1)} Housing`,
      description: `Set your housing to ${housingType}.`,
      status: 'available',
      blockers: [],
      warnings: [],
      tradeoffs: [],
      confidence_level: 'high',
      parameters: { housing_type: housingType },
    };
    return executeAction(action);
  }, [executeAction]);

  const value = useMemo<GameplayLoopContextValue>(() => ({
    playerId,
    bundle,
    dashboard: bundle?.dashboard || null,
    actionHub: bundle?.actionHub || null,
    economySummary: bundle?.economySummary || null,
    stockMarket: bundle?.stockMarket || null,
    businesses: bundle?.businesses || null,
    businessPlan: bundle?.businessPlan || null,
    endOfDaySummary: bundle?.endOfDaySummary || null,
    loading,
    refreshing,
    error,
    sourceMode: bundle?.source.mode || 'live',
    sourceNotes: bundle?.source.notes || [],
    lastSyncedAt: bundle?.fetchedAt || null,
    transactionHistory,
    feedbackPromptDay,
    requestFeedbackPrompt,
    dismissFeedbackPrompt,
    summaryAutoOpenDay,
    consumeSummaryAutoOpen,
    acknowledgeSummarySeen,
    feedback,
    setFeedback,
    refresh,
    dailySession,
    dailyProgression,
    canonicalState,
    economyState,
    jobIncome,
    expenseDebt,
    selectedPreviewAction,
    actionPreview,
    previewLoading,
    previewError,
    openActionPreview,
    closeActionPreview,
    executeSelectedAction,
    executeAction,
    executingAction,
    busyActionKey,
    operateBusinessAction,
    operateBusiness,
    endingDay,
    endCurrentDay,
    startNextDay,
    pendingTrade,
    buyOneStock,
    sellOneStock,
    sellAllStock,
    eatMeal,
    takeLoan,
    selectHousing,
  }), [
    playerId,
    bundle,
    loading,
    refreshing,
    error,
    transactionHistory,
    feedbackPromptDay,
    requestFeedbackPrompt,
    dismissFeedbackPrompt,
    summaryAutoOpenDay,
    consumeSummaryAutoOpen,
    acknowledgeSummarySeen,
    feedback,
    refresh,
    dailySession,
    dailyProgression,
    canonicalState,
    economyState,
    jobIncome,
    expenseDebt,
    selectedPreviewAction,
    actionPreview,
    previewLoading,
    previewError,
    openActionPreview,
    closeActionPreview,
    executeSelectedAction,
    executeAction,
    executingAction,
    busyActionKey,
    operateBusinessAction,
    operateBusiness,
    endingDay,
    endCurrentDay,
    startNextDay,
    pendingTrade,
    buyOneStock,
    sellOneStock,
    sellAllStock,
    eatMeal,
    takeLoan,
    selectHousing,
  ]);

  return (
    <GameplayLoopContext.Provider value={value}>
      {children}
    </GameplayLoopContext.Provider>
  );
}

export function useGameplayLoop() {
  const ctx = useContext(GameplayLoopContext);
  if (!ctx) {
    throw new Error('useGameplayLoop must be used inside GameplayLoopProvider.');
  }
  return ctx;
}
