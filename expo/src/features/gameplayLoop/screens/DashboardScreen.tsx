import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import ActionHubPanel from '@/components/gameplay/ActionHubPanel';
import { OnboardingHighlight } from '@/components/onboarding';
import EmptyStateView from '@/components/ui/EmptyStateView';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import { finalizePlayerWorkState } from '@/lib/api/gameplay';
import { BALANCE } from '@/lib/balanceConfig';
import { normalizeJobName } from '@/lib/economySafety';
import { formatMoney } from '@/lib/gameplayFormatters';
import { recordInfo } from '@/lib/logger';
import { DailyActionItem } from '@/types/gameplay';

import { useGameplayLoop } from '../context';
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

function getRideshareTripPreview(mode: RideshareMode, trips: number): {
  payMin: number;
  payMax: number;
  stress: number;
  health: number;
} {
  if (mode === 'night') {
    return { payMin: trips * 22, payMax: trips * 35, stress: trips * 4, health: trips * -3 };
  }
  if (mode === 'morning_peak' || mode === 'evening_peak') {
    return { payMin: trips * 18, payMax: trips * 28, stress: trips * 5, health: trips * -1 };
  }
  return { payMin: trips * 12, payMax: trips * 20, stress: trips * 2, health: trips * -1 };
}

function sanitizeRideShareReason(reason: string | null | undefined): string {
  const normalized = String(reason || '').trim();
  if (!normalized) return 'Ride share unavailable right now.';
  if (normalized.toLowerCase().includes('not authenticated')) {
    return 'Ride share is unavailable right now.';
  }
  return normalized;
}

interface StarterJobOption {
  job_key: string;
  title: string;
  monthly_pay_xgp: number;
  stability_weight: number;
  performance_weight: number;
  stress_sensitivity: number;
}

const INTERACTION_DIAGNOSTICS_ENABLED =
  __DEV__
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === 'true'
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === '1';

function asStarterJobOptions(raw: unknown): StarterJobOption[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((entry) => {
      const row = entry && typeof entry === 'object' ? (entry as Record<string, unknown>) : {};
      const job_key = normalizeJobName(row.job_key) || '';
      if (!job_key) return null;
      return {
        job_key,
        title: String(row.title || job_key),
        monthly_pay_xgp: Number(row.monthly_pay_xgp || 0) || 0,
        stability_weight: Number(row.stability_weight || 0) || 0,
        performance_weight: Number(row.performance_weight || 0) || 0,
        stress_sensitivity: Number(row.stress_sensitivity || 0) || 0,
      };
    })
    .filter((entry): entry is StarterJobOption => Boolean(entry));
}

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
  const cash = stats?.cash_xgp ?? 0;
  const stress = stats?.stress ?? 0;
  const health = stats?.health ?? 100;
  const debt = loop.expenseDebt?.debtAmount ?? stats?.debt_xgp ?? 0;

  const [houstonNow, setHoustonNow] = useState(() => new Date());
  const [autoClockingOut, setAutoClockingOut] = useState(false);
  const [timelineNotes, setTimelineNotes] = useState<TimelineNote[]>([]);
  const [busyRecoveryId, setBusyRecoveryId] = useState<RecoveryPresetId | null>(null);
  const previousWorkStateRef = useRef<{
    completedAt: string | null;
    shiftEndsAt: string | null;
    active: boolean;
  } | null>(null);
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
  const shiftEndLabel = workState?.shift_ends_at ? formatHoustonNow(new Date(workState.shift_ends_at)) : '5:00 PM';
  const scheduledShiftWindowLabel = shiftWindowLabel(workState);
  const scheduledShiftEndLabel = workState?.scheduled_shift_end_label || shiftEndLabel;
  const lastCompletedShift = workState?.last_completed_shift || null;

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
    if (backendShiftActive) return `Backend shows an active shift until ${shiftEndLabel}.`;
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
  const rideshareMode = getRideshareMode(houstonHour);

  const rideshareTripsToday = useMemo(
    () => loop.dailySession.actionsTakenToday
      .filter((entry) => canonicalDashboardActionKey(String(entry.action_key || '')) === 'side_income' && entry.success)
      .reduce((sum, entry) => {
        const rawTrips = Number(entry.raw_result?.trips ?? entry.raw_result?.trips_completed ?? 1);
        return sum + (Number.isFinite(rawTrips) ? Math.max(1, Math.round(rawTrips)) : 1);
      }, 0),
    [loop.dailySession.actionsTakenToday],
  );
  const rideshareEarnedToday = useMemo(
    () => loop.dailySession.actionsTakenToday
      .filter((entry) => canonicalDashboardActionKey(String(entry.action_key || '')) === 'side_income' && entry.success)
      .reduce((sum, entry) => {
        const earnedRaw = Number(
          (entry.raw_result?.earned ?? entry.raw_result?.net_income_xgp ?? entry.impact_snapshot?.cash_delta_xgp) || 0,
        );
        return sum + (Number.isFinite(earnedRaw) ? earnedRaw : 0);
      }, 0),
    [loop.dailySession.actionsTakenToday],
  );
  const rideshareDailyCap = Math.max(1, Number(BALANCE.ACTION_CAPS.side_income || 6));
  const sideIncomeGuard = sideIncomeAction
    ? loop.dailySession.canExecuteAction(sideIncomeAction)
    : { allowed: false, reason: 'Ride share action is not available yet.', timeCostUnits: 0 };
  const rideshareAvailable = Boolean(
    sideIncomeAction
    && !backendShiftActive
    && Boolean(workState?.rideshare_available)
    && sideIncomeGuard.allowed
    && loop.dailySession.sessionStatus === 'active',
  );

  const rideshareStatusLabel = useMemo(() => {
    if (loop.dailySession.sessionStatus !== 'active') return 'Day ended';
    if (backendShiftActive || autoClockingOut) return `Unavailable during work shift (available after ${shiftEndLabel})`;
    if (workState?.is_weekend) return 'Available all day (weekend)';
    if (workState?.no_shift_scheduled) return 'Available all day (no required shift)';
    if (!workState?.rideshare_unlocked) return `Available after ${scheduledShiftEndLabel} (shift end)`;
    if (!sideIncomeAction) return 'Ride share not unlocked yet';
    if (!sideIncomeGuard.allowed) return sanitizeRideShareReason(sideIncomeGuard.reason);
    return 'Available now';
  }, [
    autoClockingOut,
    backendShiftActive,
    loop.dailySession.sessionStatus,
    scheduledShiftEndLabel,
    shiftEndLabel,
    sideIncomeAction,
    sideIncomeGuard.allowed,
    sideIncomeGuard.reason,
    workState?.is_weekend,
    workState?.no_shift_scheduled,
    workState?.rideshare_unlocked,
  ]);

  const busyActionKey = canonicalDashboardActionKey(String(loop.busyActionKey || ''));
  const runningSideIncome = loop.executingAction && busyActionKey === 'side_income';
  const runningWorkAction = loop.executingAction && busyActionKey === 'work_shift';

  const switchJobAction = useMemo(() => {
    if (!loop.actionHub) return null;
    return (
      [...(loop.actionHub.recommended_actions || []), ...(loop.actionHub.available_actions || [])]
        .find((action) => String(action.action_key || '').toLowerCase() === 'switch_job')
      || null
    );
  }, [loop.actionHub]);
  const starterJobOptions = useMemo(
    () => asStarterJobOptions(switchJobAction?.parameters?.job_options),
    [switchJobAction?.parameters?.job_options],
  );
  const currentJobKey = String(
    loop.actionHub?.debug_meta?.current_job_key
    || loop.dashboard?.stats?.current_job
    || '',
  ).trim();
  const jobProgress = loop.dashboard?.job_progress || null;
  const jobLevelMax = Math.max(1, Number(jobProgress?.max_job_level || 40));
  const jobLevel = Math.max(1, Math.min(jobLevelMax, Number(jobProgress?.job_level || jobProgress?.skill_level || 1)));
  const jobXp = Math.max(0, Number(jobProgress?.job_xp || 0));
  const jobXpToNext = Math.max(0, Number(jobProgress?.job_xp_to_next_level || 0));
  const monthlyPay = Number(jobProgress?.monthly_pay_xgp || 0);
  const estimatedHourlyPay = monthlyPay > 0 ? monthlyPay / 30 / 8 : 0;
  const jobLevelDetail = jobLevel >= jobLevelMax
    ? `Level cap reached (${jobLevelMax})`
    : `${Math.round(jobXp)} / ${Math.round(jobXpToNext)} XP to next`;
  const employerLabel = String(
    jobProgress?.position_title
    || jobProgress?.employer_company_name
    || '',
  ).trim();
  const hasStarterJobSelected = Boolean(
    loop.actionHub?.debug_meta?.has_starter_job_selected
    ?? currentJobKey,
  );
  const firstSessionFlag = Boolean(
    loop.dashboard?.debug_meta?.new_player_first_session
    ?? loop.actionHub?.debug_meta?.new_player_first_session
    ?? false,
  );
  const showStarterJobChooser = starterJobOptions.length > 0 && (firstSessionFlag || !hasStarterJobSelected);
  const selectingStarterJob = loop.executingAction && loop.busyActionKey === 'switch_job';
  const endDayDisabled = !loop.dailyProgression.canAdvanceDay || loop.endingDay || backendShiftActive || autoClockingOut;

  useEffect(() => {
    if (!INTERACTION_DIAGNOSTICS_ENABLED) return;
    recordInfo('gameplayLoop', 'Dashboard job selection visibility evaluated.', {
      action: 'job_selection_visibility',
      context: {
        playerId: loop.playerId,
        firstSessionFlag,
        showStarterJobChooser,
        starterJobOptionsCount: starterJobOptions.length,
        hasStarterJobSelected,
        currentJobKey: currentJobKey || null,
      },
    });
  }, [
    currentJobKey,
    firstSessionFlag,
    hasStarterJobSelected,
    loop.playerId,
    showStarterJobChooser,
    starterJobOptions.length,
  ]);

  const selectStarterJob = (job: StarterJobOption) => {
    const rawJobKey = String(job.job_key || '');
    const canonicalJobKey = normalizeJobName(rawJobKey);
    if (!canonicalJobKey) return;
    if (INTERACTION_DIAGNOSTICS_ENABLED) {
      recordInfo('gameplayLoop', 'Starter job selected from dashboard.', {
        action: 'dashboard_switch_job_selected',
        context: {
          playerId: loop.playerId,
          rawJobKey,
          canonicalJobKey,
          hasStarterJobSelected,
        },
      });
    }
    const template: DailyActionItem = switchJobAction || {
      action_key: 'switch_job',
      title: 'Choose Your First Job',
      description: 'Select one starter role to unlock work-shift income.',
      status: 'available',
      blockers: [],
      warnings: [],
      tradeoffs: [],
      confidence_level: 'unknown',
      parameters: {},
    };
    const action: DailyActionItem = {
      ...template,
      title: hasStarterJobSelected ? `Switch To ${job.title}` : `Choose ${job.title}`,
      status: 'available',
      parameters: {
        ...(template.parameters || {}),
        new_job_key: canonicalJobKey,
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

  const todaysActivity = useMemo(() => {
    const merged = [...timelineNotes, ...actionTimeline];
    return merged.sort(
      (a, b) => new Date(a.timestampIso).getTime() - new Date(b.timestampIso).getTime(),
    );
  }, [actionTimeline, timelineNotes]);

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
      detail: 'Backend shift started. Waiting for Houston-time completion.',
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
        title: 'Backend confirmed shift completion',
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
          rideshareAvailable: Boolean(workState?.rideshare_available),
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
        rideshareAvailable: workState.rideshare_available,
        rideshareUnlocked: workState.rideshare_unlocked,
      },
    });
  }, [
    loopPlayerId,
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
        detail: 'Requesting backend finalize/refresh.',
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
            message: 'Timer reached zero. Waiting for backend confirmation to finish the shift.',
          });
        } else if (finalizedState?.shift_status === 'completed') {
          const earnedCash = Number(finalizedState.last_completed_shift?.earned_cash_xgp || 0);
          const xpGained = Number(finalizedState.last_completed_shift?.xp_gained || 0);
          setLoopFeedback({
            tone: 'success',
            message: `Shift completed. Earned ${formatMoney(earnedCash)} and ${Math.round(xpGained)} XP.`,
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

    if (backendShiftActive || autoClockingOut) {
      loop.setFeedback({
        tone: 'error',
        message: `Unavailable during work shift. Available after ${shiftEndLabel}.`,
      });
      return;
    }

    if (!sideIncomeGuard.allowed) {
      loop.setFeedback({
        tone: 'error',
        message: sanitizeRideShareReason(sideIncomeGuard.reason),
      });
      return;
    }

    const trips = requestedTrips === 3 || requestedTrips === 5 ? requestedTrips : 1;
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
    await loop.eatMeal(mealType);
    setBusyMeal(null);
  }

  // Finance / Loans
  const [loanAmount, setLoanAmount] = useState<100 | 200 | 300 | 500>(100);
  const [busyLoan, setBusyLoan] = useState(false);
  const busyFinance = loop.executingAction || busyLoan;
  const loanRepay = Math.round(loanAmount * 1.15);

  async function handleLoan() {
    if (busyFinance) return;
    setBusyLoan(true);
    await loop.takeLoan(loanAmount);
    setBusyLoan(false);
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
        <OnboardingHighlight target="dashboard-core-stats">
          <GameplaySummaryCard eyebrow="Status" title="Money, Health &amp; Stress">
            <GameplayCompactMetricRows
              items={[
                {
                  label: 'Cash',
                  value: formatMoney(cash),
                  tone: cash < 50 ? 'danger' : cash < 200 ? 'warning' : 'positive',
                },
                {
                  label: 'Net flow today',
                  value: signedCurrency(netCashFlow),
                  tone: netCashFlow >= 0 ? 'positive' : 'danger',
                },
                {
                  label: 'Debt',
                  value: formatMoney(stats.debt_xgp),
                  tone: stats.debt_xgp > cash ? 'danger' : 'neutral',
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
      ) : (
        <GameplayWarningBanner
          title="No stats loaded"
          message="Pull to refresh."
          tone="info"
        />
      )}

      {/* Game time */}
      <GameplaySummaryCard eyebrow="Game Time" title="Houston Clock">
        <GameplayCompactMetricRows
          items={[
            { label: 'Current day', value: `Day ${dayLabel}` },
            { label: 'Current time', value: `${formatHoustonNow(houstonNow)} CT` },
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

      {/* Work shift */}
      <GameplaySummaryCard eyebrow="Work" title="Income &amp; Shifts">
        <View style={styles.metricRow}>
          <GameplayStatCard
            label="Today's pay"
            value={loop.jobIncome.dailyIncomeLabel}
            tone={loop.jobIncome.incomeAmount != null && loop.jobIncome.incomeAmount >= 0 ? 'positive' : 'warning'}
            note={employerLabel || (loop.jobIncome.currentJob ? loop.jobIncome.currentJob.replace(/_/g, ' ') : 'No job selected')}
          />
          <GameplayStatCard
            label="Job level"
            value={`Lv ${jobLevel}/${jobLevelMax}`}
            tone={jobLevel >= jobLevelMax ? 'positive' : 'info'}
            note={jobLevelDetail}
          />
          <GameplayStatCard
            label="Pay scale"
            value={monthlyPay > 0 ? formatMoney(monthlyPay) : '--'}
            tone={monthlyPay > 0 ? 'positive' : 'neutral'}
            note={monthlyPay > 0 ? `~${formatMoney(estimatedHourlyPay)}/hour` : 'Monthly salary updates with level'}
          />
          <GameplayStatCard
            label="Shift status"
            value={autoClockingOut ? 'Auto-finalizing' : backendShiftActive ? 'On shift' : backendShiftCompleted ? 'Completed' : canClockIn ? 'Ready to clock in' : 'Off shift'}
            tone={backendShiftActive || autoClockingOut ? 'warning' : backendShiftCompleted ? 'positive' : canClockIn ? 'positive' : 'neutral'}
            note={
              backendShiftActive || autoClockingOut
                ? `Ends at ${shiftEndLabel} CT`
                : backendShiftCompleted
                  ? 'Backend confirmed completion'
                  : `Window: ${scheduledShiftWindowLabel}`
            }
          />
          <GameplayStatCard
            label="Shift timer"
            value={backendShiftActive ? shiftRemainingLabel : autoClockingOut ? 'Syncing...' : '--'}
            tone={backendShiftActive || autoClockingOut ? 'warning' : 'neutral'}
            note={SHIFT_SHORT_MODE ? 'Backend timer (accelerated testing mode)' : 'Backend auto-finalizes at shift end'}
          />
          <GameplayStatCard
            label="Time left"
            value={`${loop.dailySession.remainingTimeUnits}/${loop.dailySession.totalTimeUnits}`}
            tone={loop.dailySession.remainingTimeUnits <= 2 ? 'warning' : 'info'}
            note="Each shift uses time units."
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
            message={`Backend shows you clocked in. Shift ends at ${shiftEndLabel} CT.`}
            tone="info"
          />
        ) : autoClockingOut ? (
          <GameplayWarningBanner
            title="Auto-finalizing"
            message="Timer reached zero. Waiting for backend confirmation before unlocking ride share."
            tone="warning"
          />
        ) : backendShiftCompleted && lastCompletedShift ? (
          <GameplayWarningBanner
            title="Shift completed"
            message={`Earned ${formatMoney(lastCompletedShift.earned_cash_xgp)} | XP +${Math.round(lastCompletedShift.xp_gained)} | Ride share ${rideshareStatusLabel.toLowerCase()}.`}
            tone="info"
          />
        ) : clockInBlocker ? (
          <Text style={styles.helperText}>{clockInBlocker}</Text>
        ) : (
          <Text style={styles.helperText}>
            Clock in, then let the backend finalize the shift when Houston time reaches the scheduled end.
          </Text>
        )}
      </GameplaySummaryCard>

      {showStarterJobChooser ? (
        <GameplaySummaryCard
          eyebrow={hasStarterJobSelected ? 'Switch Job' : 'Day 1 - Choose Your Job'}
          title={hasStarterJobSelected ? `Current: ${currentJobKey.replace(/_/g, ' ')}` : 'Pick a Role to Start Earning'}
        >
          <View style={styles.jobOptionsGrid}>
            {starterJobOptions.map((job) => {
              const isCurrent = currentJobKey === job.job_key;
              return (
                <View key={job.job_key} style={[styles.jobOptionCard, isCurrent ? styles.jobOptionCardActive : null]}>
                  <Text style={styles.jobTitle}>{job.title}</Text>
                  <Text style={styles.jobPay}>~{Math.round(job.monthly_pay_xgp)} xgp/mo</Text>
                  <Pressable
                    accessibilityRole="button"
                    style={[
                      styles.jobSelectButton,
                      isCurrent ? styles.jobSelectButtonCurrent : null,
                      selectingStarterJob ? styles.jobSelectButtonDisabled : null,
                    ]}
                    disabled={selectingStarterJob || isCurrent}
                    onPress={() => selectStarterJob(job)}
                  >
                    <Text style={[styles.jobSelectButtonLabel, isCurrent ? styles.jobSelectButtonLabelCurrent : null]}>
                      {isCurrent ? 'Current Job' : selectingStarterJob ? 'Applying...' : 'Select'}
                    </Text>
                  </Pressable>
                </View>
              );
            })}
          </View>
        </GameplaySummaryCard>
      ) : null}

      {/* Ride share */}
      <GameplaySummaryCard eyebrow="Side Income" title="Post-Shift Ride Share">
        <GameplayCompactMetricRows
          items={[
            {
              label: 'Status',
              value: rideshareStatusLabel,
              tone: rideshareAvailable ? 'positive' : backendShiftActive || autoClockingOut ? 'warning' : 'neutral',
            },
            { label: 'Houston time', value: `${formatHoustonNow(houstonNow)} CT` },
            { label: 'Mode', value: formatRideshareMode(rideshareMode) },
            {
              label: 'Trips today',
              value: `${Math.round(workState?.side_income_hours_today || rideshareTripsToday)} / ${rideshareDailyCap}`,
            },
            {
              label: 'Ride share earned today',
              value: formatMoney(rideshareEarnedToday),
              tone: rideshareEarnedToday > 0 ? 'positive' : 'neutral',
            },
            { label: 'Time per trip', value: '1 time unit (20-45 mins simulated)' },
          ]}
        />

        <View style={styles.recoveryList}>
          {RIDESHARE_TRIP_OPTIONS.map((tripOption) => {
            const preview = getRideshareTripPreview(rideshareMode, tripOption);
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
                    disabled={!rideshareAvailable || runningSideIncome || autoClockingOut || loop.executingAction}
                  />
                </View>
              </View>
            );
          })}
        </View>
      </GameplaySummaryCard>

      {/* Action hub */}
      {actionHubForDisplay ? (
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
      ) : (
        <EmptyStateView
          title="No actions loaded"
          subtitle="Refresh to pull the latest actions."
        />
      )}

      {/* Recovery */}
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

      {/* Activity history */}
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

      {/* Meals */}
      <GameplaySummaryCard eyebrow="Life" title="Food &amp; Meals">
        {cash < 6 ? (
          <GameplayWarningBanner
            title="Not enough cash for a meal"
            message="You need at least 6 XGP. Run a shift first."
            tone="danger"
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
              disabled={busyLife || cash < 6}
            />
          </View>
        </View>
      </GameplaySummaryCard>

      {/* Finance */}
      <GameplaySummaryCard eyebrow="Finance" title="Quick Loan">
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
      </GameplaySummaryCard>

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
  jobOptionsGrid: {
    gap: theme.spacing.sm,
  },
  jobOptionCard: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.lg,
    backgroundColor: theme.color.surfaceAlt,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xxs,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  jobOptionCardActive: {
    borderColor: '#86efac',
    backgroundColor: '#f0fdf4',
  },
  jobTitle: {
    color: theme.color.textPrimary,
    ...theme.typography.bodyMd,
    fontWeight: '800',
    flex: 1,
  },
  jobPay: {
    color: theme.color.info,
    ...theme.typography.bodySm,
    fontWeight: '700',
    marginRight: theme.spacing.sm,
  },
  jobSelectButton: {
    minHeight: 36,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    borderColor: '#1d4ed8',
    backgroundColor: '#1d4ed8',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: theme.spacing.sm,
  },
  jobSelectButtonCurrent: {
    borderColor: '#16a34a',
    backgroundColor: '#dcfce7',
  },
  jobSelectButtonDisabled: {
    opacity: 0.7,
  },
  jobSelectButtonLabel: {
    color: '#ffffff',
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  jobSelectButtonLabelCurrent: {
    color: '#166534',
  },
});

