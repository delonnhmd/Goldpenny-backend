import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Animated, StyleSheet, Text, TextInput, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';

import ActionHubPanel from '@/components/gameplay/ActionHubPanel';
import AnimatedMoneyValue from '@/components/motion/AnimatedMoneyValue';
import PulseAlertView from '@/components/motion/PulseAlertView';
import SlideFadeInOnChange from '@/components/motion/SlideFadeInOnChange';
import { OnboardingHighlight } from '@/components/onboarding';
import EmptyStateView from '@/components/ui/EmptyStateView';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import { finalizePlayerWorkState } from '@/lib/api/gameplay';
import { BALANCE } from '@/lib/balanceConfig';
import { formatMoney } from '@/lib/gameplayFormatters';
import { recordInfo } from '@/lib/logger';
import {
  DailyActionItem,
  EconomySignalChip,
  JobMarketJobSnapshot,
} from '@/types/gameplay';

import { useGameplayLoop } from '../context';
import JobMarketPanel from '../components/JobMarketPanel';
import {
  GameplayCompactMetricRows,
  GameplayStickyActionArea,
  GameplaySummaryCard,
  GameplayStatCard,
  GameplayWarningBanner,
} from '../components/GameplayUIParts';
import GameplayLoopScaffold from '../GameplayLoopScaffold';

function signedCurrency(value: number): string {
  const sign = value > 0 ? '+' : '';
  return `${sign}${formatMoney(value)}`;
}

function signedWhole(value: number): string {
  const rounded = Math.round(value);
  if (rounded > 0) return `+${rounded}`;
  return String(rounded);
}

function createActionRequestId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function formatRiskLevel(level: string | null | undefined): string {
  const normalized = String(level || '').trim().toLowerCase();
  if (normalized === 'critical') return 'Critical';
  if (normalized === 'high') return 'High';
  if (normalized === 'moderate') return 'Moderate';
  return 'Low';
}

function riskTone(level: string | null | undefined): 'neutral' | 'info' | 'warning' | 'danger' | 'positive' {
  const normalized = String(level || '').trim().toLowerCase();
  if (normalized === 'critical') return 'danger';
  if (normalized === 'high') return 'warning';
  if (normalized === 'moderate') return 'info';
  return 'positive';
}

const HOUSTON_TIMEZONE = 'America/Chicago';
const RIDESHARE_TRIP_OPTIONS = [1, 3, 5] as const;
const SHIFT_SHORT_MODE =
  __DEV__
  || process.env.EXPO_PUBLIC_SHIFT_TIMER_SHORT_MODE === 'true'
  || process.env.EXPO_PUBLIC_SHIFT_TIMER_SHORT_MODE === '1';

interface TimelineNote {
  id: string;
  timestampIso: string;
  title: string;
  detail: string;
  category: 'work' | 'rideshare' | 'recovery' | 'meal' | 'finance' | 'system';
}

type TimedActivityCardId = 'watch_tv' | 'watch_movie' | 'read_book' | 'jogging' | 'skill_training';

interface TimedActivityCardPreset {
  id: TimedActivityCardId;
  title: string;
  primaryEffect: string;
  secondaryEffect: string;
  timeRule: string;
}

const TIMED_ACTIVITY_PRESETS: TimedActivityCardPreset[] = [
  {
    id: 'watch_tv',
    title: 'Watch TV',
    primaryEffect: '-1 stress every 2 min',
    secondaryEffect: 'Interruptible any time once started.',
    timeRule: 'Costs 1 unit every 20 min while running.',
  },
  {
    id: 'watch_movie',
    title: 'Watch Movie',
    primaryEffect: '-1 stress every 2 min',
    secondaryEffect: 'Best for longer off-hours blocks.',
    timeRule: 'Costs 1 unit every 20 min while running.',
  },
  {
    id: 'read_book',
    title: 'Read Book',
    primaryEffect: '-1 stress every 2 min',
    secondaryEffect: 'Good low-pressure recovery time.',
    timeRule: 'Costs 1 unit every 20 min while running.',
  },
  {
    id: 'jogging',
    title: 'Jogging',
    primaryEffect: '-1 stress every 2 min',
    secondaryEffect: `+${BALANCE.REALTIME.JOGGING_HEALTH_GAIN} health every ${BALANCE.REALTIME.JOGGING_HEALTH_INTERVAL_MINUTES} min`,
    timeRule: 'Costs 1 unit every 20 min while running.',
  },
  {
    id: 'skill_training',
    title: 'Skill Training',
    primaryEffect: `+${BALANCE.REALTIME.TRAINING_SKILL_GAIN_PER_UNIT} skill every ${BALANCE.REALTIME.MINUTES_PER_UNIT} min`,
    secondaryEffect: `Efficiency bonus after ${BALANCE.REALTIME.TRAINING_BONUS_THRESHOLD_UNITS * BALANCE.REALTIME.MINUTES_PER_UNIT} min`,
    timeRule: 'Costs 1 unit every 20 min while running.',
  },
];

function canonicalDashboardActionKey(actionKey: string): string {
  const raw = String(actionKey || '').toLowerCase().trim();
  if (!raw) return '';
  if (raw.includes('work') || raw.includes('shift')) return 'work_shift';
  if (raw.includes('ride') || raw.includes('side_income') || raw.includes('delivery')) return 'side_income';
  if (raw === 'watch_tv' || raw === 'watch_movie' || raw === 'read_book' || raw === 'jogging') return 'recovery_activity';
  if (raw.includes('rest') || raw.includes('recover')) return 'rest';
  if (raw === 'skill_training' || raw === 'study') return 'skill_training';
  if (raw === 'start_training' || (raw.includes('start') && raw.includes('training'))) return 'start_training';
  if (raw.includes('debt') || raw.includes('loan') || raw.includes('borrow')) return 'finance';
  if (raw.includes('meal') || raw.includes('eat')) return 'meal';
  return raw;
}

function getHoustonHour(date: Date): number {
  const formatted = new Intl.DateTimeFormat('en-US', {
    timeZone: HOUSTON_TIMEZONE,
    hour: 'numeric',
    hour12: false,
  }).format(date);
  const parsed = Number(formatted);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(23, Math.floor(parsed)));
}

function formatHoustonNow(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: HOUSTON_TIMEZONE,
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date);
}

function formatHoustonDate(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: HOUSTON_TIMEZONE,
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(date);
}

function formatHoustonWeekday(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: HOUSTON_TIMEZONE,
    weekday: 'long',
  }).format(date);
}

function formatHoustonTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '--:--';
  return formatHoustonNow(date);
}

function formatSecondsRemaining(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const hh = Math.floor(seconds / 3600);
  const mm = Math.floor((seconds % 3600) / 60);
  const ss = seconds % 60;
  if (hh > 0) {
    return `${hh}h ${String(mm).padStart(2, '0')}m ${String(ss).padStart(2, '0')}s`;
  }
  return `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
}

function formatMinutesLabel(totalMinutes: number): string {
  const rounded = Math.max(0, Math.floor(totalMinutes));
  if (rounded >= 60) {
    const hours = Math.floor(rounded / 60);
    const minutes = rounded % 60;
    return `${hours}h ${String(minutes).padStart(2, '0')}m`;
  }
  return `${rounded} min`;
}

function formatUnitButtonLabel(units: number): string {
  const safeUnits = Math.max(0, Math.round(Number(units) || 0));
  return `${safeUnits}u`;
}

function formatTimedUnitRateLabel(units = 1): string {
  const safeUnits = Math.max(0, Math.round(Number(units) || 0));
  return `${safeUnits}u/${BALANCE.REALTIME.MINUTES_PER_UNIT}m`;
}

function shiftWindowLabel(workState?: {
  is_weekend?: boolean | null;
  scheduled_shift_window_label?: string | null;
  testing_mode?: {
    enabled?: boolean | null;
    shift_length_label?: string | null;
  } | null;
} | null): string {
  if (workState?.is_weekend) return 'Weekend - no required shift';
  const testingMode = workState?.testing_mode;
  const testingShiftLabel = String(testingMode?.shift_length_label || '').trim();
  if (testingMode?.enabled && testingShiftLabel) {
    return `On-demand - ${testingShiftLabel}`;
  }
  return workState?.scheduled_shift_window_label || 'No scheduled window';
}

type RideshareMode = 'morning_peak' | 'midday' | 'evening_peak' | 'night';

function getRideshareMode(hour: number): RideshareMode {
  if (hour >= 6 && hour < 9) return 'morning_peak';
  if (hour >= 9 && hour < 16) return 'midday';
  if (hour >= 16 && hour < 19) return 'evening_peak';
  if (hour >= 20 || hour < 1) return 'night';
  return 'midday';
}

function formatRideshareMode(mode: RideshareMode): string {
  if (mode === 'morning_peak') return 'Morning Peak';
  if (mode === 'evening_peak') return 'Evening Peak';
  if (mode === 'night') return 'Night';
  return 'Midday';
}

function getRideshareTripPreview(
  mode: RideshareMode,
  trips: number,
  options?: {
  payMinPerTrip?: number;
  payMaxPerTrip?: number;
  stressModifier?: number;
},
): {
  payMin: number;
  payMax: number;
  stress: number;
  health: number;
} {
  const stressModifier = Number(options?.stressModifier || 0);
  if (Number.isFinite(options?.payMinPerTrip) && Number.isFinite(options?.payMaxPerTrip)) {
    let baseStress = 2;
    let baseHealth = -1;
    if (mode === 'night') {
      baseStress = 4;
      baseHealth = -3;
    } else if (mode === 'morning_peak' || mode === 'evening_peak') {
      baseStress = 5;
    }
    return {
      payMin: trips * Number(options?.payMinPerTrip || 0),
      payMax: trips * Number(options?.payMaxPerTrip || 0),
      stress: trips * Math.max(1, baseStress + stressModifier),
      health: trips * baseHealth,
    };
  }
  if (mode === 'night') {
    return { payMin: trips * 22, payMax: trips * 35, stress: trips * Math.max(1, 4 + stressModifier), health: trips * -3 };
  }
  if (mode === 'morning_peak' || mode === 'evening_peak') {
    return { payMin: trips * 18, payMax: trips * 28, stress: trips * Math.max(1, 5 + stressModifier), health: trips * -1 };
  }
  return { payMin: trips * 12, payMax: trips * 20, stress: trips * Math.max(1, 2 + stressModifier), health: trips * -1 };
}

function sanitizeRideShareReason(reason: string | null | undefined): string {
  const normalized = String(reason || '').trim();
  if (!normalized) return 'Ride share unavailable right now.';
  if (normalized.toLowerCase().includes('not authenticated')) {
    return 'Ride share is unavailable right now.';
  }
  return normalized;
}

function stripUnavailablePrefix(reason: string | null | undefined): string {
  const normalized = String(reason || '').trim();
  if (!normalized) return '';
  return normalized.replace(/^Unavailable:\s*/i, '').trim();
}

interface DerivedRideshareState {
  canRideshare: boolean;
  status: string;
  reason: string;
  blockReasonCode: string | null;
  blockReasonValue: number | null;
}

function deriveRideshareState(options: {
  sessionStatus: 'active' | 'ended';
  hasSideIncomeAction: boolean;
  autoClockingOut: boolean;
  backendShiftActive: boolean;
  daySettled: boolean;
  rideshareState: {
    can_rideshare: boolean;
    status: string;
    reason: string;
    block_reason?: string | null;
    block_reason_code?: string | null;
    block_reason_value?: number | null;
    rideshare_allowed_here?: boolean;
  } | null;
  currentStress: number;
  currentHealth: number;
  stressThreshold: number;
  healthThreshold: number;
  rideshareRemainingTrips: number;
  rideshareHoursRemainingToday: number;
  shiftEndLabel: string;
}): DerivedRideshareState {
  const {
    sessionStatus,
    hasSideIncomeAction,
    autoClockingOut,
    backendShiftActive,
    daySettled,
    rideshareState,
    currentStress,
    currentHealth,
    stressThreshold,
    healthThreshold,
    rideshareRemainingTrips,
    rideshareHoursRemainingToday,
    shiftEndLabel,
  } = options;

  if (sessionStatus !== 'active') {
    return {
      canRideshare: false,
      status: 'day_ended',
      reason: 'Day ended.',
      blockReasonCode: 'day_ended',
      blockReasonValue: null,
    };
  }
  if (!hasSideIncomeAction) {
    return {
      canRideshare: false,
      status: 'unavailable',
      reason: 'Ride share action is not available yet.',
      blockReasonCode: 'action_unavailable',
      blockReasonValue: null,
    };
  }
  if (autoClockingOut) {
    return {
      canRideshare: false,
      status: 'shift_sync',
      reason: 'Auto-finalizing shift. Ride share unlocks after sync.',
      blockReasonCode: 'shift_sync',
      blockReasonValue: null,
    };
  }
  if (backendShiftActive) {
    return {
      canRideshare: false,
      status: 'shift_active',
      reason: `Action unavailable during active shift. Available after ${shiftEndLabel}.`,
      blockReasonCode: 'shift_active',
      blockReasonValue: null,
    };
  }
  if (!rideshareState) {
    return {
      canRideshare: false,
      status: 'syncing',
      reason: 'Ride share status syncing...',
      blockReasonCode: 'syncing',
      blockReasonValue: null,
    };
  }
  if (String(rideshareState.status || '') === 'shift_active' && !rideshareState.can_rideshare) {
    const reason = sanitizeRideShareReason(rideshareState.block_reason || rideshareState.reason);
    return {
      canRideshare: false,
      status: 'shift_active',
      reason,
      blockReasonCode: rideshareState.block_reason_code || 'shift_active',
      blockReasonValue: rideshareState.block_reason_value ?? null,
    };
  }
  if (daySettled || rideshareHoursRemainingToday <= 0) {
    return {
      canRideshare: false,
      status: 'not_enough_time',
      reason: 'Not enough time left today for rideshare.',
      blockReasonCode: 'not_enough_time',
      blockReasonValue: rideshareHoursRemainingToday,
    };
  }
  if (rideshareRemainingTrips <= 0) {
    return {
      canRideshare: false,
      status: 'limit_reached',
      reason: 'Unavailable: daily trip limit reached.',
      blockReasonCode: 'limit_reached',
      blockReasonValue: 0,
    };
  }
  if (currentStress >= stressThreshold) {
    return {
      canRideshare: false,
      status: 'stress_high',
      reason: `Unavailable: stress too high (${Math.round(currentStress)}/100).`,
      blockReasonCode: 'stress_high',
      blockReasonValue: Math.round(currentStress),
    };
  }
  if (currentHealth < healthThreshold) {
    return {
      canRideshare: false,
      status: 'health_low',
      reason: `Unavailable: health too low (${Math.round(currentHealth)}/100).`,
      blockReasonCode: 'health_low',
      blockReasonValue: Math.round(currentHealth),
    };
  }
  if (rideshareState.rideshare_allowed_here === false) {
    return {
      canRideshare: false,
      status: 'location_restricted',
      reason: sanitizeRideShareReason(rideshareState.block_reason || rideshareState.reason),
      blockReasonCode: rideshareState.block_reason_code || 'location_restricted',
      blockReasonValue: rideshareState.block_reason_value ?? null,
    };
  }
  if (!rideshareState.can_rideshare) {
    return {
      canRideshare: false,
      status: String(rideshareState.status || 'blocked'),
      reason: sanitizeRideShareReason(rideshareState.block_reason || rideshareState.reason),
      blockReasonCode: rideshareState.block_reason_code || String(rideshareState.status || 'blocked'),
      blockReasonValue: rideshareState.block_reason_value ?? null,
    };
  }
  return {
    canRideshare: true,
    status: 'available',
    reason: sanitizeRideShareReason(rideshareState.reason || 'Ride Share is available now.'),
    blockReasonCode: null,
    blockReasonValue: null,
  };
}

function sanitizeSalaryText(value: string | null | undefined, fallback: string): string {
  const normalized = String(value || fallback).replace(/Â·/g, '-').trim();
  return normalized || fallback;
}

function ledgerActivitySummary(entry: { category?: string; description?: string; amount?: number }): {
  title: string;
  detail: string;
  category: TimelineNote['category'];
} {
  const categoryKey = String(entry.category || '').toLowerCase();
  const amount = Number(entry.amount || 0);
  const amountLabel = `${amount > 0 ? '+' : ''}${formatMoney(amount)}`;
  if (categoryKey === 'salary') {
    return {
      title: 'Salary income',
      detail: `${amountLabel} posted from main job salary.`,
      category: 'work',
    };
  }
  if (categoryKey === 'ride_share') {
    return {
      title: 'Rideshare income',
      detail: `${amountLabel} from ride share trips.`,
      category: 'rideshare',
    };
  }
  if (categoryKey.includes('food') || categoryKey.includes('meal') || categoryKey.includes('dinner')) {
    return {
      title: 'Food expense',
      detail: `${amountLabel} for meal spending.`,
      category: 'meal',
    };
  }
  if (categoryKey.includes('debt')) {
    return {
      title: 'Debt payment',
      detail: `${amountLabel} applied to debt obligations.`,
      category: 'finance',
    };
  }
  return {
    title: String(entry.description || 'Ledger update'),
    detail: `${amountLabel} (${categoryKey.replace(/_/g, ' ') || 'general'})`,
    category: 'system',
  };
}

const INTERACTION_DIAGNOSTICS_ENABLED =
  __DEV__
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === 'true'
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === '1';

const LOAN_AMOUNTS = [100, 200, 300, 500] as const;

export default function DashboardScreen() {
  useScreenTimer('dashboard');
  const loop = useGameplayLoop();
  const loopPlayerId = loop.playerId;
  const refreshGameplay = loop.refresh;
  const setLoopFeedback = loop.setFeedback;
  const onboarding = useOnboarding();
  const guidedDashboardActive = onboarding.isActive && onboarding.currentStep?.route === 'dashboard';

  // Stats
  const stats = loop.dashboard?.stats;
  const authoritativeState = loop.authoritativeState;
  const authoritativePlayerState = authoritativeState?.player_state || null;
  const netCashFlow = loop.economyState.netCashFlow ?? 0;
  const pressureLabel = loop.expenseDebt.debtPressure.charAt(0).toUpperCase()
    + loop.expenseDebt.debtPressure.slice(1);
  const criticalDebtPressure = String(loop.expenseDebt.debtPressure || '').toLowerCase() === 'critical';
  const cash = authoritativePlayerState?.cash ?? stats?.cash_xgp ?? 0;
  const baseStress = stats?.stress ?? authoritativePlayerState?.stress ?? 0;
  const baseHealth = stats?.health ?? authoritativePlayerState?.health ?? 100;
  const debt = authoritativePlayerState?.debt ?? loop.expenseDebt?.debtAmount ?? stats?.debt_xgp ?? 0;
  const cashTone: 'positive' | 'neutral' | 'danger' = cash > 0 ? 'positive' : cash < 0 ? 'danger' : 'neutral';
  const stress = Math.max(0, baseStress - loop.dailySession.stressRecoveredToday);
  const health = Math.max(0, Math.min(100, baseHealth + loop.dailySession.healthGainedToday));

  const [houstonNow, setHoustonNow] = useState(() => new Date());
  const [autoClockingOut, setAutoClockingOut] = useState(false);
  const [timelineNotes, setTimelineNotes] = useState<TimelineNote[]>([]);
  const [rideshareResultCard, setRideshareResultCard] = useState<{
    actionId: string;
    trips: number;
    earned: number;
    stressDelta: number;
    healthDelta: number;
    mode: string;
  } | null>(null);
  const previousWorkStateRef = useRef<{
    completedAt: string | null;
    shiftEndsAt: string | null;
    active: boolean;
  } | null>(null);
  const rideshareResultAnim = useRef(new Animated.Value(0)).current;
  const lastRideshareActionIdRef = useRef<string | null>(null);
  const autoFinalizeAttemptRef = useRef<{
    shiftEndsAt: string;
    attemptedAtMs: number;
  } | null>(null);

  useEffect(() => {
    const timer = setInterval(() => {
      setHoustonNow(new Date());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useFocusEffect(useCallback(() => {
    void refreshGameplay({ silent: true });
    return undefined;
  }, [refreshGameplay]));

  useEffect(() => {
    const latest = [...loop.dailySession.actionsTakenToday]
      .reverse()
      .find((entry) => (
        canonicalDashboardActionKey(String(entry.action_key || '')) === 'side_income'
        && entry.success
      ));
    if (!latest || latest.id === lastRideshareActionIdRef.current) return;
    lastRideshareActionIdRef.current = latest.id;
    const earned = Number(
      latest.raw_result?.earned
      ?? latest.raw_result?.net_income_xgp
      ?? latest.impact_snapshot?.cash_delta_xgp
      ?? 0,
    );
    const stressDelta = Number(
      latest.raw_result?.stress_change
      ?? latest.raw_result?.stress_delta
      ?? latest.impact_snapshot?.stress_delta
      ?? 0,
    );
    const healthDelta = Number(
      latest.raw_result?.health_change
      ?? latest.raw_result?.health_delta
      ?? latest.impact_snapshot?.health_delta
      ?? 0,
    );
    const trips = Number(latest.raw_result?.trips_completed ?? latest.raw_result?.trips ?? 1) || 1;
    const mode = String(latest.raw_result?.mode_used || latest.raw_result?.mode || '');
    setRideshareResultCard({
      actionId: latest.id,
      trips,
      earned,
      stressDelta,
      healthDelta,
      mode,
    });

    rideshareResultAnim.stopAnimation();
    rideshareResultAnim.setValue(0);
    Animated.sequence([
      Animated.timing(rideshareResultAnim, {
        toValue: 1,
        duration: 180,
        useNativeDriver: false,
      }),
      Animated.timing(rideshareResultAnim, {
        toValue: 0,
        duration: 800,
        useNativeDriver: false,
      }),
    ]).start();
  }, [loop.dailySession.actionsTakenToday, rideshareResultAnim]);

  const rideshareResultGlow = rideshareResultAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, 0.24],
  });

  // Work / Job selection
  const allActionItems = useMemo(() => {
    if (!loop.actionHub) return [];
    return [
      ...(loop.actionHub.recommended_actions || []),
      ...(loop.actionHub.available_actions || []),
      ...(loop.actionHub.blocked_actions || []),
    ];
  }, [loop.actionHub]);

  const workShiftAction = useMemo(
    () => allActionItems.find((action) => canonicalDashboardActionKey(String(action.action_key || '')) === 'work_shift') || null,
    [allActionItems],
  );
  const sideIncomeAction = useMemo(
    () => allActionItems.find((action) => canonicalDashboardActionKey(String(action.action_key || '')) === 'side_income') || null,
    [allActionItems],
  );
  const workState = authoritativeState?.work_state || loop.dashboard?.work_state || loop.actionHub?.work_state || null;
  const backendHoustonDate = workState?.current_houston_time
    ? new Date(workState.current_houston_time)
    : houstonNow;
  const economyOverview = loop.dashboard?.economy_risk_overview || null;
  const macroConditions = Array.isArray(economyOverview?.macro_conditions)
    ? economyOverview.macro_conditions
    : [];
  const opportunitySignals = Array.isArray(economyOverview?.opportunity_signals)
    ? economyOverview.opportunity_signals
    : [];
  const riskBadges = Array.isArray(economyOverview?.risk_badges)
    ? economyOverview.risk_badges
    : [];
  const findSignal = (signals: EconomySignalChip[], key: string): EconomySignalChip | null => (
    signals.find((entry) => String(entry.key || '').trim().toLowerCase() === key) || null
  );
  const needsDinnerReminder = Boolean(workState?.needs_dinner_reminder);
  const dinnerReminderMessage = String(
    workState?.dinner_reminder_message || 'Dinner not completed. Eat now to avoid health loss.',
  );
  const dinnerResolvedToday = Boolean(workState?.dinner_resolved_today);
  const backendShiftActive = Boolean(workState?.is_on_shift ?? workState?.main_shift_active_flag);
  const workStatus = String(
    workState?.work_status
    || workState?.current_action_state
    || (backendShiftActive ? 'on_shift' : 'off_shift'),
  ).trim();
  const backendShiftCompleted = Boolean(
    workState
    && (workStatus === 'off_shift_after_work' || workState.shift_status === 'completed')
    && !backendShiftActive
    && Number(workState.main_shift_hours_today || 0) > 0,
  );
  const backendShiftEndsAtMs = workState?.shift_ends_at ? new Date(workState.shift_ends_at).getTime() : Number.NaN;
  const backendShiftCompletedAt = workState?.shift_completed_at || null;
  const shiftRemainingSeconds = Number.isFinite(backendShiftEndsAtMs) && backendShiftActive
    ? Math.max(0, Math.floor((backendShiftEndsAtMs - houstonNow.getTime()) / 1000))
    : 0;
  const shiftRemainingLabel = formatSecondsRemaining(shiftRemainingSeconds);
  const testingMode = workState?.testing_mode || null;
  const testingModeEnabled = Boolean(testingMode?.enabled);
  const testingShiftLabel = String(
    testingMode?.shift_length_label
    || (SHIFT_SHORT_MODE ? '15 minutes' : 'Standard shift schedule'),
  );
  const shiftEndLabel = String(
    workState?.shift_end_time_label
    || (workState?.shift_ends_at ? `${formatHoustonNow(new Date(workState.shift_ends_at))} CT` : '5:00 PM CT'),
  );
  const scheduledShiftWindowLabel = shiftWindowLabel(workState);
  const shiftScheduleCardLabel = testingModeEnabled && !backendShiftActive ? 'Shift timer' : 'Shift end (CT)';
  const shiftScheduleCardValue = backendShiftActive
    ? shiftEndLabel
    : testingModeEnabled
      ? `Clock in + ${testingShiftLabel}`
      : `${workState?.scheduled_shift_end_label || '5:00 PM'} CT`;
  const shiftScheduleCardNote = testingModeEnabled && !backendShiftActive
    ? 'Starts when you clock in.'
    : 'Houston local time.';
  const shiftEndedLabel = String(
    workState?.shift_completed_time_label
    || workState?.shift_end_time_label
    || '',
  ).trim();
  const lastCompletedShift = workState?.last_completed_shift || null;
  const salaryEarnedToday = Number(workState?.salary_earned_today || 0);
  const salaryEarnedYesterday = Number(workState?.salary_earned_yesterday || 0);
  const workPayModelLabel = String(workState?.pay_model_label || 'Paid daily after shift completion');
  const salaryPaymentStatus = String(workState?.salary_payment_status || '').toLowerCase();
  const salaryStatusLabel = sanitizeSalaryText(workState?.salary_status_label, 'No salary posted');
  const salaryStatusMessage = sanitizeSalaryText(workState?.salary_status_message, 'No salary posted yet.');
  const currentSalaryAudit = workState?.current_shift_salary_audit || null;
  const lastSalaryPosted = workState?.last_salary_posted || null;
  const recentSalaryAudits = Array.isArray(workState?.recent_salary_audits)
    ? workState.recent_salary_audits
    : [];
  const salaryStatusTone: 'neutral' | 'info' | 'warning' | 'danger' | 'positive' = (
    salaryPaymentStatus === 'posted'
      ? 'positive'
      : salaryPaymentStatus === 'failed'
        ? 'danger'
        : salaryPaymentStatus === 'pending'
          ? 'warning'
          : workState?.missed_shift_today
            ? 'warning'
            : 'neutral'
  );
  const lastSalaryPostedLabel = lastSalaryPosted
    ? `${lastSalaryPosted.final_salary_paid > 0 ? '+' : ''}${formatMoney(lastSalaryPosted.final_salary_paid)}`
    : '--';
  const lastSalaryPostedNote = lastSalaryPosted
    ? `Job: ${lastSalaryPosted.job_display_name || lastSalaryPosted.job_key || 'Current job'} | ${lastSalaryPosted.transaction_confirmed ? 'Transaction confirmed' : 'Awaiting confirmation'}`
    : 'No completed salary posting yet.';
  const currentHoustonTimeLabel = String(
    workState?.current_houston_time_label
    || `${formatHoustonNow(houstonNow)} CT`,
  );
  const currentHoustonDateLabel = String(
    workState?.current_houston_date_label
    || formatHoustonDate(backendHoustonDate),
  );
  const currentHoustonDayOfWeekLabel = String(
    workState?.day_of_week
    || formatHoustonWeekday(backendHoustonDate),
  );
  const shiftsCompletedToday = Number(testingMode?.shifts_completed_today ?? workState?.shifts_completed_today ?? 0);
  const maxDailyMainShifts = Number(testingMode?.max_daily_main_shifts || 1);
  const overtimeShiftAvailable = Boolean(testingMode?.overtime_shift_available);
  const overtimeUsedToday = Boolean(testingMode?.overtime_used_today);
  const weekendRideshareOnly = Boolean(testingMode?.weekend_rideshare_only);
  const nextShiftNumberAvailable = Number(testingMode?.next_shift_number_available || 0);
  const dailyShiftLimitReached = Boolean(testingMode?.daily_shift_limit_reached);
  const rideshareCapToday = Number(testingMode?.rideshare_cap_today || 0);
  const marketDataMessage = String(workState?.market_data_message || '').trim();
  const dayRolloverLabel = String(workState?.day_rollover_time_label || '12:00 AM CT');
  const autoRolloverRecapLines = Array.isArray(workState?.auto_rollover_recap_lines)
    ? workState.auto_rollover_recap_lines.filter(Boolean)
    : [];
  const deliveryDemandSignal = findSignal(opportunitySignals, 'delivery_demand');
  const rideshareDemandSignal = findSignal(opportunitySignals, 'rideshare_demand');
  const fuelPressureSignal = findSignal(macroConditions, 'fuel_pressure');
  const foodInflationSignal = findSignal(macroConditions, 'food_inflation');
  const unemploymentSignal = findSignal(macroConditions, 'unemployment_pressure');
  const confidenceSignal = findSignal(macroConditions, 'consumer_mood');
  const supplySignal = findSignal(macroConditions, 'supply_chain_stress');
  const workDemandSignal = deliveryDemandSignal || rideshareDemandSignal;
  const workDemandLabel = workDemandSignal
    ? `${formatRiskLevel(workDemandSignal.level)}${workDemandSignal.value_text ? ` - ${workDemandSignal.value_text}` : ''}`
    : 'Moderate';
  const workIncomeVisibilityLabel = backendShiftActive
    ? 'Shift active - salary pending until completion.'
    : salaryStatusMessage;
  const nextShiftLabel = weekendRideshareOnly
    ? 'Weekend rideshare-only'
    : overtimeShiftAvailable
      ? `Overtime available (${Number(testingMode?.second_shift_overtime_multiplier || 1.5).toFixed(1)}x)`
      : dailyShiftLimitReached
        ? 'Daily shift limit reached'
        : maxDailyMainShifts > 1 && nextShiftNumberAvailable > 0
          ? `Shift ${nextShiftNumberAvailable}/${maxDailyMainShifts} available`
          : 'Standard shift available';

  useEffect(() => {
    setAutoClockingOut(false);
    setTimelineNotes([]);
    previousWorkStateRef.current = null;
    autoFinalizeAttemptRef.current = null;
  }, [loop.dailySession.currentDay]);

  const appendTimelineNote = (note: Omit<TimelineNote, 'id'>) => {
    const id = `${note.timestampIso}_${Math.random().toString(36).slice(2, 8)}`;
    setTimelineNotes((prev) => [...prev, { ...note, id }]);
  };

  const houstonHour = getHoustonHour(houstonNow);

  const workExecutionGuard = workShiftAction
    ? loop.dailySession.canExecuteAction(workShiftAction)
    : { allowed: false, reason: 'No shift action available.', timeCostUnits: 0 };

  const canClockIn = Boolean(
    workShiftAction
    && !backendShiftActive
    && !autoClockingOut
    && loop.dailySession.sessionStatus === 'active'
    && workExecutionGuard.allowed
  );

  const clockInBlocker = useMemo(() => {
    if (backendShiftActive) return `Shift already active until ${shiftEndLabel}.`;
    if (loop.dailySession.sessionStatus !== 'active') return 'Day already ended.';
    if (!workShiftAction) return 'No work shift is available right now.';
    if (!workExecutionGuard.allowed) return workExecutionGuard.reason || 'Cannot start shift right now.';
    return null;
  }, [
    backendShiftActive,
    loop.dailySession.sessionStatus,
    shiftEndLabel,
    workExecutionGuard.allowed,
    workExecutionGuard.reason,
    workShiftAction,
  ]);

  const gamePhaseLabel = useMemo(() => (
    String(
      workState?.phase_status_label
      || (workState?.is_weekend ? 'Weekend' : 'Weekday'),
    )
  ), [workState?.is_weekend, workState?.phase_status_label]);

  const dayLabel = loop.dailySession.currentDay || loop.dailyProgression.currentGameDay || 1;
  const recoveryState = authoritativeState?.recovery_state || workState?.recovery_state || null;
  const passiveRecoverySummary = recoveryState?.passive_off_hours_recovery || null;
  const weekendRecoverySummary = recoveryState?.weekend_recovery || null;
  const rideshareState = authoritativeState?.rideshare_state || workState?.rideshare_state || null;
  const currentLocationLabel = String(
    workState?.current_location_label
    || rideshareState?.current_location_label
    || 'Home',
  );
  const currentLocationRegion = String(
    workState?.current_location_region
    || rideshareState?.current_location_region
    || '',
  );
  const rideshareDemandBonusPct = Number(rideshareState?.demand_bonus_pct || 0);
  const rideshareStressModifier = Number(rideshareState?.stress_delta_modifier || 0);
  const ridesharePayMinPerTrip = Number(rideshareState?.estimated_pay_min_per_trip || Number.NaN);
  const ridesharePayMaxPerTrip = Number(rideshareState?.estimated_pay_max_per_trip || Number.NaN);
  const rideshareMode = (
    rideshareState?.mode
      ? String(rideshareState.mode)
      : getRideshareMode(houstonHour)
  ) as RideshareMode;
  const rideshareTripsToday = rideshareState?.trips_today ?? Math.max(0, Math.round(workState?.side_income_hours_today ?? 0));
  const rideshareDailyCap = rideshareState?.max_trips ?? Math.max(1, rideshareCapToday || Number(BALANCE.ACTION_CAPS.side_income || 6));
  const rideshareRemainingTrips = rideshareState?.remaining_trips ?? Math.max(0, rideshareDailyCap - rideshareTripsToday);
  const rideshareHoursRemainingToday = rideshareState?.hours_remaining_today ?? Math.max(0, Number(workState?.hours_available || 0));
  const rideshareTimeCostPerTrip = Math.max(1, Number(rideshareState?.time_cost_per_trip_units || 1));
  const rideshareStressThreshold = Math.max(1, Number(rideshareState?.stress_threshold || BALANCE.RIDESHARE.MAX_STRESS));
  const rideshareHealthThreshold = Math.max(0, Number(rideshareState?.health_threshold || BALANCE.RIDESHARE.MIN_HEALTH));
  const rideshareEarnedToday = useMemo(
    () => {
      const backendEarned = Number(workState?.rideshare_earned_today ?? Number.NaN);
      if (Number.isFinite(backendEarned) && backendEarned >= 0) {
        return backendEarned;
      }
      const transactionEarned = (loop.dailyActivity?.transactions || [])
        .filter((entry) => String(entry.category || '').toLowerCase() === 'ride_share' && Number(entry.amount) > 0)
        .reduce((sum, entry) => sum + Number(entry.amount || 0), 0);
      if (Number.isFinite(transactionEarned) && transactionEarned > 0) {
        return transactionEarned;
      }
      return loop.dailySession.actionsTakenToday
        .filter((entry) => canonicalDashboardActionKey(String(entry.action_key || '')) === 'side_income' && entry.success)
        .reduce((sum, entry) => {
          const earnedRaw = Number(
            (entry.raw_result?.earned ?? entry.raw_result?.net_income_xgp ?? entry.impact_snapshot?.cash_delta_xgp) || 0,
          );
          return sum + (Number.isFinite(earnedRaw) ? earnedRaw : 0);
        }, 0);
    },
    [loop.dailyActivity?.transactions, loop.dailySession.actionsTakenToday, workState?.rideshare_earned_today],
  );
  const rideshareEligibilitySnapshot = useMemo(() => (
    rideshareState
      ? {
        can_rideshare: Boolean(rideshareState.can_rideshare),
        status: String(rideshareState.status || 'unavailable'),
        reason: String(rideshareState.reason || rideshareState.block_reason || 'Ride share unavailable right now.'),
        block_reason: rideshareState.block_reason ?? null,
        block_reason_code: rideshareState.block_reason_code ?? null,
        block_reason_value: rideshareState.block_reason_value ?? null,
        rideshare_allowed_here: rideshareState.rideshare_allowed_here ?? undefined,
      }
      : null
  ), [rideshareState]);

  const rideshareDerivedState = useMemo(() => deriveRideshareState({
    sessionStatus: loop.dailySession.sessionStatus,
    hasSideIncomeAction: Boolean(sideIncomeAction),
    autoClockingOut,
    backendShiftActive,
    daySettled: Boolean(workState?.day_settled),
    rideshareState: rideshareEligibilitySnapshot,
    currentStress: stress,
    currentHealth: health,
    stressThreshold: rideshareStressThreshold,
    healthThreshold: rideshareHealthThreshold,
    rideshareRemainingTrips,
    rideshareHoursRemainingToday,
    shiftEndLabel,
  }), [
    autoClockingOut,
    backendShiftActive,
    health,
    loop.dailySession.sessionStatus,
    rideshareHealthThreshold,
    rideshareHoursRemainingToday,
    rideshareRemainingTrips,
    rideshareEligibilitySnapshot,
    rideshareStressThreshold,
    shiftEndLabel,
    sideIncomeAction,
    stress,
    workState?.day_settled,
  ]);
  const rideshareBlockReason = rideshareDerivedState.reason;
  const rideshareStatusLabel = rideshareDerivedState.reason;
  const postShiftBannerMessage = backendShiftCompleted
    ? (
      rideshareDerivedState.canRideshare
        ? 'Shift completed - You are now off shift. Ride share available now.'
        : `Shift completed - Rideshare blocked: ${stripUnavailablePrefix(rideshareDerivedState.reason) || 'Unavailable right now.'}`
    )
    : '';
  const busyActionKey = canonicalDashboardActionKey(String(loop.busyActionKey || ''));
  const runningSideIncome = loop.executingAction && busyActionKey === 'side_income';
  const runningWorkAction = loop.executingAction && busyActionKey === 'work_shift';

  const getRideShareDisabledReason = useCallback((requestedTrips: number): string | null => {
    if (!sideIncomeAction) return 'Ride share action is not available yet.';
    if (loop.dailySession.sessionStatus !== 'active') return 'Day ended.';
    if (autoClockingOut) return 'Auto-finalizing shift. Ride share unlocks after sync.';
    if (runningSideIncome || loop.executingAction) return 'Another action is running.';
    if (!rideshareState) return 'Ride share status syncing...';
    if (!rideshareDerivedState.canRideshare) return rideshareDerivedState.reason;
    if (requestedTrips > rideshareRemainingTrips) {
      if (rideshareRemainingTrips <= 0) {
        return rideshareDerivedState.reason || sanitizeRideShareReason(rideshareState.reason || 'Daily ride share limit reached.');
      }
      return `Only ${rideshareRemainingTrips} ${rideshareRemainingTrips === 1 ? 'trip' : 'trips'} remaining today.`;
    }
    if (requestedTrips > rideshareHoursRemainingToday) {
      return 'Not enough time remaining for that trip bundle.';
    }
    return null;
  }, [
    autoClockingOut,
    loop.dailySession.sessionStatus,
    loop.executingAction,
    rideshareHoursRemainingToday,
    rideshareRemainingTrips,
    rideshareDerivedState.canRideshare,
    rideshareDerivedState.reason,
    rideshareState,
    runningSideIncome,
    sideIncomeAction,
  ]);

  const rideshareDisableReasonsByTrip = useMemo(() => ({
    1: getRideShareDisabledReason(1),
    3: getRideShareDisabledReason(3),
    5: getRideShareDisabledReason(5),
  }), [getRideShareDisabledReason]);

  const rideshareAvailable = rideshareDerivedState.canRideshare && !rideshareDisableReasonsByTrip[1];

  const jobMarket = workState?.job_market || null;
  const currentJobKey = String(
    authoritativeState?.current_job_key
    || workState?.authoritative_current_job_id
    || workState?.active_shift_job_id
    || workState?.scheduled_shift_job_id
    || loop.actionHub?.debug_meta?.current_job_key
    || loop.dashboard?.stats?.current_job
    || '',
  ).trim();
  const currentJobDisplayName = String(
    authoritativeState?.current_job_label
    || workState?.current_job_display_name
    || loop.dashboard?.stats?.current_job_display
    || (currentJobKey ? currentJobKey.replace(/_/g, ' ') : 'No job selected'),
  ).trim();
  const jobProgress = loop.dashboard?.job_progress || null;
  const currentJobProgression = workState?.current_job_progression || jobProgress || null;
  const progressionFeedback = workState?.job_progression_feedback || null;
  const jobLevelMax = Math.max(1, Number(currentJobProgression?.max_job_level || 2));
  const jobLevel = Math.max(
    1,
    Math.min(
      jobLevelMax,
      Number(workState?.current_job_level || currentJobProgression?.job_level || currentJobProgression?.skill_level || 1),
    ),
  );
  const jobXp = Math.max(0, Number(currentJobProgression?.job_xp || 0));
  const jobXpToNext = Math.max(0, Number(currentJobProgression?.job_xp_to_next_level || 0));
  const liveJobXp = jobXp + loop.dailySession.skillProgressGainedToday;
  const promotionTier = String(currentJobProgression?.promotion_tier || 'Junior');
  const projectedNextMonthlyPay = Number(currentJobProgression?.estimated_next_level_monthly_salary_xgp || 0);
  const projectedSalaryIncreasePct = Number(currentJobProgression?.next_level_salary_increase_pct || 3);
  const jobLevelDetail = jobXpToNext <= 0
    ? 'Senior - max level reached'
    : `${Math.round(liveJobXp)} / ${Math.round(jobXpToNext)} XP to next`;
  const employerLabel = String(
    currentJobProgression?.position_title
    || currentJobProgression?.employer_company_name
    || '',
  ).trim();
  const hasStarterJobSelected = Boolean(
    jobMarket?.has_main_job
    ?? loop.actionHub?.debug_meta?.has_starter_job_selected
    ?? currentJobKey,
  );
  const firstSessionFlag = Boolean(
    loop.dashboard?.debug_meta?.new_player_first_session
    ?? loop.actionHub?.debug_meta?.new_player_first_session
    ?? false,
  );
  const showJobMarket = Boolean(
    (jobMarket?.jobs && jobMarket.jobs.length > 0)
    || firstSessionFlag
    || !hasStarterJobSelected,
  );
  const endDayDisabled = !loop.dailyProgression.canAdvanceDay || loop.endingDay || backendShiftActive || autoClockingOut;
  const economySummaryLine = String(
    economyOverview?.summary_line
    || 'Market signals are available for today.',
  ).trim();
  const economyMacroItems = [
    { label: 'Fuel pressure', signal: fuelPressureSignal },
    { label: 'Food inflation', signal: foodInflationSignal },
    { label: 'Job market', signal: unemploymentSignal },
    { label: 'Consumer mood', signal: confidenceSignal },
    { label: 'Supply chain', signal: supplySignal },
  ];
  const economyOpportunityItems = [
    { label: 'Rideshare demand', signal: rideshareDemandSignal },
    { label: 'Delivery demand', signal: deliveryDemandSignal },
  ];
  const currentTimedActivity = loop.dailySession.currentActivity;
  const hasActiveTimedActivity = loop.dailySession.hasActiveTimedActivity;
  const mealInProgress = currentTimedActivity === 'eat_meal';
  const activeSessionElapsedLabel = formatMinutesLabel(loop.dailySession.currentActivityElapsedMinutes);
  const nextUnitCountdownLabel = formatMinutesLabel(loop.dailySession.nextUnitCountdownMinutes);
  const mealMinimumRemainingMinutes = Math.max(
    0,
    BALANCE.REALTIME.MEAL_MIN_MINUTES - loop.dailySession.currentActivityElapsedMinutes,
  );
  const idleRecoveryLabel = `1 stress every ${BALANCE.REALTIME.IDLE_STRESS_RECOVERY_MINUTES} min away from the app`;
  const activeRecoveryLabel = `1 stress every ${BALANCE.REALTIME.ACTIVE_STRESS_RECOVERY_MINUTES} min while active`;
  const currentTrainingProgressLabel = `+${loop.dailySession.sessionSkillProgress}`;
  const currentHealthGainLabel = signedWhole(loop.dailySession.sessionHealthGained);
  const currentStressRecoveryLabel = signedWhole(-loop.dailySession.sessionStressRecovered);

  const stopCurrentTimedActivity = useCallback(() => {
    const stopped = loop.dailySession.stopTimedActivity();
    if (!stopped.allowed) {
      loop.setFeedback({
        tone: 'error',
        message: stopped.reason || 'This activity cannot be stopped right now.',
      });
      return;
    }
    loop.setFeedback({
      tone: 'success',
      message: `${loop.dailySession.currentActivityName} stopped.`,
    });
  }, [loop.dailySession, loop]);

  const getTimedActivityDisabledReason = useCallback((activityId: TimedActivityCardId): string | null => {
    if (backendShiftActive || autoClockingOut) {
      return `Action unavailable during active shift. Available after ${shiftEndLabel}.`;
    }
    if (currentTimedActivity === activityId) return null;
    const guard = loop.dailySession.canStartTimedActivity(activityId);
    return guard.allowed ? null : guard.reason;
  }, [autoClockingOut, backendShiftActive, currentTimedActivity, loop.dailySession, shiftEndLabel]);

  const startTimedActivity = useCallback((activityId: TimedActivityCardId) => {
    const disabledReason = getTimedActivityDisabledReason(activityId);
    if (disabledReason) {
      loop.setFeedback({
        tone: 'error',
        message: disabledReason,
      });
      return;
    }

    const started = loop.dailySession.startTimedActivity(activityId);
    if (!started.allowed) {
      loop.setFeedback({
        tone: 'error',
        message: started.reason || 'This activity is unavailable right now.',
      });
      return;
    }

    const preset = TIMED_ACTIVITY_PRESETS.find((entry) => entry.id === activityId);
    loop.setFeedback({
      tone: 'success',
      message: `${preset?.title || 'Activity'} started. Time now deducts over time instead of on button press.`,
    });
  }, [getTimedActivityDisabledReason, loop]);

  useEffect(() => {
    if (!INTERACTION_DIAGNOSTICS_ENABLED) return;
    recordInfo('gameplayLoop', 'Dashboard job market visibility evaluated.', {
      action: 'job_selection_visibility',
      context: {
        playerId: loop.playerId,
        firstSessionFlag,
        showJobMarket,
        jobMarketOptionsCount: jobMarket?.jobs?.length || 0,
        hasStarterJobSelected,
        currentJobKey: currentJobKey || null,
      },
    });
  }, [
    currentJobKey,
    firstSessionFlag,
    hasStarterJobSelected,
    jobMarket?.jobs?.length,
    loop.playerId,
    showJobMarket,
  ]);

  const switchToMarketJob = (job: JobMarketJobSnapshot) => {
    const targetJobKey = String(job.job_key || '').trim().toLowerCase();
    if (!targetJobKey) return;
    if (INTERACTION_DIAGNOSTICS_ENABLED) {
      recordInfo('gameplayLoop', 'Job market switch requested from dashboard.', {
        action: 'dashboard_switch_job_selected',
        context: {
          playerId: loop.playerId,
          targetJobKey,
          currentJobKey: currentJobKey || null,
        },
      });
    }
    const action: DailyActionItem = {
      action_key: 'switch_job',
      title: `Switch to ${job.display_name || targetJobKey.replace(/_/g, ' ')}`,
      description: 'Switch main job from Job Market.',
      status: 'available',
      blockers: [],
      warnings: [],
      tradeoffs: [],
      confidence_level: 'high',
      parameters: {
        new_job_key: targetJobKey,
      },
    };
    void loop.executeAction(action);
  };

  const startMarketTraining = (job: JobMarketJobSnapshot) => {
    const certificationKey = String(job.certification_key || '').trim().toLowerCase();
    if (!certificationKey) return;
    if (INTERACTION_DIAGNOSTICS_ENABLED) {
      recordInfo('gameplayLoop', 'Job market training requested from dashboard.', {
        action: 'dashboard_start_training_selected',
        context: {
          playerId: loop.playerId,
          certificationKey,
          targetJobKey: String(job.job_key || ''),
        },
      });
    }
    const action: DailyActionItem = {
      action_key: 'start_training',
      title: `Start Training: ${job.certification_name || certificationKey.replace(/_/g, ' ')}`,
      description: 'Begin certification training to unlock this job.',
      status: 'available',
      blockers: [],
      warnings: [],
      tradeoffs: [],
      confidence_level: 'medium',
      parameters: {
        certification_key: certificationKey,
      },
    };
    void loop.executeAction(action);
  };

  const actionTimeline = useMemo(() => loop.dailySession.actionsTakenToday.map((entry) => {
    const key = canonicalDashboardActionKey(String(entry.action_key || ''));
    let category: TimelineNote['category'] = 'system';
    if (key === 'work_shift') category = 'work';
    else if (key === 'side_income') category = 'rideshare';
    else if (key === 'recovery_activity' || key === 'rest' || key === 'skill_training' || key === 'start_training') category = 'recovery';
    else if (key === 'meal') category = 'meal';
    else if (key === 'finance') category = 'finance';

    return {
      id: entry.id,
      timestampIso: entry.executed_at,
      title: entry.title,
      detail: entry.result_summary || entry.description || (entry.success ? 'Action completed.' : 'Action failed.'),
      category,
    };
  }), [loop.dailySession.actionsTakenToday]);

  const ledgerTimeline = useMemo(() => (loop.dailyActivity?.transactions || []).map((entry) => {
    const summary = ledgerActivitySummary(entry);
    return {
      id: `ledger_${entry.id}`,
      timestampIso: entry.timestamp || new Date().toISOString(),
      title: summary.title,
      detail: summary.detail,
      category: summary.category,
    };
  }), [loop.dailyActivity?.transactions]);

  const todaysActivity = useMemo(() => {
    const merged = ledgerTimeline.length > 0
      ? [...timelineNotes, ...ledgerTimeline]
      : [...timelineNotes, ...actionTimeline];
    return merged.sort(
      (a, b) => new Date(a.timestampIso).getTime() - new Date(b.timestampIso).getTime(),
    );
  }, [actionTimeline, ledgerTimeline, timelineNotes]);

  const actionHubForDisplay = useMemo(() => {
    if (!loop.actionHub) return null;
    const hiddenKeys = new Set([
      'rest',
      'study',
      'watch_tv',
      'watch_movie',
      'read_book',
      'jogging',
      'eat_meal',
      'skill_training',
      'start_training',
    ]);
    const stripRoutineActions = (actions: DailyActionItem[]) =>
      actions.filter((action) => {
        const rawKey = String(action.action_key || '').trim().toLowerCase();
        const key = canonicalDashboardActionKey(rawKey);
        return key !== 'work_shift'
          && key !== 'side_income'
          && key !== 'recovery_activity'
          && key !== 'rest'
          && key !== 'skill_training'
          && key !== 'start_training'
          && key !== 'meal'
          && !hiddenKeys.has(rawKey);
      });

    return {
      ...loop.actionHub,
      recommended_actions: stripRoutineActions(loop.actionHub.recommended_actions || []),
      available_actions: stripRoutineActions(loop.actionHub.available_actions || []),
      blocked_actions: stripRoutineActions(loop.actionHub.blocked_actions || []),
    };
  }, [loop.actionHub]);
  const diagnosticsTruthItems = useMemo(() => {
    if (!INTERACTION_DIAGNOSTICS_ENABLED || !authoritativeState) return [];
    return [
      {
        label: 'Current job',
        value: currentJobKey || '--',
        note: currentJobDisplayName || 'No job selected',
      },
      {
        label: 'Cash / Debt',
        value: `${formatMoney(cash)} / ${formatMoney(debt)}`,
        note: `Stress ${stress} | Health ${health}`,
      },
      {
        label: 'Rideshare truth',
        value: rideshareDerivedState.canRideshare ? 'Available' : 'Blocked',
        note: rideshareDerivedState.blockReasonCode
          ? `${rideshareDerivedState.blockReasonCode}${rideshareDerivedState.blockReasonValue != null ? ` (${rideshareDerivedState.blockReasonValue})` : ''}`
          : 'none',
      },
      {
        label: 'Trips',
        value: `${rideshareState?.trips_today ?? 0} / ${authoritativeState?.rideshare_state?.trip_cap_today ?? rideshareDailyCap}`,
        note: `${rideshareRemainingTrips} remaining | ${rideshareHoursRemainingToday} units left`,
      },
      {
        label: 'Debt payment',
        value: authoritativeState.debt_payment_state.can_pay_debt ? 'Available' : 'Blocked',
        note: authoritativeState.debt_payment_state.can_pay_debt
          ? `Max ${formatMoney(authoritativeState.debt_payment_state.max_payable_now)}`
          : (authoritativeState.debt_payment_state.block_reason_code || 'unavailable'),
      },
      {
        label: 'Shift start',
        value: authoritativeState.shift_state.can_start_shift ? 'Available' : 'Blocked',
        note: authoritativeState.shift_state.can_start_overtime_shift ? 'Overtime available' : (authoritativeState.shift_state.block_reason_code || 'standard only'),
      },
      {
        label: 'Recovery',
        value: `${authoritativeState.recovery_state.recovery_actions_remaining} left`,
        note: `${authoritativeState.recovery_state.category_used}/${authoritativeState.recovery_state.category_cap} used`,
      },
      {
        label: 'Truth refresh',
        value: authoritativeState.refreshed_at || '--',
        note: `${(authoritativeState.degraded_sections || []).join(', ') || 'No degraded sections'}`,
      },
    ];
  }, [
    authoritativeState,
    cash,
    currentJobDisplayName,
    currentJobKey,
    debt,
    health,
    rideshareDailyCap,
    rideshareDerivedState.blockReasonCode,
    rideshareDerivedState.blockReasonValue,
    rideshareDerivedState.canRideshare,
    rideshareHoursRemainingToday,
    rideshareRemainingTrips,
    rideshareState?.trips_today,
    stress,
  ]);

  const handleClockIn = async () => {
    if (!workShiftAction || !canClockIn) {
      if (clockInBlocker) {
        loop.setFeedback({
          tone: 'error',
          message: clockInBlocker,
        });
      }
      return;
    }

    const ok = await loop.executeAction(workShiftAction);
    if (!ok) return;

    appendTimelineNote({
      timestampIso: new Date().toISOString(),
      title: `Clocked in to ${workShiftAction.title}`,
      detail: `Shift started. Current job: ${currentJobDisplayName}.`,
      category: 'work',
    });
  };

  useEffect(() => {
    const previous = previousWorkStateRef.current;
    if (previous?.active && !backendShiftActive) {
      setAutoClockingOut(false);
      autoFinalizeAttemptRef.current = null;
    }

    if (
      previous
      && previous.completedAt !== backendShiftCompletedAt
      && backendShiftCompletedAt
      && lastCompletedShift
    ) {
      appendTimelineNote({
        timestampIso: backendShiftCompletedAt,
        title: 'Shift completion confirmed',
        detail: (
          `Earned ${formatMoney(lastCompletedShift.earned_cash_xgp)} | `
          + `XP +${Math.round(lastCompletedShift.xp_gained)} | `
          + `Stress ${signedWhole(lastCompletedShift.stress_change)} | `
          + `Health ${signedWhole(lastCompletedShift.health_change)}`
        ),
        category: 'work',
      });
      recordInfo('gameplayLoop', 'Backend returned completed shift state.', {
        action: 'work_state_completed',
        context: {
          playerId: loop.playerId,
          shiftCompletedAt: backendShiftCompletedAt,
          rideshareAvailable: Boolean(workState?.rideshare_state?.can_rideshare),
          earnedCash: lastCompletedShift.earned_cash_xgp,
          xpGained: lastCompletedShift.xp_gained,
        },
      });
    }

    previousWorkStateRef.current = {
      completedAt: backendShiftCompletedAt,
      shiftEndsAt: workState?.shift_ends_at || null,
      active: backendShiftActive,
    };
  }, [
    backendShiftActive,
    backendShiftCompletedAt,
    lastCompletedShift,
    loop.playerId,
    workState?.rideshare_available,
    workState?.shift_ends_at,
  ]);

  useEffect(() => {
    if (!INTERACTION_DIAGNOSTICS_ENABLED || !workState) return;
    recordInfo('gameplayLoop', 'Ride share availability state refreshed.', {
      action: 'rideshare_availability_refresh',
      context: {
        playerId: loopPlayerId,
        shiftStatus: workState.shift_status,
        backendActive: workState.main_shift_active_flag,
        rideshareStatePayload: workState.rideshare_state || null,
        effectiveStress: stress,
        effectiveHealth: health,
        derivedStatus: rideshareDerivedState.status,
        derivedBlockReasonCode: rideshareDerivedState.blockReasonCode,
        derivedBlockReasonValue: rideshareDerivedState.blockReasonValue,
        statusLabelShown: rideshareStatusLabel,
        buttonDisabledReasonRun1: rideshareDisableReasonsByTrip[1],
        buttonDisabledReasonRun3: rideshareDisableReasonsByTrip[3],
        buttonDisabledReasonRun5: rideshareDisableReasonsByTrip[5],
      },
    });
  }, [
    health,
    loopPlayerId,
    rideshareDerivedState.blockReasonCode,
    rideshareDerivedState.blockReasonValue,
    rideshareDerivedState.status,
    rideshareDisableReasonsByTrip,
    rideshareStatusLabel,
    stress,
    workState,
  ]);

  useEffect(() => {
    if (!backendShiftActive || !workState?.shift_ends_at || autoClockingOut) return;
    if (shiftRemainingSeconds > 0) return;

    const currentAttempt = autoFinalizeAttemptRef.current;
    const nowMs = houstonNow.getTime();
    if (
      currentAttempt
      && currentAttempt.shiftEndsAt === workState.shift_ends_at
      && nowMs - currentAttempt.attemptedAtMs < 5000
    ) {
      return;
    }

    let cancelled = false;
    autoFinalizeAttemptRef.current = {
      shiftEndsAt: workState.shift_ends_at,
      attemptedAtMs: nowMs,
    };

    const autoFinalize = async () => {
      setAutoClockingOut(true);
      recordInfo('gameplayLoop', 'Shift timer reached zero.', {
        action: 'shift_timer_zero',
        context: {
          playerId: loopPlayerId,
          shiftEndsAt: workState.shift_ends_at,
          shiftStatus: workState.shift_status,
        },
      });
      appendTimelineNote({
        timestampIso: new Date().toISOString(),
        title: 'Shift timer ended',
        detail: 'Finalizing shift and refreshing your work status.',
        category: 'system',
      });

      try {
        const finalizedState = await finalizePlayerWorkState(loopPlayerId);
        recordInfo('gameplayLoop', 'Finalize request fired after timer end.', {
          action: 'work_state_finalize_request',
          context: {
            playerId: loopPlayerId,
            shiftStatus: finalizedState?.shift_status || 'unknown',
            backendActive: Boolean(finalizedState?.main_shift_active_flag),
            rideshareAvailable: Boolean(finalizedState?.rideshare_available),
          },
        });
        await refreshGameplay({ silent: true });

        if (cancelled) return;

        if (finalizedState?.main_shift_active_flag) {
          setLoopFeedback({
            tone: 'info',
            message: 'Timer reached zero. Shift finalization is still in progress.',
          });
        } else if (String(finalizedState?.salary_payment_status || '').toLowerCase() === 'failed') {
          setLoopFeedback({
            tone: 'error',
            message: sanitizeSalaryText(
              finalizedState?.salary_status_message,
              'Shift completed, but salary could not be posted yet.',
            ),
          });
        } else if (finalizedState?.shift_status === 'completed') {
          const earnedCash = Number(finalizedState.last_completed_shift?.earned_cash_xgp || 0);
          const xpGained = Number(finalizedState.last_completed_shift?.xp_gained || 0);
          const progressionMsg = String(
            finalizedState?.job_progression_feedback?.feedback_message
            || '',
          ).trim();
          const finalizedRideshareReason = sanitizeRideShareReason(
            finalizedState?.rideshare_block_reason
            || finalizedState?.rideshare_state?.block_reason
            || (!finalizedState?.rideshare_state?.can_rideshare ? finalizedState?.rideshare_state?.reason : ''),
          );
          const postShiftMessage = finalizedState?.rideshare_state?.can_rideshare
            ? 'Shift completed. You are now off shift. Ride share available now.'
            : `Shift completed. You are now off shift. Rideshare blocked: ${stripUnavailablePrefix(finalizedRideshareReason) || 'Unavailable right now.'}.`;
          setLoopFeedback({
            tone: 'success',
            message: progressionMsg
              ? `${postShiftMessage} Earned ${formatMoney(earnedCash)} and ${Math.round(xpGained)} work XP. ${progressionMsg}.`
              : `${postShiftMessage} Earned ${formatMoney(earnedCash)} and ${Math.round(xpGained)} work XP.`,
          });
        }
      } catch (error) {
        if (!cancelled) {
          setLoopFeedback({
            tone: 'error',
            message: error instanceof Error ? error.message : String(error),
          });
        }
      } finally {
        if (!cancelled) {
          setAutoClockingOut(false);
        }
      }
    };

    void autoFinalize();

    return () => {
      cancelled = true;
    };
  }, [
    autoClockingOut,
    backendShiftActive,
    houstonNow,
    loopPlayerId,
    refreshGameplay,
    setLoopFeedback,
    shiftRemainingSeconds,
    workState,
    workState?.shift_ends_at,
    workState?.shift_status,
  ]);

  const runRideShareTrip = async (requestedTrips: number) => {
    if (!sideIncomeAction) {
      loop.setFeedback({
        tone: 'error',
        message: rideshareBlockReason || 'Ride share is not unlocked yet.',
      });
      return;
    }

    const trips = requestedTrips === 3 || requestedTrips === 5 ? requestedTrips : 1;
    const disabledReason = getRideShareDisabledReason(trips);
    if (disabledReason) {
      loop.setFeedback({
        tone: 'error',
        message: disabledReason,
      });
      return;
    }
    const tripAction: DailyActionItem = {
      ...sideIncomeAction,
      title: `Ride Share (${trips} ${trips === 1 ? 'Trip' : 'Trips'})`,
      parameters: {
        ...(sideIncomeAction.parameters || {}),
        trips,
        time_cost_units: trips,
      },
    };

    await loop.executeAction(tripAction);
  };

  const handleTimedActivityPress = (activityId: TimedActivityCardId) => {
    if (currentTimedActivity === activityId) {
      stopCurrentTimedActivity();
      return;
    }
    startTimedActivity(activityId);
  };

  // Life / Meals
  const [busyMeal, setBusyMeal] = useState<string | null>(null);
  const busyLife =
    loop.executingAction
    || busyMeal !== null
    || backendShiftActive
    || autoClockingOut
    || mealInProgress;

  async function handleEat(mealType: 'breakfast' | 'lunch' | 'dinner') {
    if (backendShiftActive || autoClockingOut) {
      loop.setFeedback({
        tone: 'error',
        message: `Meals and recovery are unavailable during shift. Available after ${shiftEndLabel}.`,
      });
      return;
    }

    if (busyLife) return;

    const mealGuard = loop.dailySession.canStartTimedActivity('eat_meal', { mealType });
    if (!mealGuard.allowed) {
      loop.setFeedback({
        tone: 'error',
        message: mealGuard.reason || 'Meal is unavailable right now.',
      });
      return;
    }

    setBusyMeal(`eat_${mealType}`);
    try {
      const ok = await loop.eatMeal(mealType);
      if (ok) {
        const started = loop.dailySession.startTimedActivity('eat_meal', {
          mealType,
          recordHistory: false,
        });
        if (!started.allowed && started.reason) {
          loop.setFeedback({
            tone: 'info',
            message: started.reason,
          });
        }
      }
    } finally {
      setBusyMeal(null);
    }
  }

  // Finance / Loans
  const [loanAmount, setLoanAmount] = useState<100 | 200 | 300 | 500>(100);
  const [busyLoan, setBusyLoan] = useState(false);
  const [debtPaymentAmount, setDebtPaymentAmount] = useState<string>('25');
  const [busyDebtPayment, setBusyDebtPayment] = useState(false);
  const busyFinance = loop.executingAction || busyLoan || busyDebtPayment;
  const loanRepay = Math.round(loanAmount * 1.15);
  const maxDebtPayable = useMemo(() => {
    const capped = Math.min(Math.max(0, cash), Math.max(0, debt));
    return Math.round(capped * 100) / 100;
  }, [cash, debt]);
  const parsedDebtPayment = useMemo(() => {
    const parsed = Number(String(debtPaymentAmount || '').trim());
    if (!Number.isFinite(parsed)) return 0;
    return Math.round(Math.max(0, parsed) * 100) / 100;
  }, [debtPaymentAmount]);

  async function handleLoan() {
    if (busyFinance) return;
    setBusyLoan(true);
    try {
      await loop.takeLoan(loanAmount);
    } finally {
      setBusyLoan(false);
    }
  }

  async function handleDebtPayment(explicitAmount?: number) {
    if (busyFinance) return;
    const amount = Number.isFinite(explicitAmount) ? Number(explicitAmount) : parsedDebtPayment;
    if (!Number.isFinite(amount) || amount <= 0) {
      loop.setFeedback({
        tone: 'error',
        message: 'Enter a debt payment amount greater than 0.',
      });
      return;
    }
    const normalizedAmount = Math.round(amount * 100) / 100;
    if (normalizedAmount > cash) {
      loop.setFeedback({
        tone: 'error',
        message: 'Not enough cash for this debt payment.',
      });
      return;
    }
    if (normalizedAmount > debt) {
      loop.setFeedback({
        tone: 'error',
        message: 'Amount exceeds current debt.',
      });
      return;
    }
    setBusyDebtPayment(true);
    try {
      const requestId = createActionRequestId('debt_payment');
      const ok = await loop.executeAction({
        action_key: 'debt_payment',
        title: `Pay ${formatMoney(normalizedAmount)} debt`,
        description: 'Pay debt from available cash.',
        status: 'available',
        blockers: [],
        warnings: [],
        tradeoffs: [],
        confidence_level: 'high',
        parameters: {
          payment_amount: normalizedAmount,
          request_id: requestId,
        },
      });
      if (ok) {
        const remainingCash = Math.max(0, cash - normalizedAmount);
        const remainingDebt = Math.max(0, debt - normalizedAmount);
        const nextSuggestedAmount = Math.min(normalizedAmount, remainingCash, remainingDebt);
        setDebtPaymentAmount(nextSuggestedAmount > 0 ? String(Math.round(nextSuggestedAmount * 100) / 100) : '');
        loop.setFeedback({
          tone: 'success',
          message: `Paid ${formatMoney(normalizedAmount)} toward debt.`,
        });
      }
    } finally {
      setBusyDebtPayment(false);
    }
  }

  return (
    <GameplayLoopScaffold
      title="Dashboard"
      subtitle="Actions, status, and what to do now"
      activeNavKey="dashboard"
      footer={guidedDashboardActive ? null : (
        <GameplayStickyActionArea
          summary={
            backendShiftActive
              ? `On shift - ${shiftRemainingLabel} remaining`
              : autoClockingOut
                ? 'Auto-finalizing shift...'
                : `${loop.dailySession.remainingTimeUnits} time units left today`
          }
          secondaryLabel="Check Market"
          onSecondaryPress={() => onboarding.navigateTo('market')}
          primaryLabel={loop.endingDay ? 'Settling Day...' : 'End Day'}
          onPrimaryPress={() => void loop.endCurrentDay()}
          primaryLoading={loop.endingDay}
          primaryDisabled={endDayDisabled}
        />
      )}
    >
      {/* Stats */}
      {stats ? (
        <SlideFadeInOnChange
          watchValue={`stats_${dayLabel}_${Math.round(cash * 100)}_${Math.round(debt * 100)}_${Math.round(netCashFlow * 100)}`}
          delayMs={20}
        >
          <OnboardingHighlight target="dashboard-core-stats">
            <GameplaySummaryCard eyebrow="Status" title="Money, Health &amp; Stress">
              <GameplayCompactMetricRows
                items={[
                  {
                    label: 'Cash',
                    value: formatMoney(cash),
                    tone: cashTone,
                    valueNode: (
                      <AnimatedMoneyValue
                        value={cash}
                        tone={cash > 0 ? 'positive' : cash < 0 ? 'danger' : 'neutral'}
                        durationMs={850}
                        threshold={0.2}
                      />
                    ),
                  },
                  {
                    label: 'Net flow today',
                    value: signedCurrency(netCashFlow),
                    tone: netCashFlow > 0 ? 'positive' : netCashFlow < 0 ? 'danger' : 'neutral',
                    valueNode: (
                      <AnimatedMoneyValue
                        value={netCashFlow}
                        tone={netCashFlow > 0 ? 'positive' : netCashFlow < 0 ? 'danger' : 'neutral'}
                        durationMs={700}
                        threshold={0.1}
                        showSign
                      />
                    ),
                  },
                  {
                    label: 'Debt',
                    value: formatMoney(stats.debt_xgp),
                    tone: stats.debt_xgp > cash ? 'danger' : 'neutral',
                    valueNode: (
                      <AnimatedMoneyValue
                        value={stats.debt_xgp}
                        tone={stats.debt_xgp > cash ? 'danger' : 'neutral'}
                        durationMs={900}
                        threshold={0.2}
                        invertDeltaTone
                      />
                    ),
                  },
                  {
                    label: 'Health',
                    value: `${Math.round(health)} / 100`,
                    tone: health < 40 ? 'danger' : health < 65 ? 'warning' : 'positive',
                  },
                  {
                    label: 'Stress',
                    value: String(Math.round(stress)),
                    tone: stress >= 75 ? 'danger' : stress >= 55 ? 'warning' : 'neutral',
                  },
                  {
                    label: 'Debt pressure',
                    value: pressureLabel,
                    tone: loop.expenseDebt.debtWarning ? 'danger' : 'neutral',
                  },
                ]}
              />
            </GameplaySummaryCard>
          </OnboardingHighlight>
        </SlideFadeInOnChange>
      ) : (
        <GameplayWarningBanner
          title="No stats loaded"
          message="Pull to refresh."
          tone="info"
        />
      )}

      {criticalDebtPressure ? (
        <PulseAlertView active tone="danger" strength="strong" intervalMs={2400}>
          <GameplayWarningBanner
            title="Debt pressure critical"
            message="Debt is in the critical zone. Prioritize income and debt repayment before optional spending."
            tone="danger"
          />
        </PulseAlertView>
      ) : null}

      {needsDinnerReminder ? (
        <PulseAlertView active tone="warning" strength="soft" intervalMs={2200}>
          <GameplayWarningBanner
            title="You still need dinner tonight."
            message={dinnerReminderMessage}
            tone="warning"
          />
        </PulseAlertView>
      ) : null}

      {/* Game time */}
      <SlideFadeInOnChange
        watchValue={`clock_${dayLabel}_${backendShiftActive ? 'active' : backendShiftCompleted ? 'done' : 'idle'}_${houstonHour}`}
        delayMs={40}
      >
        <GameplaySummaryCard eyebrow="Game Time" title="Houston Clock">
          <GameplayCompactMetricRows
            items={[
              { label: 'Current day', value: `Day ${dayLabel}` },
              { label: 'Time left', value: `${loop.dailySession.remainingTimeUnits}/${loop.dailySession.totalTimeUnits} units` },
              { label: 'Unit size', value: `${BALANCE.REALTIME.MINUTES_PER_UNIT} mins` },
              { label: 'Houston time', value: currentHoustonTimeLabel },
              { label: 'Day reset', value: dayRolloverLabel },
              { label: 'Date', value: currentHoustonDateLabel },
              { label: 'Day of week', value: currentHoustonDayOfWeekLabel },
              {
                label: 'Phase / status',
                value: gamePhaseLabel,
                tone: gamePhaseLabel === 'Weekend' ? 'warning' : 'info',
              },
              { label: 'Shift window', value: scheduledShiftWindowLabel },
              { label: 'Timer mode', value: testingModeEnabled ? 'Testing mode active' : SHIFT_SHORT_MODE ? 'Accelerated testing mode' : 'Real-time mode' },
            ]}
          />
        </GameplaySummaryCard>
      </SlideFadeInOnChange>

      {marketDataMessage ? (
        <GameplayWarningBanner
          title="Market data temporarily unavailable"
          message={marketDataMessage}
          tone="warning"
        />
      ) : null}

      {autoRolloverRecapLines.length > 0 ? (
        <GameplayWarningBanner
          title="Day rollover complete"
          message={autoRolloverRecapLines.join(' ')}
          tone="info"
        />
      ) : null}

      {/* Economy */}
      <SlideFadeInOnChange
        watchValue={`economy_${dayLabel}_${economySummaryLine}_${workDemandLabel}`}
        delayMs={50}
      >
        <GameplaySummaryCard eyebrow="Economy" title="Today's Risk &amp; Opportunity">
          <Text style={styles.helperText}>{economySummaryLine}</Text>
          <GameplayCompactMetricRows
            items={economyMacroItems.map((entry, index) => ({
              label: entry.label,
              value: formatRiskLevel(entry.signal?.level),
              tone: riskTone(entry.signal?.level),
              note: entry.signal?.value_text || `Signal ${index + 1}`,
            }))}
          />
          <GameplayCompactMetricRows
            items={economyOpportunityItems.map((entry) => ({
              label: entry.label,
              value: formatRiskLevel(entry.signal?.level),
              tone: riskTone(entry.signal?.level),
              note: entry.signal?.value_text || 'Moderate',
            }))}
          />
          {riskBadges.length > 0 ? (
            <View style={styles.riskBadgeWrap}>
              {riskBadges.slice(0, 5).map((badge, index) => {
                const normalizedLevel = String(badge.level || '').toLowerCase();
                const badgeStyle = normalizedLevel === 'critical'
                  ? styles.riskBadgeCritical
                  : normalizedLevel === 'high'
                    ? styles.riskBadgeHigh
                    : normalizedLevel === 'moderate'
                      ? styles.riskBadgeModerate
                      : styles.riskBadgeLow;
                return (
                  <View key={`${badge.key || badge.label || 'badge'}_${index}`} style={[styles.riskBadge, badgeStyle]}>
                    <Text style={styles.riskBadgeText}>
                      {badge.label}: {formatRiskLevel(badge.level)}
                    </Text>
                  </View>
                );
              })}
            </View>
          ) : null}
        </GameplaySummaryCard>
      </SlideFadeInOnChange>

      {/* Work shift */}
      <SlideFadeInOnChange
        watchValue={`work_${dayLabel}_${backendShiftActive ? 'active' : backendShiftCompleted ? 'done' : workState?.missed_shift_today ? 'missed' : 'idle'}_${Math.round(salaryEarnedToday * 100)}`}
        delayMs={60}
      >
        <GameplaySummaryCard eyebrow="Work" title="Income &amp; Shifts">
        <View style={styles.metricRow}>
          <GameplayStatCard
            label="Current job"
            value={currentJobDisplayName || 'No job selected'}
            tone={currentJobKey ? 'info' : 'warning'}
            note={employerLabel || (currentJobKey ? `Role key: ${currentJobKey.replace(/_/g, ' ')}` : 'Choose a job to unlock stable shifts.')}
          />
          <GameplayStatCard
            label="Shift status"
            value={
              autoClockingOut
                ? 'Auto-finalizing'
                : backendShiftActive
                  ? 'Active'
                  : backendShiftCompleted
                    ? 'Off shift after work'
                    : canClockIn
                      ? 'Ready'
                      : 'Off shift'
            }
            tone={backendShiftActive || autoClockingOut ? 'warning' : backendShiftCompleted ? 'positive' : canClockIn ? 'positive' : 'neutral'}
            note={
              backendShiftActive || autoClockingOut
                ? `Ends ${shiftEndLabel}`
                : backendShiftCompleted
                  ? `${shiftEndedLabel ? `Ended ${shiftEndedLabel} · ` : ''}${postShiftBannerMessage}`
                  : `Window: ${scheduledShiftWindowLabel}`
            }
          />
          <GameplayStatCard
            label={shiftScheduleCardLabel}
            value={shiftScheduleCardValue}
            tone={backendShiftActive ? 'warning' : 'info'}
            note={shiftScheduleCardNote}
          />
          <GameplayStatCard
            label="Testing mode"
            value={testingModeEnabled ? 'On' : 'Off'}
            tone={testingModeEnabled ? 'warning' : 'neutral'}
            note={testingModeEnabled ? `Shift length: ${testingShiftLabel}` : 'Production rules active.'}
          />
          <GameplayStatCard
            label="Shifts today"
            value={`${Math.max(0, shiftsCompletedToday)} / ${Math.max(1, maxDailyMainShifts)}`}
            tone={dailyShiftLimitReached ? 'warning' : overtimeShiftAvailable ? 'positive' : 'info'}
            note={nextShiftLabel}
          />
          <GameplayStatCard
            label="Salary today"
            value={salaryEarnedToday > 0 ? `+${formatMoney(salaryEarnedToday)}` : 'No salary yet'}
            tone={salaryEarnedToday > 0 ? 'positive' : backendShiftActive ? 'warning' : 'neutral'}
            note={workIncomeVisibilityLabel}
          />
          <GameplayStatCard
            label="Payment status"
            value={salaryStatusLabel}
            tone={salaryStatusTone}
            note={
              currentSalaryAudit?.failure_reason
                ? currentSalaryAudit.failure_reason
                : salaryStatusMessage
            }
          />
          <GameplayStatCard
            label="Last salary"
            value={lastSalaryPostedLabel}
            tone={lastSalaryPosted?.transaction_confirmed ? 'positive' : 'neutral'}
            note={
              lastSalaryPosted?.salary_posted_at
                ? `${lastSalaryPostedNote} | ${formatHoustonTimestamp(lastSalaryPosted.salary_posted_at)}`
                : lastSalaryPostedNote
            }
          />
          <GameplayStatCard
            label="Pay model"
            value={workPayModelLabel}
            tone="info"
            note={salaryEarnedYesterday > 0 ? `Yesterday +${formatMoney(salaryEarnedYesterday)}` : 'Daily payout after shift completion.'}
          />
          <GameplayStatCard
            label="Job level"
            value={`Lv ${jobLevel}`}
            tone={promotionTier === 'Senior' ? 'positive' : 'info'}
            note={`${promotionTier} · ${jobLevelDetail}`}
          />
          <GameplayStatCard
            label="Salary preview"
            value={projectedNextMonthlyPay > 0 ? formatMoney(projectedNextMonthlyPay) : '--'}
            tone="info"
            note={`Estimated next milestone (+${projectedSalaryIncreasePct > 1 ? Math.round(projectedSalaryIncreasePct) : projectedSalaryIncreasePct.toFixed(1)}%). Live payroll unchanged.`}
          />
          <GameplayStatCard
            label="Demand today"
            value={workDemandLabel}
            tone={riskTone(workDemandSignal?.level)}
            note={rideshareDemandSignal?.value_text || 'Check economy card for details.'}
          />
          <GameplayStatCard
            label="Time left"
            value={`${loop.dailySession.remainingTimeUnits}/${loop.dailySession.totalTimeUnits}`}
            tone={loop.dailySession.remainingTimeUnits <= 2 ? 'warning' : 'info'}
            note={testingModeEnabled ? `Testing mode active. Shift length: ${testingShiftLabel}.` : 'Real-time shift timer.'}
          />
        </View>

        <View style={styles.clockInButtonWrap}>
          <PrimaryButton
            label={
              autoClockingOut
                ? 'Auto-finalizing...'
                : runningWorkAction
                  ? 'Starting shift...'
                  : backendShiftActive
                    ? `On shift (${shiftRemainingLabel})`
                    : `${String(workShiftAction?.title || 'Clock In')} (${formatUnitButtonLabel(workExecutionGuard.timeCostUnits)})`
            }
            onPress={() => void handleClockIn()}
            disabled={!canClockIn || backendShiftActive || autoClockingOut || runningWorkAction}
          />
        </View>

        {backendShiftActive ? (
          <GameplayWarningBanner
            title="Shift active"
            message={`Clocked in as ${currentJobDisplayName} - shift ends at ${shiftEndLabel}.`}
            tone="info"
          />
        ) : salaryPaymentStatus === 'failed' ? (
          <GameplayWarningBanner
            title="Salary posting failed"
            message={currentSalaryAudit?.failure_reason || salaryStatusMessage}
            tone="warning"
          />
        ) : salaryPaymentStatus === 'pending' && !backendShiftActive ? (
          <GameplayWarningBanner
            title="Salary posting pending"
            message={salaryStatusMessage}
            tone="warning"
          />
        ) : autoClockingOut ? (
          <GameplayWarningBanner
            title="Auto-finalizing"
            message="Timer reached zero. Finalizing shift and unlocking post-shift actions."
            tone="warning"
          />
        ) : weekendRideshareOnly ? (
          <GameplayWarningBanner
            title="Weekend testing rule active"
            message={`No required main shift. Rideshare cap today: ${rideshareDailyCap} trips.`}
            tone="info"
          />
        ) : backendShiftCompleted && lastCompletedShift ? (
          <GameplayWarningBanner
            title="Shift completed"
            message={
              progressionFeedback?.feedback_message
                ? `${postShiftBannerMessage} Earned ${formatMoney(lastCompletedShift.earned_cash_xgp)} | Work XP +${Math.round(lastCompletedShift.xp_gained)} | ${progressionFeedback.feedback_message}.`
                : `${postShiftBannerMessage} Earned ${formatMoney(lastCompletedShift.earned_cash_xgp)} | Work XP +${Math.round(lastCompletedShift.xp_gained)}.`
            }
            tone="info"
          />
        ) : clockInBlocker ? (
          <Text style={styles.helperText}>{clockInBlocker}</Text>
        ) : (
          <Text style={styles.helperText}>
            Clock in to start your shift. It auto-finalizes when Houston time reaches shift end.
          </Text>
        )}
        <Text style={styles.helperText}>
          Payroll model: {workPayModelLabel}. Salary transactions are posted to Daily Activity and transaction history.
        </Text>
        {recentSalaryAudits.length > 0 ? (
          <View style={styles.salaryAuditList}>
            {recentSalaryAudits.map((audit) => (
              <View key={audit.audit_id || audit.shift_token} style={styles.salaryAuditRow}>
                <View style={styles.salaryAuditCopy}>
                  <Text style={styles.salaryAuditTitle}>
                    Day {audit.day_number} - {audit.job_display_name || audit.job_key || 'Main job'}
                  </Text>
                  <Text style={styles.salaryAuditDetail}>
                    {sanitizeSalaryText(
                      audit.payment_status === 'posted'
                        ? `Salary posted +${formatMoney(audit.final_salary_paid)}`
                        : audit.payment_status === 'failed'
                          ? 'Salary posting failed'
                          : 'Salary pending verification',
                      'Salary update',
                    )}
                  </Text>
                </View>
                <Text style={[
                  styles.salaryAuditAmount,
                  audit.payment_status === 'posted'
                    ? styles.salaryAuditAmountPositive
                    : audit.payment_status === 'failed'
                      ? styles.salaryAuditAmountNegative
                      : styles.salaryAuditAmountNeutral,
                ]}
                >
                  {audit.payment_status === 'posted'
                    ? `+${formatMoney(audit.final_salary_paid)}`
                    : audit.payment_status === 'failed'
                      ? 'Failed'
                      : 'Pending'}
                </Text>
              </View>
            ))}
          </View>
        ) : null}
        {workState?.missed_shift_today ? (
          <PulseAlertView active tone="warning" strength="soft" intervalMs={2300}>
            <GameplayWarningBanner
              title="Missed shift warning"
              message={`No salary earned. Health ${signedWhole(workState?.missed_shift_health_delta ?? -5)}, Stress +${Math.max(0, Number(workState?.missed_shift_stress_delta ?? 6))}.`}
              tone="warning"
            />
          </PulseAlertView>
        ) : null}
      </GameplaySummaryCard>
      </SlideFadeInOnChange>

      {showJobMarket ? (
        <SlideFadeInOnChange
          watchValue={`job_market_${dayLabel}_${currentJobKey}_${loop.busyActionKey || 'idle'}`}
          delayMs={70}
        >
          <JobMarketPanel
            jobMarket={jobMarket}
            executingAction={loop.executingAction}
            busyActionKey={loop.busyActionKey}
            onSwitchJob={switchToMarketJob}
            onStartTraining={startMarketTraining}
          />
        </SlideFadeInOnChange>
      ) : null}

      {/* Ride share */}
      <SlideFadeInOnChange
        watchValue={`rideshare_${dayLabel}_${Math.round(rideshareTripsToday)}_${Math.round(rideshareEarnedToday * 100)}_${rideshareState?.status || ''}`}
        delayMs={80}
      >
        <GameplaySummaryCard eyebrow="Side Income" title="Post-Shift Ride Share">
          <GameplayCompactMetricRows
            items={[
              {
                label: 'Status',
                value: rideshareStatusLabel,
                tone: rideshareAvailable ? 'positive' : backendShiftActive || autoClockingOut ? 'warning' : 'neutral',
              },
              {
                label: 'Current location',
                value: currentLocationRegion ? `${currentLocationLabel} (${currentLocationRegion})` : currentLocationLabel,
              },
              { label: 'Houston time', value: `${formatHoustonNow(houstonNow)} CT` },
              { label: 'Mode', value: formatRideshareMode(rideshareMode) },
              {
                label: 'Location demand',
                value: `${rideshareDemandBonusPct >= 0 ? '+' : ''}${rideshareDemandBonusPct.toFixed(0)}%`,
                tone: rideshareDemandBonusPct > 0 ? 'positive' : rideshareDemandBonusPct < 0 ? 'warning' : 'neutral',
              },
              {
                label: 'Trips today',
                value: `${Math.round(rideshareTripsToday)} / ${rideshareDailyCap}`,
              },
              { label: 'Trips remaining', value: String(Math.max(0, rideshareRemainingTrips)) },
              {
                label: 'Ride share earned today',
                value: formatMoney(rideshareEarnedToday),
                tone: rideshareEarnedToday > 0 ? 'positive' : 'neutral',
                valueNode: (
                  <AnimatedMoneyValue
                    value={rideshareEarnedToday}
                    tone={rideshareEarnedToday > 0 ? 'positive' : 'neutral'}
                    durationMs={820}
                    threshold={0.1}
                  />
                ),
              },
              { label: 'Time per trip', value: `${Math.max(1, Number(rideshareState?.time_cost_per_trip_units || 1))} time unit (20-45 mins simulated)` },
            ]}
          />

          {runningSideIncome ? (
            <GameplayWarningBanner
              title="Rideshare running"
              message="Processing trip bundle and updating cash, stress, health, and time."
              tone="info"
            />
          ) : weekendRideshareOnly ? (
            <GameplayWarningBanner
              title="Weekend testing rule active"
              message={`No required main shift. Rideshare cap today: ${rideshareDailyCap} trips.`}
              tone="info"
            />
          ) : backendShiftCompleted ? (
            <GameplayWarningBanner
              title="Post-shift status"
              message={postShiftBannerMessage}
              tone={rideshareAvailable ? 'info' : 'warning'}
            />
          ) : !rideshareAvailable ? (
            <GameplayWarningBanner
              title="Rideshare blocked"
              message={rideshareBlockReason}
              tone={backendShiftActive || autoClockingOut ? 'info' : 'warning'}
            />
          ) : null}

          {rideshareResultCard ? (
            <Animated.View
              style={[
                styles.rideshareResultCard,
                {
                  backgroundColor: rideshareResultGlow.interpolate({
                    inputRange: [0, 1],
                    outputRange: ['rgba(16,185,129,0.06)', 'rgba(16,185,129,0.24)'],
                  }),
                  borderColor: rideshareResultGlow.interpolate({
                    inputRange: [0, 1],
                    outputRange: ['#6ee7b7', '#16a34a'],
                  }),
                },
              ]}
            >
              <Text style={styles.rideshareResultTitle}>
                Ride share result ({rideshareResultCard.trips} {rideshareResultCard.trips === 1 ? 'trip' : 'trips'})
              </Text>
              <Text style={styles.rideshareResultMeta}>
                Mode: {rideshareResultCard.mode || formatRideshareMode(rideshareMode)}
              </Text>
              <View style={styles.rideshareResultRow}>
                <Text style={styles.rideshareResultLabel}>Cash:</Text>
                <AnimatedMoneyValue
                  value={Math.max(0, rideshareResultCard.earned)}
                  tone="positive"
                  showSign
                  threshold={0.01}
                  durationMs={700}
                  formatter={(next) => {
                    const abs = formatMoney(Math.abs(next));
                    return `+${abs}`;
                  }}
                  style={styles.rideshareResultValue}
                />
              </View>
              <Text style={styles.rideshareResultMeta}>
                Stress {signedWhole(rideshareResultCard.stressDelta)} | Health {signedWhole(rideshareResultCard.healthDelta)}
              </Text>
            </Animated.View>
          ) : null}

          <View style={styles.recoveryList}>
            {RIDESHARE_TRIP_OPTIONS.map((tripOption) => {
              const preview = getRideshareTripPreview(
                rideshareMode,
                tripOption,
                {
                  payMinPerTrip: Number.isFinite(ridesharePayMinPerTrip) ? ridesharePayMinPerTrip : undefined,
                  payMaxPerTrip: Number.isFinite(ridesharePayMaxPerTrip) ? ridesharePayMaxPerTrip : undefined,
                  stressModifier: rideshareStressModifier,
                },
              );
              const buttonDisabledReason = rideshareDisableReasonsByTrip[tripOption as 1 | 3 | 5];
              return (
                <View key={`rideshare_${tripOption}`} style={styles.recoveryRow}>
                  <View style={styles.recoveryInfo}>
                    <Text style={styles.recoveryTitle}>{tripOption} {tripOption === 1 ? 'Trip' : 'Trips'}</Text>
                    <Text style={styles.recoveryMeta}>
                      Expected pay {formatMoney(preview.payMin)}-{formatMoney(preview.payMax)} | Stress {signedWhole(preview.stress)} | Health {signedWhole(preview.health)}
                    </Text>
                  </View>
                  <View style={styles.recoveryActionWrap}>
                    <SecondaryButton
                      label={
                        runningSideIncome
                          ? 'Running...'
                          : `Run ${tripOption} (${formatUnitButtonLabel(tripOption * rideshareTimeCostPerTrip)})`
                      }
                      onPress={() => void runRideShareTrip(tripOption)}
                      disabled={Boolean(buttonDisabledReason)}
                    />
                  </View>
                </View>
              );
            })}
          </View>
        </GameplaySummaryCard>
      </SlideFadeInOnChange>

      {/* Action hub */}
      {actionHubForDisplay ? (
        <SlideFadeInOnChange
          watchValue={`actionhub_${dayLabel}_${loop.dailySession.actionsTakenToday.length}_${loop.dailySession.remainingTimeUnits}`}
          delayMs={100}
        >
          <OnboardingHighlight target="work-first-action">
            <ActionHubPanel
              hub={actionHubForDisplay}
              onExecuteAction={(action) => void loop.executeAction(action)}
              getExecutionGuard={(action) => loop.dailySession.canExecuteAction(action)}
              remainingTimeUnits={loop.dailySession.remainingTimeUnits}
              totalTimeUnits={loop.dailySession.totalTimeUnits}
              sessionStatus={loop.dailySession.sessionStatus}
              progressRatio={loop.dailySession.progress}
            />
          </OnboardingHighlight>
        </SlideFadeInOnChange>
      ) : (
        <EmptyStateView
          title="No actions loaded"
          subtitle="Refresh to pull the latest actions."
        />
      )}

      {INTERACTION_DIAGNOSTICS_ENABLED && diagnosticsTruthItems.length > 0 ? (
        <SlideFadeInOnChange
          watchValue={`diagnostics_${authoritativeState?.refreshed_at || 'none'}_${rideshareDerivedState.blockReasonCode || 'none'}`}
          delayMs={110}
        >
          <GameplaySummaryCard eyebrow="Diagnostics" title="Action Truth Lock">
            <GameplayCompactMetricRows items={diagnosticsTruthItems} />
          </GameplaySummaryCard>
        </SlideFadeInOnChange>
      ) : null}

      {/* Recovery */}
      <SlideFadeInOnChange
        watchValue={`recovery_${dayLabel}_${currentTimedActivity || 'idle'}_${loop.dailySession.stressRecoveredToday}_${loop.dailySession.skillProgressGainedToday}`}
        delayMs={120}
      >
      <GameplaySummaryCard eyebrow="Recovery" title="Timed Recovery &amp; Training">
        {(backendShiftActive || autoClockingOut) ? (
          <GameplayWarningBanner
            title="Recovery locked during shift"
            message={`Recovery actions unlock after ${shiftEndLabel} CT.`}
            tone="warning"
          />
        ) : null}
        <GameplayCompactMetricRows
          items={[
            {
              label: 'Time left',
              value: `${loop.dailySession.remainingTimeUnits}/${loop.dailySession.totalTimeUnits} units`,
            },
            {
              label: 'Idle recovery',
              value: idleRecoveryLabel,
              tone: 'positive',
            },
            {
              label: 'Active recovery',
              value: activeRecoveryLabel,
              tone: 'positive',
            },
            {
              label: 'Stress recovered today',
              value: signedWhole(-loop.dailySession.stressRecoveredToday),
              tone: loop.dailySession.stressRecoveredToday > 0 ? 'positive' : 'neutral',
            },
            {
              label: 'Health gained today',
              value: signedWhole(loop.dailySession.healthGainedToday),
              tone: loop.dailySession.healthGainedToday > 0 ? 'positive' : 'neutral',
            },
            {
              label: 'Skill gained today',
              value: `+${loop.dailySession.skillProgressGainedToday}`,
              tone: loop.dailySession.skillProgressGainedToday > 0 ? 'positive' : 'neutral',
            },
            {
              label: 'Weekend recovery',
              value: weekendRecoverySummary?.is_weekend
                ? `${signedWhole(Number(weekendRecoverySummary?.stress_delta || 0))} (${String(weekendRecoverySummary?.tier || 'pending')})`
                : 'Pending',
              tone: weekendRecoverySummary?.is_weekend ? 'positive' : 'neutral',
            },
          ]}
        />
        <Text style={styles.helperText}>
          1 unit = {BALANCE.REALTIME.MINUTES_PER_UNIT} mins. Time cost is deducted over time, not at start.
        </Text>
        <Text style={styles.helperText}>
          Weekend recovery still applies even if you ride share, but the settlement bonus can be reduced.
        </Text>

        {hasActiveTimedActivity ? (
          <View style={styles.sessionCard}>
            <Text style={styles.sessionTitle}>{loop.dailySession.currentActivityName}</Text>
            <Text style={styles.sessionMeta}>Elapsed: {activeSessionElapsedLabel}</Text>
            <Text style={styles.sessionMeta}>Next unit cost in: {nextUnitCountdownLabel}</Text>
            {currentTimedActivity === 'skill_training' ? (
              <>
                <Text style={styles.sessionMeta}>Skill progress gained: {currentTrainingProgressLabel}</Text>
                <Text style={styles.sessionMeta}>
                  {loop.dailySession.trainingEfficiencyBonusActive
                    ? 'Efficiency bonus active for this session.'
                    : `Bonus unlocks after ${BALANCE.REALTIME.TRAINING_BONUS_THRESHOLD_UNITS * BALANCE.REALTIME.MINUTES_PER_UNIT} min.`}
                </Text>
              </>
            ) : (
              <>
                <Text style={styles.sessionMeta}>Stress recovered: {currentStressRecoveryLabel}</Text>
                <Text style={styles.sessionMeta}>Health gained: {currentHealthGainLabel}</Text>
              </>
            )}
            {mealInProgress ? (
              <Text style={styles.sessionMeta}>
                {loop.dailySession.canStopCurrentActivity
                  ? 'Meal minimum reached. You can stop whenever you are ready.'
                  : `Meal locked for ${formatMinutesLabel(mealMinimumRemainingMinutes)} more.`}
              </Text>
            ) : null}
            <View style={styles.recoveryActionWrap}>
              <SecondaryButton
                label={
                  mealInProgress && !loop.dailySession.canStopCurrentActivity
                    ? `Locked (${formatMinutesLabel(mealMinimumRemainingMinutes)} left)`
                    : 'Stop Activity'
                }
                onPress={stopCurrentTimedActivity}
                disabled={!loop.dailySession.canStopCurrentActivity}
              />
            </View>
          </View>
        ) : (
          <GameplayWarningBanner
            title="Resting automatically"
            message="Stress recovers 1 point every 10 minutes while you are away from the app and not running another activity."
            tone="info"
          />
        )}

        <View style={styles.recoveryList}>
          {TIMED_ACTIVITY_PRESETS.map((preset) => {
            const running = currentTimedActivity === preset.id;
            const actionDisabledReason = running ? null : getTimedActivityDisabledReason(preset.id);
            return (
              <View key={preset.id} style={styles.recoveryRow}>
                <View style={styles.recoveryInfo}>
                  <Text style={styles.recoveryTitle}>{preset.title}</Text>
                  <Text style={styles.recoveryMeta}>{preset.primaryEffect}</Text>
                  <Text style={styles.recoveryMeta}>{preset.secondaryEffect}</Text>
                  <Text style={styles.recoveryMeta}>{preset.timeRule}</Text>
                  {running ? (
                    <Text style={styles.recoveryMeta}>
                      Running now. Elapsed {activeSessionElapsedLabel}. Next unit in {nextUnitCountdownLabel}.
                    </Text>
                  ) : null}
                  {actionDisabledReason ? (
                    <Text style={styles.helperText}>{actionDisabledReason}</Text>
                  ) : null}
                </View>
                <View style={styles.recoveryActionWrap}>
                  <SecondaryButton
                    label={running ? 'Stop' : `Start (${formatTimedUnitRateLabel(1)})`}
                    onPress={() => {
                      handleTimedActivityPress(preset.id);
                    }}
                    disabled={Boolean(actionDisabledReason)}
                  />
                </View>
              </View>
            );
          })}
        </View>
      </GameplaySummaryCard>
      </SlideFadeInOnChange>

      {/* Activity history */}
      <SlideFadeInOnChange
        watchValue={`activity_${dayLabel}_${todaysActivity.length}`}
        delayMs={140}
      >
      <GameplaySummaryCard eyebrow="Today" title="Activity History">
        {todaysActivity.length > 0 ? (
          <View style={styles.activityList}>
            {todaysActivity.map((entry) => (
              <View key={entry.id} style={styles.activityRow}>
                <Text style={styles.activityTime}>{formatHoustonTimestamp(entry.timestampIso)}</Text>
                <View style={styles.activityCopy}>
                  <Text style={styles.activityTitle}>{entry.title}</Text>
                  <Text style={styles.activityDetail}>{entry.detail}</Text>
                </View>
              </View>
            ))}
          </View>
        ) : (
          <Text style={styles.activityEmpty}>No activity yet today. Start with clock-in, meals, recovery, or a ride share trip.</Text>
        )}
      </GameplaySummaryCard>
      </SlideFadeInOnChange>

      {/* Meals */}
      <SlideFadeInOnChange
        watchValue={`food_${dayLabel}_${dinnerResolvedToday ? 'done' : 'pending'}_${busyMeal || 'idle'}`}
        delayMs={160}
      >
      <GameplaySummaryCard eyebrow="Life" title="Food &amp; Meals">
        {cash < 6 ? (
          <GameplayWarningBanner
            title="Low cash for meals"
            message="Breakfast/Lunch need cash. Dinner can still be resolved with survival debt if needed."
            tone="warning"
          />
        ) : null}
        {workState?.day_settled ? (
          <GameplayWarningBanner
            title="Day finalized"
            message="Dinner outcome already recorded during settlement."
            tone="info"
          />
        ) : null}
        {dinnerResolvedToday && !workState?.day_settled ? (
          <GameplayWarningBanner
            title="Dinner already resolved"
            message={`Dinner mode today: ${String(workState?.dinner_mode_today || 'recorded').replace(/_/g, ' ')}.`}
            tone="info"
          />
        ) : null}
        {mealInProgress ? (
          <GameplayWarningBanner
            title={`Eating ${String(loop.dailySession.currentMealType || 'meal')}`}
            message={
              loop.dailySession.canStopCurrentActivity
                ? 'Meal minimum reached. Time continues to deduct over time until you stop.'
                : `Meal locked for ${formatMinutesLabel(mealMinimumRemainingMinutes)} more. Minimum required: ${BALANCE.REALTIME.MEAL_MIN_MINUTES} min.`
            }
            tone="info"
          />
        ) : null}
        <Text style={styles.helperText}>
          Meals cost 6 XGP each, require at least {BALANCE.REALTIME.MEAL_MIN_MINUTES} minutes, and then deduct {formatTimedUnitRateLabel(1)} while active instead of charging time on button press.
        </Text>
        <View style={styles.buttonRow}>
          <View style={styles.mealBtn}>
            <PrimaryButton
              label={busyMeal === 'eat_breakfast' ? 'Eating...' : `Breakfast\n(-6 XGP • ${formatTimedUnitRateLabel(1)})`}
              onPress={() => void handleEat('breakfast')}
              disabled={busyLife || cash < 6}
            />
          </View>
          <View style={styles.mealBtn}>
            <SecondaryButton
              label={busyMeal === 'eat_lunch' ? 'Eating...' : `Lunch\n(-6 XGP • ${formatTimedUnitRateLabel(1)})`}
              onPress={() => void handleEat('lunch')}
              disabled={busyLife || cash < 6}
            />
          </View>
          <View style={styles.mealBtn}>
            <SecondaryButton
              label={busyMeal === 'eat_dinner' ? 'Eating...' : `Dinner\n(-6 XGP • ${formatTimedUnitRateLabel(1)})`}
              onPress={() => void handleEat('dinner')}
              disabled={busyLife || Boolean(workState?.day_settled) || dinnerResolvedToday}
            />
          </View>
        </View>
      </GameplaySummaryCard>
      </SlideFadeInOnChange>

      {/* Finance */}
      <SlideFadeInOnChange
        watchValue={`finance_${dayLabel}_${Math.round(debt * 100)}_${Math.round(cash * 100)}_${busyFinance ? 'busy' : 'idle'}`}
        delayMs={180}
      >
      <GameplaySummaryCard eyebrow="Finance" title="Quick Loan &amp; Debt Payment">
        {debt > 200 ? (
          <GameplayWarningBanner
            title="High debt"
            message={`Current debt: ${formatMoney(debt)}. Borrowing adds more - try earning first.`}
            tone="warning"
          />
        ) : null}
        <View style={styles.loanAmountRow}>
          {LOAN_AMOUNTS.map((amt) => {
            const active = loanAmount === amt;
            return (
              <View key={amt} style={styles.loanAmtBtn}>
                {active ? (
                  <PrimaryButton label={`${amt} XGP`} onPress={() => setLoanAmount(amt)} disabled={busyFinance} />
                ) : (
                  <SecondaryButton label={`${amt} XGP`} onPress={() => setLoanAmount(amt)} disabled={busyFinance} />
                )}
              </View>
            );
          })}
        </View>
        <Text style={styles.loanRepayNote}>
          Borrow {loanAmount} XGP -&gt; owe {loanRepay} XGP (+15%).
        </Text>
        <View style={styles.loanConfirmBtn}>
          <PrimaryButton
            label={busyLoan ? 'Borrowing...' : `Borrow ${loanAmount} XGP (0u)`}
            onPress={() => void handleLoan()}
            disabled={busyFinance}
          />
        </View>

        <View style={styles.debtDivider} />
        <Text style={styles.loanRepayNote}>
          Pay Debt: cash {formatMoney(cash)} | debt {formatMoney(debt)} | max payable now {formatMoney(maxDebtPayable)}.
        </Text>
        <View style={styles.debtInputRow}>
          <TextInput
            value={debtPaymentAmount}
            keyboardType="decimal-pad"
            onChangeText={setDebtPaymentAmount}
            style={styles.debtInput}
            placeholder="Amount"
            placeholderTextColor={theme.color.muted}
            editable={!busyFinance}
          />
          <View style={styles.debtPayButtonWrap}>
            <PrimaryButton
              label={busyDebtPayment ? 'Paying...' : 'Pay Debt (0u)'}
              onPress={() => void handleDebtPayment()}
              disabled={busyFinance || maxDebtPayable <= 0}
            />
          </View>
        </View>
        <View style={styles.debtQuickRow}>
          {[10, 25, 50].map((quickAmount) => (
            <View key={`quick_debt_${quickAmount}`} style={styles.loanAmtBtn}>
              <SecondaryButton
                label={`Pay ${quickAmount} (0u)`}
                onPress={() => void handleDebtPayment(quickAmount)}
                disabled={busyFinance || quickAmount > maxDebtPayable}
              />
            </View>
          ))}
          <View style={styles.loanAmtBtn}>
            <SecondaryButton
              label="Pay Max (0u)"
              onPress={() => void handleDebtPayment(maxDebtPayable)}
              disabled={busyFinance || maxDebtPayable <= 0}
            />
          </View>
        </View>
      </GameplaySummaryCard>
      </SlideFadeInOnChange>

      {/* Warnings */}
      {cash < 50 ? (
        <GameplayWarningBanner
          title="Almost out of money"
          message="Run a work shift to earn XGP, or borrow a quick loan above."
          tone="danger"
        />
      ) : null}

      {stress >= 70 ? (
        <GameplayWarningBanner
          title="Stress is very high"
          message="Use meals or recovery actions before stress starts harming health."
          tone="warning"
        />
      ) : null}

    </GameplayLoopScaffold>
  );
}

const styles = StyleSheet.create({
  metricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  clockInButtonWrap: {
    marginTop: theme.spacing.xs,
  },
  helperText: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
  riskBadgeWrap: {
    marginTop: theme.spacing.xs,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.xs,
  },
  riskBadge: {
    borderWidth: 1,
    borderRadius: theme.radius.pill,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xxs,
  },
  riskBadgeLow: {
    borderColor: '#86efac',
    backgroundColor: '#f0fdf4',
  },
  riskBadgeModerate: {
    borderColor: '#93c5fd',
    backgroundColor: '#eff6ff',
  },
  riskBadgeHigh: {
    borderColor: '#fcd34d',
    backgroundColor: '#fffbeb',
  },
  riskBadgeCritical: {
    borderColor: '#fca5a5',
    backgroundColor: '#fef2f2',
  },
  riskBadgeText: {
    ...theme.typography.caption,
    color: theme.color.textPrimary,
    fontWeight: '700',
  },
  recoveryList: {
    gap: theme.spacing.sm,
  },
  recoveryRow: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    backgroundColor: theme.color.surfaceAlt,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xs,
  },
  recoveryInfo: {
    gap: theme.spacing.xxs,
  },
  recoveryTitle: {
    ...theme.typography.bodyMd,
    color: theme.color.textPrimary,
    fontWeight: '700',
  },
  recoveryMeta: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
  },
  recoveryActionWrap: {
    marginTop: theme.spacing.xxs,
  },
  sessionCard: {
    borderWidth: 1,
    borderColor: theme.color.info,
    borderRadius: theme.radius.lg,
    backgroundColor: theme.color.surfaceAlt,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  sessionTitle: {
    ...theme.typography.bodyMd,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  sessionMeta: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
  rideshareResultCard: {
    borderWidth: 1,
    borderRadius: theme.radius.lg,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xxs,
    marginTop: theme.spacing.xs,
  },
  rideshareResultTitle: {
    ...theme.typography.bodySm,
    color: '#065f46',
    fontWeight: '800',
  },
  rideshareResultMeta: {
    ...theme.typography.caption,
    color: '#065f46',
  },
  rideshareResultRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  rideshareResultLabel: {
    ...theme.typography.caption,
    color: '#065f46',
    fontWeight: '700',
  },
  rideshareResultValue: {
    ...theme.typography.bodySm,
    fontWeight: '800',
    color: '#166534',
  },
  activityList: {
    gap: theme.spacing.sm,
  },
  activityRow: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    backgroundColor: theme.color.surfaceAlt,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: theme.spacing.sm,
  },
  activityTime: {
    ...theme.typography.label,
    color: theme.color.info,
    minWidth: 62,
  },
  activityCopy: {
    flex: 1,
    gap: theme.spacing.xxs,
  },
  activityTitle: {
    ...theme.typography.bodySm,
    color: theme.color.textPrimary,
    fontWeight: '700',
  },
  activityDetail: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
  },
  activityEmpty: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
  salaryAuditList: {
    gap: theme.spacing.sm,
    marginTop: theme.spacing.sm,
  },
  salaryAuditRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
  },
  salaryAuditCopy: {
    flex: 1,
    gap: theme.spacing.xxs,
  },
  salaryAuditTitle: {
    ...theme.typography.bodySm,
    color: theme.color.textPrimary,
    fontWeight: '700',
  },
  salaryAuditDetail: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
  },
  salaryAuditAmount: {
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  salaryAuditAmountPositive: {
    color: theme.color.positive,
  },
  salaryAuditAmountNegative: {
    color: theme.color.danger,
  },
  salaryAuditAmountNeutral: {
    color: theme.color.textSecondary,
  },
  buttonRow: {
    gap: theme.spacing.sm,
    marginTop: theme.spacing.sm,
  },
  mealBtn: {
    flex: 1,
  },
  loanAmountRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.sm,
  },
  loanAmtBtn: {
    flex: 1,
    minWidth: 70,
  },
  loanRepayNote: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
    marginTop: theme.spacing.xs,
    marginBottom: theme.spacing.xs,
  },
  loanConfirmBtn: {
    marginTop: theme.spacing.xs,
  },
  debtDivider: {
    marginTop: theme.spacing.md,
    marginBottom: theme.spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: theme.color.border,
  },
  debtInputRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    alignItems: 'center',
    marginBottom: theme.spacing.sm,
  },
  debtInput: {
    flex: 1,
    minHeight: 42,
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    paddingHorizontal: theme.spacing.sm,
    color: theme.color.textPrimary,
    backgroundColor: theme.color.surfaceAlt,
    ...theme.typography.bodyMd,
  },
  debtPayButtonWrap: {
    minWidth: 130,
  },
  debtQuickRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
});
