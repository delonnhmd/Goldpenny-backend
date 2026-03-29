import React, { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import ActionHubPanel from '@/components/gameplay/ActionHubPanel';
import { OnboardingHighlight } from '@/components/onboarding';
import EmptyStateView from '@/components/ui/EmptyStateView';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import { BALANCE } from '@/lib/balanceConfig';
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
const SHIFT_START_HOUR = 9;
const SHIFT_END_HOUR = 17;
const FULL_SHIFT_SECONDS = 8 * 60 * 60;
const SHORT_SHIFT_SECONDS = Math.max(30, Number(process.env.EXPO_PUBLIC_SHIFT_TIMER_SECONDS || 90));
const SHIFT_SHORT_MODE =
  __DEV__
  || process.env.EXPO_PUBLIC_SHIFT_TIMER_SHORT_MODE === 'true'
  || process.env.EXPO_PUBLIC_SHIFT_TIMER_SHORT_MODE === '1';

interface ShiftClockState {
  startedAtMs: number;
  endsAtMs: number;
  action: DailyActionItem;
}

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

function shiftWindowLabel(): string {
  return '9:00 AM - 5:00 PM (Houston)';
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
      const job_key = String(row.job_key || '').trim();
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
  const [activeShift, setActiveShift] = useState<ShiftClockState | null>(null);
  const [autoClockingOut, setAutoClockingOut] = useState(false);
  const [timelineNotes, setTimelineNotes] = useState<TimelineNote[]>([]);
  const [busyRecoveryId, setBusyRecoveryId] = useState<RecoveryPresetId | null>(null);

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

  useEffect(() => {
    setActiveShift(null);
    setAutoClockingOut(false);
    setTimelineNotes([]);
    setBusyRecoveryId(null);
  }, [loop.dailySession.currentDay]);

  const appendTimelineNote = (note: Omit<TimelineNote, 'id'>) => {
    const id = `${note.timestampIso}_${Math.random().toString(36).slice(2, 8)}`;
    setTimelineNotes((prev) => [...prev, { ...note, id }]);
  };

  const houstonHour = getHoustonHour(houstonNow);
  const currentShiftWindowOpen = houstonHour >= SHIFT_START_HOUR && houstonHour < SHIFT_END_HOUR;
  const shiftDurationSeconds = SHIFT_SHORT_MODE ? SHORT_SHIFT_SECONDS : FULL_SHIFT_SECONDS;
  const shiftRemainingSeconds = activeShift
    ? Math.max(0, Math.floor((activeShift.endsAtMs - houstonNow.getTime()) / 1000))
    : 0;
  const shiftRemainingLabel = formatSecondsRemaining(shiftRemainingSeconds);
  const shiftEndLabel = activeShift
    ? formatHoustonNow(new Date(activeShift.endsAtMs))
    : '5:00 PM';

  const workExecutionGuard = workShiftAction
    ? loop.dailySession.canExecuteAction(workShiftAction)
    : { allowed: false, reason: 'No shift action available.', timeCostUnits: 0 };

  const canClockIn = Boolean(
    workShiftAction
    && !activeShift
    && !autoClockingOut
    && loop.dailySession.sessionStatus === 'active'
    && workExecutionGuard.allowed
    && (SHIFT_SHORT_MODE || currentShiftWindowOpen),
  );

  const clockInBlocker = useMemo(() => {
    if (activeShift) return 'You are already clocked in.';
    if (loop.dailySession.sessionStatus !== 'active') return 'Day already ended.';
    if (!workShiftAction) return 'No work shift is available right now.';
    if (!SHIFT_SHORT_MODE && !currentShiftWindowOpen) return 'Clock-in opens at 9:00 AM Houston time.';
    if (!workExecutionGuard.allowed) return workExecutionGuard.reason || 'Cannot start shift right now.';
    return null;
  }, [
    activeShift,
    currentShiftWindowOpen,
    loop.dailySession.sessionStatus,
    workExecutionGuard.allowed,
    workExecutionGuard.reason,
    workShiftAction,
  ]);

  const gamePhaseLabel = useMemo(() => {
    if (loop.dailySession.sessionStatus === 'ended') return 'End of day';
    if (activeShift) return 'On shift';
    if (houstonHour < SHIFT_START_HOUR) return 'Before shift';
    if (houstonHour >= SHIFT_END_HOUR) return 'After shift';
    return 'Before shift';
  }, [activeShift, houstonHour, loop.dailySession.sessionStatus]);

  const dayLabel = loop.dailySession.currentDay || loop.dailyProgression.currentGameDay || 1;

  const rideshareTripsToday = useMemo(
    () => loop.dailySession.actionsTakenToday.filter((entry) => canonicalDashboardActionKey(String(entry.action_key || '')) === 'side_income' && entry.success).length,
    [loop.dailySession.actionsTakenToday],
  );
  const rideshareEarnedToday = useMemo(
    () => loop.dailySession.actionsTakenToday
      .filter((entry) => canonicalDashboardActionKey(String(entry.action_key || '')) === 'side_income' && entry.success)
      .reduce((sum, entry) => sum + Number(entry.impact_snapshot?.cash_delta_xgp || 0), 0),
    [loop.dailySession.actionsTakenToday],
  );
  const rideshareDailyCap = Math.max(1, Number(BALANCE.ACTION_CAPS.side_income || 5));
  const rideshareTimeWindowOpen = SHIFT_SHORT_MODE || houstonHour < SHIFT_START_HOUR || houstonHour >= SHIFT_END_HOUR;
  const sideIncomeGuard = sideIncomeAction
    ? loop.dailySession.canExecuteAction(sideIncomeAction)
    : { allowed: false, reason: 'Ride share action is not available yet.', timeCostUnits: 0 };
  const rideshareAvailable = Boolean(
    sideIncomeAction
    && !activeShift
    && rideshareTimeWindowOpen
    && sideIncomeGuard.allowed
    && loop.dailySession.sessionStatus === 'active',
  );

  const rideshareStatusLabel = useMemo(() => {
    if (loop.dailySession.sessionStatus !== 'active') return 'Day ended';
    if (activeShift) return `Unavailable during work shift (available after ${shiftEndLabel})`;
    if (!rideshareTimeWindowOpen) return 'Available after 5:00 PM';
    if (!sideIncomeAction) return 'Ride share not unlocked yet';
    if (!sideIncomeGuard.allowed) return sanitizeRideShareReason(sideIncomeGuard.reason);
    if (houstonHour >= SHIFT_END_HOUR) return 'Available after shift';
    if (houstonHour < SHIFT_START_HOUR) return 'Available before shift';
    return 'Available now';
  }, [
    activeShift,
    houstonHour,
    loop.dailySession.sessionStatus,
    rideshareTimeWindowOpen,
    shiftEndLabel,
    sideIncomeAction,
    sideIncomeGuard.allowed,
    sideIncomeGuard.reason,
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
  const endDayDisabled = !loop.dailyProgression.canAdvanceDay || loop.endingDay || Boolean(activeShift) || autoClockingOut;

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
        new_job_key: job.job_key,
        job_key: job.job_key,
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

    const startMs = Date.now();
    const endMs = startMs + (shiftDurationSeconds * 1000);

    setActiveShift({
      startedAtMs: startMs,
      endsAtMs: endMs,
      action: workShiftAction,
    });

    appendTimelineNote({
      timestampIso: new Date(startMs).toISOString(),
      title: `Clocked in to ${workShiftAction.title}`,
      detail: `Shift timer started (${formatSecondsRemaining(shiftDurationSeconds)}${SHIFT_SHORT_MODE ? ' short mode' : ''}).`,
      category: 'work',
    });

    loop.setFeedback({
      tone: 'info',
      message: `Clocked in. Shift auto-completes in ${formatSecondsRemaining(shiftDurationSeconds)}.`,
    });
  };

  useEffect(() => {
    if (!activeShift || autoClockingOut) return;
    if (houstonNow.getTime() < activeShift.endsAtMs) return;

    let cancelled = false;

    const autoClockOut = async () => {
      setAutoClockingOut(true);
      appendTimelineNote({
        timestampIso: new Date().toISOString(),
        title: 'Shift timer ended',
        detail: 'Auto clock-out triggered.',
        category: 'system',
      });

      const ok = await loop.executeAction(activeShift.action);

      if (!cancelled) {
        appendTimelineNote({
          timestampIso: new Date().toISOString(),
          title: ok ? 'Shift completed' : 'Shift completion failed',
          detail: ok ? 'Shift payout and effects were applied.' : 'Shift payout failed. Try clocking in again.',
          category: 'work',
        });
        setActiveShift(null);
        setAutoClockingOut(false);
      }
    };

    void autoClockOut();

    return () => {
      cancelled = true;
    };
  }, [activeShift, autoClockingOut, houstonNow, loop]);

  const runRideShareTrip = async () => {
    if (!sideIncomeAction) {
      loop.setFeedback({
        tone: 'error',
        message: 'Ride share is not unlocked yet.',
      });
      return;
    }

    if (activeShift) {
      loop.setFeedback({
        tone: 'error',
        message: `Unavailable during work shift. Available after ${shiftEndLabel}.`,
      });
      return;
    }

    if (!rideshareTimeWindowOpen) {
      loop.setFeedback({
        tone: 'error',
        message: 'Ride share is only available before 9:00 AM or after 5:00 PM.',
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

    await loop.executeAction(sideIncomeAction);
  };

  const runRecoveryAction = async (preset: RecoveryPreset) => {
    if (activeShift || autoClockingOut) {
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
  const busyLife = loop.executingAction || busyMeal !== null || Boolean(activeShift) || autoClockingOut;

  async function handleEat(mealType: 'breakfast' | 'lunch' | 'dinner') {
    if (activeShift || autoClockingOut) {
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
          summary={activeShift ? `On shift - ${shiftRemainingLabel} remaining` : `${loop.dailySession.remainingTimeUnits} time units left today`}
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
            { label: 'Phase / status', value: gamePhaseLabel, tone: activeShift ? 'warning' : 'info' },
            { label: 'Shift window', value: shiftWindowLabel() },
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
            value={activeShift ? 'On shift' : autoClockingOut ? 'Auto clocking out' : canClockIn ? 'Ready to clock in' : 'Off shift'}
            tone={activeShift ? 'warning' : canClockIn ? 'positive' : 'neutral'}
            note={activeShift ? `Ends at ${shiftEndLabel} CT` : `Window: ${shiftWindowLabel()}`}
          />
          <GameplayStatCard
            label="Shift timer"
            value={activeShift ? shiftRemainingLabel : '--'}
            tone={activeShift ? 'warning' : 'neutral'}
            note={SHIFT_SHORT_MODE ? `Short mode (${shiftDurationSeconds}s)` : 'Auto clock-out at shift end'}
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
                ? 'Auto clocking out...'
                : runningWorkAction
                  ? 'Applying shift...'
                  : activeShift
                    ? `On shift (${shiftRemainingLabel})`
                    : 'Clock In'
            }
            onPress={() => void handleClockIn()}
            disabled={!canClockIn || Boolean(activeShift) || autoClockingOut || runningWorkAction}
          />
        </View>

        {activeShift ? (
          <GameplayWarningBanner
            title="Shift active"
            message={`You are clocked in. Auto clock-out at ${shiftEndLabel} CT.`}
            tone="info"
          />
        ) : clockInBlocker ? (
          <Text style={styles.helperText}>{clockInBlocker}</Text>
        ) : (
          <Text style={styles.helperText}>
            Clock in during shift hours, then wait for auto clock-out and payout.
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
              tone: rideshareAvailable ? 'positive' : activeShift ? 'warning' : 'neutral',
            },
            { label: 'Trips today', value: `${rideshareTripsToday} / ${rideshareDailyCap}` },
            {
              label: 'Ride share earned today',
              value: formatMoney(rideshareEarnedToday),
              tone: rideshareEarnedToday > 0 ? 'positive' : 'neutral',
            },
            { label: 'Time cost per trip', value: `${sideIncomeGuard.timeCostUnits || 1} units` },
          ]}
        />
        <View style={styles.clockInButtonWrap}>
          <PrimaryButton
            label={runningSideIncome ? 'Completing trip...' : 'Run Ride Share Trip'}
            onPress={() => void runRideShareTrip()}
            disabled={!rideshareAvailable || runningSideIncome || autoClockingOut || loop.executingAction}
          />
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
        {(activeShift || autoClockingOut) ? (
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
                    disabled={Boolean(busyRecoveryId) || loop.executingAction || Boolean(activeShift) || autoClockingOut}
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

