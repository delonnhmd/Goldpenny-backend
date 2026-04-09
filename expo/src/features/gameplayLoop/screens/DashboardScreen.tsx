import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Animated, StyleSheet, Text, TextInput, View } from 'react-native';

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
import { DailyActionItem, EconomySignalChip, JobMarketJobSnapshot } from '@/types/gameplay';

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

type RecoveryPresetId = 'watch_tv' | 'watch_movie' | 'read_book' | 'jogging' | 'eat_meal' | 'rest';

interface RecoveryPreset {
  id: RecoveryPresetId;
  title: string;
  timeCostUnits: number;
  stressChange: number;
  healthChange: number;
  skillChange: number;
}

const RECOVERY_PRESETS: RecoveryPreset[] = [
  { id: 'watch_tv', title: 'Watch TV', timeCostUnits: 1, stressChange: -4, healthChange: 0, skillChange: 0 },
  { id: 'watch_movie', title: 'Watch Movie', timeCostUnits: 1, stressChange: -5, healthChange: 0, skillChange: 0 },
  { id: 'read_book', title: 'Read Book', timeCostUnits: 1, stressChange: -2, healthChange: 0, skillChange: 1 },
  { id: 'jogging', title: 'Jogging', timeCostUnits: 1, stressChange: -3, healthChange: 2, skillChange: 0 },
  { id: 'eat_meal', title: 'Eat Meal', timeCostUnits: 1, stressChange: -4, healthChange: 2, skillChange: 0 },
  { id: 'rest', title: 'Rest', timeCostUnits: 1, stressChange: -6, healthChange: 3, skillChange: 0 },
];

function canonicalDashboardActionKey(actionKey: string): string {
  const raw = String(actionKey || '').toLowerCase().trim();
  if (!raw) return '';
  if (raw.includes('work') || raw.includes('shift')) return 'work_shift';
  if (raw.includes('ride') || raw.includes('side_income') || raw.includes('delivery')) return 'side_income';
  if (raw.includes('rest') || raw.includes('recover')) return 'rest';
  if (raw.includes('study') || raw.includes('train')) return 'study';
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

function shiftWindowLabel(workState?: {
  is_weekend?: boolean | null;
  scheduled_shift_window_label?: string | null;
} | null): string {
  if (workState?.is_weekend) return 'Weekend - no required shift';
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
  const netCashFlow = loop.economyState.netCashFlow ?? 0;
  const pressureLabel = loop.expenseDebt.debtPressure.charAt(0).toUpperCase()
    + loop.expenseDebt.debtPressure.slice(1);
  const criticalDebtPressure = String(loop.expenseDebt.debtPressure || '').toLowerCase() === 'critical';
  const cash = stats?.cash_xgp ?? 0;
  const stress = stats?.stress ?? 0;
  const health = stats?.health ?? 100;
  const debt = loop.expenseDebt?.debtAmount ?? stats?.debt_xgp ?? 0;
  const cashTone: 'positive' | 'neutral' | 'danger' = cash > 0 ? 'positive' : cash < 0 ? 'danger' : 'neutral';

  const [houstonNow, setHoustonNow] = useState(() => new Date());
  const [autoClockingOut, setAutoClockingOut] = useState(false);
  const [timelineNotes, setTimelineNotes] = useState<TimelineNote[]>([]);
  const [busyRecoveryId, setBusyRecoveryId] = useState<RecoveryPresetId | null>(null);
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
  const workState = loop.dashboard?.work_state || loop.actionHub?.work_state || null;
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
  const backendShiftActive = Boolean(workState?.main_shift_active_flag);
  const backendShiftCompleted = Boolean(
    workState
    && workState.shift_status === 'completed'
    && !workState.main_shift_active_flag
    && Number(workState.main_shift_hours_today || 0) > 0,
  );
  const backendShiftEndsAtMs = workState?.shift_ends_at ? new Date(workState.shift_ends_at).getTime() : Number.NaN;
  const backendShiftCompletedAt = workState?.shift_completed_at || null;
  const shiftRemainingSeconds = Number.isFinite(backendShiftEndsAtMs) && backendShiftActive
    ? Math.max(0, Math.floor((backendShiftEndsAtMs - houstonNow.getTime()) / 1000))
    : 0;
  const shiftRemainingLabel = formatSecondsRemaining(shiftRemainingSeconds);
  const shiftEndLabel = String(
    workState?.shift_end_time_label
    || (workState?.shift_ends_at ? `${formatHoustonNow(new Date(workState.shift_ends_at))} CT` : '5:00 PM CT'),
  );
  const scheduledShiftWindowLabel = shiftWindowLabel(workState);
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

  useEffect(() => {
    setAutoClockingOut(false);
    setTimelineNotes([]);
    setBusyRecoveryId(null);
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

  const gamePhaseLabel = useMemo(() => {
    if (loop.dailySession.sessionStatus === 'ended') return 'End of day';
    if (workState?.is_weekend) return 'Weekend';
    if (autoClockingOut) return 'Auto-finalizing';
    if (backendShiftActive) return 'On shift';
    if (backendShiftCompleted) return 'Shift completed';
    if (houstonHour < 9) return 'Before shift';
    if (houstonHour >= 17) return 'After shift';
    return 'Before shift';
  }, [autoClockingOut, backendShiftActive, backendShiftCompleted, houstonHour, loop.dailySession.sessionStatus, workState?.is_weekend]);

  const dayLabel = loop.dailySession.currentDay || loop.dailyProgression.currentGameDay || 1;
  const rideshareState = workState?.rideshare_state || null;
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
  const rideshareDailyCap = rideshareState?.max_trips ?? Math.max(1, Number(BALANCE.ACTION_CAPS.side_income || 6));
  const rideshareRemainingTrips = rideshareState?.remaining_trips ?? Math.max(0, rideshareDailyCap - rideshareTripsToday);
  const rideshareHoursRemainingToday = rideshareState?.hours_remaining_today ?? Math.max(0, Number(workState?.hours_available || 0));
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

  const rideshareStatusLabel = useMemo(() => {
    if (loop.dailySession.sessionStatus !== 'active') return 'Day ended';
    if (!sideIncomeAction) return 'Ride share action unavailable right now.';
    if (!rideshareState) return 'Ride share status syncing...';
    return sanitizeRideShareReason(rideshareState.reason || (rideshareState.can_rideshare ? 'Ride Share is available now.' : 'Ride share unavailable right now.'));
  }, [loop.dailySession.sessionStatus, rideshareState, sideIncomeAction]);
  const busyActionKey = canonicalDashboardActionKey(String(loop.busyActionKey || ''));
  const runningSideIncome = loop.executingAction && busyActionKey === 'side_income';
  const runningWorkAction = loop.executingAction && busyActionKey === 'work_shift';

  const getRideShareDisabledReason = useCallback((requestedTrips: number): string | null => {
    if (!sideIncomeAction) return 'Ride share action is not available yet.';
    if (loop.dailySession.sessionStatus !== 'active') return 'Day ended.';
    if (autoClockingOut) return 'Auto-finalizing shift. Ride share unlocks after sync.';
    if (runningSideIncome || loop.executingAction) return 'Another action is running.';
    if (!rideshareState) return 'Ride share status syncing...';
    if (!rideshareState.can_rideshare) return sanitizeRideShareReason(rideshareState.reason);
    if (requestedTrips > rideshareRemainingTrips) {
      if (rideshareRemainingTrips <= 0) {
        return sanitizeRideShareReason(rideshareState.reason || 'Daily ride share limit reached.');
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
    rideshareState,
    runningSideIncome,
    sideIncomeAction,
  ]);

  const rideshareDisableReasonsByTrip = useMemo(() => ({
    1: getRideShareDisabledReason(1),
    3: getRideShareDisabledReason(3),
    5: getRideShareDisabledReason(5),
  }), [getRideShareDisabledReason]);

  const rideshareAvailable = !rideshareDisableReasonsByTrip[1];

  const jobMarket = workState?.job_market || null;
  const currentJobKey = String(
    workState?.authoritative_current_job_id
    || workState?.active_shift_job_id
    || workState?.scheduled_shift_job_id
    || loop.actionHub?.debug_meta?.current_job_key
    || loop.dashboard?.stats?.current_job
    || '',
  ).trim();
  const currentJobDisplayName = String(
    workState?.current_job_display_name
    || loop.dashboard?.stats?.current_job_display
    || (currentJobKey ? currentJobKey.replace(/_/g, ' ') : 'No job selected'),
  ).trim();
  const jobProgress = loop.dashboard?.job_progress || null;
  const currentJobProgression = workState?.current_job_progression || jobProgress || null;
  const progressionFeedback = workState?.job_progression_feedback || null;
  const jobLevelMax = Math.max(1, Number(currentJobProgression?.max_job_level || 10));
  const jobLevel = Math.max(
    1,
    Math.min(
      jobLevelMax,
      Number(workState?.current_job_level || currentJobProgression?.job_level || currentJobProgression?.skill_level || 1),
    ),
  );
  const jobXp = Math.max(0, Number(currentJobProgression?.job_xp || 0));
  const jobXpToNext = Math.max(0, Number(currentJobProgression?.job_xp_to_next_level || 0));
  const promotionTier = String(currentJobProgression?.promotion_tier || 'Junior');
  const projectedNextMonthlyPay = Number(currentJobProgression?.estimated_next_level_monthly_salary_xgp || 0);
  const projectedSalaryIncreasePct = Number(currentJobProgression?.next_level_salary_increase_pct || 3);
  const jobLevelDetail = jobLevel >= jobLevelMax
    ? `Level cap reached (${jobLevelMax})`
    : `${Math.round(jobXp)} / ${Math.round(jobXpToNext)} XP to next`;
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
    else if (key === 'rest' || key === 'study') category = 'recovery';
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
    const stripRoutineActions = (actions: DailyActionItem[]) =>
      actions.filter((action) => {
        const key = canonicalDashboardActionKey(String(action.action_key || ''));
        return key !== 'work_shift' && key !== 'side_income';
      });

    return {
      ...loop.actionHub,
      recommended_actions: stripRoutineActions(loop.actionHub.recommended_actions || []),
      available_actions: stripRoutineActions(loop.actionHub.available_actions || []),
      blocked_actions: stripRoutineActions(loop.actionHub.blocked_actions || []),
    };
  }, [loop.actionHub]);

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
        statusLabelShown: rideshareStatusLabel,
        buttonDisabledReasonRun1: rideshareDisableReasonsByTrip[1],
        buttonDisabledReasonRun3: rideshareDisableReasonsByTrip[3],
        buttonDisabledReasonRun5: rideshareDisableReasonsByTrip[5],
      },
    });
  }, [
    loopPlayerId,
    rideshareDisableReasonsByTrip,
    rideshareStatusLabel,
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
          setLoopFeedback({
            tone: 'success',
            message: progressionMsg
              ? `Shift completed. Earned ${formatMoney(earnedCash)} and ${Math.round(xpGained)} work XP. ${progressionMsg}.`
              : `Shift completed. Earned ${formatMoney(earnedCash)} and ${Math.round(xpGained)} work XP.`,
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
        message: 'Ride share is not unlocked yet.',
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

  const runRecoveryAction = async (preset: RecoveryPreset) => {
    if (backendShiftActive || autoClockingOut) {
      loop.setFeedback({
        tone: 'error',
        message: `Recovery actions are unavailable during shift. Available after ${shiftEndLabel}.`,
      });
      return;
    }

    setBusyRecoveryId(preset.id);

    try {
      if (preset.id === 'eat_meal') {
        await loop.eatMeal('dinner');
      } else if (preset.id === 'read_book') {
        await loop.executeAction({
          action_key: 'study',
          title: 'Read Book',
          description: 'Read for focused recovery and skill growth.',
          status: 'available',
          blockers: [],
          warnings: [],
          tradeoffs: [],
          confidence_level: 'high',
          parameters: { training_hours: 1 },
        });
      } else if (preset.id === 'jogging') {
        await loop.executeAction({
          action_key: 'rest',
          title: 'Jogging',
          description: 'Jog lightly to lower stress and improve health.',
          status: 'available',
          blockers: [],
          warnings: [],
          tradeoffs: [],
          confidence_level: 'medium',
          parameters: { recovery_mode: 'jogging' },
        });
      } else if (preset.id === 'watch_tv' || preset.id === 'watch_movie') {
        await loop.executeAction({
          action_key: 'rest',
          title: preset.title,
          description: `${preset.title} to decompress before your next money move.`,
          status: 'available',
          blockers: [],
          warnings: [],
          tradeoffs: [],
          confidence_level: 'high',
          parameters: { recovery_mode: preset.id },
        });
      } else {
        await loop.executeAction({
          action_key: 'rest',
          title: 'Rest',
          description: 'Take a short recovery block to reduce stress.',
          status: 'available',
          blockers: [],
          warnings: [],
          tradeoffs: [],
          confidence_level: 'high',
          parameters: { recovery_mode: 'rest' },
        });
      }
    } finally {
      setBusyRecoveryId(null);
    }
  };

  // Life / Meals
  const [busyMeal, setBusyMeal] = useState<string | null>(null);
  const busyLife = loop.executingAction || busyMeal !== null || backendShiftActive || autoClockingOut;

  async function handleEat(mealType: 'breakfast' | 'lunch' | 'dinner') {
    if (backendShiftActive || autoClockingOut) {
      loop.setFeedback({
        tone: 'error',
        message: `Meals and recovery are unavailable during shift. Available after ${shiftEndLabel}.`,
      });
      return;
    }

    if (busyLife) return;

    setBusyMeal(`eat_${mealType}`);
    try {
      await loop.eatMeal(mealType);
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
        },
      });
      if (ok) {
        setDebtPaymentAmount('0');
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
              { label: 'Houston time', value: currentHoustonTimeLabel },
              { label: 'Day reset', value: dayRolloverLabel },
              { label: 'Date', value: formatHoustonDate(houstonNow) },
              {
                label: 'Phase / status',
                value: gamePhaseLabel,
                tone: backendShiftActive || autoClockingOut ? 'warning' : backendShiftCompleted ? 'positive' : 'info',
              },
              { label: 'Shift window', value: scheduledShiftWindowLabel },
              { label: 'Timer mode', value: SHIFT_SHORT_MODE ? 'Accelerated testing mode' : 'Real-time mode' },
            ]}
          />
        </GameplaySummaryCard>
      </SlideFadeInOnChange>

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
            value={autoClockingOut ? 'Auto-finalizing' : backendShiftActive ? 'Active' : backendShiftCompleted ? 'Completed' : canClockIn ? 'Ready' : 'Off shift'}
            tone={backendShiftActive || autoClockingOut ? 'warning' : backendShiftCompleted ? 'positive' : canClockIn ? 'positive' : 'neutral'}
            note={
              backendShiftActive || autoClockingOut
                ? `Ends ${shiftEndLabel}`
                : backendShiftCompleted
                  ? salaryStatusMessage
                  : `Window: ${scheduledShiftWindowLabel}`
            }
          />
          <GameplayStatCard
            label="Shift end (CT)"
            value={backendShiftActive ? shiftEndLabel : `${workState?.scheduled_shift_end_label || '5:00 PM'} CT`}
            tone={backendShiftActive ? 'warning' : 'info'}
            note="Houston local time."
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
            value={`Lv ${jobLevel}/${jobLevelMax}`}
            tone={jobLevel >= jobLevelMax ? 'positive' : 'info'}
            note={`${promotionTier} · ${jobLevelDetail}`}
          />
          <GameplayStatCard
            label="Salary preview"
            value={projectedNextMonthlyPay > 0 ? formatMoney(projectedNextMonthlyPay) : '--'}
            tone="info"
            note={`Estimated next level (+${Math.round(projectedSalaryIncreasePct)}%). Live payroll unchanged.`}
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
            note={SHIFT_SHORT_MODE ? 'Accelerated testing mode.' : 'Real-time shift timer.'}
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
                    : 'Clock In'
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
        ) : backendShiftCompleted && lastCompletedShift ? (
          <GameplayWarningBanner
            title="Shift completed"
            message={
              progressionFeedback?.feedback_message
                ? `Earned ${formatMoney(lastCompletedShift.earned_cash_xgp)} | Work XP +${Math.round(lastCompletedShift.xp_gained)} | ${progressionFeedback.feedback_message} | Ride share ${rideshareStatusLabel.toLowerCase()}.`
                : `Earned ${formatMoney(lastCompletedShift.earned_cash_xgp)} | Work XP +${Math.round(lastCompletedShift.xp_gained)} | Ride share ${rideshareStatusLabel.toLowerCase()}.`
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
                      label={runningSideIncome ? 'Running...' : `Run ${tripOption}`}
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

      {/* Recovery */}
      <SlideFadeInOnChange
        watchValue={`recovery_${dayLabel}_${backendShiftActive ? 'locked' : 'open'}_${busyRecoveryId || 'idle'}`}
        delayMs={120}
      >
      <GameplaySummaryCard eyebrow="Recovery" title="Recovery Actions">
        {(backendShiftActive || autoClockingOut) ? (
          <GameplayWarningBanner
            title="Recovery locked during shift"
            message={`Recovery actions unlock after ${shiftEndLabel} CT.`}
            tone="warning"
          />
        ) : null}

        <View style={styles.recoveryList}>
          {RECOVERY_PRESETS.map((preset) => {
            const running = busyRecoveryId === preset.id;
            return (
              <View key={preset.id} style={styles.recoveryRow}>
                <View style={styles.recoveryInfo}>
                  <Text style={styles.recoveryTitle}>{preset.title}</Text>
                  <Text style={styles.recoveryMeta}>
                    Time {preset.timeCostUnits}u | Stress {signedWhole(preset.stressChange)} | Health {signedWhole(preset.healthChange)} | Skill {signedWhole(preset.skillChange)}
                  </Text>
                </View>
                <View style={styles.recoveryActionWrap}>
                  <SecondaryButton
                    label={running ? 'Running...' : 'Do'}
                    onPress={() => void runRecoveryAction(preset)}
                    disabled={Boolean(busyRecoveryId) || loop.executingAction || backendShiftActive || autoClockingOut}
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
        <View style={styles.buttonRow}>
          <View style={styles.mealBtn}>
            <PrimaryButton
              label={busyMeal === 'eat_breakfast' ? 'Eating...' : 'Breakfast (-6 XGP)'}
              onPress={() => void handleEat('breakfast')}
              disabled={busyLife || cash < 6}
            />
          </View>
          <View style={styles.mealBtn}>
            <SecondaryButton
              label={busyMeal === 'eat_lunch' ? 'Eating...' : 'Lunch (-6 XGP)'}
              onPress={() => void handleEat('lunch')}
              disabled={busyLife || cash < 6}
            />
          </View>
          <View style={styles.mealBtn}>
            <SecondaryButton
              label={busyMeal === 'eat_dinner' ? 'Eating...' : 'Dinner (-6 XGP)'}
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
            label={busyLoan ? 'Borrowing...' : `Borrow ${loanAmount} XGP`}
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
              label={busyDebtPayment ? 'Paying...' : 'Pay Debt'}
              onPress={() => void handleDebtPayment()}
              disabled={busyFinance || maxDebtPayable <= 0}
            />
          </View>
        </View>
        <View style={styles.debtQuickRow}>
          {[10, 25, 50].map((quickAmount) => (
            <View key={`quick_debt_${quickAmount}`} style={styles.loanAmtBtn}>
              <SecondaryButton
                label={`Pay ${quickAmount}`}
                onPress={() => void handleDebtPayment(quickAmount)}
                disabled={busyFinance || quickAmount > maxDebtPayable}
              />
            </View>
          ))}
          <View style={styles.loanAmtBtn}>
            <SecondaryButton
              label="Pay Max"
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



