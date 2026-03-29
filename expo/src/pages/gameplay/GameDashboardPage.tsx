import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { router } from 'expo-router';
import { RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import ActionHistoryPanel from '@/components/gameplay/ActionHistoryPanel';
import ActionHubPanel from '@/components/gameplay/ActionHubPanel';
import ActionPreviewModal from '@/components/gameplay/ActionPreviewModal';
import ActiveCommitmentCard from '@/components/gameplay/ActiveCommitmentCard';
import BusinessOperationsCard from '@/components/gameplay/BusinessOperationsCard';
import BusinessPlanCard from '@/components/gameplay/BusinessPlanCard';
import BusinessMarginsCard from '@/components/gameplay/BusinessMarginsCard';
import CommutePressureCard from '@/components/gameplay/CommutePressureCard';
import CommitmentFeedbackCard from '@/components/gameplay/CommitmentFeedbackCard';
import CommitmentHistoryCard from '@/components/gameplay/CommitmentHistoryCard';
import CommitmentPickerCard from '@/components/gameplay/CommitmentPickerCard';
import CommitmentProgressCard from '@/components/gameplay/CommitmentProgressCard';
import DailyBriefCard from '@/components/gameplay/DailyBriefCard';
import DailyGoalsCard from '@/components/gameplay/DailyGoalsCard';
import DebtVsGrowthCard from '@/components/gameplay/DebtVsGrowthCard';
import EconomyExplainerCard from '@/components/gameplay/EconomyExplainerCard';
import EmptyStateCard from '@/components/gameplay/EmptyStateCard';
import EndOfDaySummaryCard from '@/components/gameplay/EndOfDaySummaryCard';
import ErrorStateCard from '@/components/gameplay/ErrorStateCard';
import FuturePreparationCard from '@/components/gameplay/FuturePreparationCard';
import FutureOpportunitiesCard from '@/components/gameplay/FutureOpportunitiesCard';
import HousingTradeoffCard from '@/components/gameplay/HousingTradeoffCard';
import LoadingStateCard from '@/components/gameplay/LoadingStateCard';
import MarketOverviewCard from '@/components/gameplay/MarketOverviewCard';
import NotificationsDrawer from '@/components/gameplay/NotificationsDrawer';
import LocalPressureCard from '@/components/gameplay/LocalPressureCard';
import OnboardingBanner from '@/components/gameplay/OnboardingBanner';
import PatternInsightsCard from '@/components/gameplay/PatternInsightsCard';
import PlayerStatsBar from '@/components/gameplay/PlayerStatsBar';
import RandomEventCard from '@/components/gameplay/RandomEventCard';
import PlayerPatternsCard from '@/components/gameplay/PlayerPatternsCard';
import PriceTrendsCard from '@/components/gameplay/PriceTrendsCard';
import ProgressionSummaryCard from '@/components/gameplay/ProgressionSummaryCard';
import RecoveryVsPushCard from '@/components/gameplay/RecoveryVsPushCard';
import RegionMemoryCard from '@/components/gameplay/RegionMemoryCard';
import ShortHorizonPlansCard from '@/components/gameplay/ShortHorizonPlansCard';
import StockMarketCard from '@/components/gameplay/StockMarketCard';
import SecondaryDashboardSection from '@/components/gameplay/SecondaryDashboardSection';
import PrimaryDashboardSection from '@/components/gameplay/PrimaryDashboardSection';
import StreaksCard from '@/components/gameplay/StreaksCard';
import StrategyRecommendationCard from '@/components/gameplay/StrategyRecommendationCard';
import SupplyChainStoryCard from '@/components/gameplay/SupplyChainStoryCard';
import ThumbReachActionDock from '@/components/gameplay/ThumbReachActionDock';
import WeeklySummaryCard from '@/components/gameplay/WeeklySummaryCard';
import WeeklyMissionsCard from '@/components/gameplay/WeeklyMissionsCard';
import WorldNarrativeCard from '@/components/gameplay/WorldNarrativeCard';
import AppShell from '@/components/layout/AppShell';
import ContentStack from '@/components/layout/ContentStack';
import PageContainer from '@/components/layout/PageContainer';
import FadeInView from '@/components/motion/FadeInView';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { ActionExecutionGuard, useDailySession } from '@/hooks/useDailySession';
import { useDailyProgression } from '@/hooks/useDailyProgression';
import { useEconomyState } from '@/hooks/useEconomyState';
import { useExpenseDebt } from '@/hooks/useExpenseDebt';
import { useJobIncome } from '@/hooks/useJobIncome';
import { useRandomEvent } from '@/hooks/useRandomEvent';
import {
  attachGameplayEventState,
  createGameplayCanonicalState,
} from '@/lib/gameplayRuntimeState';
import { recordError, recordInfo, recordWarning } from '@/lib/logger';
import {
  activateCommitment,
  cancelCommitment,
  getAvailableCommitments,
  getCommitmentFeedback,
  getCommitmentHistory,
  getCommitmentSummary,
  refreshCommitment,
  replaceCommitment,
} from '@/lib/api/commitment';
import { getPlayerBusinesses } from '@/lib/api/business';
import { buyStock, getStockMarketSnapshot, sellStock } from '@/lib/api/stocks';
import {
  getBusinessMargins,
  getCommutePressure,
  getEconomyExplainer,
  getEconomyPresentationSummary,
  getFutureTeasers,
  getMarketOverview,
  getPriceTrends,
} from '@/lib/api/economyPresentation';
import {
  endDay,
  executeAction,
  getEndOfDaySummary,
  getPlayerActions,
  getPlayerDashboard,
  getPlayerNotifications,
  getWeeklySummary,
  previewPlayerAction,
} from '@/lib/api/gameplay';
import { getProgressionSummary } from '@/lib/api/progression';
import {
  advanceOnboarding,
  getOnboardingDashboardConfig,
  getOnboardingGuidance,
  getOnboardingState,
  getOnboardingUnlockSchedule,
  skipOnboarding,
} from '@/lib/api/onboarding';
import {
  getBusinessPlan,
  getDebtVsGrowth,
  getFuturePreparation,
  getHousingTradeoff,
  getRecoveryVsPush,
  getShortHorizonPlans,
  getStrategyRecommendation,
} from '@/lib/api/strategicPlanning';
import {
  getLocalPressure,
  getPlayerPatterns,
  getRegionMemory,
  getWorldMemoryPatterns,
  getWorldNarrative,
} from '@/lib/api/worldMemory';
import {
  ActionExecutionResponse,
  ActionPreviewResponse,
  DashboardSignalItem,
  DailyActionHubResponse,
  DailyActionItem,
  EndDayResponse,
  EndOfDaySummaryResponse,
  GameplayActionKey,
  PlayerDashboardResponse,
  PlayerNotificationResponse,
  WeeklyPlayerSummaryResponse,
} from '@/types/gameplay';
import {
  CommitmentFeedbackResponse,
  CommitmentHistoryResponse,
  CommitmentSummaryResponse,
  AvailableCommitmentsResponse,
  AvailableCommitmentItem,
} from '@/types/commitment';
import { PlayerBusinessesResponse } from '@/types/business';
import { StockMarketItem, StockMarketSnapshotResponse, StockTradeExecutionResponse } from '@/types/stocks';
import {
  BusinessMarginsResponse,
  CommutePressureResponse,
  EconomyPresentationSummaryResponse,
  FutureOpportunityTeasersResponse,
  MarketOverviewResponse,
  PlayerEconomyExplainerResponse,
  PriceTrendsResponse,
} from '@/types/economyPresentation';
import { ProgressionSummaryResponse } from '@/types/progression';
import {
  OnboardingDashboardConfigResponse,
  OnboardingGuidanceResponse,
  OnboardingStateResponse,
  OnboardingUnlockScheduleResponse,
} from '@/types/onboarding';
import {
  BusinessPlanResponse,
  DebtVsGrowthResponse,
  FuturePreparationResponse,
  HousingTradeoffResponse,
  RecoveryVsPushResponse,
  ShortHorizonPlansResponse,
  StrategyRecommendationResponse,
} from '@/types/strategicPlanning';
import {
  LocalPressureSummaryResponse,
  PlayerPatternSummaryResponse,
  RegionMemorySummaryResponse,
  WorldNarrativeResponse,
  WorldPatternsResponse,
} from '@/types/worldMemory';
import { SecondaryGroupKey, UI_LAYOUT_CONFIG } from '@/lib/ui_layout_config';
import {
  buildBusinessSummary,
  buildEconomySummary,
  buildPlanningSummary,
  buildWorldSummary,
} from '@/lib/uiSummaryFormatters';
import {
  buildBasketPressureSignals,
  buildBottleneckOpportunityHints,
  buildDailyBriefImpactBullets,
  buildJobChangeHints,
} from '@/lib/worldEconomySignalMapper';
import { theme } from '@/design/theme';
import { useBreakpoint } from '@/hooks/useBreakpoint';

type SectionStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'error';

interface SectionState<T> {
  status: SectionStatus;
  data: T | null;
  error: string | null;
}

type FeedbackTone = 'success' | 'error' | 'info';

interface FeedbackState {
  tone: FeedbackTone;
  message: string;
}

type MobilePrimarySectionKey = 'action_hub' | 'business_operations' | 'stock_market';

function initialSection<T>(): SectionState<T> {
  return {
    status: 'idle',
    data: null,
    error: null,
  };
}

function normalizeError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

function recordSettledFailures(action: string, results: PromiseSettledResult<unknown>[]) {
  const failures = results.filter((result): result is PromiseRejectedResult => result.status === 'rejected');
  if (failures.length === 0) return;
  recordWarning('gameplay', 'One or more gameplay refresh requests failed.', {
    action,
    context: {
      failureCount: failures.length,
      messages: failures.slice(0, 3).map((result) => normalizeError(result.reason)),
    },
  });
}

function deriveSuggestedTimeUnits(snapshot: PlayerDashboardResponse | null): number {
  if (!snapshot) return 10;
  const debug = snapshot.debug_meta || {};
  const directUnits = Number(debug.daily_time_units ?? debug.time_units ?? debug.hours_available_units);
  if (Number.isFinite(directUnits)) return directUnits;
  const hoursAvailable = Number(debug.hours_available ?? debug.remaining_hours);
  if (Number.isFinite(hoursAvailable)) {
    if (hoursAvailable >= 20) return 10;
    return Math.max(6, Math.min(16, Math.round(hoursAvailable / 2)));
  }
  return 10;
}

function feedbackToneStyle(tone: FeedbackTone): { borderColor: string; backgroundColor: string; color: string } {
  if (tone === 'success') {
    return { borderColor: '#86efac', backgroundColor: '#f0fdf4', color: '#166534' };
  }
  if (tone === 'error') {
    return { borderColor: '#fecaca', backgroundColor: '#fef2f2', color: '#b91c1c' };
  }
  return { borderColor: '#bfdbfe', backgroundColor: '#eff6ff', color: '#1e40af' };
}

function feedbackToneLabel(tone: FeedbackTone): string {
  if (tone === 'success') return 'Action Update';
  if (tone === 'error') return 'Needs Attention';
  return 'Gameplay Note';
}

function formatSignedValue(value: number, digits = 0): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}`;
}

function buildActionFeedbackMessage(
  result: ActionExecutionResponse,
  supplementalMessage?: string | null,
): string {
  const parts: string[] = [];
  const primary = String(result.message || '').trim();
  const summary = String(result.result_summary || '').trim();

  if (primary) parts.push(primary);
  if (summary && summary !== primary) parts.push(summary);
  if (typeof result.cash_delta_xgp === 'number' && Number.isFinite(result.cash_delta_xgp) && result.cash_delta_xgp !== 0) {
    parts.push(`Cash ${formatSignedValue(result.cash_delta_xgp, 2)} xgp.`);
  }
  if (typeof result.stress_delta === 'number' && Number.isFinite(result.stress_delta) && result.stress_delta !== 0) {
    parts.push(`Stress ${formatSignedValue(result.stress_delta)}.`);
  }
  if (typeof result.health_delta === 'number' && Number.isFinite(result.health_delta) && result.health_delta !== 0) {
    parts.push(`Health ${formatSignedValue(result.health_delta)}.`);
  }
  if (supplementalMessage) parts.push(supplementalMessage);

  return parts.join(' ');
}

function buildEndDayFeedbackMessage(result: EndDayResponse): string {
  const parts: string[] = [];
  const headline = String(result.summary_headline || result.message || 'Day settled successfully.').trim();

  if (headline) parts.push(headline);
  if (typeof result.ending_cash_xgp === 'number' && Number.isFinite(result.ending_cash_xgp)) {
    parts.push(`Ending cash ${result.ending_cash_xgp.toFixed(2)} xgp.`);
  }
  if (typeof result.stress_change === 'number' && Number.isFinite(result.stress_change) && result.stress_change !== 0) {
    parts.push(`Stress ${formatSignedValue(result.stress_change)}.`);
  }
  if (typeof result.health_change === 'number' && Number.isFinite(result.health_change) && result.health_change !== 0) {
    parts.push(`Health ${formatSignedValue(result.health_change)}.`);
  }

  return parts.join(' ');
}

function buildPendingActionFeedback(action: DailyActionItem): string {
  const canonicalKey = canonicalThumbActionKey(action.action_key);
  if (canonicalKey === 'work_shift') return 'Working now. Income update is on the way.';
  if (canonicalKey === 'operate_business') return 'Running your business. Today\'s cash flow is updating.';
  if (canonicalKey === 'recovery_action') return 'Recovery started. Stress and health are updating.';
  return `${action.title} in progress. Applying today\'s result now.`;
}

function buildPendingEndDayFeedback(dayNumber: number | null | undefined): string {
  return dayNumber != null
    ? `Closing Day ${dayNumber}. Earnings, expenses, and new warnings are being settled.`
    : 'Closing the day. Earnings, expenses, and new warnings are being settled.';
}

function formatPercentSigned(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
}

function buildPendingStockTradeFeedback(stock: StockMarketItem | null | undefined, side: 'buy' | 'sell', shares: number): string {
  const actionWord = side === 'buy' ? 'Buying' : 'Selling';
  const stockLabel = stock?.stock_name || stock?.stock_id || 'stock';
  const trend = stock && Number.isFinite(stock.daily_change_pct)
    ? ` Stock ${formatPercentSigned(stock.daily_change_pct)} today.`
    : '';
  return `${actionWord} ${shares} share${shares === 1 ? '' : 's'} of ${stockLabel}.${trend}`;
}

function buildStockTradeFeedbackMessage(
  result: StockTradeExecutionResponse,
  side: 'buy' | 'sell',
  stock?: StockMarketItem | null,
): string {
  const actionWord = side === 'buy' ? 'Bought' : 'Sold';
  const stockLabel = stock?.stock_name || result.stock_id;
  const parts = [`${actionWord} ${result.shares} share${result.shares === 1 ? '' : 's'} of ${stockLabel}.`];

  if (stock && Number.isFinite(stock.daily_change_pct)) {
    parts.push(`Stock ${formatPercentSigned(stock.daily_change_pct)} today.`);
  }

  parts.push(`Price ${result.execution_price.toFixed(2)} xgp.`);
  parts.push(`Fee ${result.fee_amount.toFixed(2)} xgp.`);
  parts.push(`Cash ${result.remaining_cash_xgp.toFixed(2)} xgp.`);
  return parts.join(' ');
}

function summarizeStatusLabel(states: SectionState<unknown>[]): string | null {
  const statuses = states.map((state) => state.status);
  if (statuses.some((status) => status === 'error')) return 'partial';
  if (statuses.some((status) => status === 'loading' || status === 'idle')) return 'updating';
  if (statuses.every((status) => status === 'empty')) return 'empty';
  if (statuses.some((status) => status === 'ready')) return 'ready';
  return null;
}

function canonicalThumbActionKey(actionKey: GameplayActionKey): string {
  const raw = String(actionKey || '').toLowerCase().trim();
  if (!raw) return '';
  if (raw === 'switch_job' || (raw.includes('switch') && raw.includes('job'))) return 'switch_job';
  if (raw === 'recovery_action' || raw.includes('recovery')) return 'recovery_action';
  if (raw.includes('rest') || raw.includes('recover') || raw.includes('sleep')) return 'recovery_action';
  if (raw === 'work_shift' || raw.includes('work') || raw.includes('shift')) return 'work_shift';
  return raw;
}

function onboardingDockActionId(stepKey: string | null | undefined): string | null {
  const key = String(stepKey || '').trim();
  if (key === 'first_income_action') return 'work';
  if (key === 'end_first_day') return 'advance_day';
  return null;
}

function guidanceActionToDockActionId(
  actionKey: string | null | undefined,
  hasBusinessOption: boolean,
): string | null {
  const key = String(actionKey || '').trim().toLowerCase();
  if (!key) return null;
  if (key === 'work_shift' || key === 'side_income') return 'work';
  if (key === 'recovery_action' || key === 'rest') return 'recovery';
  if (key === 'end_day' || key === 'start_next_day') return 'advance_day';
  if (key === 'change_region') return 'jobs';
  if (key === 'explore_opportunity') return hasBusinessOption ? 'business' : 'stocks';
  return null;
}

function deriveProgressionFeedback(
  before: ProgressionSummaryResponse | null,
  after: ProgressionSummaryResponse | null,
): string | null {
  if (!before || !after) return null;

  const beforeCompletedGoals = new Set(
    before.daily_goals.filter((g) => g.status === 'completed').map((g) => g.goal_key),
  );
  const newlyCompletedGoal = after.daily_goals.find(
    (g) => g.status === 'completed' && !beforeCompletedGoals.has(g.goal_key),
  );
  if (newlyCompletedGoal) {
    return `Daily goal completed: ${newlyCompletedGoal.title}`;
  }

  const beforeMissionProgress = new Map(before.weekly_missions.map((m) => [m.mission_key, m.progress_current]));
  const advancedMission = after.weekly_missions.find(
    (m) => Number(m.progress_current) > Number(beforeMissionProgress.get(m.mission_key) || 0),
  );
  if (advancedMission) {
    return `Weekly mission progress: ${advancedMission.title} (${advancedMission.progress_current}/${advancedMission.progress_target})`;
  }

  const beforeStreak = new Map(before.streaks.map((s) => [s.streak_key, Number(s.current_count) || 0]));
  const increasedStreak = after.streaks.find(
    (s) => Number(s.current_count) > Number(beforeStreak.get(s.streak_key) || 0),
  );
  if (increasedStreak) {
    return `Streak increased: ${increasedStreak.title} is now ${increasedStreak.current_count}.`;
  }

  return null;
}

function deriveCommitmentFeedback(
  before: CommitmentSummaryResponse | null,
  after: CommitmentSummaryResponse | null,
): FeedbackState | null {
  if (!after) return null;
  const previous = before?.active_commitment;
  const next = after.active_commitment;
  const hadActive = Boolean(previous && previous.status === 'active' && previous.commitment_key);
  const hasActive = Boolean(next && next.status === 'active' && next.commitment_key);

  if (!hadActive && hasActive) {
    return {
      tone: 'success',
      message: `Commitment activated: ${next.title}`,
    };
  }

  if (hadActive && !hasActive) {
    const reward = next.reward_summary ? ` ${next.reward_summary}` : '';
    return {
      tone: 'info',
      message: `Commitment closed.${reward}`.trim(),
    };
  }

  if (!hadActive || !hasActive) return null;

  const adherenceDelta = Number(next.adherence_score || 0) - Number(previous?.adherence_score || 0);
  const momentumDelta = Number(next.momentum_score || 0) - Number(previous?.momentum_score || 0);
  if (adherenceDelta >= 1 || momentumDelta >= 1) {
    return {
      tone: 'success',
      message: `Commitment momentum +${Math.max(1, Math.round(momentumDelta || adherenceDelta))}: ${next.title}`,
    };
  }

  const drift = String(next.drift_level || '').toLowerCase();
  if (drift === 'moderate' || drift === 'high') {
    return {
      tone: 'error',
      message: `Warning: ${next.title} is drifting off-plan.`,
    };
  }

  return null;
}

function describeSignalItem(item: DashboardSignalItem | null | undefined, fallback: string): string {
  if (!item) return fallback;
  const title = String(item.title || '').trim();
  const description = String(item.description || '').trim();
  return title || description || fallback;
}

function toDashboardSignalItems(
  items: string[] | null | undefined,
  prefix: string,
  category: string,
  severity: DashboardSignalItem['severity'],
): DashboardSignalItem[] {
  const normalized: DashboardSignalItem[] = [];
  (items || []).forEach((item, index) => {
    const text = String(item || '').trim();
    if (!text) return;
    normalized.push({
      key: `${prefix}_${index}`,
      title: text,
      description: text,
      category,
      severity,
    });
  });
  return normalized;
}

function buildBundleBrief(summary: EconomyPresentationSummaryResponse): string {
  const lines = summary.daily_brief?.summary_lines?.filter(Boolean) || [];
  if (lines.length > 0) {
    return lines.slice(0, 3).join(' ');
  }

  if (summary.supply_chain_summary?.short_summary) {
    return summary.supply_chain_summary.short_summary;
  }

  return summary.market_overview?.short_explainer || 'No backend economy brief available.';
}

function overlayDashboardWithEconomySummary(
  dashboard: PlayerDashboardResponse,
  summary: EconomyPresentationSummaryResponse | null,
): PlayerDashboardResponse {
  if (!summary) return dashboard;

  const headline = summary.daily_brief?.headline || dashboard.headline;
  const dailyBrief = buildBundleBrief(summary);

  let topOpportunities = toDashboardSignalItems(
    summary.player_opportunities,
    'backend_opportunity',
    'economy',
    'medium',
  );
  // If the backend provided no player_opportunities, derive from supply-chain bottlenecks and job changes.
  if (topOpportunities.length === 0 && summary.daily_brief) {
    const derived = [
      ...buildBottleneckOpportunityHints(summary.daily_brief.top_bottlenecks || []),
      ...buildJobChangeHints(summary.daily_brief.top_job_changes || []),
    ].slice(0, 3);
    topOpportunities = derived.map((item, index) => ({
      key: `derived_opportunity_${index}`,
      title: item.title,
      description: item.description,
      category: 'economy',
      severity: 'medium' as DashboardSignalItem['severity'],
    }));
  }

  let topRisks = toDashboardSignalItems(
    summary.player_warnings,
    'backend_warning',
    'economy',
    'medium',
  );
  // If the backend provided no player_warnings, derive from basket price movers.
  if (topRisks.length === 0 && summary.daily_brief) {
    const derived = buildBasketPressureSignals(summary.daily_brief.top_basket_movers || []);
    topRisks = derived.map((item, index) => ({
      key: `derived_risk_${index}`,
      title: item.title,
      description: item.description,
      category: 'economy',
      severity: 'medium' as DashboardSignalItem['severity'],
    }));
  }

  return {
    ...dashboard,
    headline,
    daily_brief: dailyBrief,
    top_opportunities: topOpportunities.length > 0 ? topOpportunities : dashboard.top_opportunities,
    top_risks: topRisks.length > 0 ? topRisks : dashboard.top_risks,
  };
}

const SECONDARY_GROUP_SECTION_KEYS = new Set<string>([
  'market_overview',
  'price_trends',
  'business_margins',
  'business_plan',
  'commute_pressure',
  'housing_tradeoff',
  'economy_explainer',
  'future_teasers',
  'future_preparation',
  'world_memory',
  'commitment',
  'strategic_planning',
  'debt_growth',
  'recovery_vs_push',
  'progression',
  'weekly_summary',
  'weekly_missions',
]);

export default function GameDashboardPage({
  playerId,
  onExecuteActionOverride,
}: {
  playerId: string;
  onExecuteActionOverride?: (
    actionKey: GameplayActionKey,
    actionParameters?: Record<string, unknown>,
  ) => Promise<ActionExecutionResponse | void> | ActionExecutionResponse | void;
}) {
  const [dashboardState, setDashboardState] = useState<SectionState<PlayerDashboardResponse>>(initialSection);
  const [actionState, setActionState] = useState<SectionState<DailyActionHubResponse>>(initialSection);
  const [notificationsState, setNotificationsState] = useState<SectionState<PlayerNotificationResponse>>(initialSection);
  const [eodState, setEodState] = useState<SectionState<EndOfDaySummaryResponse>>(initialSection);
  const [weeklyState, setWeeklyState] = useState<SectionState<WeeklyPlayerSummaryResponse>>(initialSection);
  const [progressionState, setProgressionState] = useState<SectionState<ProgressionSummaryResponse>>(initialSection);
  const [economyPresentationSummaryState, setEconomyPresentationSummaryState] = useState<SectionState<EconomyPresentationSummaryResponse>>(initialSection);
  const [marketOverviewState, setMarketOverviewState] = useState<SectionState<MarketOverviewResponse>>(initialSection);
  const [priceTrendsState, setPriceTrendsState] = useState<SectionState<PriceTrendsResponse>>(initialSection);
  const [businessMarginsState, setBusinessMarginsState] = useState<SectionState<BusinessMarginsResponse>>(initialSection);
  const [commutePressureState, setCommutePressureState] = useState<SectionState<CommutePressureResponse>>(initialSection);
  const [economyExplainerState, setEconomyExplainerState] = useState<SectionState<PlayerEconomyExplainerResponse>>(initialSection);
  const [futureTeasersState, setFutureTeasersState] = useState<SectionState<FutureOpportunityTeasersResponse>>(initialSection);
  const [shortHorizonPlansState, setShortHorizonPlansState] = useState<SectionState<ShortHorizonPlansResponse>>(initialSection);
  const [housingTradeoffState, setHousingTradeoffState] = useState<SectionState<HousingTradeoffResponse>>(initialSection);
  const [debtVsGrowthState, setDebtVsGrowthState] = useState<SectionState<DebtVsGrowthResponse>>(initialSection);
  const [businessPlanState, setBusinessPlanState] = useState<SectionState<BusinessPlanResponse>>(initialSection);
  const [playerBusinessesState, setPlayerBusinessesState] = useState<SectionState<PlayerBusinessesResponse>>(initialSection);
  const [stockMarketState, setStockMarketState] = useState<SectionState<StockMarketSnapshotResponse>>(initialSection);
  const [recoveryVsPushState, setRecoveryVsPushState] = useState<SectionState<RecoveryVsPushResponse>>(initialSection);
  const [strategyRecommendationState, setStrategyRecommendationState] = useState<SectionState<StrategyRecommendationResponse>>(initialSection);
  const [futurePreparationState, setFuturePreparationState] = useState<SectionState<FuturePreparationResponse>>(initialSection);
  const [worldPatternsState, setWorldPatternsState] = useState<SectionState<WorldPatternsResponse>>(initialSection);
  const [worldNarrativeState, setWorldNarrativeState] = useState<SectionState<WorldNarrativeResponse>>(initialSection);
  const [worldLocalPressureState, setWorldLocalPressureState] = useState<SectionState<LocalPressureSummaryResponse>>(initialSection);
  const [worldPlayerPatternsState, setWorldPlayerPatternsState] = useState<SectionState<PlayerPatternSummaryResponse>>(initialSection);
  const [worldRegionMemoryState, setWorldRegionMemoryState] = useState<SectionState<RegionMemorySummaryResponse>>(initialSection);
  const [commitmentAvailableState, setCommitmentAvailableState] = useState<SectionState<AvailableCommitmentsResponse>>(initialSection);
  const [commitmentSummaryState, setCommitmentSummaryState] = useState<SectionState<CommitmentSummaryResponse>>(initialSection);
  const [commitmentFeedbackState, setCommitmentFeedbackState] = useState<SectionState<CommitmentFeedbackResponse>>(initialSection);
  const [commitmentHistoryState, setCommitmentHistoryState] = useState<SectionState<CommitmentHistoryResponse>>(initialSection);
  const [commitmentBusy, setCommitmentBusy] = useState(false);
  const [onboardingState, setOnboardingState] = useState<SectionState<OnboardingStateResponse>>(initialSection);
  const [onboardingGuidanceState, setOnboardingGuidanceState] = useState<SectionState<OnboardingGuidanceResponse>>(initialSection);
  const [onboardingConfigState, setOnboardingConfigState] = useState<SectionState<OnboardingDashboardConfigResponse>>(initialSection);
  const [onboardingUnlockState, setOnboardingUnlockState] = useState<SectionState<OnboardingUnlockScheduleResponse>>(initialSection);
  const [onboardingBusy, setOnboardingBusy] = useState(false);

  const [refreshing, setRefreshing] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [feedback, setFeedback] = useState<FeedbackState | null>(null);

  const [selectedAction, setSelectedAction] = useState<DailyActionItem | null>(null);
  const [selectedActionGuard, setSelectedActionGuard] = useState<ActionExecutionGuard | null>(null);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewPayload, setPreviewPayload] = useState<ActionPreviewResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [executingAction, setExecutingAction] = useState(false);
  const [pendingStockTrade, setPendingStockTrade] = useState<{ stockId: string; side: 'buy' | 'sell' } | null>(null);
  const [endingDay, setEndingDay] = useState(false);
  const [lastEndDayResult, setLastEndDayResult] = useState<EndDayResponse | null>(null);

  // Synchronous ref guards prevent double-tap races on day transitions.
  const executeActionGuardRef = useRef(false);
  const stockTradeGuardRef = useRef(false);
  const endDayGuardRef = useRef(false);
  const startingNextDayRef = useRef(false);
  const commitmentGuardRef = useRef(false);
  const onboardingGuardRef = useRef(false);
  const previewRequestIdRef = useRef(0);
  const previewAbortControllerRef = useRef<AbortController | null>(null);
  const selectedActionRef = useRef<DailyActionItem | null>(null);
  selectedActionRef.current = selectedAction;

  // Tracks latest gameplayState so onExecuteAction can read currentJob without a stale closure.
  const gameplayStateRef = useRef<ReturnType<typeof attachGameplayEventState> | null>(null);

  const dailySession = useDailySession(playerId);
  const { isMobile } = useBreakpoint();
  const scrollRef = useRef<ScrollView | null>(null);
  const sectionOffsetsRef = useRef<Record<string, number>>({});
  const [activeShellTab, setActiveShellTab] = useState<'home' | 'actions' | 'progress' | 'insights' | 'profile'>('home');
  // action_hub defaults to expanded — it is the primary action surface and must be
  // immediately visible without extra taps. business_operations and stock_market
  // default to collapsed to keep the portrait loop compact.
  const [expandedPrimarySections, setExpandedPrimarySections] = useState<Record<MobilePrimarySectionKey, boolean>>({
    action_hub: true,
    business_operations: false,
    stock_market: false,
  });
  const [expandedSecondaryGroups, setExpandedSecondaryGroups] = useState<Record<SecondaryGroupKey, boolean>>(() =>
    UI_LAYOUT_CONFIG.secondaryGroups.reduce((acc, group) => ({
      ...acc,
      [group.key]: !group.defaultCollapsed,
    }), {
      economy_overview: false,
      business_insights: false,
      planning_commitment: false,
      progression: false,
      world_memory: false,
    } as Record<SecondaryGroupKey, boolean>),
  );

  const loadDashboard = useCallback(async () => {
    setDashboardState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getPlayerDashboard(playerId);
      setDashboardState({
        status: data ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setDashboardState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadActionHub = useCallback(async () => {
    setActionState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getPlayerActions(playerId);
      const actionCount =
        data.recommended_actions.length + data.available_actions.length + data.blocked_actions.length;
      setActionState({
        status: actionCount > 0 ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setActionState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadNotifications = useCallback(async () => {
    setNotificationsState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getPlayerNotifications(playerId);
      setNotificationsState({
        status: data.notifications.length > 0 ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setNotificationsState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadEndOfDaySummary = useCallback(async () => {
    setEodState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getEndOfDaySummary(playerId);
      setEodState({
        status: data ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setEodState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadWeeklySummary = useCallback(async () => {
    setWeeklyState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getWeeklySummary(playerId);
      setWeeklyState({
        status: data ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setWeeklyState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadProgression = useCallback(async (): Promise<ProgressionSummaryResponse | null> => {
    setProgressionState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getProgressionSummary(playerId);
      const hasContent =
        data.daily_goals.length > 0 || data.weekly_missions.length > 0 || data.streaks.length > 0;
      setProgressionState({
        status: hasContent ? 'ready' : 'empty',
        data,
        error: null,
      });
      return data;
    } catch (error) {
      setProgressionState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
      return null;
    }
  }, [playerId]);

  const loadMarketOverview = useCallback(async () => {
    setMarketOverviewState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getMarketOverview(playerId);
      setMarketOverviewState({
        status: data ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setMarketOverviewState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadPriceTrends = useCallback(async () => {
    setPriceTrendsState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getPriceTrends(playerId);
      setPriceTrendsState({
        status: data.items.length > 0 ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setPriceTrendsState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadBusinessMargins = useCallback(async () => {
    setBusinessMarginsState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getBusinessMargins(playerId);
      setBusinessMarginsState({
        status: data.items.length > 0 ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setBusinessMarginsState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadCommutePressure = useCallback(async () => {
    setCommutePressureState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getCommutePressure(playerId);
      setCommutePressureState({
        status: data ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setCommutePressureState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadEconomyExplainer = useCallback(async () => {
    setEconomyExplainerState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getEconomyExplainer(playerId);
      setEconomyExplainerState({
        status: data ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setEconomyExplainerState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadFutureTeasers = useCallback(async () => {
    setFutureTeasersState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getFutureTeasers(playerId);
      setFutureTeasersState({
        status: data.teasers.length > 0 ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setFutureTeasersState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const applyEconomyPresentationBundle = useCallback((data: EconomyPresentationSummaryResponse) => {
    setEconomyPresentationSummaryState({
      status: 'ready',
      data,
      error: null,
    });
    setMarketOverviewState({
      status: data.market_overview ? 'ready' : 'empty',
      data: data.market_overview,
      error: null,
    });
    setPriceTrendsState({
      status: data.price_trends.items.length > 0 ? 'ready' : 'empty',
      data: data.price_trends,
      error: null,
    });
    setBusinessMarginsState({
      status: data.business_margins.items.length > 0 ? 'ready' : 'empty',
      data: data.business_margins,
      error: null,
    });
    setCommutePressureState({
      status: data.commute_pressure ? 'ready' : 'empty',
      data: data.commute_pressure,
      error: null,
    });
    setEconomyExplainerState({
      status: data.explainer ? 'ready' : 'empty',
      data: data.explainer,
      error: null,
    });
    setFutureTeasersState({
      status: data.future_teasers.teasers.length > 0 ? 'ready' : 'empty',
      data: data.future_teasers,
      error: null,
    });
  }, []);

  const loadEconomyPresentationBundle = useCallback(async () => {
    setEconomyPresentationSummaryState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getEconomyPresentationSummary(playerId);
      applyEconomyPresentationBundle(data);
      return data;
    } catch (error) {
      setEconomyPresentationSummaryState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
      throw error;
    }
  }, [applyEconomyPresentationBundle, playerId]);

  const loadEconomyOverviewWithFallback = useCallback(async () => {
    try {
      await loadEconomyPresentationBundle();
    } catch (error) {
      recordWarning('gameplay', 'Economy summary bundle failed. Falling back to legacy economy endpoints.', {
        action: 'load_economy_bundle_fallback',
        error,
        context: { playerId },
      });
      await Promise.allSettled([
        loadMarketOverview(),
        loadPriceTrends(),
        loadBusinessMargins(),
        loadCommutePressure(),
        loadEconomyExplainer(),
        loadFutureTeasers(),
      ]);
      setEconomyPresentationSummaryState((prev) => (
        prev.data
          ? { ...prev, status: 'ready', error: null }
          : { status: 'empty', data: null, error: null }
      ));
    }
  }, [
    loadBusinessMargins,
    loadCommutePressure,
    loadEconomyExplainer,
    loadEconomyPresentationBundle,
    loadFutureTeasers,
    loadMarketOverview,
    loadPriceTrends,
    playerId,
  ]);

  const loadShortHorizonPlans = useCallback(async () => {
    setShortHorizonPlansState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getShortHorizonPlans(playerId);
      setShortHorizonPlansState({
        status: data.options.length > 0 ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setShortHorizonPlansState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadHousingTradeoff = useCallback(async () => {
    setHousingTradeoffState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getHousingTradeoff(playerId);
      setHousingTradeoffState({
        status: data ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setHousingTradeoffState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadDebtVsGrowth = useCallback(async () => {
    setDebtVsGrowthState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getDebtVsGrowth(playerId);
      setDebtVsGrowthState({
        status: data.items.length > 0 ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setDebtVsGrowthState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadBusinessPlan = useCallback(async () => {
    setBusinessPlanState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getBusinessPlan(playerId);
      setBusinessPlanState({
        status: data.items.length > 0 ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setBusinessPlanState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadPlayerBusinesses = useCallback(async () => {
    setPlayerBusinessesState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getPlayerBusinesses(playerId);
      setPlayerBusinessesState({
        status: data.businesses.some((b) => b.is_active) ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setPlayerBusinessesState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadStockMarket = useCallback(async () => {
    setStockMarketState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getStockMarketSnapshot(playerId);
      setStockMarketState({
        status: data.stocks.length > 0 ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setStockMarketState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadRecoveryVsPush = useCallback(async () => {
    setRecoveryVsPushState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getRecoveryVsPush(playerId);
      setRecoveryVsPushState({
        status: data ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setRecoveryVsPushState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadStrategyRecommendation = useCallback(async () => {
    setStrategyRecommendationState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getStrategyRecommendation(playerId);
      setStrategyRecommendationState({
        status: data ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setStrategyRecommendationState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadFuturePreparation = useCallback(async () => {
    setFuturePreparationState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getFuturePreparation(playerId);
      setFuturePreparationState({
        status: data.items.length > 0 ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setFuturePreparationState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadWorldPatterns = useCallback(async () => {
    setWorldPatternsState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getWorldMemoryPatterns(playerId);
      setWorldPatternsState({
        status: data.items.length > 0 ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setWorldPatternsState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadWorldNarrative = useCallback(async () => {
    setWorldNarrativeState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getWorldNarrative(playerId);
      setWorldNarrativeState({
        status: data ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setWorldNarrativeState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadWorldLocalPressure = useCallback(async () => {
    setWorldLocalPressureState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getLocalPressure(playerId);
      setWorldLocalPressureState({
        status: data ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setWorldLocalPressureState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadWorldPlayerPatterns = useCallback(async () => {
    setWorldPlayerPatternsState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getPlayerPatterns(playerId);
      const hasItems =
        Boolean(data.dominant_player_pattern) ||
        data.supporting_patterns.length > 0 ||
        data.risk_patterns.length > 0 ||
        data.improving_patterns.length > 0;
      setWorldPlayerPatternsState({
        status: hasItems ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setWorldPlayerPatternsState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadWorldRegionMemory = useCallback(async () => {
    setWorldRegionMemoryState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getRegionMemory(playerId);
      setWorldRegionMemoryState({
        status: data ? 'ready' : 'empty',
        data,
        error: null,
      });
    } catch (error) {
      setWorldRegionMemoryState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
    }
  }, [playerId]);

  const loadCommitmentAvailable = useCallback(async (): Promise<AvailableCommitmentsResponse | null> => {
    setCommitmentAvailableState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getAvailableCommitments(playerId);
      setCommitmentAvailableState({
        status: data.items.length > 0 ? 'ready' : 'empty',
        data,
        error: null,
      });
      return data;
    } catch (error) {
      setCommitmentAvailableState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
      return null;
    }
  }, [playerId]);

  const loadCommitmentSummary = useCallback(async (): Promise<CommitmentSummaryResponse | null> => {
    setCommitmentSummaryState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getCommitmentSummary(playerId);
      const hasActive = data.active_commitment.status === 'active' && Boolean(data.active_commitment.commitment_key);
      setCommitmentSummaryState({
        status: hasActive ? 'ready' : 'empty',
        data,
        error: null,
      });
      return data;
    } catch (error) {
      setCommitmentSummaryState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
      return null;
    }
  }, [playerId]);

  const loadCommitmentFeedback = useCallback(async (): Promise<CommitmentFeedbackResponse | null> => {
    setCommitmentFeedbackState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getCommitmentFeedback(playerId);
      setCommitmentFeedbackState({
        status: data.items.length > 0 ? 'ready' : 'empty',
        data,
        error: null,
      });
      return data;
    } catch (error) {
      setCommitmentFeedbackState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
      return null;
    }
  }, [playerId]);

  const loadCommitmentHistory = useCallback(async (): Promise<CommitmentHistoryResponse | null> => {
    setCommitmentHistoryState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getCommitmentHistory(playerId, { limit: 12 });
      setCommitmentHistoryState({
        status: data.entries.length > 0 ? 'ready' : 'empty',
        data,
        error: null,
      });
      return data;
    } catch (error) {
      setCommitmentHistoryState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
      return null;
    }
  }, [playerId]);

  const loadOnboardingState = useCallback(async (): Promise<OnboardingStateResponse | null> => {
    setOnboardingState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getOnboardingState(playerId);
      setOnboardingState({
        status: data ? 'ready' : 'empty',
        data,
        error: null,
      });
      return data;
    } catch (error) {
      setOnboardingState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
      return null;
    }
  }, [playerId]);

  const loadOnboardingGuidance = useCallback(async (): Promise<OnboardingGuidanceResponse | null> => {
    setOnboardingGuidanceState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getOnboardingGuidance(playerId);
      setOnboardingGuidanceState({
        status: data ? 'ready' : 'empty',
        data,
        error: null,
      });
      return data;
    } catch (error) {
      setOnboardingGuidanceState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
      return null;
    }
  }, [playerId]);

  const loadOnboardingConfig = useCallback(async (): Promise<OnboardingDashboardConfigResponse | null> => {
    setOnboardingConfigState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getOnboardingDashboardConfig(playerId);
      setOnboardingConfigState({
        status: data ? 'ready' : 'empty',
        data,
        error: null,
      });
      return data;
    } catch (error) {
      setOnboardingConfigState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
      return null;
    }
  }, [playerId]);

  const loadOnboardingUnlockSchedule = useCallback(async (): Promise<OnboardingUnlockScheduleResponse | null> => {
    setOnboardingUnlockState((prev) => ({ ...prev, status: 'loading', error: null }));
    try {
      const data = await getOnboardingUnlockSchedule(playerId);
      setOnboardingUnlockState({
        status: data ? 'ready' : 'empty',
        data,
        error: null,
      });
      return data;
    } catch (error) {
      setOnboardingUnlockState({
        status: 'error',
        data: null,
        error: normalizeError(error),
      });
      return null;
    }
  }, [playerId]);

  const loadOnboardingBundle = useCallback(async () => {
    const [state, guidance, config, unlock] = await Promise.all([
      loadOnboardingState(),
      loadOnboardingGuidance(),
      loadOnboardingConfig(),
      loadOnboardingUnlockSchedule(),
    ]);
    return { state, guidance, config, unlock };
  }, [
    loadOnboardingConfig,
    loadOnboardingGuidance,
    loadOnboardingState,
    loadOnboardingUnlockSchedule,
  ]);

  const applyOnboardingActionResult = useCallback((payload: {
    state: OnboardingStateResponse;
    guidance: OnboardingGuidanceResponse;
    dashboard_config: OnboardingDashboardConfigResponse;
    unlock_schedule: OnboardingUnlockScheduleResponse;
  }) => {
    setOnboardingState({ status: 'ready', data: payload.state, error: null });
    setOnboardingGuidanceState({ status: 'ready', data: payload.guidance, error: null });
    setOnboardingConfigState({ status: 'ready', data: payload.dashboard_config, error: null });
    setOnboardingUnlockState({ status: 'ready', data: payload.unlock_schedule, error: null });
  }, []);

  const hasOnboardingBundle = onboardingState.status === 'ready'
    && onboardingGuidanceState.status === 'ready'
    && onboardingConfigState.status === 'ready'
    && onboardingUnlockState.status === 'ready';

  const onboardingStatus = String(
    hasOnboardingBundle
      ? onboardingState.data?.onboarding_status || onboardingConfigState.data?.onboarding_status || 'not_started'
      : 'completed',
  ).toLowerCase();
  const onboardingActive = onboardingStatus === 'not_started' || onboardingStatus === 'in_progress';
  const guidedExperienceActive = hasOnboardingBundle
    ? Boolean(
      onboardingActive
        || onboardingGuidanceState.data?.guided_experience_active
        || onboardingConfigState.data?.guided_experience_active
        || onboardingState.data?.guided_experience_active,
    )
    : false;
  const visibleSectionSet = useMemo(
    () => new Set((onboardingConfigState.data?.visible_sections || []).map((entry) => String(entry))),
    [onboardingConfigState.data?.visible_sections],
  );
  const blockedActionReasonByKey = useMemo(() => {
    const mapping = new Map<string, string>();
    (onboardingConfigState.data?.blocked_actions_for_onboarding || []).forEach((entry) => {
      if (entry?.action_key) {
        mapping.set(String(entry.action_key), String(entry.reason || 'Locked during onboarding.'));
      }
    });
    return mapping;
  }, [onboardingConfigState.data?.blocked_actions_for_onboarding]);
  const allowedActionsSet = useMemo(
    () => new Set((onboardingConfigState.data?.allowed_actions || []).map((entry) => String(entry))),
    [onboardingConfigState.data?.allowed_actions],
  );

  const isSectionAllowedByOnboarding = useCallback((sectionKey: string): boolean => {
    if (!guidedExperienceActive) return true;
    if (visibleSectionSet.size === 0) return true;
    return visibleSectionSet.has(sectionKey);
  }, [guidedExperienceActive, visibleSectionSet]);

  const isSectionVisible = useCallback((sectionKey: string): boolean => {
    if (!isSectionAllowedByOnboarding(sectionKey)) return false;
    if (SECONDARY_GROUP_SECTION_KEYS.has(sectionKey)) return false;
    if (UI_LAYOUT_CONFIG.hideByDefault.includes(sectionKey)) return false;
    return true;
  }, [isSectionAllowedByOnboarding]);

  const isOnboardingActionAllowed = useCallback((actionKey: string | null | undefined): boolean => {
    if (!guidedExperienceActive) return true;
    if (!actionKey) return true;
    if (allowedActionsSet.size === 0) return true;
    return allowedActionsSet.has(String(actionKey));
  }, [allowedActionsSet, guidedExperienceActive]);

  const onboardingActionBlockReason = useCallback((actionKey: string | null | undefined): string => {
    const key = String(actionKey || '');
    if (!key) return 'Action unavailable during onboarding.';
    return blockedActionReasonByKey.get(key) || 'This action unlocks later in onboarding.';
  }, [blockedActionReasonByKey]);

  const loadAll = useCallback(async () => {
    setRefreshing(true);
    const results = await Promise.allSettled([
      loadOnboardingBundle(),
      loadDashboard(),
      loadActionHub(),
      loadNotifications(),
      loadEndOfDaySummary(),
      loadWeeklySummary(),
      loadProgression(),
      loadEconomyOverviewWithFallback(),
      loadShortHorizonPlans(),
      loadHousingTradeoff(),
      loadDebtVsGrowth(),
      loadBusinessPlan(),
      loadPlayerBusinesses(),
      loadStockMarket(),
      loadRecoveryVsPush(),
      loadStrategyRecommendation(),
      loadFuturePreparation(),
      loadWorldPatterns(),
      loadWorldNarrative(),
      loadWorldLocalPressure(),
      loadWorldPlayerPatterns(),
      loadWorldRegionMemory(),
      loadCommitmentAvailable(),
      loadCommitmentSummary(),
      loadCommitmentFeedback(),
      loadCommitmentHistory(),
    ]);
    recordSettledFailures('load_all', results);
    setRefreshing(false);
  }, [
    loadActionHub,
    loadOnboardingBundle,
    loadBusinessPlan,
    loadPlayerBusinesses,
    loadStockMarket,
    loadDashboard,
    loadDebtVsGrowth,
    loadEconomyOverviewWithFallback,
    loadEndOfDaySummary,
    loadFuturePreparation,
    loadHousingTradeoff,
    loadNotifications,
    loadProgression,
    loadRecoveryVsPush,
    loadShortHorizonPlans,
    loadStrategyRecommendation,
    loadWeeklySummary,
    loadWorldPatterns,
    loadWorldNarrative,
    loadWorldLocalPressure,
    loadWorldPlayerPatterns,
    loadWorldRegionMemory,
    loadCommitmentAvailable,
    loadCommitmentSummary,
    loadCommitmentFeedback,
    loadCommitmentHistory,
  ]);

  const refreshAfterAction = useCallback(async (actionKey?: GameplayActionKey): Promise<FeedbackState[]> => {
    const beforeProgression = progressionState.data;
    const beforeCommitment = commitmentSummaryState.data;
    const followUpFeedback: FeedbackState[] = [];
    if (actionKey) {
      try {
        const payload = await advanceOnboarding(playerId, { action_key: String(actionKey) });
        applyOnboardingActionResult(payload);
      } catch (error) {
        recordWarning('gameplay', 'Onboarding progression refresh failed after action.', {
          action: 'refresh_after_action',
          context: {
            actionKey: String(actionKey),
          },
          error,
        });
        // Best-effort onboarding refresh; keep gameplay flow alive.
      }
    }
    if (actionKey) {
      try {
        await refreshCommitment(playerId, { actionKey: String(actionKey) });
      } catch (error) {
        recordWarning('gameplay', 'Commitment refresh failed after action.', {
          action: 'refresh_after_action',
          context: {
            actionKey: String(actionKey),
          },
          error,
        });
        // Commitment refresh is best-effort and should not break action flow.
      }
    }

    const results = await Promise.allSettled([
      loadOnboardingBundle(),
      loadDashboard(),
      loadActionHub(),
      loadNotifications(),
      loadProgression(),
      loadEconomyOverviewWithFallback(),
      loadShortHorizonPlans(),
      loadHousingTradeoff(),
      loadDebtVsGrowth(),
      loadBusinessPlan(),
      loadRecoveryVsPush(),
      loadStrategyRecommendation(),
      loadFuturePreparation(),
      loadWorldPatterns(),
      loadWorldNarrative(),
      loadWorldLocalPressure(),
      loadWorldPlayerPatterns(),
      loadWorldRegionMemory(),
      loadCommitmentAvailable(),
      loadCommitmentSummary(),
      loadCommitmentFeedback(),
      loadCommitmentHistory(),
      loadPlayerBusinesses(),
      loadStockMarket(),
    ]);
    recordSettledFailures('refresh_after_action', results);
    const progressionResult = results[4];
    const commitmentSummaryResult = results[19];

    if (progressionResult.status === 'fulfilled') {
      const message = deriveProgressionFeedback(beforeProgression, progressionResult.value);
      if (message) {
        followUpFeedback.push({ tone: 'success', message });
      }
    }

    if (commitmentSummaryResult.status === 'fulfilled') {
      const commitmentFeedback = deriveCommitmentFeedback(beforeCommitment, commitmentSummaryResult.value);
      if (commitmentFeedback) {
        followUpFeedback.push(commitmentFeedback);
      }
    }
    return followUpFeedback;
  }, [
    applyOnboardingActionResult,
    commitmentSummaryState.data,
    loadOnboardingBundle,
    loadActionHub,
    loadBusinessPlan,
    loadPlayerBusinesses,
    loadStockMarket,
    loadDashboard,
    loadDebtVsGrowth,
    loadEconomyOverviewWithFallback,
    loadFuturePreparation,
    loadHousingTradeoff,
    loadNotifications,
    loadProgression,
    loadRecoveryVsPush,
    loadShortHorizonPlans,
    loadStrategyRecommendation,
    loadWorldPatterns,
    loadWorldNarrative,
    loadWorldLocalPressure,
    loadWorldPlayerPatterns,
    loadWorldRegionMemory,
    loadCommitmentAvailable,
    loadCommitmentSummary,
    loadCommitmentFeedback,
    loadCommitmentHistory,
    playerId,
    progressionState.data,
  ]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const dailyProgression = useDailyProgression(
    playerId,
    dailySession.sessionStatus,
    dailySession.pendingExecution || executingAction || endingDay,
  );

  useEffect(() => {
    if (!dailyProgression.isHydrated) return;
    const suggestedUnits = deriveSuggestedTimeUnits(dashboardState.data);
    dailySession.initializeDay(dailyProgression.currentGameDay, suggestedUnits);
  }, [dailyProgression.currentGameDay, dailyProgression.isHydrated, dailySession, dashboardState.data]);

  const getExecutionGuard = useCallback((action: DailyActionItem): ActionExecutionGuard => {
    const explicit = Number(
      (action.parameters?.time_cost_units as number) ??
      (action.debug_meta?.time_cost_units as number),
    );
    return dailySession.canExecuteAction(action, Number.isFinite(explicit) ? explicit : undefined);
  }, [dailySession]);

  const applySessionBlockers = useCallback(
    (actions: DailyActionItem[]): DailyActionItem[] =>
      actions.map((action) => {
        if (!isOnboardingActionAllowed(action.action_key)) {
          const reason = onboardingActionBlockReason(action.action_key);
          const blockers = [reason, ...(action.blockers || [])];
          return {
            ...action,
            status: 'blocked',
            blocker_text: blockers[0] || action.blocker_text || 'Action unavailable',
            blockers,
            debug_meta: {
              ...(action.debug_meta || {}),
              onboarding_blocker: true,
            },
          };
        }
        const guard = getExecutionGuard(action);
        if (guard.allowed) return action;
        if (action.status === 'blocked') return action;
        const blockers = [...(action.blockers || [])];
        if (guard.reason) blockers.unshift(guard.reason);
        return {
          ...action,
          status: 'blocked',
          blocker_text: blockers[0] || action.blocker_text || 'Action unavailable',
          blockers,
          debug_meta: {
            ...(action.debug_meta || {}),
            local_blocker: true,
            local_time_cost_units: guard.timeCostUnits,
          },
        };
      }),
    [getExecutionGuard, isOnboardingActionAllowed, onboardingActionBlockReason],
  );

  const effectiveActionHub = useMemo(() => {
    if (!actionState.data) return null;
    return {
      ...actionState.data,
      recommended_actions: applySessionBlockers(actionState.data.recommended_actions),
      available_actions: applySessionBlockers(actionState.data.available_actions),
      blocked_actions: applySessionBlockers(actionState.data.blocked_actions),
    };
  }, [actionState.data, applySessionBlockers]);

  const effectiveDashboard = useMemo(() => {
    if (!dashboardState.data) return null;
    return overlayDashboardWithEconomySummary(dashboardState.data, economyPresentationSummaryState.data);
  }, [dashboardState.data, economyPresentationSummaryState.data]);

  const notificationCount = notificationsState.data?.notifications.length || 0;
  const gameplayCoreState = useMemo(() => createGameplayCanonicalState({
    playerId,
    currentDay: dailyProgression.currentGameDay,
    sessionStatus: dailySession.sessionStatus,
    dashboard: effectiveDashboard,
    endOfDay: eodState.data,
  }), [playerId, dailyProgression.currentGameDay, dailySession.sessionStatus, effectiveDashboard, eodState.data]);
  const randomEvent = useRandomEvent(
    playerId,
    dailyProgression.currentGameDay,
    gameplayCoreState.cashOnHand,
    dailyProgression.isHydrated && dailySession.currentDay === dailyProgression.currentGameDay,
  );
  const gameplayState = useMemo(
    () => attachGameplayEventState(gameplayCoreState, randomEvent.activeEvent),
    [gameplayCoreState, randomEvent.activeEvent],
  );
  // Keep ref in sync so callbacks that capture stale closures can still read the latest job state.
  gameplayStateRef.current = gameplayState;
  const economyState = useEconomyState(gameplayState);
  const expenseDebt = useExpenseDebt(gameplayState);
  const jobIncome = useJobIncome(gameplayState);

  const resetPreviewState = useCallback(() => {
    previewRequestIdRef.current += 1;
    previewAbortControllerRef.current?.abort();
    previewAbortControllerRef.current = null;
    setPreviewVisible(false);
    setSelectedAction(null);
    setSelectedActionGuard(null);
    setPreviewPayload(null);
    setPreviewError(null);
    setPreviewLoading(false);
  }, []);

  const closePreview = useCallback(() => {
    if (executingAction) return;
    resetPreviewState();
  }, [executingAction, resetPreviewState]);

  const openPreview = useCallback(
    async (action: DailyActionItem) => {
      if (!isOnboardingActionAllowed(action.action_key)) {
        setFeedback({ tone: 'error', message: onboardingActionBlockReason(action.action_key) });
        return;
      }
      const guard = getExecutionGuard(action);
      if (!guard.allowed) {
        setFeedback({ tone: 'error', message: guard.reason || 'Action blocked right now.' });
        return;
      }
      const requestId = previewRequestIdRef.current + 1;
      previewRequestIdRef.current = requestId;
      setSelectedAction(action);
      setSelectedActionGuard(guard);
      setPreviewVisible(true);
      setPreviewLoading(true);
      setPreviewPayload(null);
      setPreviewError(null);
      previewAbortControllerRef.current?.abort();
      const abortController = new AbortController();
      previewAbortControllerRef.current = abortController;
      try {
        const payload = await previewPlayerAction(playerId, {
          action_key: action.action_key,
          parameters: action.parameters || {},
        }, {
          signal: abortController.signal,
        });
        if (previewRequestIdRef.current !== requestId) return;
        const previewTime = Number(payload.expected_time_impact?.amount);
        if (Number.isFinite(previewTime) && previewTime > 0) {
          setSelectedActionGuard(dailySession.canExecuteAction(action, previewTime));
        }
        setPreviewPayload(payload);
      } catch (error) {
        if (previewRequestIdRef.current !== requestId) return;
        if (error instanceof Error && error.name === 'AbortError') {
          return;
        }
        recordWarning('gameplay', 'Action preview failed.', {
          action: 'open_preview',
          context: {
            actionKey: String(action.action_key),
          },
          error,
        });
        setPreviewError(normalizeError(error));
      } finally {
        if (previewRequestIdRef.current === requestId) {
          if (previewAbortControllerRef.current === abortController) {
            previewAbortControllerRef.current = null;
          }
          setPreviewLoading(false);
        }
      }
    },
    [dailySession, getExecutionGuard, isOnboardingActionAllowed, onboardingActionBlockReason, playerId],
  );

  const onExecuteAction = useCallback(async (
    actionKey: GameplayActionKey,
    actionParams: Record<string, unknown> = {},
  ) => {
    if (!isOnboardingActionAllowed(actionKey)) {
      throw new Error(onboardingActionBlockReason(actionKey));
    }
    const baseAction = selectedAction || {
      action_key: actionKey,
      title: String(actionKey),
      description: 'Executed from gameplay action flow.',
      status: 'available' as const,
      blockers: [],
    };
    const guard = selectedActionGuard || dailySession.canExecuteAction(baseAction);
    if (!guard.allowed) {
      throw new Error(guard.reason || 'Action blocked right now.');
    }

    if (onExecuteActionOverride) {
      const externalResult = await onExecuteActionOverride(actionKey, actionParams);
      if (externalResult && typeof externalResult === 'object' && 'success' in externalResult) {
        return externalResult as ActionExecutionResponse;
      }
      return {
        player_id: playerId,
        action_key: actionKey,
        success: true,
        message: 'Action executed',
        result_summary: 'Action completed.',
        time_cost_units: guard.timeCostUnits,
      };
    }

    const canonicalKey = String(actionKey).toLowerCase().trim();
    const isWorkShift = canonicalKey === 'work_shift' || (canonicalKey.includes('work') && !canonicalKey.includes('switch'));

    // For work shifts: require a current canonical job before hitting the API.
    if (isWorkShift) {
      const currentJob = gameplayStateRef.current?.currentJob ?? null;
      if (!currentJob) {
        throw new Error('You need an active job to perform a work shift. Acquire a job first.');
      }
    }

    // Inject the canonical job for work_shift if the action hub did not supply it.
    const currentJobParam =
      isWorkShift && !actionParams.job_name && !actionParams.job && !actionParams.current_job
        ? { current_job: gameplayStateRef.current?.currentJob ?? null }
        : {};

    return executeAction(playerId, actionKey, {
      ...actionParams,
      ...currentJobParam,
      time_cost_units: guard.timeCostUnits,
    });
  }, [
    dailySession,
    isOnboardingActionAllowed,
    onExecuteActionOverride,
    onboardingActionBlockReason,
    playerId,
    selectedAction,
    selectedActionGuard,
  ]);

  const executeActionItem = useCallback(async (
    action: DailyActionItem,
    options?: { closePreview?: boolean; guard?: ActionExecutionGuard | null },
  ) => {
    if (executeActionGuardRef.current) return;

    const guard = options?.guard || getExecutionGuard(action);
    if (!guard.allowed) {
      setFeedback({ tone: 'error', message: guard.reason || 'Action blocked right now.' });
      return;
    }

    executeActionGuardRef.current = true;
    setExecutingAction(true);
    dailySession.setPendingExecution(true);
    setFeedback({ tone: 'info', message: buildPendingActionFeedback(action) });
    try {
      const result = await onExecuteAction(action.action_key, action.parameters || {});
      const consumed = Math.max(1, Math.round(Number(result.time_cost_units) || guard.timeCostUnits));
      dailySession.consumeTime(consumed);
      dailySession.addActionToHistory({
        action_key: action.action_key,
        title: action.title,
        description: action.description,
        result_summary: result.result_summary,
        time_cost_units: consumed,
        success: true,
        impact_snapshot: {
          cash_delta_xgp: result.cash_delta_xgp,
          stress_delta: result.stress_delta,
          health_delta: result.health_delta,
        },
      });
      if (options?.closePreview) {
        resetPreviewState();
      }
      const followUpFeedback = await refreshAfterAction(action.action_key);
      const supplementalMessage = followUpFeedback.map((item) => item.message).find(Boolean);
      recordInfo('gameplay', 'Gameplay action executed successfully.', {
        action: 'execute_action',
        context: {
          actionKey: String(action.action_key),
          consumedTimeUnits: consumed,
          followUpFeedbackCount: followUpFeedback.length,
          quickExecute: !options?.closePreview,
        },
      });
      setFeedback({
        tone: 'success',
        message: buildActionFeedbackMessage(result, supplementalMessage),
      });
    } catch (error) {
      const message = normalizeError(error);
      dailySession.addActionToHistory({
        action_key: action.action_key,
        title: action.title,
        description: action.description,
        result_summary: '',
        time_cost_units: 0,
        success: false,
        error_message: message,
      });
      recordError('gameplay', 'Gameplay action execution failed.', {
        action: 'execute_action',
        context: {
          actionKey: String(action.action_key),
        },
        error,
      });
      setFeedback({ tone: 'error', message: message || 'Action failed.' });
    } finally {
      executeActionGuardRef.current = false;
      setExecutingAction(false);
      dailySession.setPendingExecution(false);
    }
  }, [dailySession, getExecutionGuard, onExecuteAction, refreshAfterAction, resetPreviewState]);

  const handleExecuteSelectedAction = useCallback(async () => {
    if (!selectedAction) return;
    const action = selectedAction;
    if (selectedActionRef.current?.action_key !== action.action_key) {
      setFeedback({ tone: 'error', message: 'Selected action changed. Review the latest preview before executing.' });
      return;
    }

    const guard = selectedActionGuard || dailySession.canExecuteAction(action);
    if (!guard.allowed) {
      setFeedback({ tone: 'error', message: guard.reason || 'Action blocked right now.' });
      return;
    }
    await executeActionItem(action, { closePreview: true, guard });
  }, [dailySession, executeActionItem, selectedAction, selectedActionGuard]);

  const handleOperateBusiness = useCallback(async () => {
    if (executeActionGuardRef.current) return;
    const guard = dailySession.canExecuteAction({ action_key: 'operate_business' });
    if (!guard.allowed) {
      setFeedback({ tone: 'error', message: guard.reason || 'Cannot operate business right now.' });
      return;
    }
    executeActionGuardRef.current = true;
    setExecutingAction(true);
    dailySession.setPendingExecution(true);
    setFeedback({ tone: 'info', message: 'Running your business. Today\'s result is being calculated.' });
    try {
      const result = await onExecuteAction('operate_business', {});
      const consumed = Math.max(1, Math.round(Number(result.time_cost_units) || guard.timeCostUnits));
      dailySession.consumeTime(consumed);
      dailySession.addActionToHistory({
        action_key: 'operate_business',
        title: 'Run Business',
        description: 'Operated business for the day.',
        result_summary: result.result_summary,
        time_cost_units: consumed,
        success: true,
        impact_snapshot: {
          cash_delta_xgp: result.cash_delta_xgp,
          stress_delta: result.stress_delta,
          health_delta: result.health_delta,
        },
      });
      const followUpFeedback = await refreshAfterAction('operate_business');
      const supplementalMessage = followUpFeedback.map((item) => item.message).find(Boolean);
      recordInfo('gameplay', 'Business operated successfully.', {
        action: 'operate_business',
        context: {},
      });
      setFeedback({
        tone: 'success',
        message: buildActionFeedbackMessage(result, supplementalMessage),
      });
    } catch (error) {
      const message = normalizeError(error);
      dailySession.addActionToHistory({
        action_key: 'operate_business',
        title: 'Run Business',
        description: 'Operated business for the day.',
        result_summary: '',
        time_cost_units: 0,
        success: false,
        error_message: message,
      });
      recordError('gameplay', 'Business operation failed.', {
        action: 'operate_business',
        error,
      });
      setFeedback({ tone: 'error', message: message || 'Business operation failed.' });
    } finally {
      executeActionGuardRef.current = false;
      setExecutingAction(false);
      dailySession.setPendingExecution(false);
    }
  }, [dailySession, onExecuteAction, refreshAfterAction]);

  const handleEndDay = useCallback(async () => {
    // synchronous ref guard fires before any state reads to close the double-tap race window
    if (endDayGuardRef.current) return;
    if (dailySession.sessionStatus !== 'active') {
      setFeedback({ tone: 'info', message: 'Day already ended. Start next day to continue.' });
      return;
    }
    if (dailySession.pendingExecution || executingAction || endingDay) return;

    endDayGuardRef.current = true;
    setEndingDay(true);
    dailySession.setPendingExecution(true);
    setFeedback({ tone: 'info', message: buildPendingEndDayFeedback(dailyProgression.currentGameDay) });
    try {
      const result = await endDay(playerId);
      setLastEndDayResult(result);
      dailySession.endDay();
      await dailyProgression.markDayAdvanced(result.settled_day);
      try {
        const onboardingPayload = await advanceOnboarding(playerId, { action_key: 'end_day' });
        applyOnboardingActionResult(onboardingPayload);
      } catch (error) {
        recordWarning('gameplay', 'Onboarding refresh failed after end day.', {
          action: 'end_day',
          error,
        });
        // End-day onboarding evaluation is best-effort.
      }
      recordInfo('gameplay', 'Day ended successfully.', {
        action: 'end_day',
        context: {
          settledDay: result.settled_day,
        },
      });
      setFeedback({
        tone: 'success',
        message: buildEndDayFeedbackMessage(result),
      });
      const refreshResults = await Promise.allSettled([
        loadOnboardingBundle(),
        loadDashboard(),
        loadActionHub(),
        loadNotifications(),
        loadEndOfDaySummary(),
        loadWeeklySummary(),
        loadProgression(),
        loadEconomyOverviewWithFallback(),
        loadShortHorizonPlans(),
        loadHousingTradeoff(),
        loadDebtVsGrowth(),
        loadBusinessPlan(),
        loadRecoveryVsPush(),
        loadStrategyRecommendation(),
        loadFuturePreparation(),
        loadWorldPatterns(),
        loadWorldNarrative(),
        loadWorldLocalPressure(),
        loadWorldPlayerPatterns(),
        loadWorldRegionMemory(),
        loadCommitmentAvailable(),
        loadCommitmentSummary(),
        loadCommitmentFeedback(),
        loadCommitmentHistory(),
        loadPlayerBusinesses(),
        loadStockMarket(),
      ]);
      recordSettledFailures('end_day_refresh', refreshResults);
    } catch (error) {
      recordError('gameplay', 'Ending day failed.', {
        action: 'end_day',
        error,
      });
      setFeedback({
        tone: 'error',
        message: normalizeError(error),
      });
    } finally {
      endDayGuardRef.current = false;
      setEndingDay(false);
      dailySession.setPendingExecution(false);
    }
  }, [
    dailySession,
    endingDay,
    executingAction,
    loadActionHub,
    applyOnboardingActionResult,
    loadOnboardingBundle,
    loadBusinessPlan,
    loadPlayerBusinesses,
    loadStockMarket,
    loadDashboard,
    loadDebtVsGrowth,
    loadEconomyOverviewWithFallback,
    loadEndOfDaySummary,
    loadFuturePreparation,
    loadHousingTradeoff,
    loadNotifications,
    loadProgression,
    loadRecoveryVsPush,
    loadShortHorizonPlans,
    loadStrategyRecommendation,
    loadWorldPatterns,
    loadWorldNarrative,
    loadWorldLocalPressure,
    loadWorldPlayerPatterns,
    loadWorldRegionMemory,
    loadWeeklySummary,
    loadCommitmentAvailable,
    loadCommitmentSummary,
    loadCommitmentFeedback,
    loadCommitmentHistory,
    dailyProgression,
    playerId,
  ]);

  const handleStartNextDay = useCallback(async () => {
    // Synchronous ref guard prevents double-advance if the button is tapped twice.
    if (startingNextDayRef.current) return;
    startingNextDayRef.current = true;
    try {
      const nextDayNumber = await dailyProgression.markDayStarted();
      dailySession.resetSession({
        totalUnits: deriveSuggestedTimeUnits(dashboardState.data),
        nextDay: nextDayNumber,
      });
      setLastEndDayResult(null);
      recordInfo('gameplay', 'Started next gameplay day.', {
        action: 'start_next_day',
        context: {
          nextDayNumber,
        },
      });
      setFeedback({ tone: 'info', message: 'New day started. Choose your next action.' });
      await loadAll();
    } finally {
      startingNextDayRef.current = false;
    }
  }, [dailyProgression, dailySession, dashboardState.data, loadAll]);

  const refreshCommitmentSections = useCallback(async () => {
    const results = await Promise.allSettled([
      loadCommitmentAvailable(),
      loadCommitmentSummary(),
      loadCommitmentFeedback(),
      loadCommitmentHistory(),
      loadStrategyRecommendation(),
      loadShortHorizonPlans(),
    ]);
    recordSettledFailures('refresh_commitment_sections', results);
  }, [
    loadCommitmentAvailable,
    loadCommitmentSummary,
    loadCommitmentFeedback,
    loadCommitmentHistory,
    loadStrategyRecommendation,
    loadShortHorizonPlans,
  ]);

  const handleActivateCommitment = useCallback(async (
    item: AvailableCommitmentItem,
    options?: { replaceActive?: boolean },
  ) => {
    if (!item?.commitment_key) return;
    if (commitmentGuardRef.current) return;
    commitmentGuardRef.current = true;
    setCommitmentBusy(true);
    try {
      const current = commitmentSummaryState.data?.active_commitment;
      const hasActive = Boolean(current && current.status === 'active' && current.commitment_key);
      const shouldReplace = Boolean(options?.replaceActive || hasActive);
      if (shouldReplace) {
        await replaceCommitment(playerId, {
          commitment_key: item.commitment_key,
          duration_days: item.suggested_duration_days,
          replace_active: true,
        });
      } else {
        await activateCommitment(playerId, {
          commitment_key: item.commitment_key,
          duration_days: item.suggested_duration_days,
          replace_active: false,
        });
      }
      await refreshCommitmentSections();
      setFeedback({
        tone: 'success',
        message: shouldReplace
          ? `Commitment replaced: ${item.title}`
          : `Commitment activated: ${item.title}`,
      });
    } catch (error) {
      setFeedback({ tone: 'error', message: normalizeError(error) });
    } finally {
      commitmentGuardRef.current = false;
      setCommitmentBusy(false);
    }
  }, [commitmentSummaryState.data?.active_commitment, playerId, refreshCommitmentSections]);

  const handleCancelCommitment = useCallback(async () => {
    if (commitmentGuardRef.current) return;
    commitmentGuardRef.current = true;
    setCommitmentBusy(true);
    try {
      await cancelCommitment(playerId);
      await refreshCommitmentSections();
      setFeedback({ tone: 'info', message: 'Commitment cancelled. You can pick a new plan.' });
    } catch (error) {
      setFeedback({ tone: 'error', message: normalizeError(error) });
    } finally {
      commitmentGuardRef.current = false;
      setCommitmentBusy(false);
    }
  }, [playerId, refreshCommitmentSections]);

  const handleAdvanceOnboarding = useCallback(async (actionKey?: string | null) => {
    if (onboardingGuardRef.current) return;
    onboardingGuardRef.current = true;
    setOnboardingBusy(true);
    try {
      const payload = await advanceOnboarding(playerId, {
        action_key: actionKey || undefined,
      });
      applyOnboardingActionResult(payload);
      setFeedback({ tone: 'success', message: payload.message || 'Onboarding updated.' });
    } catch (error) {
      setFeedback({ tone: 'error', message: normalizeError(error) });
    } finally {
      onboardingGuardRef.current = false;
      setOnboardingBusy(false);
    }
  }, [applyOnboardingActionResult, playerId]);

  const handleSkipOnboarding = useCallback(async () => {
    if (onboardingGuardRef.current) return;
    onboardingGuardRef.current = true;
    setOnboardingBusy(true);
    try {
      const payload = await skipOnboarding(playerId);
      applyOnboardingActionResult(payload);
      setFeedback({ tone: 'info', message: payload.message || 'Onboarding skipped.' });
    } catch (error) {
      setFeedback({ tone: 'error', message: normalizeError(error) });
    } finally {
      onboardingGuardRef.current = false;
      setOnboardingBusy(false);
    }
  }, [applyOnboardingActionResult, playerId]);

  const isPrimarySectionExpanded = useCallback((sectionKey: MobilePrimarySectionKey): boolean => {
    if (!isMobile) return true;
    return expandedPrimarySections[sectionKey];
  }, [expandedPrimarySections, isMobile]);

  const togglePrimarySection = useCallback((sectionKey: MobilePrimarySectionKey) => {
    if (!isMobile) return;
    setExpandedPrimarySections((prev) => ({
      ...prev,
      [sectionKey]: !prev[sectionKey],
    }));
  }, [isMobile]);

  const scrollToSection = useCallback((sectionKey: string) => {
    const y = sectionOffsetsRef.current[sectionKey];
    if (typeof y !== 'number') return;
    scrollRef.current?.scrollTo({ y: Math.max(0, y - 24), animated: true });
  }, []);

  const openPrimarySection = useCallback((sectionKey: MobilePrimarySectionKey) => {
    setActiveShellTab('actions');
    if (isMobile) {
      setExpandedPrimarySections((prev) => ({
        ...prev,
        [sectionKey]: true,
      }));
    }
    requestAnimationFrame(() => {
      scrollToSection(sectionKey);
    });
  }, [isMobile, scrollToSection]);

  const highlightedSection = guidedExperienceActive
    ? onboardingConfigState.data?.highlighted_section || null
    : null;
  const highlightedSecondaryGroup = useMemo(() => {
    if (!highlightedSection) return null;
    const group = UI_LAYOUT_CONFIG.secondaryGroups.find((entry) =>
      entry.sectionDependencies.includes(highlightedSection),
    );
    return group?.key || null;
  }, [highlightedSection]);

  const wrapSection = useCallback((sectionKey: string, node: React.ReactNode) => (
    <FadeInView>
      <View
        onLayout={(event) => {
          sectionOffsetsRef.current[sectionKey] = event.nativeEvent.layout.y;
        }}
        style={[
          styles.sectionShell,
          highlightedSection === sectionKey || highlightedSecondaryGroup === sectionKey
            ? styles.highlightSection
            : null,
        ]}
      >
        {node}
      </View>
    </FadeInView>
  ), [highlightedSection, highlightedSecondaryGroup]);

  const secondaryHiddenByOnboarding = guidedExperienceActive && UI_LAYOUT_CONFIG.onboarding.hideSecondaryDuringOnboarding;
  const forceCollapsedSecondary = guidedExperienceActive && UI_LAYOUT_CONFIG.onboarding.forceCollapseSecondary;

  const secondaryGroupVisibility = useMemo(() => ({
    economy_overview: UI_LAYOUT_CONFIG.secondaryGroups
      .find((group) => group.key === 'economy_overview')
      ?.sectionDependencies.some((sectionKey) => isSectionAllowedByOnboarding(sectionKey)) || false,
    business_insights: UI_LAYOUT_CONFIG.secondaryGroups
      .find((group) => group.key === 'business_insights')
      ?.sectionDependencies.some((sectionKey) => isSectionAllowedByOnboarding(sectionKey)) || false,
    planning_commitment: UI_LAYOUT_CONFIG.secondaryGroups
      .find((group) => group.key === 'planning_commitment')
      ?.sectionDependencies.some((sectionKey) => isSectionAllowedByOnboarding(sectionKey)) || false,
    progression: UI_LAYOUT_CONFIG.secondaryGroups
      .find((group) => group.key === 'progression')
      ?.sectionDependencies.some((sectionKey) => isSectionAllowedByOnboarding(sectionKey)) || false,
    world_memory: UI_LAYOUT_CONFIG.secondaryGroups
      .find((group) => group.key === 'world_memory')
      ?.sectionDependencies.some((sectionKey) => isSectionAllowedByOnboarding(sectionKey)) || false,
  }), [isSectionAllowedByOnboarding]);

  const toggleSecondaryGroup = useCallback((groupKey: SecondaryGroupKey) => {
    setExpandedSecondaryGroups((prev) => ({
      ...prev,
      [groupKey]: !prev[groupKey],
    }));
  }, []);

  const collapseAllSecondaryGroups = useCallback(() => {
    setExpandedSecondaryGroups({
      economy_overview: false,
      business_insights: false,
      planning_commitment: false,
      progression: false,
      world_memory: false,
    });
  }, []);

  const mobileNavItems = useMemo(
    () => [
      {
        key: 'home',
        label: 'Brief',
        onPress: () => {
          setActiveShellTab('home');
          collapseAllSecondaryGroups();
          requestAnimationFrame(() => {
            scrollToSection('daily_brief');
          });
        },
      },
      {
        key: 'actions',
        label: 'Actions',
        onPress: () => {
          setActiveShellTab('actions');
          setExpandedPrimarySections((prev) => ({
            ...prev,
            action_hub: true,
          }));
          requestAnimationFrame(() => {
            scrollToSection('action_hub');
          });
        },
      },
      {
        key: 'progress',
        label: 'Progress',
        onPress: () => {
          setActiveShellTab('progress');
          setExpandedSecondaryGroups((prev) => ({ ...prev, progression: true }));
          requestAnimationFrame(() => {
            scrollToSection('progression');
          });
        },
      },
      {
        key: 'insights',
        label: 'Insights',
        onPress: () => {
          setActiveShellTab('insights');
          setExpandedSecondaryGroups((prev) => ({
            ...prev,
            economy_overview: true,
            planning_commitment: true,
            world_memory: true,
          }));
          requestAnimationFrame(() => {
            scrollToSection('economy_overview');
          });
        },
      },
      {
        key: 'profile',
        label: 'Account',
        onPress: () => {
          setActiveShellTab('profile');
          router.push('/account/index');
        },
      },
    ],
    [collapseAllSecondaryGroups, scrollToSection],
  );

  const isSecondaryGroupExpanded = useCallback((groupKey: SecondaryGroupKey): boolean => {
    if (highlightedSecondaryGroup === groupKey) return true;
    if (forceCollapsedSecondary) return false;
    return expandedSecondaryGroups[groupKey];
  }, [expandedSecondaryGroups, forceCollapsedSecondary, highlightedSecondaryGroup]);

  const economySummary = useMemo(
    () =>
      buildEconomySummary(
        marketOverviewState.data,
        priceTrendsState.data,
        commutePressureState.data,
        economyPresentationSummaryState.data?.supply_chain_summary,
      ),
    [
      commutePressureState.data,
      economyPresentationSummaryState.data?.supply_chain_summary,
      marketOverviewState.data,
      priceTrendsState.data,
    ],
  );
  const businessSummary = useMemo(
    () => buildBusinessSummary(businessMarginsState.data),
    [businessMarginsState.data],
  );
  const planningSummary = useMemo(
    () => buildPlanningSummary(strategyRecommendationState.data, commitmentSummaryState.data),
    [commitmentSummaryState.data, strategyRecommendationState.data],
  );
  const worldSummary = useMemo(
    () =>
      buildWorldSummary(
        worldNarrativeState.data,
        worldPatternsState.data,
        worldLocalPressureState.data,
      ),
    [worldLocalPressureState.data, worldNarrativeState.data, worldPatternsState.data],
  );
  const progressionSummary = useMemo(() => {
    if (!progressionState.data) return 'Goals and streak momentum will appear after your first actions.';
    const completedGoals = progressionState.data.daily_goals.filter((goal) => goal.status === 'completed').length;
    const totalGoals = progressionState.data.daily_goals.length;
    const activeStreak = progressionState.data.streaks.find((streak) => Number(streak.current_count) > 0);
    const streakLine = activeStreak ? `${activeStreak.title} streak ${activeStreak.current_count}` : 'No active streak yet';
    return `${completedGoals}/${totalGoals} daily goals complete. ${streakLine}.`;
  }, [progressionState.data]);
  const actionHubSummary = useMemo(() => {
    if (!effectiveActionHub) return 'Action options will load shortly.';
    return `${effectiveActionHub.recommended_actions.length} recommended, ${effectiveActionHub.available_actions.length} available, ${effectiveActionHub.blocked_actions.length} blocked.`;
  }, [effectiveActionHub]);
  const dailyBriefSummary = useMemo(() => {
    if (!effectiveDashboard) return 'Today’s headline, top opportunity, and top risk.';
    const leadRisk = describeSignalItem(effectiveDashboard.top_risks?.[0], 'No major risk flagged');
    const leadOpportunity = describeSignalItem(effectiveDashboard.top_opportunities?.[0], 'No major opportunity flagged');
    return `${leadOpportunity}. Risk: ${leadRisk}.`;
  }, [effectiveDashboard]);
  const statsSummary = useMemo(() => economyState.summaryLine, [economyState.summaryLine]);
  const dailyBriefImpactBullets = useMemo(
    () => buildDailyBriefImpactBullets(economyPresentationSummaryState.data?.daily_brief),
    [economyPresentationSummaryState.data?.daily_brief],
  );

  const economyStatusLabel = useMemo(
    () =>
      summarizeStatusLabel([
        economyPresentationSummaryState as SectionState<unknown>,
        marketOverviewState as SectionState<unknown>,
        priceTrendsState as SectionState<unknown>,
        commutePressureState as SectionState<unknown>,
        housingTradeoffState as SectionState<unknown>,
        economyExplainerState as SectionState<unknown>,
        futureTeasersState as SectionState<unknown>,
      ]),
    [
      commutePressureState,
      economyPresentationSummaryState,
      economyExplainerState,
      futureTeasersState,
      housingTradeoffState,
      marketOverviewState,
      priceTrendsState,
    ],
  );
  const businessStatusLabel = useMemo(
    () =>
      summarizeStatusLabel([
        businessMarginsState as SectionState<unknown>,
        businessPlanState as SectionState<unknown>,
      ]),
    [businessMarginsState, businessPlanState],
  );

  const activeBusinessRecord = useMemo(
    () => playerBusinessesState.data?.businesses.find((b) => b.is_active) ?? null,
    [playerBusinessesState.data],
  );

  const stockMarketSummary = useMemo(() => {
    const market = stockMarketState.data;
    if (!market) return 'Ten sector stocks priced from the canonical daily close.';
    const pnl = market.portfolio.total_unrealized_pnl_xgp;
    return `${market.stocks.length} stocks. ${market.portfolio.holdings_count} held. Unrealized ${pnl > 0 ? '+' : ''}${pnl.toFixed(2)} xgp.`;
  }, [stockMarketState.data]);

  const thumbActionPool = useMemo(
    () => effectiveActionHub
      ? [...effectiveActionHub.recommended_actions, ...effectiveActionHub.available_actions]
      : [],
    [effectiveActionHub],
  );

  const workQuickAction = useMemo(
    () => thumbActionPool.find((action) => canonicalThumbActionKey(action.action_key) === 'work_shift') ?? null,
    [thumbActionPool],
  );

  const recoveryQuickAction = useMemo(
    () => thumbActionPool.find((action) => canonicalThumbActionKey(action.action_key) === 'recovery_action') ?? null,
    [thumbActionPool],
  );

  const switchJobQuickAction = useMemo(
    () => thumbActionPool.find((action) => canonicalThumbActionKey(action.action_key) === 'switch_job') ?? null,
    [thumbActionPool],
  );

  const businessMarginForActive = useMemo(() => {
    if (!activeBusinessRecord || !businessMarginsState.data) return null;
    return businessMarginsState.data.items.find(
      (i) => i.business_key === activeBusinessRecord.business_type,
    ) ?? null;
  }, [activeBusinessRecord, businessMarginsState.data]);

  const businessPlanForActive = useMemo(() => {
    if (!activeBusinessRecord || !businessPlanState.data) return null;
    return businessPlanState.data.items.find(
      (i) => i.business_key === activeBusinessRecord.business_type,
    ) ?? null;
  }, [activeBusinessRecord, businessPlanState.data]);

  const businessOperateSummary = useMemo(() => {
    if (!activeBusinessRecord) return null;
    const typeLabel =
      activeBusinessRecord.business_type === 'fruit_shop' ? 'Fruit Shop' : 'Food Truck';
    const operatedToday = dailySession.getActionCount('operate_business') >= 1;
    if (operatedToday) return `${typeLabel} — operated today`;
    const marginLabel = businessMarginForActive?.margin_outlook;
    return marginLabel
      ? `${typeLabel} — ${String(marginLabel).replace(/_/g, ' ')}`
      : typeLabel;
  }, [activeBusinessRecord, businessMarginForActive, dailySession]);

  const handleTradeStock = useCallback(async (stockId: string, side: 'buy' | 'sell', shares: number) => {
    if (stockTradeGuardRef.current) return;
    if (!Number.isInteger(shares) || shares <= 0) {
      setFeedback({ tone: 'error', message: 'Trade quantity must be a positive whole number.' });
      return;
    }
    if (dailySession.sessionStatus !== 'active') {
      setFeedback({ tone: 'error', message: 'Day ended. Start next day to continue trading.' });
      return;
    }
    if (dailySession.pendingExecution || executingAction || endingDay) {
      setFeedback({ tone: 'error', message: 'Another gameplay update is still in progress.' });
      return;
    }

    stockTradeGuardRef.current = true;
    setPendingStockTrade({ stockId, side });
    const stock = stockMarketState.data?.stocks.find((entry) => entry.stock_id === stockId) || null;
    setFeedback({ tone: 'info', message: buildPendingStockTradeFeedback(stock, side, shares) });
    try {
      const result = side === 'buy'
        ? await buyStock(playerId, stockId, shares)
        : await sellStock(playerId, stockId, shares);

      const refreshResults = await Promise.allSettled([
        loadStockMarket(),
        loadDashboard(),
      ]);
      recordSettledFailures('stock_trade_refresh', refreshResults);

      setFeedback({
        tone: 'success',
        message: buildStockTradeFeedbackMessage(result, side, stock),
      });
    } catch (error) {
      recordError('gameplay', 'Stock trade failed.', {
        action: 'stock_trade',
        context: { stockId, side, shares },
        error,
      });
      setFeedback({ tone: 'error', message: normalizeError(error) || 'Stock trade failed.' });
    } finally {
      stockTradeGuardRef.current = false;
      setPendingStockTrade(null);
    }
  }, [dailySession.pendingExecution, dailySession.sessionStatus, endingDay, executingAction, loadDashboard, loadStockMarket, playerId, stockMarketState.data]);

  const handleQuickWorkAction = useCallback(() => {
    if (workQuickAction) {
      void executeActionItem(workQuickAction);
      return;
    }
    openPrimarySection('action_hub');
  }, [executeActionItem, openPrimarySection, workQuickAction]);

  const handleQuickRecoveryAction = useCallback(() => {
    if (randomEvent.activeEvent && randomEvent.availableRecoveryActions.length > 0) {
      setActiveShellTab('actions');
      requestAnimationFrame(() => {
        scrollToSection('random_event');
      });
      return;
    }
    if (recoveryQuickAction) {
      void executeActionItem(recoveryQuickAction);
      return;
    }
    openPrimarySection('action_hub');
  }, [executeActionItem, openPrimarySection, randomEvent.activeEvent, randomEvent.availableRecoveryActions.length, recoveryQuickAction, scrollToSection]);

  const handleQuickBusinessAction = useCallback(() => {
    if (activeBusinessRecord) {
      void handleOperateBusiness();
      return;
    }
    openPrimarySection('business_operations');
  }, [activeBusinessRecord, handleOperateBusiness, openPrimarySection]);

  const handleQuickStockAction = useCallback(() => {
    openPrimarySection('stock_market');
  }, [openPrimarySection]);

  const handleQuickJobAction = useCallback(() => {
    if (switchJobQuickAction) {
      void openPreview(switchJobQuickAction);
      return;
    }
    openPrimarySection('action_hub');
  }, [openPreview, openPrimarySection, switchJobQuickAction]);

  const workQuickGuard = workQuickAction ? getExecutionGuard(workQuickAction) : null;
  const recoveryQuickGuard = recoveryQuickAction ? getExecutionGuard(recoveryQuickAction) : null;
  const switchJobQuickGuard = switchJobQuickAction ? getExecutionGuard(switchJobQuickAction) : null;
  const businessQuickGuard = activeBusinessRecord
    ? dailySession.canExecuteAction({ action_key: 'operate_business' })
    : null;

  const planningStatusLabel = useMemo(
    () =>
      summarizeStatusLabel([
        shortHorizonPlansState as SectionState<unknown>,
        strategyRecommendationState as SectionState<unknown>,
        debtVsGrowthState as SectionState<unknown>,
        recoveryVsPushState as SectionState<unknown>,
        commitmentSummaryState as SectionState<unknown>,
        commitmentAvailableState as SectionState<unknown>,
        commitmentFeedbackState as SectionState<unknown>,
        commitmentHistoryState as SectionState<unknown>,
        futurePreparationState as SectionState<unknown>,
      ]),
    [
      commitmentAvailableState,
      commitmentFeedbackState,
      commitmentHistoryState,
      commitmentSummaryState,
      debtVsGrowthState,
      futurePreparationState,
      recoveryVsPushState,
      shortHorizonPlansState,
      strategyRecommendationState,
    ],
  );
  const progressionStatusLabel = useMemo(
    () =>
      summarizeStatusLabel([
        progressionState as SectionState<unknown>,
        weeklyState as SectionState<unknown>,
      ]),
    [progressionState, weeklyState],
  );
  const worldStatusLabel = useMemo(
    () =>
      summarizeStatusLabel([
        worldNarrativeState as SectionState<unknown>,
        worldPatternsState as SectionState<unknown>,
        worldLocalPressureState as SectionState<unknown>,
        worldPlayerPatternsState as SectionState<unknown>,
        worldRegionMemoryState as SectionState<unknown>,
      ]),
    [
      worldLocalPressureState,
      worldNarrativeState,
      worldPatternsState,
      worldPlayerPatternsState,
      worldRegionMemoryState,
    ],
  );

  const feedbackStyle = feedback ? feedbackToneStyle(feedback.tone) : null;
  const dashboardRefreshing = dashboardState.status === 'loading' && Boolean(effectiveDashboard);
  const actionHubRefreshing = actionState.status === 'loading' && Boolean(effectiveActionHub);
  const stockMarketRefreshing = stockMarketState.status === 'loading' && Boolean(stockMarketState.data);
  const showingRefreshNotice = refreshing || dashboardRefreshing || actionHubRefreshing || stockMarketRefreshing;
  const onboardingStepKey = onboardingGuidanceState.data?.step_key || onboardingState.data?.current_step_key || null;
  const preferredGuidanceActionKey = onboardingConfigState.data?.highlighted_action_key
    || onboardingGuidanceState.data?.required_action_key
    || null;
  const highlightedDockActionId = guidedExperienceActive
    ? guidanceActionToDockActionId(preferredGuidanceActionKey, Boolean(activeBusinessRecord))
      || onboardingDockActionId(onboardingStepKey)
    : null;
  const onboardingLoadFailed = onboardingState.status === 'error'
    || onboardingGuidanceState.status === 'error'
    || onboardingConfigState.status === 'error'
    || onboardingUnlockState.status === 'error';
  const hasVisibleActionZone = Boolean(
    isSectionVisible('business_operations')
      || isSectionVisible('stock_market')
      || isSectionVisible('action_hub')
      || (randomEvent.activeEvent && dailySession.sessionStatus === 'active'),
  );
  const hasVisibleSecondarySections = !secondaryHiddenByOnboarding && Object.values(secondaryGroupVisibility).some(Boolean);

  return (
    <AppShell
      title="Gold Penny Gameplay"
      subtitle={`Player ID: ${playerId}`}
      headerRight={(
        <View style={styles.headerActions}>
          <SecondaryButton label="Refresh Data" onPress={loadAll} />
          {isSectionVisible('notifications') ? (
            <SecondaryButton
              label={`Alerts (${notificationCount})`}
              onPress={() => setNotificationsOpen(true)}
            />
          ) : null}
        </View>
      )}
      footer={isMobile ? (
        <View style={styles.footerStack}>
          {guidedExperienceActive && onboardingState.data && onboardingGuidanceState.data ? (
            <OnboardingBanner
              state={onboardingState.data}
              guidance={onboardingGuidanceState.data}
              busy={onboardingBusy}
              onAdvance={(actionKey) => {
                if (String(onboardingStepKey || '') === 'read_todays_brief') {
                  void handleAdvanceOnboarding(actionKey);
                  openPrimarySection('action_hub');
                  return;
                }
                void handleAdvanceOnboarding(actionKey);
              }}
              onSkip={handleSkipOnboarding}
            />
          ) : null}
          {onboardingLoadFailed && !guidedExperienceActive ? (
            <View style={styles.onboardingFallbackBox}>
              <Text style={styles.onboardingFallbackText}>
                Guided early-day help is unavailable right now. Read the Daily Brief, take one action, then end the day.
              </Text>
            </View>
          ) : null}
          <ThumbReachActionDock
            dayNumber={dailyProgression.currentGameDay}
            remainingTimeUnits={dailySession.remainingTimeUnits}
            totalTimeUnits={dailySession.totalTimeUnits}
            sessionStatus={dailySession.sessionStatus}
            feedback={feedback}
            highlightedActionId={highlightedDockActionId}
            primaryAction={{
              id: 'work',
              label: workQuickAction?.title || 'Work',
              onPress: handleQuickWorkAction,
              disabled: Boolean(workQuickAction && !workQuickGuard?.allowed),
              emphasis: 'primary',
            }}
            advanceAction={dailySession.sessionStatus === 'ended'
              ? {
                  id: 'advance_day',
                  label: dailyProgression.isAdvancingDay ? 'Starting...' : 'Start Next Day',
                  onPress: handleStartNextDay,
                  disabled: refreshing || dailyProgression.isAdvancingDay,
                  emphasis: 'primary',
                }
              : {
                  id: 'advance_day',
                  label: endingDay ? 'Ending...' : 'End Day',
                  onPress: handleEndDay,
                  disabled: !dailyProgression.canAdvanceDay || endingDay,
                  emphasis: 'secondary',
                }}
            secondaryActions={[
              {
                id: 'business',
                label: activeBusinessRecord ? 'Run Business' : 'Business',
                onPress: handleQuickBusinessAction,
                disabled: Boolean(activeBusinessRecord && businessQuickGuard && !businessQuickGuard.allowed),
              },
              {
                id: 'recovery',
                label: randomEvent.activeEvent && randomEvent.availableRecoveryActions.length > 0 ? 'Recover Event' : 'Recover',
                onPress: handleQuickRecoveryAction,
                disabled: Boolean(!randomEvent.activeEvent && recoveryQuickAction && !recoveryQuickGuard?.allowed),
              },
              {
                id: 'stocks',
                label: 'Stocks',
                onPress: handleQuickStockAction,
                disabled: stockMarketState.status === 'loading',
              },
              {
                id: 'jobs',
                label: 'Jobs',
                onPress: handleQuickJobAction,
                disabled: Boolean(switchJobQuickAction && !switchJobQuickGuard?.allowed),
              },
            ]}
          />
        </View>
      ) : null}
      bottomNavItems={isMobile ? mobileNavItems : undefined}
      activeBottomNavKey={isMobile ? activeShellTab : null}
    >
      <PageContainer>
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={[
            styles.content,
            isMobile ? styles.contentWithBottomNav : null,
          ]}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadAll} />}
          showsVerticalScrollIndicator={false}
        >
          <ContentStack gap={theme.spacing.md}>
        {feedback && feedbackStyle && !isMobile ? (
          <FadeInView key={`${feedback.tone}:${feedback.message}`} slide={6}>
            <View
              style={[
                styles.feedbackBox,
                {
                  borderColor: feedbackStyle.borderColor,
                  backgroundColor: feedbackStyle.backgroundColor,
                },
              ]}
            >
              <Text style={[styles.feedbackLabel, { color: feedbackStyle.color }]}>{feedbackToneLabel(feedback.tone)}</Text>
              <Text style={[styles.feedbackText, { color: feedbackStyle.color }]}>{feedback.message}</Text>
            </View>
          </FadeInView>
        ) : null}

        {showingRefreshNotice && !endingDay ? (
          <FadeInView key={`refresh-${String(showingRefreshNotice)}`} slide={4}>
            <LoadingStateCard label="Refreshing the latest state without interrupting play..." compact />
          </FadeInView>
        ) : null}

        {!isMobile && isSectionVisible('day_controls') ? wrapSection(
          'day_controls',
          <View style={styles.dayControlCard}>
            <View style={styles.dayControlCopy}>
              <Text style={styles.dayControlTitle}>Daily Session — Day {dailyProgression.currentGameDay}</Text>
              <Text style={styles.dayControlMeta}>
                {dailySession.remainingTimeUnits}/{dailySession.totalTimeUnits} time units left
              </Text>
              <Text style={styles.dayControlMeta}>
                Status: {dailySession.sessionStatus === 'active' ? 'Active' : 'Ended'}
              </Text>
            </View>
            <View style={styles.dayControlButtons}>
              <PrimaryButton
                style={styles.dayControlPrimaryButton}
                label="End Day"
                onPress={handleEndDay}
                disabled={!dailyProgression.canAdvanceDay || startingNextDayRef.current}
                loading={endingDay}
              />
              {dailySession.sessionStatus === 'ended' ? (
                <SecondaryButton
                  style={styles.dayControlSecondaryButton}
                  label="Start Next Day"
                  onPress={handleStartNextDay}
                  disabled={refreshing || dailyProgression.isAdvancingDay}
                  loading={dailyProgression.isAdvancingDay}
                />
              ) : null}
            </View>
          </View>,
        ) : null}

        {!effectiveDashboard && (dashboardState.status === 'loading' || dashboardState.status === 'idle') ? (
          <LoadingStateCard label="Loading dashboard..." />
        ) : null}
        {dashboardState.status === 'error' ? (
          <ErrorStateCard
            title="Dashboard unavailable"
            message={dashboardState.error || undefined}
            onRetry={loadDashboard}
          />
        ) : null}
        {dashboardState.status === 'empty' ? (
          <EmptyStateCard
            title="No dashboard snapshot yet"
            subtitle="Run a day cycle to generate the first gameplay snapshot."
          />
        ) : null}

        {effectiveDashboard ? (
          <>
            {isSectionVisible('daily_brief')
              ? wrapSection(
                'daily_brief',
                <PrimaryDashboardSection title="Daily Brief" summary={dailyBriefSummary}>
                  {dashboardRefreshing ? <LoadingStateCard label="Updating brief..." compact /> : null}
                  <DailyBriefCard dashboard={effectiveDashboard} impactBullets={dailyBriefImpactBullets} />
                </PrimaryDashboardSection>,
              )
              : null}
            {isSectionVisible('player_stats')
              ? wrapSection(
                'player_stats',
                <PrimaryDashboardSection title="Player Snapshot" summary={statsSummary} statusLabel={economyState.statusLabel}>
                  {dashboardRefreshing ? <LoadingStateCard label="Updating snapshot..." compact /> : null}
                  <PlayerStatsBar stats={effectiveDashboard.stats} economy={economyState} currentGameDay={dailyProgression.currentGameDay} jobIncome={jobIncome} expenseDebt={expenseDebt} />
                </PrimaryDashboardSection>,
              )
              : null}
          </>
        ) : null}

        {hasVisibleActionZone ? <Text style={styles.layerLabel}>Action Zone</Text> : null}

        {activeBusinessRecord
          ? wrapSection(
              'business_operations',
              <PrimaryDashboardSection
                title="Your Business Today"
                summary={businessOperateSummary}
                collapsible={isMobile}
                expanded={isPrimarySectionExpanded('business_operations')}
                onToggle={() => togglePrimarySection('business_operations')}
              >
                <BusinessOperationsCard
                  activeRecord={activeBusinessRecord}
                  profitSnapshot={playerBusinessesState.data?.profit_snapshot ?? null}
                  margins={businessMarginForActive}
                  plan={businessPlanForActive}
                  operatedToday={dailySession.getActionCount('operate_business') >= 1}
                  sessionActive={dailySession.sessionStatus === 'active'}
                  isExecuting={executingAction}
                  onOperate={handleOperateBusiness}
                />
              </PrimaryDashboardSection>,
            )
          : null}

        {isSectionVisible('business_operations') && playerBusinessesState.status === 'ready' && !activeBusinessRecord ? (
          wrapSection(
            'business_operations',
            <PrimaryDashboardSection
              title="Your Business Today"
              summary="No active business is running right now."
              collapsible={isMobile}
              expanded={isPrimarySectionExpanded('business_operations')}
              onToggle={() => togglePrimarySection('business_operations')}
            >
              <EmptyStateCard
                title="No active business"
                subtitle="Open or reactivate a business before relying on this lane for daily cash flow."
              />
            </PrimaryDashboardSection>,
          )
        ) : null}

        {isSectionVisible('stock_market') && !stockMarketState.data && (stockMarketState.status === 'loading' || stockMarketState.status === 'idle') ? (
          <LoadingStateCard label="Loading stock market..." />
        ) : null}
        {isSectionVisible('stock_market') && stockMarketState.status === 'error' ? (
          <ErrorStateCard
            title="Stock market unavailable"
            message={stockMarketState.error || undefined}
            onRetry={loadStockMarket}
          />
        ) : null}
        {isSectionVisible('stock_market') && stockMarketState.data ? (
          wrapSection(
            'stock_market',
            <PrimaryDashboardSection
              title="Stock Market"
              summary={stockMarketSummary}
              collapsible={isMobile}
              expanded={isPrimarySectionExpanded('stock_market')}
              onToggle={() => togglePrimarySection('stock_market')}
            >
              {stockMarketRefreshing ? <LoadingStateCard label="Refreshing stock prices..." compact /> : null}
              <StockMarketCard
                market={stockMarketState.data}
                sessionActive={dailySession.sessionStatus === 'active'}
                pendingTradeStockId={pendingStockTrade?.stockId ?? null}
                pendingTradeSide={pendingStockTrade?.side ?? null}
                onBuyOne={(stockId) => {
                  void handleTradeStock(stockId, 'buy', 1);
                }}
                onSellOne={(stockId) => {
                  void handleTradeStock(stockId, 'sell', 1);
                }}
                onSellAll={(stockId, quantity) => {
                  void handleTradeStock(stockId, 'sell', quantity);
                }}
              />
            </PrimaryDashboardSection>,
          )
        ) : null}

        {randomEvent.activeEvent && dailySession.sessionStatus === 'active'
          ? wrapSection(
              'random_event',
              <PrimaryDashboardSection
                title="Today's Event"
                summary={`${randomEvent.activeEvent.title} — ${randomEvent.activeEvent.effectSummary}`}
              >
                <RandomEventCard
                  event={randomEvent.activeEvent}
                  availableRecoveryActions={randomEvent.availableRecoveryActions}
                  onApplyRecoveryAction={(action) => {
                    randomEvent.applyRecoveryAction(action.recoveryActionId);
                    setFeedback({ tone: 'info', message: `${action.label}: ${action.effectSummary}` });
                  }}
                  onDismiss={randomEvent.dismissEvent}
                />
              </PrimaryDashboardSection>,
            )
          : null}

        {isSectionVisible('action_hub') && !effectiveActionHub && (actionState.status === 'loading' || actionState.status === 'idle') ? (
          <LoadingStateCard label="Loading action hub..." />
        ) : null}
        {isSectionVisible('action_hub') && actionState.status === 'error' ? (
          <ErrorStateCard
            title="Action hub unavailable"
            message={actionState.error || undefined}
            onRetry={loadActionHub}
          />
        ) : null}
        {isSectionVisible('action_hub') && actionState.status === 'empty' ? (
          <EmptyStateCard
            title="No actions currently available"
            subtitle="Check back after the next simulation cycle."
          />
        ) : null}
        {isSectionVisible('action_hub') && effectiveActionHub ? (
          wrapSection(
            'action_hub',
            <PrimaryDashboardSection
              title="Action Hub"
              summary={actionHubSummary}
              collapsible={isMobile}
              expanded={isPrimarySectionExpanded('action_hub')}
              onToggle={() => togglePrimarySection('action_hub')}
            >
              {actionHubRefreshing ? <LoadingStateCard label="Refreshing available actions..." compact /> : null}
              <ActionHubPanel
                hub={effectiveActionHub}
                onPreviewAction={openPreview}
                getExecutionGuard={getExecutionGuard}
                remainingTimeUnits={dailySession.remainingTimeUnits}
                totalTimeUnits={dailySession.totalTimeUnits}
                sessionStatus={dailySession.sessionStatus}
                progressRatio={dailySession.progress}
              />
              {isSectionVisible('action_history') ? (
                <ActionHistoryPanel
                  entries={dailySession.actionsTakenToday}
                  sessionStatus={dailySession.sessionStatus}
                />
              ) : null}
            </PrimaryDashboardSection>,
          )
        ) : null}

        {hasVisibleSecondarySections ? <Text style={styles.layerLabel}>Deep Dives</Text> : null}

        {!secondaryHiddenByOnboarding && secondaryGroupVisibility.economy_overview ? (
          wrapSection(
            'economy_overview',
            <SecondaryDashboardSection
              title="Economy + Market"
              summary={economySummary}
              statusLabel={economyStatusLabel}
              expanded={isSecondaryGroupExpanded('economy_overview')}
              onToggle={() => toggleSecondaryGroup('economy_overview')}
            >
              {isSectionAllowedByOnboarding('market_overview') && (marketOverviewState.status === 'loading' || marketOverviewState.status === 'idle') ? (
                <LoadingStateCard label="Loading market overview..." />
              ) : null}
              {isSectionAllowedByOnboarding('market_overview') && marketOverviewState.status === 'error' ? (
                <ErrorStateCard
                  title="Market overview unavailable"
                  message={marketOverviewState.error || undefined}
                  onRetry={loadMarketOverview}
                />
              ) : null}
              {isSectionAllowedByOnboarding('market_overview') && marketOverviewState.status === 'ready' && marketOverviewState.data ? (
                <MarketOverviewCard overview={marketOverviewState.data} />
              ) : null}

              {isSectionAllowedByOnboarding('price_trends') && (priceTrendsState.status === 'loading' || priceTrendsState.status === 'idle') ? (
                <LoadingStateCard label="Loading price trends..." />
              ) : null}
              {isSectionAllowedByOnboarding('price_trends') && priceTrendsState.status === 'error' ? (
                <ErrorStateCard
                  title="Price trends unavailable"
                  message={priceTrendsState.error || undefined}
                  onRetry={loadPriceTrends}
                />
              ) : null}
              {isSectionAllowedByOnboarding('price_trends') && priceTrendsState.status === 'ready' && priceTrendsState.data ? (
                <PriceTrendsCard trends={priceTrendsState.data} />
              ) : null}

              {isSectionAllowedByOnboarding('commute_pressure') && (commutePressureState.status === 'loading' || commutePressureState.status === 'idle') ? (
                <LoadingStateCard label="Loading commute pressure..." />
              ) : null}
              {isSectionAllowedByOnboarding('commute_pressure') && commutePressureState.status === 'error' ? (
                <ErrorStateCard
                  title="Commute pressure unavailable"
                  message={commutePressureState.error || undefined}
                  onRetry={loadCommutePressure}
                />
              ) : null}
              {isSectionAllowedByOnboarding('commute_pressure') && commutePressureState.status === 'ready' && commutePressureState.data ? (
                <CommutePressureCard commute={commutePressureState.data} />
              ) : null}

              {isSectionAllowedByOnboarding('housing_tradeoff') && (housingTradeoffState.status === 'loading' || housingTradeoffState.status === 'idle') ? (
                <LoadingStateCard label="Loading housing tradeoff..." />
              ) : null}
              {isSectionAllowedByOnboarding('housing_tradeoff') && housingTradeoffState.status === 'error' ? (
                <ErrorStateCard
                  title="Housing tradeoff unavailable"
                  message={housingTradeoffState.error || undefined}
                  onRetry={loadHousingTradeoff}
                />
              ) : null}
              {isSectionAllowedByOnboarding('housing_tradeoff') && housingTradeoffState.status === 'ready' && housingTradeoffState.data ? (
                <HousingTradeoffCard tradeoff={housingTradeoffState.data} />
              ) : null}

              {isSectionAllowedByOnboarding('economy_explainer') && (economyExplainerState.status === 'loading' || economyExplainerState.status === 'idle') ? (
                <LoadingStateCard label="Loading economy explainer..." />
              ) : null}
              {isSectionAllowedByOnboarding('economy_explainer') && economyExplainerState.status === 'error' ? (
                <ErrorStateCard
                  title="Economy explainer unavailable"
                  message={economyExplainerState.error || undefined}
                  onRetry={loadEconomyExplainer}
                />
              ) : null}
              {isSectionAllowedByOnboarding('economy_explainer') && economyExplainerState.status === 'ready' && economyExplainerState.data ? (
                <EconomyExplainerCard explainer={economyExplainerState.data} />
              ) : null}

              {isSectionAllowedByOnboarding('future_teasers') && (futureTeasersState.status === 'loading' || futureTeasersState.status === 'idle') ? (
                <LoadingStateCard label="Loading future opportunity teasers..." />
              ) : null}
              {isSectionAllowedByOnboarding('future_teasers') && futureTeasersState.status === 'error' ? (
                <ErrorStateCard
                  title="Future opportunity teasers unavailable"
                  message={futureTeasersState.error || undefined}
                  onRetry={loadFutureTeasers}
                />
              ) : null}
              {isSectionAllowedByOnboarding('future_teasers') && futureTeasersState.status === 'ready' && futureTeasersState.data ? (
                <FutureOpportunitiesCard teasers={futureTeasersState.data} />
              ) : null}

              {(economyPresentationSummaryState.status === 'loading' || economyPresentationSummaryState.status === 'idle') ? (
                <LoadingStateCard label="Loading backend economy summary..." />
              ) : null}
              {economyPresentationSummaryState.status === 'error' ? (
                <ErrorStateCard
                  title="Backend economy summary unavailable"
                  message={economyPresentationSummaryState.error || undefined}
                  onRetry={loadEconomyOverviewWithFallback}
                />
              ) : null}
              {economyPresentationSummaryState.status === 'ready' && economyPresentationSummaryState.data ? (
                <SupplyChainStoryCard
                  summary={economyPresentationSummaryState.data.supply_chain_summary}
                  story={economyPresentationSummaryState.data.supply_chain_story}
                  warnings={economyPresentationSummaryState.data.player_warnings}
                  opportunities={economyPresentationSummaryState.data.player_opportunities}
                />
              ) : null}
            </SecondaryDashboardSection>,
          )
        ) : null}

        {!secondaryHiddenByOnboarding && secondaryGroupVisibility.business_insights ? (
          wrapSection(
            'business_insights',
            <SecondaryDashboardSection
              title="Business + Margins"
              summary={businessSummary}
              statusLabel={businessStatusLabel}
              expanded={isSecondaryGroupExpanded('business_insights')}
              onToggle={() => toggleSecondaryGroup('business_insights')}
            >
              {isSectionAllowedByOnboarding('business_margins') && (businessMarginsState.status === 'loading' || businessMarginsState.status === 'idle') ? (
                <LoadingStateCard label="Loading business margin view..." />
              ) : null}
              {isSectionAllowedByOnboarding('business_margins') && businessMarginsState.status === 'error' ? (
                <ErrorStateCard
                  title="Business margin view unavailable"
                  message={businessMarginsState.error || undefined}
                  onRetry={loadBusinessMargins}
                />
              ) : null}
              {isSectionAllowedByOnboarding('business_margins') && businessMarginsState.status === 'ready' && businessMarginsState.data ? (
                <BusinessMarginsCard margins={businessMarginsState.data} />
              ) : null}

              {isSectionAllowedByOnboarding('business_plan') && (businessPlanState.status === 'loading' || businessPlanState.status === 'idle') ? (
                <LoadingStateCard label="Loading business plan..." />
              ) : null}
              {isSectionAllowedByOnboarding('business_plan') && businessPlanState.status === 'error' ? (
                <ErrorStateCard
                  title="Business plan unavailable"
                  message={businessPlanState.error || undefined}
                  onRetry={loadBusinessPlan}
                />
              ) : null}
              {isSectionAllowedByOnboarding('business_plan') && businessPlanState.status === 'ready' && businessPlanState.data ? (
                <BusinessPlanCard plan={businessPlanState.data} />
              ) : null}
            </SecondaryDashboardSection>,
          )
        ) : null}

        {!secondaryHiddenByOnboarding && secondaryGroupVisibility.planning_commitment ? (
          wrapSection(
            'planning_commitment',
            <SecondaryDashboardSection
              title="Planning + Commitment"
              summary={planningSummary}
              statusLabel={planningStatusLabel}
              expanded={isSecondaryGroupExpanded('planning_commitment')}
              onToggle={() => toggleSecondaryGroup('planning_commitment')}
            >
              {isSectionAllowedByOnboarding('strategic_recommendation') && (strategyRecommendationState.status === 'loading' || strategyRecommendationState.status === 'idle') ? (
                <LoadingStateCard label="Loading strategy recommendation..." />
              ) : null}
              {isSectionAllowedByOnboarding('strategic_recommendation') && strategyRecommendationState.status === 'error' ? (
                <ErrorStateCard
                  title="Strategy recommendation unavailable"
                  message={strategyRecommendationState.error || undefined}
                  onRetry={loadStrategyRecommendation}
                />
              ) : null}
              {isSectionAllowedByOnboarding('strategic_recommendation') && strategyRecommendationState.status === 'ready' && strategyRecommendationState.data ? (
                <StrategyRecommendationCard recommendation={strategyRecommendationState.data} />
              ) : null}

              {isSectionAllowedByOnboarding('strategic_planning') && (shortHorizonPlansState.status === 'loading' || shortHorizonPlansState.status === 'idle') ? (
                <LoadingStateCard label="Loading short-horizon plans..." />
              ) : null}
              {isSectionAllowedByOnboarding('strategic_planning') && shortHorizonPlansState.status === 'error' ? (
                <ErrorStateCard
                  title="Short-horizon plans unavailable"
                  message={shortHorizonPlansState.error || undefined}
                  onRetry={loadShortHorizonPlans}
                />
              ) : null}
              {isSectionAllowedByOnboarding('strategic_planning') && shortHorizonPlansState.status === 'ready' && shortHorizonPlansState.data ? (
                <ShortHorizonPlansCard plans={shortHorizonPlansState.data} />
              ) : null}

              {isSectionAllowedByOnboarding('debt_growth') && (debtVsGrowthState.status === 'loading' || debtVsGrowthState.status === 'idle') ? (
                <LoadingStateCard label="Loading debt vs growth analysis..." />
              ) : null}
              {isSectionAllowedByOnboarding('debt_growth') && debtVsGrowthState.status === 'error' ? (
                <ErrorStateCard
                  title="Debt vs growth analysis unavailable"
                  message={debtVsGrowthState.error || undefined}
                  onRetry={loadDebtVsGrowth}
                />
              ) : null}
              {isSectionAllowedByOnboarding('debt_growth') && debtVsGrowthState.status === 'ready' && debtVsGrowthState.data ? (
                <DebtVsGrowthCard analysis={debtVsGrowthState.data} />
              ) : null}

              {isSectionAllowedByOnboarding('recovery_vs_push') && (recoveryVsPushState.status === 'loading' || recoveryVsPushState.status === 'idle') ? (
                <LoadingStateCard label="Loading recovery vs push analysis..." />
              ) : null}
              {isSectionAllowedByOnboarding('recovery_vs_push') && recoveryVsPushState.status === 'error' ? (
                <ErrorStateCard
                  title="Recovery vs push analysis unavailable"
                  message={recoveryVsPushState.error || undefined}
                  onRetry={loadRecoveryVsPush}
                />
              ) : null}
              {isSectionAllowedByOnboarding('recovery_vs_push') && recoveryVsPushState.status === 'ready' && recoveryVsPushState.data ? (
                <RecoveryVsPushCard analysis={recoveryVsPushState.data} />
              ) : null}

              {isSectionAllowedByOnboarding('future_preparation') && (futurePreparationState.status === 'loading' || futurePreparationState.status === 'idle') ? (
                <LoadingStateCard label="Loading future path preparation..." />
              ) : null}
              {isSectionAllowedByOnboarding('future_preparation') && futurePreparationState.status === 'error' ? (
                <ErrorStateCard
                  title="Future path preparation unavailable"
                  message={futurePreparationState.error || undefined}
                  onRetry={loadFuturePreparation}
                />
              ) : null}
              {isSectionAllowedByOnboarding('future_preparation') && futurePreparationState.status === 'ready' && futurePreparationState.data ? (
                <FuturePreparationCard future={futurePreparationState.data} />
              ) : null}

              {isSectionAllowedByOnboarding('commitment') && (commitmentSummaryState.status === 'loading' || commitmentSummaryState.status === 'idle') ? (
                <LoadingStateCard label="Loading commitment summary..." />
              ) : null}
              {isSectionAllowedByOnboarding('commitment') && commitmentSummaryState.status === 'error' ? (
                <ErrorStateCard
                  title="Commitment summary unavailable"
                  message={commitmentSummaryState.error || undefined}
                  onRetry={loadCommitmentSummary}
                />
              ) : null}
              {isSectionAllowedByOnboarding('commitment') && commitmentSummaryState.data ? (
                <View style={styles.groupStack}>
                  <ActiveCommitmentCard
                    commitment={commitmentSummaryState.data.active_commitment}
                    busy={commitmentBusy}
                    onCancel={handleCancelCommitment}
                  />
                  <CommitmentProgressCard summary={commitmentSummaryState.data} />
                </View>
              ) : null}

              {isSectionAllowedByOnboarding('commitment') && (commitmentAvailableState.status === 'loading' || commitmentAvailableState.status === 'idle') ? (
                <LoadingStateCard label="Loading commitment options..." />
              ) : null}
              {isSectionAllowedByOnboarding('commitment') && commitmentAvailableState.status === 'error' ? (
                <ErrorStateCard
                  title="Commitment options unavailable"
                  message={commitmentAvailableState.error || undefined}
                  onRetry={loadCommitmentAvailable}
                />
              ) : null}
              {isSectionAllowedByOnboarding('commitment') && commitmentAvailableState.data ? (
                <CommitmentPickerCard
                  available={commitmentAvailableState.data}
                  activeCommitment={commitmentSummaryState.data?.active_commitment || null}
                  busy={commitmentBusy}
                  onActivate={handleActivateCommitment}
                />
              ) : null}

              {isSectionAllowedByOnboarding('commitment') && (commitmentFeedbackState.status === 'loading' || commitmentFeedbackState.status === 'idle') ? (
                <LoadingStateCard label="Loading commitment feedback..." />
              ) : null}
              {isSectionAllowedByOnboarding('commitment') && commitmentFeedbackState.status === 'error' ? (
                <ErrorStateCard
                  title="Commitment feedback unavailable"
                  message={commitmentFeedbackState.error || undefined}
                  onRetry={loadCommitmentFeedback}
                />
              ) : null}
              {isSectionAllowedByOnboarding('commitment') && commitmentFeedbackState.status === 'ready' && commitmentFeedbackState.data ? (
                <CommitmentFeedbackCard feedback={commitmentFeedbackState.data} />
              ) : null}

              {isSectionAllowedByOnboarding('commitment') && (commitmentHistoryState.status === 'loading' || commitmentHistoryState.status === 'idle') ? (
                <LoadingStateCard label="Loading commitment history..." />
              ) : null}
              {isSectionAllowedByOnboarding('commitment') && commitmentHistoryState.status === 'error' ? (
                <ErrorStateCard
                  title="Commitment history unavailable"
                  message={commitmentHistoryState.error || undefined}
                  onRetry={loadCommitmentHistory}
                />
              ) : null}
              {isSectionAllowedByOnboarding('commitment') && commitmentHistoryState.status === 'ready' && commitmentHistoryState.data ? (
                <CommitmentHistoryCard history={commitmentHistoryState.data} />
              ) : null}
            </SecondaryDashboardSection>,
          )
        ) : null}

        {!secondaryHiddenByOnboarding && secondaryGroupVisibility.progression ? (
          wrapSection(
            'progression',
            <SecondaryDashboardSection
              title="Progression"
              summary={progressionSummary}
              statusLabel={progressionStatusLabel}
              expanded={isSecondaryGroupExpanded('progression')}
              onToggle={() => toggleSecondaryGroup('progression')}
            >
              {isSectionAllowedByOnboarding('progression') && (progressionState.status === 'loading' || progressionState.status === 'idle') ? (
                <LoadingStateCard label="Loading progression..." />
              ) : null}
              {isSectionAllowedByOnboarding('progression') && progressionState.status === 'error' ? (
                <ErrorStateCard
                  title="Progression unavailable"
                  message={progressionState.error || undefined}
                  onRetry={loadProgression}
                />
              ) : null}
              {isSectionAllowedByOnboarding('progression') && progressionState.status === 'empty' ? (
                <EmptyStateCard
                  title="No progression goals yet"
                  subtitle="Complete one action to generate your first goals and streaks."
                />
              ) : null}
              {isSectionAllowedByOnboarding('progression') && progressionState.status === 'ready' && progressionState.data ? (
                <View style={styles.groupStack}>
                  <ProgressionSummaryCard summary={progressionState.data} />
                  <DailyGoalsCard goals={progressionState.data.daily_goals} />
                  <StreaksCard streaks={progressionState.data.streaks} />
                  <WeeklyMissionsCard missions={progressionState.data.weekly_missions} />
                </View>
              ) : null}

              {isSectionAllowedByOnboarding('weekly_summary') && (weeklyState.status === 'loading' || weeklyState.status === 'idle') ? (
                <LoadingStateCard label="Loading weekly summary..." />
              ) : null}
              {isSectionAllowedByOnboarding('weekly_summary') && weeklyState.status === 'error' ? (
                <ErrorStateCard
                  title="Weekly summary unavailable"
                  message={weeklyState.error || undefined}
                  onRetry={loadWeeklySummary}
                />
              ) : null}
              {isSectionAllowedByOnboarding('weekly_summary') && weeklyState.status === 'ready' && weeklyState.data ? (
                <WeeklySummaryCard summary={weeklyState.data} />
              ) : null}
            </SecondaryDashboardSection>,
          )
        ) : null}

        {!secondaryHiddenByOnboarding && secondaryGroupVisibility.world_memory ? (
          wrapSection(
            'world_memory',
            <SecondaryDashboardSection
              title="World Memory"
              summary={worldSummary}
              statusLabel={worldStatusLabel}
              expanded={isSecondaryGroupExpanded('world_memory')}
              onToggle={() => toggleSecondaryGroup('world_memory')}
            >
              {isSectionAllowedByOnboarding('world_memory') && (worldNarrativeState.status === 'loading' || worldNarrativeState.status === 'idle') ? (
                <LoadingStateCard label="Loading world narrative..." />
              ) : null}
              {isSectionAllowedByOnboarding('world_memory') && worldNarrativeState.status === 'error' ? (
                <ErrorStateCard
                  title="World narrative unavailable"
                  message={worldNarrativeState.error || undefined}
                  onRetry={loadWorldNarrative}
                />
              ) : null}
              {isSectionAllowedByOnboarding('world_memory') && worldNarrativeState.status === 'ready' && worldNarrativeState.data ? (
                <WorldNarrativeCard narrative={worldNarrativeState.data} />
              ) : null}

              {isSectionAllowedByOnboarding('world_memory') && (worldLocalPressureState.status === 'loading' || worldLocalPressureState.status === 'idle') ? (
                <LoadingStateCard label="Loading local pressure memory..." />
              ) : null}
              {isSectionAllowedByOnboarding('world_memory') && worldLocalPressureState.status === 'error' ? (
                <ErrorStateCard
                  title="Local pressure memory unavailable"
                  message={worldLocalPressureState.error || undefined}
                  onRetry={loadWorldLocalPressure}
                />
              ) : null}
              {isSectionAllowedByOnboarding('world_memory') && worldLocalPressureState.status === 'ready' && worldLocalPressureState.data ? (
                <LocalPressureCard local={worldLocalPressureState.data} />
              ) : null}

              {isSectionAllowedByOnboarding('world_memory') && (worldPatternsState.status === 'loading' || worldPatternsState.status === 'idle') ? (
                <LoadingStateCard label="Loading pattern insights..." />
              ) : null}
              {isSectionAllowedByOnboarding('world_memory') && worldPatternsState.status === 'error' ? (
                <ErrorStateCard
                  title="Pattern insights unavailable"
                  message={worldPatternsState.error || undefined}
                  onRetry={loadWorldPatterns}
                />
              ) : null}
              {isSectionAllowedByOnboarding('world_memory') && worldPatternsState.status === 'ready' && worldPatternsState.data ? (
                <PatternInsightsCard patterns={worldPatternsState.data} />
              ) : null}

              {isSectionAllowedByOnboarding('world_memory') && (worldPlayerPatternsState.status === 'loading' || worldPlayerPatternsState.status === 'idle') ? (
                <LoadingStateCard label="Loading player pattern memory..." />
              ) : null}
              {isSectionAllowedByOnboarding('world_memory') && worldPlayerPatternsState.status === 'error' ? (
                <ErrorStateCard
                  title="Player pattern memory unavailable"
                  message={worldPlayerPatternsState.error || undefined}
                  onRetry={loadWorldPlayerPatterns}
                />
              ) : null}
              {isSectionAllowedByOnboarding('world_memory') && worldPlayerPatternsState.status === 'ready' && worldPlayerPatternsState.data ? (
                <PlayerPatternsCard patterns={worldPlayerPatternsState.data} />
              ) : null}

              {isSectionAllowedByOnboarding('world_memory') && (worldRegionMemoryState.status === 'loading' || worldRegionMemoryState.status === 'idle') ? (
                <LoadingStateCard label="Loading region memory..." />
              ) : null}
              {isSectionAllowedByOnboarding('world_memory') && worldRegionMemoryState.status === 'error' ? (
                <ErrorStateCard
                  title="Region memory unavailable"
                  message={worldRegionMemoryState.error || undefined}
                  onRetry={loadWorldRegionMemory}
                />
              ) : null}
              {isSectionAllowedByOnboarding('world_memory') && worldRegionMemoryState.status === 'ready' && worldRegionMemoryState.data ? (
                <RegionMemoryCard region={worldRegionMemoryState.data} />
              ) : null}
            </SecondaryDashboardSection>,
          )
        ) : null}

        {isSectionVisible('end_of_day_summary') && (eodState.status === 'loading' || eodState.status === 'idle') && dailySession.sessionStatus === 'ended' ? (
          <FadeInView key={`eod-loading-${dailyProgression.currentGameDay}`} slide={8}>
            <LoadingStateCard label="Settling the day and gathering results..." />
          </FadeInView>
        ) : null}
        {isSectionVisible('end_of_day_summary') && eodState.status === 'error' && dailySession.sessionStatus === 'ended' ? (
          <ErrorStateCard
            title="End-of-day summary unavailable"
            message={eodState.error || undefined}
            onRetry={loadEndOfDaySummary}
          />
        ) : null}
        {isSectionVisible('end_of_day_summary') && eodState.status === 'ready' && eodState.data
          ? wrapSection('end_of_day_summary', <FadeInView key={`eod-summary-${eodState.data.as_of_date}`} slide={10}><EndOfDaySummaryCard summary={eodState.data} /></FadeInView>)
          : null}

        {isSectionVisible('end_of_day_summary') && lastEndDayResult && eodState.status !== 'ready' ? (
          <FadeInView key={`eod-fallback-${lastEndDayResult.settled_day}`} slide={10}>
            <View style={styles.fallbackSummaryCard}>
              <Text style={styles.fallbackSummaryTitle}>Day Settled</Text>
              <Text style={styles.fallbackSummaryText}>
                {lastEndDayResult.summary_headline || lastEndDayResult.summary || lastEndDayResult.message}
              </Text>
            </View>
          </FadeInView>
        ) : null}

          </ContentStack>
        </ScrollView>
      </PageContainer>

      <ActionPreviewModal
        visible={previewVisible}
        action={selectedAction}
        preview={previewPayload}
        loading={previewLoading}
        error={previewError}
        onClose={closePreview}
        onExecuteAction={handleExecuteSelectedAction}
        executeDisabled={dailySession.sessionStatus !== 'active' || endingDay || dailySession.pendingExecution}
        executeGuard={selectedActionGuard || undefined}
        executing={executingAction}
      />

      {isSectionVisible('notifications') ? (
        <NotificationsDrawer
          visible={notificationsOpen}
          notifications={notificationsState.data?.notifications || []}
          onClose={() => setNotificationsOpen(false)}
        />
      ) : null}
    </AppShell>
  );
}

const styles = StyleSheet.create({
  headerActions: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    flexWrap: 'wrap',
  },
  content: {
    paddingTop: theme.spacing.md,
    paddingBottom: theme.spacing.xxxl,
  },
  contentWithBottomNav: {
    paddingBottom: theme.spacing.lg,
  },
  sectionShell: {
    gap: theme.spacing.sm,
  },
  layerLabel: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
    fontWeight: '800',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    paddingHorizontal: theme.spacing.xs,
    marginTop: theme.spacing.xs,
  },
  highlightSection: {
    borderWidth: 2,
    borderColor: '#93c5fd',
    borderRadius: theme.radius.lg,
    padding: 4,
    backgroundColor: '#f8fbff',
  },
  groupStack: {
    gap: theme.spacing.sm,
  },
  footerStack: {
    gap: theme.spacing.sm,
  },
  feedbackBox: {
    borderWidth: 1,
    borderRadius: theme.radius.xl,
    paddingVertical: theme.spacing.md,
    paddingHorizontal: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  feedbackLabel: {
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  feedbackText: {
    ...theme.typography.bodySm,
    fontWeight: '600',
    lineHeight: 18,
  },
  dayControlCard: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.lg,
    backgroundColor: theme.color.surface,
    padding: theme.spacing.md,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: theme.spacing.sm,
    flexWrap: 'wrap',
  },
  dayControlCopy: {
    gap: theme.spacing.xxs,
  },
  dayControlTitle: {
    color: theme.color.textPrimary,
    ...theme.typography.headingSm,
  },
  dayControlMeta: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
    fontWeight: '600',
  },
  dayControlButtons: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    flexWrap: 'wrap',
  },
  dayControlPrimaryButton: {
    minWidth: 132,
  },
  dayControlSecondaryButton: {
    minWidth: 152,
  },
  buttonDisabled: {
    opacity: 0.45,
  },
  fallbackSummaryCard: {
    borderWidth: 1,
    borderColor: '#bfdbfe',
    borderRadius: theme.radius.md,
    backgroundColor: '#eff6ff',
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  fallbackSummaryTitle: {
    color: '#1e40af',
    ...theme.typography.headingSm,
  },
  fallbackSummaryText: {
    color: '#1e3a8a',
    ...theme.typography.bodySm,
  },
  onboardingFallbackBox: {
    borderWidth: 1,
    borderColor: '#fde68a',
    borderRadius: theme.radius.md,
    backgroundColor: '#fffbeb',
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
  },
  onboardingFallbackText: {
    color: '#92400e',
    ...theme.typography.bodySm,
    fontWeight: '600',
  },
});

