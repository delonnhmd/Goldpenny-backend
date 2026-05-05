import { fetchApi, fetchApiWithFallback } from '@/lib/apiClient';
import {
  clampDeltaRange,
  normalizeCreditScore,
  normalizeCurrentDay,
  normalizeFiniteNumber,
  normalizeJobName,
  normalizeMoneyValue,
  normalizeOptionalMoneyValue,
  normalizePercentageStat,
  normalizeTimeCostUnits,
  safeNetCashFlowCalculation,
} from '@/lib/economySafety';
import { recordInfo, recordWarning } from '@/lib/logger';
import {
  ActionImpact,
  ActionExecutionResponse,
  ActionPreviewRequest,
  ActionPreviewResponse,
  AnnualRecapResponse,
  BlackSwanEventResponse,
  BlackSwanPayload,
  ActionRecommendationState,
  ConfidenceLevel,
  CompletedShiftSnapshot,
  DailyActionHubResponse,
  DailyActionItem,
  EconomyRiskOverview,
  EndStatePayload,
  EndDayResponse,
  EndOfDaySummaryResponse,
  GameTimePayload,
  GameplayAuthoritativeState,
  GameplayActionKey,
  GameplayLoopCoreResponse,
  JobProgressionTrackSnapshot,
  JobProgressionFeedbackSnapshot,
  PlayerDashboardResponse,
  PlayerNotificationItem,
  PlayerNotificationResponse,
  PlayerRunStatus,
  PlayerRunStatusResponse,
  RecoverySummarySnapshot,
  RetireRunResponse,
  RunEndSummary,
  TimelineEventItem,
  TransactionHistoryItem,
  TransactionHistoryResponse,
  TrendDirection,
  WeeklyPlayerSummaryResponse,
  WorkStateSnapshot,
} from '@/types/gameplay';


const GAMEPLAY_ROUTE_DIAGNOSTICS_ENABLED =
  __DEV__
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === 'true'
  || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === '1';

function logCanonicalRoute(resource: string, playerId: string, path: string): void {
  if (!GAMEPLAY_ROUTE_DIAGNOSTICS_ENABLED) return;
  recordInfo('gameplayApi', 'Using canonical gameplay route.', {
    action: 'canonical_route',
    context: {
      resource,
      playerId,
      path,
    },
  });
}

function toNumber(value: unknown, fallback = 0): number {
  return normalizeFiniteNumber(value, { fallback });
}

function toString(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value;
  if (value == null) return fallback;
  return String(value);
}

function normalizeExecutionParameters(
  canonical: GameplayActionKey,
  params: Record<string, unknown>,
): Record<string, unknown> {
  const normalizedParams: Record<string, unknown> = { ...params };

  if (canonical === 'switch_job') {
    const rawJobKey =
      params.new_job_key ?? params.job_key ?? params.job ?? params.job_name ?? params.target_job;
    const canonicalJobKey = normalizeJobName(rawJobKey);
    delete normalizedParams.job_key;
    delete normalizedParams.job;
    delete normalizedParams.job_name;
    delete normalizedParams.target_job;
    if (canonicalJobKey) {
      normalizedParams.new_job_key = canonicalJobKey;
    }
    if (GAMEPLAY_ROUTE_DIAGNOSTICS_ENABLED) {
      recordInfo('gameplayApi', 'Normalized switch_job payload.', {
        action: 'switch_job_payload_normalized',
        context: {
          rawJobKey: rawJobKey == null ? null : String(rawJobKey),
          canonicalJobKey,
          requestPayload: normalizedParams,
        },
      });
    }
  }

  if (canonical === 'work_shift') {
    const rawJobName = params.job_name ?? params.job ?? params.current_job;
    const canonicalJobName = normalizeJobName(rawJobName);
    delete normalizedParams.job;
    delete normalizedParams.current_job;
    if (canonicalJobName) {
      normalizedParams.job_name = canonicalJobName;
    }
    if (GAMEPLAY_ROUTE_DIAGNOSTICS_ENABLED) {
      recordInfo('gameplayApi', 'Normalized work_shift payload.', {
        action: 'work_shift_payload_normalized',
        context: {
          rawJobName: rawJobName == null ? null : String(rawJobName),
          canonicalJobName,
          requestPayload: normalizedParams,
        },
      });
    }
  }

  if (canonical === 'travel') {
    const destinationRaw =
      params.destination_key ?? params.to_location_key ?? params.location_key ?? params.destination;
    const destinationKey = toString(destinationRaw, '').trim().toLowerCase();
    delete normalizedParams.location_key;
    delete normalizedParams.destination;
    if (destinationKey) {
      normalizedParams.destination_key = destinationKey;
    }
    if (GAMEPLAY_ROUTE_DIAGNOSTICS_ENABLED) {
      recordInfo('gameplayApi', 'Normalized travel payload.', {
        action: 'travel_payload_normalized',
        context: {
          destinationRaw: destinationRaw == null ? null : String(destinationRaw),
          destinationKey,
          requestPayload: normalizedParams,
        },
      });
    }
  }

  if (canonical === 'start_training') {
    const rawCertificationKey =
      params.certification_key ?? params.track_key ?? params.certification ?? params.cert_key;
    const certificationKey = toString(rawCertificationKey, '').trim().toLowerCase();
    delete normalizedParams.track_key;
    delete normalizedParams.certification;
    delete normalizedParams.cert_key;
    if (certificationKey) {
      normalizedParams.certification_key = certificationKey;
    }
    if (GAMEPLAY_ROUTE_DIAGNOSTICS_ENABLED) {
      recordInfo('gameplayApi', 'Normalized start_training payload.', {
        action: 'start_training_payload_normalized',
        context: {
          rawCertificationKey: rawCertificationKey == null ? null : String(rawCertificationKey),
          certificationKey,
          requestPayload: normalizedParams,
        },
      });
    }
  }

  return normalizedParams;
}

function toTrendDirection(value: unknown, fallback: TrendDirection = 'flat'): TrendDirection {
  const normalized = toString(value).toLowerCase();
  if (normalized === 'up' || normalized === 'increase' || normalized === 'gain') return 'up';
  if (normalized === 'down' || normalized === 'decrease' || normalized === 'loss') return 'down';
  if (normalized === 'mixed') return 'mixed';
  if (normalized === 'flat' || normalized === 'neutral' || normalized === 'stable') return 'flat';
  return fallback;
}

function toConfidence(value: unknown): ConfidenceLevel {
  const normalized = toString(value, 'unknown').toLowerCase();
  if (normalized === 'high') return 'high';
  if (normalized === 'medium' || normalized === 'moderate') return 'medium';
  if (normalized === 'low') return 'low';
  return 'unknown';
}

function normalizeGameTime(raw: unknown): GameTimePayload | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  return {
    server_now: toString(obj.server_now, ''),
    timezone: toString(obj.timezone, 'America/Chicago'),
    next_settlement_at: toString(obj.next_settlement_at, ''),
    next_morning_brief_at: toString(obj.next_morning_brief_at, ''),
    seconds_until_settlement: Math.max(0, Math.floor(toNumber(obj.seconds_until_settlement, 0))),
    seconds_until_morning_brief: Math.max(0, Math.floor(toNumber(obj.seconds_until_morning_brief, 0))),
  };
}

function normalizeRunStatusValue(value: unknown): PlayerRunStatus {
  const normalized = toString(value, 'active').trim().toLowerCase();
  if (normalized === 'bankrupt' || normalized === 'retired') return normalized;
  return 'active';
}

function normalizeRunEndSummary(raw: unknown): RunEndSummary | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  const hasMeaningfulValue = Object.keys(obj).length > 0;
  if (!hasMeaningfulValue) return null;
  return {
    ...obj,
    cash: normalizeMoneyValue(obj.cash, { allowNegative: true, fallback: 0 }),
    debt: normalizeMoneyValue(obj.debt, { allowNegative: false, fallback: 0 }),
    credit_score: normalizeCreditScore(obj.credit_score, 650),
    net_worth: normalizeMoneyValue(obj.net_worth, { allowNegative: true, fallback: 0 }),
    days_survived: Math.max(0, Math.round(toNumber(obj.days_survived, 0))),
    businesses_owned: Math.max(0, Math.round(toNumber(obj.businesses_owned, 0))),
    land_owned: Math.max(0, Math.round(toNumber(obj.land_owned, 0))),
    best_streak: Math.max(0, Math.round(toNumber(obj.best_streak, 0))),
    actual_cash: obj.actual_cash == null
      ? null
      : normalizeMoneyValue(obj.actual_cash, { allowNegative: true, fallback: 0 }),
    retirement_title: obj.retirement_title == null ? null : toString(obj.retirement_title, ''),
  };
}

function normalizeRetirementRequirement(raw: unknown): PlayerRunStatusResponse['retirement_requirement'] {
  const obj = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  return {
    min_day: Math.max(1, Math.round(toNumber(obj.min_day, 30))),
    min_net_worth: normalizeMoneyValue(obj.min_net_worth, { allowNegative: false, fallback: 10000 }),
    current_day: Math.max(1, Math.round(toNumber(obj.current_day, 1))),
    current_net_worth: normalizeMoneyValue(obj.current_net_worth, { allowNegative: true, fallback: 0 }),
  };
}

function normalizePlayerRunStatus(raw: unknown): PlayerRunStatusResponse | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  const status = normalizeRunStatusValue(obj.run_status);
  return {
    run_status: status,
    run_ended_at: obj.run_ended_at == null ? null : toString(obj.run_ended_at, ''),
    run_end_day: obj.run_end_day == null ? null : Math.max(0, Math.round(toNumber(obj.run_end_day, 0))),
    run_end_reason: obj.run_end_reason == null ? null : toString(obj.run_end_reason, ''),
    run_end_summary: normalizeRunEndSummary(obj.run_end_summary),
    can_continue: obj.can_continue == null ? status === 'active' : Boolean(obj.can_continue),
    can_retire: Boolean(obj.can_retire),
    retirement_requirement: normalizeRetirementRequirement(obj.retirement_requirement),
  };
}

function normalizeRetireRunResponse(raw: unknown): RetireRunResponse {
  const obj = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const status = normalizePlayerRunStatus(obj) || {
    run_status: 'active' as PlayerRunStatus,
    run_ended_at: null,
    run_end_day: null,
    run_end_reason: null,
    run_end_summary: null,
    can_continue: true,
    can_retire: false,
    retirement_requirement: normalizeRetirementRequirement(null),
  };
  return {
    ...status,
    eligible: Boolean(obj.eligible),
    reason: obj.reason == null ? null : toString(obj.reason, ''),
  };
}

function normalizeAnnualRecap(raw: unknown): AnnualRecapResponse {
  const obj = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  return {
    year: Math.max(1, Math.round(toNumber(obj.year, 1))),
    days_survived: Math.max(0, Math.round(toNumber(obj.days_survived, 0))),
    starting_net_worth: normalizeMoneyValue(obj.starting_net_worth, { allowNegative: true, fallback: 0 }),
    ending_net_worth: normalizeMoneyValue(obj.ending_net_worth, { allowNegative: true, fallback: 0 }),
    net_worth_change: normalizeMoneyValue(obj.net_worth_change, { allowNegative: true, fallback: 0 }),
    cash: normalizeMoneyValue(obj.cash, { allowNegative: true, fallback: 0 }),
    debt: normalizeMoneyValue(obj.debt, { allowNegative: false, fallback: 0 }),
    credit_score: normalizeCreditScore(obj.credit_score, 650),
    businesses_owned: Math.max(0, Math.round(toNumber(obj.businesses_owned, 0))),
    land_owned: Math.max(0, Math.round(toNumber(obj.land_owned, 0))),
    best_streak: Math.max(0, Math.round(toNumber(obj.best_streak, 0))),
    total_income: normalizeMoneyValue(obj.total_income, { allowNegative: false, fallback: 0 }),
    total_expenses: normalizeMoneyValue(obj.total_expenses, { allowNegative: false, fallback: 0 }),
    biggest_win: toString(obj.biggest_win, 'No major win recorded yet.'),
    biggest_loss: toString(obj.biggest_loss, 'No major loss recorded yet.'),
    top_event: toString(obj.top_event, 'No major event recorded yet.'),
    title: toString(obj.title, 'Year Recap'),
  };
}

function normalizeTimelineType(value: unknown): TimelineEventItem['type'] {
  const normalized = toString(value, 'life').trim().toLowerCase();
  if (
    normalized === 'economy'
    || normalized === 'business'
    || normalized === 'finance'
    || normalized === 'life'
  ) {
    return normalized;
  }
  return 'life';
}

function normalizeTimelineImpact(value: unknown): TimelineEventItem['impact_level'] {
  const normalized = toString(value, 'low').trim().toLowerCase();
  if (normalized === 'high' || normalized === 'medium' || normalized === 'low') {
    return normalized;
  }
  return 'low';
}

function normalizeTimelineEvent(raw: unknown, index: number): TimelineEventItem {
  const obj = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  return {
    day: Math.max(1, Math.round(toNumber(obj.day, index + 1))),
    type: normalizeTimelineType(obj.type),
    title: toString(obj.title, 'Run event'),
    description: toString(obj.description, 'A meaningful run event was recorded.'),
    impact_level: normalizeTimelineImpact(obj.impact_level),
    icon: toString(obj.icon, 'circle'),
  };
}

function toStringList(value: unknown, fallback: string[] = []): string[] {
  if (!Array.isArray(value)) return fallback;
  return value.map((entry) => toString(entry, '').trim()).filter(Boolean);
}

function normalizeBlackSwanPayload(raw: unknown, eventId: string): BlackSwanPayload {
  const obj = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const pushRaw = obj.push_payload && typeof obj.push_payload === 'object'
    ? (obj.push_payload as Record<string, unknown>)
    : {};
  return {
    ...obj,
    affected_systems: toStringList(obj.affected_systems, ['Economy']),
    what_changed_today: toStringList(obj.what_changed_today, ['A major event moved through the city today.']),
    what_this_means: toStringList(obj.what_this_means, [
      'Review the daily brief before committing time.',
      'Watch cash, debt, and inventory pressure.',
    ]).slice(0, 3),
    source: obj.source && typeof obj.source === 'object' ? (obj.source as Record<string, unknown>) : {},
    push_payload: {
      type: 'black_swan',
      screen: 'BlackSwan',
      event_id: toString(pushRaw.event_id, eventId),
    },
  };
}

function normalizeBlackSwanEvent(raw: unknown): BlackSwanEventResponse | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  const id = toString(obj.id, '');
  if (!id) return null;
  const payload = normalizeBlackSwanPayload(obj.payload, id);
  const pushRaw = obj.push_payload && typeof obj.push_payload === 'object'
    ? (obj.push_payload as Record<string, unknown>)
    : {};
  return {
    id,
    player_id: toString(obj.player_id, ''),
    day: normalizeCurrentDay(obj.day, 1),
    event_type: toString(obj.event_type, 'economy_event'),
    title: toString(obj.title, 'Major Event'),
    description: toString(obj.description, 'A major event moved through the city today.'),
    severity_score: toNumber(obj.severity_score, 0),
    source_event_id: obj.source_event_id == null ? null : toString(obj.source_event_id, ''),
    payload,
    push_payload: {
      type: 'black_swan',
      screen: 'BlackSwan',
      event_id: toString(pushRaw.event_id, payload.push_payload?.event_id || id),
    },
    seen_at: obj.seen_at == null ? null : toString(obj.seen_at, ''),
    created_at: obj.created_at == null ? null : toString(obj.created_at, ''),
  };
}

function normalizeEndState(raw: unknown): EndStatePayload | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  return {
    triggered: Boolean(obj.triggered),
    run_status: normalizeRunStatusValue(obj.run_status),
    reason: obj.reason == null ? null : toString(obj.reason, ''),
    summary: normalizeRunEndSummary(obj.summary),
  };
}

function normalizeActionStatus(value: unknown): ActionRecommendationState {
  const normalized = toString(value, 'available').toLowerCase();
  if (normalized === 'recommended') return 'recommended';
  if (normalized === 'blocked') return 'blocked';
  return 'available';
}

function normalizeAction(raw: unknown, fallbackStatus: ActionRecommendationState, index: number): DailyActionItem {
  if (typeof raw === 'string') {
    return {
      action_key: raw as GameplayActionKey,
      title: raw.replace(/_/g, ' '),
      description: 'Suggested action from daily brief',
      status: fallbackStatus,
      blockers: [],
      warnings: [],
      tradeoffs: [],
      confidence_level: 'unknown',
      parameters: {},
      debug_meta: {},
    };
  }
  const obj = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const blockers = Array.isArray(obj.blockers)
    ? obj.blockers.map((entry) => toString(entry)).filter(Boolean)
    : obj.blocker_text
      ? [toString(obj.blocker_text)]
      : [];

  return {
    action_key: toString(obj.action_key || obj.key || obj.id || `action_${index}`) as GameplayActionKey,
    title: toString(obj.title || obj.name || obj.action_key || 'Action'),
    description: toString(obj.description || obj.reason || 'No description provided.'),
    status: normalizeActionStatus(obj.status || fallbackStatus),
    blockers,
    blocker_text: blockers.length > 0 ? blockers[0] : null,
    tradeoffs: Array.isArray(obj.tradeoffs) ? obj.tradeoffs.map((entry) => toString(entry)) : [],
    warnings: Array.isArray(obj.warnings) ? obj.warnings.map((entry) => toString(entry)) : [],
    confidence_level: toConfidence(obj.confidence_level),
    parameters: (obj.parameters as Record<string, unknown>) || {},
    debug_meta: (obj.debug_meta as Record<string, unknown>) || {},
  };
}

function normalizeImpact(raw: unknown, label: string, fallbackDirection: TrendDirection): ActionImpact {
  if (raw == null) {
    return { label, direction: fallbackDirection, text: 'No estimate' };
  }
  if (typeof raw === 'number') {
    const amount = clampDeltaRange(raw);
    return {
      label,
      direction: amount > 0 ? 'up' : amount < 0 ? 'down' : 'flat',
      amount,
      text: `${amount > 0 ? '+' : ''}${amount}`,
    };
  }
  if (typeof raw === 'string') {
    return {
      label,
      direction: fallbackDirection,
      text: raw,
    };
  }

  const obj = raw as Record<string, unknown>;
  const amount = obj.amount != null ? clampDeltaRange(obj.amount) : undefined;
  return {
    label: toString(obj.label, label),
    direction: toTrendDirection(obj.direction, fallbackDirection),
    amount,
    text: toString(obj.text, amount != null ? `${amount > 0 ? '+' : ''}${amount}` : ''),
  };
}

function normalizeJobProgressSnapshot(
  raw: unknown,
  fallbackJobKey = '',
): WorkStateSnapshot['current_job_progression'] {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  return {
    job_key: toString(obj.job_key, fallbackJobKey),
    job_level: Math.max(1, Math.round(toNumber(obj.job_level ?? obj.skill_level, 1))),
    skill_level: Math.max(1, Math.round(toNumber(obj.skill_level ?? obj.job_level, 1))),
    xp_total: Math.max(0, Math.round(toNumber(obj.xp_total, 0))),
    job_xp: Math.max(0, Math.round(toNumber(obj.job_xp, 0))),
    job_xp_to_next_level: Math.max(0, Math.round(toNumber(obj.job_xp_to_next_level, 0))),
    max_job_level: Math.max(1, Math.round(toNumber(obj.max_job_level, 2))),
    monthly_pay_xgp: normalizeMoneyValue(
      obj.monthly_pay_xgp ?? obj.base_salary_xgp,
      { allowNegative: false, fallback: 0 },
    ),
    promotion_tier: toString(obj.promotion_tier, 'Junior'),
    shifts_completed: Math.max(0, Math.round(toNumber(obj.shifts_completed, 0))),
    estimated_current_monthly_salary_xgp: normalizeMoneyValue(
      obj.estimated_current_monthly_salary_xgp,
      { allowNegative: false, fallback: 0 },
    ),
    estimated_next_level_monthly_salary_xgp: normalizeMoneyValue(
      obj.estimated_next_level_monthly_salary_xgp,
      { allowNegative: false, fallback: 0 },
    ),
    next_level_salary_increase_pct: normalizeFiniteNumber(obj.next_level_salary_increase_pct, { fallback: 10 }),
    salary_preview_note: toString(
      obj.salary_preview_note,
      'Estimated only - live payroll remains unchanged.',
    ),
    employer_company_symbol: toString(obj.employer_company_symbol, ''),
    employer_company_name: toString(obj.employer_company_name, ''),
    position_title: toString(obj.position_title, ''),
    shift_type: toString(obj.shift_type, ''),
  };
}

function normalizeJobProgressTrack(raw: unknown): JobProgressionTrackSnapshot {
  const obj = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
    return {
      job_key: toString(obj.job_key, ''),
      display_name: toString(obj.display_name, ''),
      status: toString(obj.status, ''),
    locked: Boolean(obj.locked),
    requires_certification: Boolean(obj.requires_certification),
    certification_key: obj.certification_key == null ? null : toString(obj.certification_key, ''),
    certification_name: obj.certification_name == null ? null : toString(obj.certification_name, ''),
    requirement_label: obj.requirement_label == null ? null : toString(obj.requirement_label, ''),
    has_progression: Boolean(obj.has_progression),
    job_level: Math.max(1, Math.round(toNumber(obj.job_level, 1))),
    promotion_tier: toString(obj.promotion_tier, 'Junior'),
    job_xp: Math.max(0, Math.round(toNumber(obj.job_xp, 0))),
    job_xp_to_next_level: Math.max(0, Math.round(toNumber(obj.job_xp_to_next_level, 0))),
    shifts_completed: Math.max(0, Math.round(toNumber(obj.shifts_completed, 0))),
    estimated_current_monthly_salary_xgp: normalizeMoneyValue(
      obj.estimated_current_monthly_salary_xgp,
      { allowNegative: false, fallback: 0 },
    ),
      estimated_next_level_monthly_salary_xgp: normalizeMoneyValue(
        obj.estimated_next_level_monthly_salary_xgp,
        { allowNegative: false, fallback: 0 },
      ),
      next_level_salary_increase_pct: normalizeFiniteNumber(obj.next_level_salary_increase_pct, { fallback: 10 }),
      salary_preview_note: obj.salary_preview_note == null ? null : toString(obj.salary_preview_note, ''),
      last_worked_at: obj.last_worked_at == null ? null : toString(obj.last_worked_at, ''),
      level_requirement: Math.max(1, Math.round(toNumber(obj.level_requirement, 1))),
      experience_requirement_shifts: Math.max(0, Math.round(toNumber(obj.experience_requirement_shifts, 0))),
      prerequisite_job_labels: Array.isArray(obj.prerequisite_job_labels)
        ? (obj.prerequisite_job_labels as unknown[]).map((entry) => toString(entry, '')).filter(Boolean)
        : [],
      path_hint: obj.path_hint == null ? null : toString(obj.path_hint, ''),
    };
  }

function normalizeJobProgressFeedback(raw: unknown): JobProgressionFeedbackSnapshot | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  return {
    job_key: toString(obj.job_key, ''),
    xp_gained: Math.max(0, Math.round(toNumber(obj.xp_gained, 0))),
    level_before: Math.max(1, Math.round(toNumber(obj.level_before, 1))),
    level_after: Math.max(1, Math.round(toNumber(obj.level_after, 1))),
    promotion_tier_before: obj.promotion_tier_before == null ? null : toString(obj.promotion_tier_before, ''),
    promotion_tier_after: obj.promotion_tier_after == null ? null : toString(obj.promotion_tier_after, ''),
    leveled_up: Boolean(obj.leveled_up),
    tier_changed: Boolean(obj.tier_changed),
    feedback_message: obj.feedback_message == null ? null : toString(obj.feedback_message, ''),
    progression: normalizeJobProgressSnapshot(obj.progression, toString(obj.job_key, '')),
  };
}

function normalizeDashboard(raw: Record<string, unknown>, playerId: string): PlayerDashboardResponse {
  const stats = (raw.stats as Record<string, unknown>) || {};
  const debugMeta = (raw.debug_meta as Record<string, unknown>) || {};
  const jobProgressRaw = (raw.job_progress && typeof raw.job_progress === 'object')
    ? (raw.job_progress as Record<string, unknown>)
    : null;
  const opportunitiesRaw =
    (Array.isArray(raw.top_opportunities) ? raw.top_opportunities : null) ||
    (Array.isArray(raw.opportunities) ? raw.opportunities : null) ||
    [];
  const risksRaw =
    (Array.isArray(raw.top_risks) ? raw.top_risks : null) ||
    (Array.isArray(raw.risks) ? raw.risks : null) ||
    [];
  const hints = Array.isArray(raw.recommended_actions)
    ? raw.recommended_actions
    : Array.isArray(raw.action_hints_json)
      ? raw.action_hints_json
      : [];
  const workState = normalizeWorkState(
    raw.work_state
      ?? debugMeta.work_state,
    playerId,
  );
  const authoritativeState = normalizeAuthoritativeState(
    raw.authoritative_state ?? debugMeta.authoritative_state,
    playerId,
    workState,
  );
  const economyRiskOverview = normalizeEconomyRiskOverview(raw.economy_risk_overview);

  return {
    player_id: toString(raw.player_id, playerId),
    game_time: normalizeGameTime(raw.game_time),
    run_status: normalizePlayerRunStatus(raw.run_status),
    as_of_date: toString(raw.as_of_date || raw.date || raw.settled_day, ''),
    headline: toString(raw.headline || raw.summary_headline, 'Today at Gold Penny'),
    daily_brief: toString(raw.daily_brief || raw.summary, 'No daily brief available yet.'),
    stats: {
      cash_xgp: normalizeMoneyValue(stats.cash_xgp ?? raw.ending_cash_xgp ?? raw.cash, { allowNegative: true, fallback: 0 }),
      debt_xgp: normalizeMoneyValue(stats.debt_xgp ?? raw.ending_debt_xgp ?? raw.debt_xgp, { allowNegative: false, fallback: 0 }),
      net_worth_xgp: normalizeMoneyValue(stats.net_worth_xgp ?? raw.net_worth_xgp, { allowNegative: true, fallback: 0 }),
      stress: normalizePercentageStat(stats.stress ?? raw.stress ?? raw.stress_after, 0),
      health: normalizePercentageStat(stats.health ?? raw.health ?? raw.health_after, 100),
      credit_score: normalizeCreditScore(stats.credit_score ?? raw.ending_credit_score ?? raw.credit_score, 650),
      current_job: toString(stats.current_job ?? raw.main_job ?? raw.current_job, ''),
      current_job_display: toString(
        stats.current_job_display
          ?? workState?.current_job_display_name
          ?? raw.current_job_display,
        '',
      ),
      region_key: toString(stats.region_key ?? raw.region_key ?? raw.housing_region, ''),
    },
    state_cards: Array.isArray(raw.state_cards) ? (raw.state_cards as any) : [],
    top_opportunities: opportunitiesRaw.map((entry, index) => {
      const item = (entry || {}) as Record<string, unknown>;
      return {
        key: toString(item.key, `opportunity_${index}`),
        title: toString(item.title || item.name, 'Opportunity'),
        description: toString(item.description || item.summary, ''),
        severity: toString(item.severity || 'low') as any,
        value: item.value != null ? normalizeMoneyValue(item.value, { allowNegative: true, fallback: 0 }) : undefined,
        category: toString(item.category, ''),
      };
    }),
    top_risks: risksRaw.map((entry, index) => {
      const item = (entry || {}) as Record<string, unknown>;
      return {
        key: toString(item.key, `risk_${index}`),
        title: toString(item.title || item.name, 'Risk'),
        description: toString(item.description || item.summary, ''),
        severity: toString(item.severity || 'medium') as any,
        value: item.value != null ? normalizeMoneyValue(item.value, { allowNegative: true, fallback: 0 }) : undefined,
        category: toString(item.category, ''),
      };
    }),
    economy_risk_overview: economyRiskOverview,
    recommended_actions: hints.map((entry, index) => {
      if (typeof entry === 'string') {
        return {
          action_key: entry as GameplayActionKey,
          title: entry.replace(/_/g, ' '),
          reason: 'Recommended in daily brief',
        };
      }
      const item = (entry || {}) as Record<string, unknown>;
      return {
        action_key: toString(item.action_key || item.key || `action_${index}`) as GameplayActionKey,
        title: toString(item.title || item.name || item.action_key || 'Action'),
        reason: toString(item.reason || item.description || 'Recommended action'),
      };
    }),
    job_progress: normalizeJobProgressSnapshot(
      jobProgressRaw,
      toString(stats.current_job || ''),
    ),
    actions_remaining_today: Math.max(0, Math.round(toNumber(raw.actions_remaining_today, 0))),
    work_state: workState,
    authoritative_state: authoritativeState,
    debug_meta: debugMeta,
  };
}

function normalizeActionHub(raw: Record<string, unknown>, playerId: string): DailyActionHubResponse {
  const recommendedRaw = Array.isArray(raw.recommended_actions) ? raw.recommended_actions : [];
  const availableRaw = Array.isArray(raw.available_actions) ? raw.available_actions : [];
  const blockedRaw = Array.isArray(raw.blocked_actions) ? raw.blocked_actions : [];
  const debugMeta = (raw.debug_meta as Record<string, unknown>) || {};
  const workState = normalizeWorkState(raw.work_state ?? debugMeta.work_state, playerId);
  const authoritativeState = normalizeAuthoritativeState(
    raw.authoritative_state ?? debugMeta.authoritative_state,
    playerId,
    workState,
  );

  return {
    player_id: toString(raw.player_id, playerId),
    as_of_date: toString(raw.as_of_date || raw.date || raw.settled_day, ''),
    recommended_actions: recommendedRaw.map((entry, index) => normalizeAction(entry, 'recommended', index)),
    available_actions: availableRaw.map((entry, index) => normalizeAction(entry, 'available', index)),
    blocked_actions: blockedRaw.map((entry, index) => normalizeAction(entry, 'blocked', index)),
    top_tradeoffs: Array.isArray(raw.top_tradeoffs)
      ? raw.top_tradeoffs.map((entry) => toString(entry))
      : [],
    next_risk_warnings: Array.isArray(raw.next_risk_warnings)
      ? raw.next_risk_warnings.map((entry) => toString(entry))
      : [],
    work_state: workState,
    authoritative_state: authoritativeState,
    debug_meta: debugMeta,
  };
}

function normalizeRecoverySummaryContract(raw: unknown): RecoverySummarySnapshot | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  return {
    points: Math.max(0, Math.round(toNumber(obj.points, 0))),
    stress_delta: clampDeltaRange(obj.stress_delta, { min: -100, max: 100, fallback: 0 }),
    status: obj.status == null ? undefined : toString(obj.status, ''),
    pure_off_hours: Math.max(0, Math.round(toNumber(obj.pure_off_hours, 0))),
    rideshare_hours: Math.max(0, Math.round(toNumber(obj.rideshare_hours, 0))),
    pure_blocks: Math.max(0, Math.round(toNumber(obj.pure_blocks, 0))),
    rideshare_blocks: Math.max(0, Math.round(toNumber(obj.rideshare_blocks, 0))),
    daily_cap: Math.max(0, Math.round(toNumber(obj.daily_cap, 0))),
    window_hours: Math.max(0, Math.round(toNumber(obj.window_hours, 0))),
    tier: obj.tier == null ? undefined : toString(obj.tier, ''),
    is_weekend: Boolean(obj.is_weekend),
  };
}

function normalizeAuthoritativeState(
  raw: unknown,
  playerId: string,
  fallbackWorkState?: WorkStateSnapshot | null,
): GameplayAuthoritativeState | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  const shiftStateRaw = obj.shift_state && typeof obj.shift_state === 'object'
    ? (obj.shift_state as Record<string, unknown>)
    : {};
  const playerStateRaw = obj.player_state && typeof obj.player_state === 'object'
    ? (obj.player_state as Record<string, unknown>)
    : {};
  const rideshareRaw = obj.rideshare_state && typeof obj.rideshare_state === 'object'
    ? (obj.rideshare_state as Record<string, unknown>)
    : {};
  const debtPaymentRaw = obj.debt_payment_state && typeof obj.debt_payment_state === 'object'
    ? (obj.debt_payment_state as Record<string, unknown>)
    : {};
  const recoveryRaw = obj.recovery_state && typeof obj.recovery_state === 'object'
    ? (obj.recovery_state as Record<string, unknown>)
    : {};
  const mealStateRaw = recoveryRaw.meal_state && typeof recoveryRaw.meal_state === 'object'
    ? (recoveryRaw.meal_state as Record<string, unknown>)
    : {};
  const workState = normalizeWorkState(obj.work_state ?? fallbackWorkState, playerId);

  return {
    player_id: toString(obj.player_id, playerId),
    day_number: normalizeCurrentDay(obj.day_number, 1),
    houston_time: obj.houston_time == null ? null : toString(obj.houston_time, ''),
    houston_date: obj.houston_date == null ? null : toString(obj.houston_date, ''),
    houston_timezone: obj.houston_timezone == null ? null : toString(obj.houston_timezone, ''),
    day_phase: obj.day_phase == null ? null : toString(obj.day_phase, ''),
    current_job_key: obj.current_job_key == null ? null : toString(obj.current_job_key, ''),
    current_job_label: obj.current_job_label == null ? null : toString(obj.current_job_label, ''),
    refreshed_at: obj.refreshed_at == null ? null : toString(obj.refreshed_at, ''),
    shift_state: {
      is_on_shift: Boolean(shiftStateRaw.is_on_shift),
      shift_active: Boolean(shiftStateRaw.shift_active),
      shift_completed_today: Boolean(shiftStateRaw.shift_completed_today),
      shifts_completed_today: Math.max(0, Math.round(toNumber(shiftStateRaw.shifts_completed_today, 0))),
      can_start_shift: Boolean(shiftStateRaw.can_start_shift),
      can_start_overtime_shift: Boolean(shiftStateRaw.can_start_overtime_shift),
      shift_status: shiftStateRaw.shift_status == null ? null : toString(shiftStateRaw.shift_status, ''),
      block_reason_code: shiftStateRaw.block_reason_code == null ? null : toString(shiftStateRaw.block_reason_code, ''),
      shift_end_time_label: shiftStateRaw.shift_end_time_label == null ? null : toString(shiftStateRaw.shift_end_time_label, ''),
    },
    player_state: {
      cash: normalizeMoneyValue(playerStateRaw.cash, { allowNegative: true, fallback: 0 }),
      debt: normalizeMoneyValue(playerStateRaw.debt, { allowNegative: false, fallback: 0 }),
      health: normalizePercentageStat(playerStateRaw.health, 100),
      stress: normalizePercentageStat(playerStateRaw.stress, 0),
      credit_score: normalizeCreditScore(playerStateRaw.credit_score, 650),
    },
    rideshare_state: {
      can_rideshare: Boolean(rideshareRaw.can_rideshare),
      status: rideshareRaw.status == null ? null : toString(rideshareRaw.status, ''),
      reason: rideshareRaw.reason == null ? null : toString(rideshareRaw.reason, ''),
      block_reason: rideshareRaw.block_reason == null ? null : toString(rideshareRaw.block_reason, ''),
      block_reason_code: rideshareRaw.block_reason_code == null ? null : toString(rideshareRaw.block_reason_code, ''),
      block_reason_value: rideshareRaw.block_reason_value == null ? null : toNumber(rideshareRaw.block_reason_value, 0),
      stress_threshold: rideshareRaw.stress_threshold == null ? null : Math.round(toNumber(rideshareRaw.stress_threshold, 0)),
      health_threshold: rideshareRaw.health_threshold == null ? null : Math.round(toNumber(rideshareRaw.health_threshold, 0)),
      trips_today: Math.max(0, Math.round(toNumber(rideshareRaw.trips_today, 0))),
      max_trips: Math.max(0, Math.round(toNumber(rideshareRaw.trip_cap_today ?? rideshareRaw.max_trips, 0))),
      trip_cap_today: Math.max(0, Math.round(toNumber(rideshareRaw.trip_cap_today ?? rideshareRaw.max_trips, 0))),
      remaining_trips: Math.max(0, Math.round(toNumber(rideshareRaw.remaining_trips, 0))),
      hours_remaining_today: Math.max(0, toNumber(rideshareRaw.remaining_time_units ?? rideshareRaw.time_remaining_units ?? rideshareRaw.hours_remaining_today, 0)),
      remaining_time_units: Math.max(0, toNumber(rideshareRaw.remaining_time_units ?? rideshareRaw.time_remaining_units ?? rideshareRaw.hours_remaining_today, 0)),
      time_remaining_units: Math.max(0, toNumber(rideshareRaw.remaining_time_units ?? rideshareRaw.time_remaining_units ?? rideshareRaw.hours_remaining_today, 0)),
      current_location_key: rideshareRaw.current_location_key == null ? null : toString(rideshareRaw.current_location_key, ''),
      current_location_label: rideshareRaw.current_location_label == null ? null : toString(rideshareRaw.current_location_label, ''),
      current_location_region: rideshareRaw.current_location_region == null ? null : toString(rideshareRaw.current_location_region, ''),
      rideshare_allowed_here: rideshareRaw.rideshare_allowed_here == null ? null : Boolean(rideshareRaw.rideshare_allowed_here),
      mode: rideshareRaw.mode == null ? null : toString(rideshareRaw.mode, ''),
      time_cost_per_trip_units: rideshareRaw.time_cost_per_trip_units == null ? null : Math.max(0, toNumber(rideshareRaw.time_cost_per_trip_units, 0)),
      demand_bonus_pct: rideshareRaw.demand_bonus_pct == null ? null : normalizeFiniteNumber(rideshareRaw.demand_bonus_pct, { fallback: 0 }),
      stress_delta_modifier: rideshareRaw.stress_delta_modifier == null ? null : Math.round(toNumber(rideshareRaw.stress_delta_modifier, 0)),
      estimated_pay_min_per_trip: rideshareRaw.estimated_pay_min_per_trip == null
        ? null
        : normalizeMoneyValue(rideshareRaw.estimated_pay_min_per_trip, { allowNegative: false, fallback: 0 }),
      estimated_pay_max_per_trip: rideshareRaw.estimated_pay_max_per_trip == null
        ? null
        : normalizeMoneyValue(rideshareRaw.estimated_pay_max_per_trip, { allowNegative: false, fallback: 0 }),
    },
    debt_payment_state: {
      can_pay_debt: Boolean(debtPaymentRaw.can_pay_debt),
      max_payable_now: normalizeMoneyValue(debtPaymentRaw.max_payable_now, { allowNegative: false, fallback: 0 }),
      block_reason_code: debtPaymentRaw.block_reason_code == null ? null : toString(debtPaymentRaw.block_reason_code, ''),
      block_reason_value: debtPaymentRaw.block_reason_value == null ? null : normalizeMoneyValue(debtPaymentRaw.block_reason_value, { allowNegative: true, fallback: 0 }),
    },
    recovery_state: {
      recovery_actions_remaining: Math.max(0, Math.round(toNumber(recoveryRaw.recovery_actions_remaining, 0))),
      category_cap: Math.max(0, Math.round(toNumber(recoveryRaw.category_cap, 0))),
      category_used: Math.max(0, Math.round(toNumber(recoveryRaw.category_used, 0))),
      category_label: toString(recoveryRaw.category_label, 'Recovery / Leisure'),
      actions: Array.isArray(recoveryRaw.actions)
        ? recoveryRaw.actions.map((entry) => {
          const row = entry && typeof entry === 'object' ? (entry as Record<string, unknown>) : {};
          return {
            action_key: toString(row.action_key, ''),
            available: Boolean(row.available),
            remaining: Math.max(0, Math.round(toNumber(row.remaining, 0))),
            used: Math.max(0, Math.round(toNumber(row.used, 0))),
            daily_cap: Math.max(0, Math.round(toNumber(row.daily_cap, 0))),
            block_reason: row.block_reason == null ? null : toString(row.block_reason, ''),
            block_reason_code: row.block_reason_code == null ? null : toString(row.block_reason_code, ''),
          };
        })
        : [],
      meal_state: {
        can_eat_meal: Boolean(mealStateRaw.can_eat_meal),
        remaining: Math.max(0, Math.round(toNumber(mealStateRaw.remaining, 0))),
        block_reason: mealStateRaw.block_reason == null ? null : toString(mealStateRaw.block_reason, ''),
        block_reason_code: mealStateRaw.block_reason_code == null ? null : toString(mealStateRaw.block_reason_code, ''),
      },
      passive_off_hours_recovery: normalizeRecoverySummaryContract(recoveryRaw.passive_off_hours_recovery),
      weekend_recovery: normalizeRecoverySummaryContract(recoveryRaw.weekend_recovery),
    },
    work_state: workState,
    degraded_sections: Array.isArray(obj.degraded_sections)
      ? obj.degraded_sections.map((entry) => toString(entry, '')).filter(Boolean)
      : [],
  };
}

function normalizeCompletedShift(raw: unknown): CompletedShiftSnapshot {
  const obj = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  return {
    earned_cash_xgp: normalizeMoneyValue(obj.earned_cash_xgp, { allowNegative: true, fallback: 0 }),
    xp_gained: Math.max(0, Math.round(toNumber(obj.xp_gained, 0))),
    stress_change: clampDeltaRange(obj.stress_change, { min: -100, max: 100, fallback: 0 }),
    health_change: clampDeltaRange(obj.health_change, { min: -100, max: 100, fallback: 0 }),
    salary_payment_status: obj.salary_payment_status == null ? null : toString(obj.salary_payment_status, ''),
    salary_transaction_id: obj.salary_transaction_id == null ? null : toString(obj.salary_transaction_id, ''),
    salary_posted_at: obj.salary_posted_at == null ? null : toString(obj.salary_posted_at, ''),
    transaction_confirmed: Boolean(obj.transaction_confirmed),
    job_key: obj.job_key == null ? null : toString(obj.job_key, ''),
    job_display_name: obj.job_display_name == null ? null : toString(obj.job_display_name, ''),
  };
}

function normalizeShiftSalaryAudit(raw: unknown): WorkStateSnapshot['current_shift_salary_audit'] {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  return {
    audit_id: toString(obj.audit_id, ''),
    player_id: toString(obj.player_id, ''),
    day_number: normalizeCurrentDay(obj.day_number, 0),
    shift_token: toString(obj.shift_token, ''),
    shift_id: toString(obj.shift_id, ''),
    job_key: toString(obj.job_key, ''),
    job_display_name: toString(obj.job_display_name, ''),
    shift_started_at: obj.shift_started_at == null ? null : toString(obj.shift_started_at, ''),
    shift_ends_at: obj.shift_ends_at == null ? null : toString(obj.shift_ends_at, ''),
    shift_completed_at: obj.shift_completed_at == null ? null : toString(obj.shift_completed_at, ''),
    shift_type: obj.shift_type == null ? null : toString(obj.shift_type, ''),
    shift_number: Math.max(0, Math.round(toNumber(obj.shift_number, 0))),
    hours_worked: Math.max(0, Math.round(toNumber(obj.hours_worked, 0))),
    trigger: obj.trigger == null ? null : toString(obj.trigger, ''),
    payment_status: toString(obj.payment_status, ''),
    failure_reason: obj.failure_reason == null ? null : toString(obj.failure_reason, ''),
    base_monthly_salary: normalizeMoneyValue(obj.base_monthly_salary, { allowNegative: false, fallback: 0 }),
    pay_snapshot_used: normalizeMoneyValue(obj.pay_snapshot_used, { allowNegative: false, fallback: 0 }),
    base_hourly_pay: normalizeMoneyValue(obj.base_hourly_pay, { allowNegative: false, fallback: 0 }),
    productivity_multiplier: normalizeFiniteNumber(obj.productivity_multiplier, { fallback: 1 }),
    income_multiplier: normalizeFiniteNumber(obj.income_multiplier, { fallback: 1 }),
    job_level_multiplier: normalizeFiniteNumber(obj.job_level_multiplier, { fallback: 1 }),
    gross_shift_pay: normalizeMoneyValue(obj.gross_shift_pay, { allowNegative: false, fallback: 0 }),
    final_salary_paid: normalizeMoneyValue(obj.final_salary_paid, { allowNegative: false, fallback: 0 }),
    xp_gained: Math.max(0, Math.round(toNumber(obj.xp_gained, 0))),
    stress_change: clampDeltaRange(obj.stress_change, { min: -100, max: 100, fallback: 0 }),
    health_change: clampDeltaRange(obj.health_change, { min: -100, max: 100, fallback: 0 }),
    fatigue_change: normalizeFiniteNumber(obj.fatigue_change, { fallback: 0 }),
    overtime_penalty_applied: Boolean(obj.overtime_penalty_applied),
    overtime_applied: Boolean(obj.overtime_applied),
    overtime_multiplier_used: normalizeFiniteNumber(obj.overtime_multiplier_used, { fallback: 1 }),
    salary_transaction_id: obj.salary_transaction_id == null ? null : toString(obj.salary_transaction_id, ''),
    xgp_transaction_id: obj.xgp_transaction_id == null ? null : toString(obj.xgp_transaction_id, ''),
    player_transaction_log_id: obj.player_transaction_log_id == null ? null : toString(obj.player_transaction_log_id, ''),
    salary_posted_at: obj.salary_posted_at == null ? null : toString(obj.salary_posted_at, ''),
    cash_before: normalizeMoneyValue(obj.cash_before, { allowNegative: true, fallback: 0 }),
    cash_after: normalizeMoneyValue(obj.cash_after, { allowNegative: true, fallback: 0 }),
    transaction_confirmed: Boolean(obj.transaction_confirmed),
  };
}

function normalizeRideshareState(raw: unknown): WorkStateSnapshot['rideshare_state'] {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  return {
    can_rideshare: Boolean(obj.can_rideshare),
    status: toString(obj.status, 'not_enough_time'),
    reason: toString(obj.reason, ''),
    block_reason: obj.block_reason == null ? null : toString(obj.block_reason, ''),
    block_reason_code: obj.block_reason_code == null ? null : toString(obj.block_reason_code, ''),
    block_reason_value: obj.block_reason_value == null ? null : toNumber(obj.block_reason_value, 0),
    trips_today: Math.max(0, Math.round(toNumber(obj.trips_today, 0))),
    max_trips: Math.max(1, Math.round(toNumber(obj.max_trips, 6))),
    remaining_trips: Math.max(0, Math.round(toNumber(obj.remaining_trips, 0))),
    trips_remaining: Math.max(0, Math.round(toNumber(obj.trips_remaining ?? obj.remaining_trips, 0))),
    hours_remaining_today: Math.max(0, toNumber(obj.hours_remaining_today, 0)),
    remaining_time_units: Math.max(0, toNumber(obj.remaining_time_units ?? obj.hours_remaining_today, 0)),
    current_stress: Math.max(0, Math.round(toNumber(obj.current_stress, 0))),
    current_health: Math.max(0, Math.round(toNumber(obj.current_health, 100))),
    stress_threshold: Math.max(0, Math.round(toNumber(obj.stress_threshold, 0))),
    health_threshold: Math.max(0, Math.round(toNumber(obj.health_threshold, 0))),
    mode: toString(obj.mode, 'midday'),
    time_cost_per_trip_units: Math.max(0, toNumber(obj.time_cost_per_trip_units, 0.5)),
    current_location_key: toString(obj.current_location_key, ''),
    current_location_label: toString(obj.current_location_label, ''),
    current_location_region: toString(obj.current_location_region, ''),
    location_tier: toString(obj.location_tier, ''),
    rideshare_allowed_here: Boolean(obj.rideshare_allowed_here),
    location_label: toString(obj.location_label, ''),
    demand_bonus_pct: normalizeFiniteNumber(obj.demand_bonus_pct, { fallback: 0 }),
    stress_delta_modifier: Math.round(toNumber(obj.stress_delta_modifier, 0)),
    estimated_pay_min_per_trip: normalizeMoneyValue(obj.estimated_pay_min_per_trip, { allowNegative: false, fallback: 0 }),
    estimated_pay_max_per_trip: normalizeMoneyValue(obj.estimated_pay_max_per_trip, { allowNegative: false, fallback: 0 }),
  };
}

function normalizeEconomySignalChips(raw: unknown, keyPrefix: string): EconomyRiskOverview['macro_conditions'] {
  if (!Array.isArray(raw)) return [];
  return raw.map((entry, index) => {
    const item = entry && typeof entry === 'object' ? (entry as Record<string, unknown>) : {};
    return {
      key: toString(item.key, `${keyPrefix}_${index}`),
      label: toString(item.label, 'Signal'),
      level: toString(item.level, 'moderate').toLowerCase(),
      value_text: toString(item.value_text || item.value, ''),
      trend: toString(item.trend, ''),
    };
  });
}

function normalizeEconomyRiskOverview(raw: unknown): EconomyRiskOverview | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  return {
    macro_conditions: normalizeEconomySignalChips(obj.macro_conditions, 'macro'),
    opportunity_signals: normalizeEconomySignalChips(obj.opportunity_signals, 'opportunity'),
    risk_badges: normalizeEconomySignalChips(obj.risk_badges, 'badge'),
    summary_line: toString(obj.summary_line, ''),
  };
}

function normalizeJobMarket(raw: unknown): WorkStateSnapshot['job_market'] {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  const jobs = Array.isArray(obj.jobs)
    ? (obj.jobs as unknown[]).map((entry) => {
      const row = entry && typeof entry === 'object' ? (entry as Record<string, unknown>) : {};
        return {
          job_key: toString(row.job_key, ''),
          display_name: toString(row.display_name, ''),
          tier: toString(row.tier, 'entry'),
        base_salary_xgp: normalizeMoneyValue(row.base_salary_xgp, { allowNegative: false, fallback: 0 }),
        stress_level: toString(row.stress_level, 'Moderate'),
        status: toString(row.status, 'locked'),
        is_current_job: Boolean(row.is_current_job),
        is_future_unlock: Boolean(row.is_future_unlock),
        requires_certification: Boolean(row.requires_certification),
        certification_key: row.certification_key == null ? null : toString(row.certification_key, ''),
        certification_name: row.certification_name == null ? null : toString(row.certification_name, ''),
        certification_completed: Boolean(row.certification_completed),
        requirement_label: row.requirement_label == null ? null : toString(row.requirement_label, ''),
        can_start_training: Boolean(row.can_start_training),
        can_switch: Boolean(row.can_switch),
          training_in_progress: Boolean(row.training_in_progress),
          training_days_completed: Math.max(0, Math.round(toNumber(row.training_days_completed, 0))),
          training_days_required: Math.max(0, Math.round(toNumber(row.training_days_required, 0))),
          training_days_remaining: Math.max(0, Math.round(toNumber(row.training_days_remaining, 0))),
          progression: normalizeJobProgressSnapshot(row.progression, toString(row.job_key, '')),
          is_locked: Boolean(row.is_locked),
          is_unlocked: Boolean(row.is_unlocked),
          level_requirement: Math.max(1, Math.round(toNumber(row.level_requirement, 1))),
          experience_requirement_shifts: Math.max(0, Math.round(toNumber(row.experience_requirement_shifts, 0))),
          prerequisite_job_keys: Array.isArray(row.prerequisite_job_keys)
            ? (row.prerequisite_job_keys as unknown[]).map((entry) => toString(entry, '')).filter(Boolean)
            : [],
          prerequisite_job_labels: Array.isArray(row.prerequisite_job_labels)
            ? (row.prerequisite_job_labels as unknown[]).map((entry) => toString(entry, '')).filter(Boolean)
            : [],
          path_hint: row.path_hint == null ? null : toString(row.path_hint, ''),
        };
      })
      : [];
  const certifications = Array.isArray(obj.certifications)
    ? (obj.certifications as unknown[]).map((entry) => {
      const row = entry && typeof entry === 'object' ? (entry as Record<string, unknown>) : {};
      return {
        certification_key: toString(row.certification_key, ''),
        display_name: toString(row.display_name, ''),
        unlocks_job: row.unlocks_job == null ? null : toString(row.unlocks_job, ''),
        duration_days: Math.max(0, Math.round(toNumber(row.duration_days, 0))),
        cost_xgp: normalizeMoneyValue(row.cost_xgp, { allowNegative: false, fallback: 0 }),
        completed: Boolean(row.completed),
        in_progress: Boolean(row.in_progress),
        progress_days: Math.max(0, Math.round(toNumber(row.progress_days, 0))),
        days_remaining: Math.max(0, Math.round(toNumber(row.days_remaining, 0))),
      };
    })
    : [];

  return {
    current_job_key: toString(obj.current_job_key, ''),
    current_job_display_name: toString(obj.current_job_display_name, ''),
    has_main_job: Boolean(obj.has_main_job),
    job_sync_status: obj.job_sync_status == null ? null : toString(obj.job_sync_status, ''),
    job_sync_warning_message: obj.job_sync_warning_message == null ? null : toString(obj.job_sync_warning_message, ''),
    jobs,
    certifications,
    training_active: Boolean(obj.training_active),
    training_certification_key: obj.training_certification_key == null ? null : toString(obj.training_certification_key, ''),
    training_certification_name: obj.training_certification_name == null ? null : toString(obj.training_certification_name, ''),
    training_days_completed: Math.max(0, Math.round(toNumber(obj.training_days_completed, 0))),
    training_days_required: Math.max(0, Math.round(toNumber(obj.training_days_required, 0))),
    training_days_remaining: Math.max(0, Math.round(toNumber(obj.training_days_remaining, 0))),
    completed_certification_keys: Array.isArray(obj.completed_certification_keys)
      ? (obj.completed_certification_keys as unknown[]).map((entry) => toString(entry, '')).filter(Boolean)
      : [],
    career_progression: Array.isArray(obj.career_progression)
      ? (obj.career_progression as unknown[]).map((entry) => normalizeJobProgressTrack(entry))
      : [],
  };
}

function normalizeWorkState(raw: unknown, playerId: string): WorkStateSnapshot | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  return {
    player_id: toString(obj.player_id, playerId),
    current_houston_time: toString(obj.current_houston_time, ''),
    current_houston_time_label: obj.current_houston_time_label == null ? null : toString(obj.current_houston_time_label, ''),
    current_houston_date: obj.current_houston_date == null ? null : toString(obj.current_houston_date, ''),
    current_houston_date_label: obj.current_houston_date_label == null ? null : toString(obj.current_houston_date_label, ''),
    current_game_day: normalizeCurrentDay(obj.current_game_day ?? obj.current_day, 1),
    day_of_week: toString(obj.day_of_week, ''),
    is_weekend: Boolean(obj.is_weekend),
    phase_status_label: obj.phase_status_label == null ? null : toString(obj.phase_status_label, ''),
    testing_mode:
      obj.testing_mode && typeof obj.testing_mode === 'object'
        ? {
          enabled: Boolean((obj.testing_mode as Record<string, unknown>).enabled),
          shift_minutes: Math.max(0, Math.round(toNumber((obj.testing_mode as Record<string, unknown>).shift_minutes, 0))),
          shift_length_label:
            (obj.testing_mode as Record<string, unknown>).shift_length_label == null
              ? null
              : toString((obj.testing_mode as Record<string, unknown>).shift_length_label, ''),
          two_shift_jobs: Array.isArray((obj.testing_mode as Record<string, unknown>).two_shift_jobs)
            ? ((obj.testing_mode as Record<string, unknown>).two_shift_jobs as unknown[]).map((entry) => toString(entry, '')).filter(Boolean)
            : [],
          eligible_for_two_shifts: Boolean((obj.testing_mode as Record<string, unknown>).eligible_for_two_shifts),
          max_daily_main_shifts: Math.max(1, Math.round(toNumber((obj.testing_mode as Record<string, unknown>).max_daily_main_shifts, 1))),
          shifts_completed_today: Math.max(0, Math.round(toNumber((obj.testing_mode as Record<string, unknown>).shifts_completed_today, 0))),
          shift_1_completed: Boolean((obj.testing_mode as Record<string, unknown>).shift_1_completed),
          shift_2_completed: Boolean((obj.testing_mode as Record<string, unknown>).shift_2_completed),
          overtime_shift_available: Boolean((obj.testing_mode as Record<string, unknown>).overtime_shift_available),
          overtime_used_today: Boolean((obj.testing_mode as Record<string, unknown>).overtime_used_today),
          next_shift_number_available:
            (obj.testing_mode as Record<string, unknown>).next_shift_number_available == null
              ? null
              : Math.max(0, Math.round(toNumber((obj.testing_mode as Record<string, unknown>).next_shift_number_available, 0))),
          daily_shift_limit_reached: Boolean((obj.testing_mode as Record<string, unknown>).daily_shift_limit_reached),
          weekend_rideshare_only: Boolean((obj.testing_mode as Record<string, unknown>).weekend_rideshare_only),
          rideshare_cap_today: Math.max(0, Math.round(toNumber((obj.testing_mode as Record<string, unknown>).rideshare_cap_today, 0))),
          weekend_main_shift_enabled: Boolean((obj.testing_mode as Record<string, unknown>).weekend_main_shift_enabled),
          second_shift_overtime_multiplier: normalizeFiniteNumber((obj.testing_mode as Record<string, unknown>).second_shift_overtime_multiplier, { fallback: 1.5 }),
        }
        : null,
    day_settled: Boolean(obj.day_settled),
    day_rollover_timezone: obj.day_rollover_timezone == null ? null : toString(obj.day_rollover_timezone, ''),
    day_rollover_time_label: obj.day_rollover_time_label == null ? null : toString(obj.day_rollover_time_label, ''),
    next_day_rollover_time: obj.next_day_rollover_time == null ? null : toString(obj.next_day_rollover_time, ''),
    main_job_key: obj.main_job_key == null ? null : toString(obj.main_job_key, ''),
    authoritative_current_job_id: obj.authoritative_current_job_id == null ? null : toString(obj.authoritative_current_job_id, ''),
    current_job_display_name: obj.current_job_display_name == null ? null : toString(obj.current_job_display_name, ''),
    current_job_level: Math.max(1, Math.round(toNumber(obj.current_job_level, 1))),
    current_job_progression: normalizeJobProgressSnapshot(
      obj.current_job_progression,
      toString(obj.authoritative_current_job_id ?? obj.active_shift_job_id ?? obj.scheduled_shift_job_id ?? '', ''),
    ),
    career_job_progression: Array.isArray(obj.career_job_progression)
      ? (obj.career_job_progression as unknown[]).map((entry) => normalizeJobProgressTrack(entry))
      : [],
    job_progression_feedback: normalizeJobProgressFeedback(obj.job_progression_feedback),
    scheduled_shift_job_id: obj.scheduled_shift_job_id == null ? null : toString(obj.scheduled_shift_job_id, ''),
    active_shift_job_id: obj.active_shift_job_id == null ? null : toString(obj.active_shift_job_id, ''),
    pay_calculation_job_id: obj.pay_calculation_job_id == null ? null : toString(obj.pay_calculation_job_id, ''),
    ui_job_id: obj.ui_job_id == null ? null : toString(obj.ui_job_id, ''),
    job_truth_mismatch_detected: Boolean(obj.job_truth_mismatch_detected),
    job_truth_sources:
      obj.job_truth_sources && typeof obj.job_truth_sources === 'object'
        ? Object.fromEntries(
          Object.entries(obj.job_truth_sources as Record<string, unknown>)
            .map(([key, value]) => [toString(key, ''), toString(value, '')])
            .filter(([key]) => key.length > 0),
        )
        : {},
    job_sync_status: obj.job_sync_status == null ? null : toString(obj.job_sync_status, ''),
    job_sync_warning_message: obj.job_sync_warning_message == null ? null : toString(obj.job_sync_warning_message, ''),
    job_sync_repair_source: obj.job_sync_repair_source == null ? null : toString(obj.job_sync_repair_source, ''),
    job_sync_auto_repaired: Boolean(obj.job_sync_auto_repaired),
    job_market: normalizeJobMarket(obj.job_market),
    active_shift_id: obj.active_shift_id == null ? null : toString(obj.active_shift_id, ''),
    shift_status: toString(obj.shift_status, 'idle'),
    main_shift_active_flag: Boolean(obj.main_shift_active_flag),
    is_on_shift: obj.is_on_shift == null ? Boolean(obj.main_shift_active_flag) : Boolean(obj.is_on_shift),
    work_status: obj.work_status == null ? null : toString(obj.work_status, ''),
    current_action_state: obj.current_action_state == null ? null : toString(obj.current_action_state, ''),
    shift_started_at: obj.shift_started_at == null ? null : toString(obj.shift_started_at, ''),
    shift_ends_at: obj.shift_ends_at == null ? null : toString(obj.shift_ends_at, ''),
    shift_completed_at: obj.shift_completed_at == null ? null : toString(obj.shift_completed_at, ''),
    shift_ended_at: obj.shift_ended_at == null ? null : toString(obj.shift_ended_at, ''),
    shift_start_time_label: obj.shift_start_time_label == null ? null : toString(obj.shift_start_time_label, ''),
    shift_end_time_label: obj.shift_end_time_label == null ? null : toString(obj.shift_end_time_label, ''),
    shift_completed_time_label: obj.shift_completed_time_label == null ? null : toString(obj.shift_completed_time_label, ''),
    shift_job_name: obj.shift_job_name == null ? null : toString(obj.shift_job_name, ''),
    shift_job_display_name: obj.shift_job_display_name == null ? null : toString(obj.shift_job_display_name, ''),
    shift_type: obj.shift_type == null ? null : toString(obj.shift_type, ''),
    shift_hours: Math.max(0, Math.round(toNumber(obj.shift_hours, 0))),
    shift_number: Math.max(0, Math.round(toNumber(obj.shift_number, 0))),
    shifts_completed_today: Math.max(0, Math.round(toNumber(obj.shifts_completed_today, 0))),
    shift_1_completed: Boolean(obj.shift_1_completed),
    shift_2_completed: Boolean(obj.shift_2_completed),
    shift_expired: Boolean(obj.shift_expired),
    shift_found: Boolean(obj.shift_found),
    shift_completed_today: Boolean(obj.shift_completed_today),
    shift_required_today: Boolean(obj.shift_required_today),
    no_shift_scheduled: Boolean(obj.no_shift_scheduled),
    scheduled_shift_start: obj.scheduled_shift_start == null ? null : toString(obj.scheduled_shift_start, ''),
    scheduled_shift_end: obj.scheduled_shift_end == null ? null : toString(obj.scheduled_shift_end, ''),
    scheduled_shift_start_label: obj.scheduled_shift_start_label == null ? null : toString(obj.scheduled_shift_start_label, ''),
    scheduled_shift_end_label: obj.scheduled_shift_end_label == null ? null : toString(obj.scheduled_shift_end_label, ''),
    scheduled_shift_window_label: obj.scheduled_shift_window_label == null ? null : toString(obj.scheduled_shift_window_label, ''),
    hours_available: Math.max(0, toNumber(obj.hours_available, 0)),
    main_shift_hours_today: normalizeFiniteNumber(obj.main_shift_hours_today, { fallback: 0 }),
    side_income_hours_today: normalizeFiniteNumber(obj.side_income_hours_today, { fallback: 0 }),
    rideshare_time_today: normalizeFiniteNumber(obj.rideshare_time_today, { fallback: 0 }),
    rideshare_earned_today: normalizeMoneyValue(obj.rideshare_earned_today, { allowNegative: false, fallback: 0 }),
    recovery_hours_today: normalizeFiniteNumber(obj.recovery_hours_today, { fallback: 0 }),
    total_time_used_today: normalizeFiniteNumber(obj.total_time_used_today, { fallback: 0 }),
    did_work_today: Boolean(obj.did_work_today),
    salary_earned_today: normalizeMoneyValue(obj.salary_earned_today, { allowNegative: false, fallback: 0 }),
    salary_earned_yesterday: normalizeMoneyValue(obj.salary_earned_yesterday, { allowNegative: false, fallback: 0 }),
    pay_model: toString(obj.pay_model, ''),
    pay_model_label: toString(obj.pay_model_label, ''),
    salary_pending_until_completion: Boolean(obj.salary_pending_until_completion),
    salary_payment_status: obj.salary_payment_status == null ? null : toString(obj.salary_payment_status, ''),
    salary_status_label: obj.salary_status_label == null ? null : toString(obj.salary_status_label, '').replace(/Â·/g, '-'),
    salary_status_message: obj.salary_status_message == null ? null : toString(obj.salary_status_message, '').replace(/Â·/g, '-'),
    salary_posting_pending: Boolean(obj.salary_posting_pending),
    salary_transaction_id: obj.salary_transaction_id == null ? null : toString(obj.salary_transaction_id, ''),
    salary_posted_at: obj.salary_posted_at == null ? null : toString(obj.salary_posted_at, ''),
    salary_transaction_confirmed: Boolean(obj.salary_transaction_confirmed),
    current_shift_salary_audit: normalizeShiftSalaryAudit(obj.current_shift_salary_audit),
    last_salary_posted: normalizeShiftSalaryAudit(obj.last_salary_posted),
    recent_salary_audits: Array.isArray(obj.recent_salary_audits)
      ? (obj.recent_salary_audits as unknown[])
        .map((entry) => normalizeShiftSalaryAudit(entry))
        .filter((entry): entry is NonNullable<typeof entry> => Boolean(entry))
      : [],
    missed_penalty_today: normalizeMoneyValue(obj.missed_penalty_today, { allowNegative: false, fallback: 0 }),
    missed_shift_today: Boolean(obj.missed_shift_today),
    missed_shift_health_delta: clampDeltaRange(obj.missed_shift_health_delta, { min: -100, max: 100, fallback: 0 }),
    missed_shift_stress_delta: clampDeltaRange(obj.missed_shift_stress_delta, { min: -100, max: 100, fallback: 0 }),
    survival_penalty_today: Boolean(obj.survival_penalty_today),
    survival_health_delta: clampDeltaRange(obj.survival_health_delta, { min: -100, max: 100, fallback: 0 }),
    survival_stress_delta: clampDeltaRange(obj.survival_stress_delta, { min: -100, max: 100, fallback: 0 }),
    meals_recorded_today: Math.max(0, Math.round(toNumber(obj.meals_recorded_today, 0))),
    current_location_key: toString(obj.current_location_key, ''),
    current_location_label: toString(obj.current_location_label, ''),
    current_location_region: toString(obj.current_location_region, ''),
    city_map: obj.city_map && typeof obj.city_map === 'object'
      ? {
        current_location_key: toString((obj.city_map as Record<string, unknown>).current_location_key, ''),
        current_location_label: toString((obj.city_map as Record<string, unknown>).current_location_label, ''),
        current_location_region: toString((obj.city_map as Record<string, unknown>).current_location_region, ''),
        current_location_node_type: toString((obj.city_map as Record<string, unknown>).current_location_node_type, ''),
        nodes: Array.isArray((obj.city_map as Record<string, unknown>).nodes)
          ? ((obj.city_map as Record<string, unknown>).nodes as unknown[]).map((entry) => {
            const row = entry && typeof entry === 'object' ? (entry as Record<string, unknown>) : {};
            return {
              key: toString(row.key, ''),
              label: toString(row.label, ''),
              region: toString(row.region, ''),
              node_type: toString(row.node_type, ''),
              opportunity_tier: toString(row.opportunity_tier, ''),
              rideshare_quality: toString(row.rideshare_quality, ''),
              is_current_location: Boolean(row.is_current_location),
            };
          })
          : [],
        travel_options: Array.isArray((obj.city_map as Record<string, unknown>).travel_options)
          ? ((obj.city_map as Record<string, unknown>).travel_options as unknown[]).map((entry) => {
            const row = entry && typeof entry === 'object' ? (entry as Record<string, unknown>) : {};
            return {
              from_key: toString(row.from_key, ''),
              from_label: toString(row.from_label, ''),
              destination_key: toString(row.destination_key, ''),
              destination_label: toString(row.destination_label, ''),
              destination_region: toString(row.destination_region, ''),
              destination_node_type: toString(row.destination_node_type, ''),
              destination_opportunity_tier: toString(row.destination_opportunity_tier, ''),
              time_cost_units: Math.max(0, Math.round(toNumber(row.time_cost_units, 0))),
              stress_delta: Math.round(toNumber(row.stress_delta, 0)),
              cash_cost_xgp: normalizeMoneyValue(row.cash_cost_xgp, { allowNegative: false, fallback: 0 }),
              route_label: toString(row.route_label, ''),
              rideshare_quality: toString(row.rideshare_quality, ''),
              rideshare_allowed: Boolean(row.rideshare_allowed),
              rideshare_demand_bonus_pct: normalizeFiniteNumber(row.rideshare_demand_bonus_pct, { fallback: 0 }),
            };
          })
          : [],
      }
      : null,
    travel_options: Array.isArray(obj.travel_options)
      ? (obj.travel_options as unknown[]).map((entry) => {
        const row = entry && typeof entry === 'object' ? (entry as Record<string, unknown>) : {};
        return {
          from_key: toString(row.from_key, ''),
          from_label: toString(row.from_label, ''),
          destination_key: toString(row.destination_key, ''),
          destination_label: toString(row.destination_label, ''),
          destination_region: toString(row.destination_region, ''),
          destination_node_type: toString(row.destination_node_type, ''),
          destination_opportunity_tier: toString(row.destination_opportunity_tier, ''),
          time_cost_units: Math.max(0, Math.round(toNumber(row.time_cost_units, 0))),
          stress_delta: Math.round(toNumber(row.stress_delta, 0)),
          cash_cost_xgp: normalizeMoneyValue(row.cash_cost_xgp, { allowNegative: false, fallback: 0 }),
          route_label: toString(row.route_label, ''),
          rideshare_quality: toString(row.rideshare_quality, ''),
          rideshare_allowed: Boolean(row.rideshare_allowed),
          rideshare_demand_bonus_pct: normalizeFiniteNumber(row.rideshare_demand_bonus_pct, { fallback: 0 }),
        };
      })
      : [],
    dinner_resolved_today: Boolean(obj.dinner_resolved_today),
    dinner_mode_today: toString(obj.dinner_mode_today, ''),
    dinner_cost_today: normalizeMoneyValue(obj.dinner_cost_today, { allowNegative: false, fallback: 0 }),
    food_debt_added_today: normalizeMoneyValue(obj.food_debt_added_today, { allowNegative: false, fallback: 0 }),
    needs_dinner_reminder: Boolean(obj.needs_dinner_reminder),
    dinner_reminder_message: obj.dinner_reminder_message == null ? null : toString(obj.dinner_reminder_message, ''),
    night_eat_reminder_shown: Boolean(obj.night_eat_reminder_shown),
    last_completed_shift: normalizeCompletedShift(obj.last_completed_shift),
    can_rideshare: Boolean(obj.can_rideshare),
    rideshare_state: normalizeRideshareState(obj.rideshare_state),
    rideshare_block_reason: obj.rideshare_block_reason == null ? null : toString(obj.rideshare_block_reason, ''),
    rideshare_unlocked: Boolean(obj.rideshare_unlocked),
    rideshare_available: Boolean(obj.rideshare_available),
    rideshare_unlock_time_label: obj.rideshare_unlock_time_label == null ? null : toString(obj.rideshare_unlock_time_label, ''),
    trips_today: Math.max(0, Math.round(toNumber(obj.trips_today ?? ((obj.rideshare_state as Record<string, unknown> | undefined)?.trips_today), 0))),
    trips_remaining: Math.max(0, Math.round(toNumber(obj.trips_remaining ?? ((obj.rideshare_state as Record<string, unknown> | undefined)?.remaining_trips), 0))),
    remaining_time_units: Math.max(0, toNumber(obj.remaining_time_units ?? obj.hours_available, 0)),
    effective_current_stress: Math.max(0, Math.round(toNumber(obj.effective_current_stress, 0))),
    effective_current_health: Math.max(0, Math.round(toNumber(obj.effective_current_health, 100))),
    remaining_side_income_hours_today: normalizeFiniteNumber(obj.remaining_side_income_hours_today, { fallback: 0 }),
    degraded_sections: Array.isArray(obj.degraded_sections)
      ? (obj.degraded_sections as unknown[]).map((entry) => toString(entry, '')).filter(Boolean)
      : [],
    market_data_available: obj.market_data_available == null ? true : Boolean(obj.market_data_available),
    market_data_message: obj.market_data_message == null ? null : toString(obj.market_data_message, ''),
    action_state_refreshed_at: obj.action_state_refreshed_at == null ? null : toString(obj.action_state_refreshed_at, ''),
    auto_day_rollover:
      obj.auto_day_rollover && typeof obj.auto_day_rollover === 'object'
        ? {
          applied_days: Math.max(0, Math.round(toNumber((obj.auto_day_rollover as Record<string, unknown>).applied_days, 0))),
          missed_days: Math.max(0, Math.round(toNumber((obj.auto_day_rollover as Record<string, unknown>).missed_days, 0))),
          truncated_days: Math.max(0, Math.round(toNumber((obj.auto_day_rollover as Record<string, unknown>).truncated_days, 0))),
          previous_sync_date: toString((obj.auto_day_rollover as Record<string, unknown>).previous_sync_date, ''),
          today_date: toString((obj.auto_day_rollover as Record<string, unknown>).today_date, ''),
          settlement_days: Array.isArray((obj.auto_day_rollover as Record<string, unknown>).settlement_days)
            ? ((obj.auto_day_rollover as Record<string, unknown>).settlement_days as unknown[])
              .map((entry) => Math.max(0, Math.round(toNumber(entry, 0))))
            : [],
          triggered: Boolean((obj.auto_day_rollover as Record<string, unknown>).triggered),
        }
        : null,
    auto_finalized_previous_day: Boolean(obj.auto_finalized_previous_day),
    auto_finalized_days_count: Math.max(0, Math.round(toNumber(obj.auto_finalized_days_count, 0))),
    new_day_started_houston_time: Boolean(obj.new_day_started_houston_time),
    auto_rollover_recap_lines: Array.isArray(obj.auto_rollover_recap_lines)
      ? (obj.auto_rollover_recap_lines as unknown[]).map((entry) => toString(entry, '')).filter(Boolean)
      : [],
    offline_survival_catchup:
      obj.offline_survival_catchup && typeof obj.offline_survival_catchup === 'object'
        ? {
          applied_days: Math.max(0, Math.round(toNumber((obj.offline_survival_catchup as Record<string, unknown>).applied_days, 0))),
          missed_days: Math.max(0, Math.round(toNumber((obj.offline_survival_catchup as Record<string, unknown>).missed_days, 0))),
          truncated_days: Math.max(0, Math.round(toNumber((obj.offline_survival_catchup as Record<string, unknown>).truncated_days, 0))),
          current_day_after: Math.max(0, Math.round(toNumber((obj.offline_survival_catchup as Record<string, unknown>).current_day_after, 0))),
          sync_date_updated: Boolean((obj.offline_survival_catchup as Record<string, unknown>).sync_date_updated),
          processed_days: Array.isArray((obj.offline_survival_catchup as Record<string, unknown>).processed_days)
            ? (((obj.offline_survival_catchup as Record<string, unknown>).processed_days as unknown[]) as Array<Record<string, unknown>>)
            : [],
        }
        : null,
  };
}

function normalizePreview(raw: Record<string, unknown>, playerId: string, actionKey: GameplayActionKey): ActionPreviewResponse {
  return {
    player_id: toString(raw.player_id, playerId),
    action_key: toString(raw.action_key, actionKey) as GameplayActionKey,
    summary: toString(raw.summary, 'Preview is available.'),
    expected_cash_impact: normalizeImpact(raw.expected_cash_impact, 'Cash', 'mixed'),
    expected_stress_impact: normalizeImpact(raw.expected_stress_impact, 'Stress', 'mixed'),
    expected_health_impact: normalizeImpact(raw.expected_health_impact, 'Health', 'mixed'),
    expected_time_impact: normalizeImpact(raw.expected_time_impact, 'Time', 'mixed'),
    expected_career_impact: normalizeImpact(raw.expected_career_impact, 'Career', 'mixed'),
    expected_distress_impact: normalizeImpact(raw.expected_distress_impact, 'Distress', 'mixed'),
    blockers: Array.isArray(raw.blockers) ? raw.blockers.map((entry) => toString(entry)) : [],
    warnings: Array.isArray(raw.warnings) ? raw.warnings.map((entry) => toString(entry)) : [],
    confidence_level: toConfidence(raw.confidence_level),
    debug_meta: (raw.debug_meta as Record<string, unknown>) || {},
  };
}

function normalizeEndOfDaySummary(raw: Record<string, unknown>, playerId: string): EndOfDaySummaryResponse {
  const earned = normalizeMoneyValue(raw.total_earned_xgp ?? raw.income_xgp, { allowNegative: false, fallback: 0 });
  const spent = normalizeMoneyValue(raw.total_spent_xgp ?? raw.expenses_xgp, { allowNegative: false, fallback: 0 });
  const net = safeNetCashFlowCalculation(earned, spent, raw.net_change_xgp);
  const dayNumber = normalizeCurrentDay(raw.day_number ?? raw.guided_day_number ?? raw.day, 0);
  const debugMeta = (raw.debug_meta as Record<string, unknown>) || {};

  return {
    player_id: toString(raw.player_id, playerId),
    day_number: dayNumber > 0 ? dayNumber : undefined,
    as_of_date: toString(raw.as_of_date || raw.settled_day || raw.day_number, ''),
    game_time: normalizeGameTime(raw.game_time),
    run_status: normalizePlayerRunStatus(raw.run_status),
    end_state: normalizeEndState(raw.end_state),
    risk_warnings: Array.isArray(raw.risk_warnings)
      ? raw.risk_warnings.map((entry) => toString(entry)).filter(Boolean)
      : [],
    black_swan_pending: Boolean(raw.black_swan_pending),
    black_swan_event_id: raw.black_swan_event_id == null ? null : toString(raw.black_swan_event_id, ''),
    tomorrow_preview_time: raw.tomorrow_preview_time == null ? null : toString(raw.tomorrow_preview_time, ''),
    next_morning_brief_at: raw.next_morning_brief_at == null ? null : toString(raw.next_morning_brief_at, ''),
    total_earned_xgp: earned,
    total_spent_xgp: spent,
    net_change_xgp: net,
    guided_day_number: toNumber(raw.guided_day_number, 0),
    guided_learning_title: raw.guided_learning_title != null ? toString(raw.guided_learning_title) : null,
    guided_earned_summary: raw.guided_earned_summary != null ? toString(raw.guided_earned_summary) : null,
    guided_spent_summary: raw.guided_spent_summary != null ? toString(raw.guided_spent_summary) : null,
    guided_change_summary: raw.guided_change_summary != null ? toString(raw.guided_change_summary) : null,
    guided_watch_tomorrow: raw.guided_watch_tomorrow != null ? toString(raw.guided_watch_tomorrow) : null,
    biggest_gain: toString(raw.biggest_gain, 'No standout gain today'),
    biggest_loss: toString(raw.biggest_loss, 'No standout loss today'),
    stress_delta: clampDeltaRange(raw.stress_delta ?? raw.stress_change, { min: -100, max: 100, fallback: 0 }),
    health_delta: clampDeltaRange(raw.health_delta ?? raw.health_change, { min: -100, max: 100, fallback: 0 }),
    skill_delta: clampDeltaRange(raw.skill_delta, { min: -100, max: 100, fallback: 0 }),
    credit_score_delta: clampDeltaRange(raw.credit_score_delta ?? raw.credit_score_change, { min: -200, max: 200, fallback: 0 }),
    distress_state: toString(raw.distress_state ?? raw.distress_state_after, 'stable'),
    tomorrow_warnings: Array.isArray(raw.tomorrow_warnings)
      ? raw.tomorrow_warnings.map((entry) => toString(entry))
      : [],
    debug_meta: {
      ...debugMeta,
      latest_completed_day: toNumber(debugMeta.latest_completed_day, dayNumber),
      summary_seen_day: toNumber(debugMeta.summary_seen_day, 0),
      summary_seen_for_day: Boolean(debugMeta.summary_seen_for_day),
      should_auto_show_summary: Boolean(debugMeta.should_auto_show_summary),
      summary_gate_reason: toString(debugMeta.summary_gate_reason, ''),
    },
  };
}

function normalizeTransactionHistoryItem(raw: unknown, playerId: string, index: number): TransactionHistoryItem {
  const row = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};

  return {
    id: toString(row.id, `tx_${index}`),
    player_id: toString(row.player_id, playerId),
    day: normalizeCurrentDay(row.day, 1),
    type: toString(row.type, 'unknown'),
    category: toString(row.category, 'general'),
    amount: normalizeMoneyValue(row.amount, { allowNegative: true, fallback: 0 }),
    description: toString(row.description, 'Gameplay transaction'),
    timestamp: row.timestamp == null ? null : toString(row.timestamp),
  };
}

function normalizeWeekly(raw: Record<string, unknown>, playerId: string): WeeklyPlayerSummaryResponse {
  const weeklyIncomeMix = Array.isArray(raw.weekly_income_mix)
    ? raw.weekly_income_mix.map((entry) => {
      const item = (entry || {}) as Record<string, unknown>;
      return {
        source: toString(item.source, 'income'),
        amount_xgp: normalizeMoneyValue(item.amount_xgp ?? item.amount, { allowNegative: true, fallback: 0 }),
      };
    })
    : [];

  return {
    player_id: toString(raw.player_id, playerId),
    week_start: toString(raw.week_start, ''),
    week_end: toString(raw.week_end, ''),
    weekly_income_mix: weeklyIncomeMix,
    top_pressure: toString(raw.top_pressure || raw.largest_cost_pressure, 'No major pressure flagged'),
    strongest_opportunity: toString(raw.strongest_opportunity || raw.dominant_income_source, 'No clear opportunity flagged'),
    strategy_classification: toString(raw.strategy_classification, 'stable_worker'),
    risk_trend: toString(raw.risk_trend || raw.distress_trend, 'stable'),
    growth_trend: toString(raw.growth_trend || raw.career_trend, 'steady'),
    suggested_next_moves: Array.isArray(raw.suggested_next_moves)
      ? raw.suggested_next_moves.map((entry) => toString(entry))
      : [],
    notable_event_chain: toString(raw.notable_event_chain, ''),
    debug_meta: (raw.debug_meta as Record<string, unknown>) || {},
  };
}

function normalizeNotifications(raw: Record<string, unknown>, playerId: string): PlayerNotificationResponse {
  const notificationsRaw = Array.isArray(raw.notifications)
    ? raw.notifications
    : Array.isArray(raw.items)
      ? raw.items
      : [];

  const notifications: PlayerNotificationItem[] = notificationsRaw.map((entry, index) => {
    const item = (entry || {}) as Record<string, unknown>;
    return {
      id: toString(item.id, `notification_${index}`),
      severity: (toString(item.severity, 'info') as any) || 'info',
      category: toString(item.category, 'general'),
      title: toString(item.title, 'Notification'),
      body: toString(item.body || item.message, ''),
      suggested_action: toString(item.suggested_action, ''),
      created_at: toString(item.created_at || item.timestamp, ''),
      read: Boolean(item.read),
    };
  });

  return {
    player_id: toString(raw.player_id, playerId),
    as_of_date: toString(raw.as_of_date || raw.date, ''),
    notifications,
    debug_meta: (raw.debug_meta as Record<string, unknown>) || {},
  };
}

function canonicalActionKey(actionKey: GameplayActionKey): GameplayActionKey {
  // Core logic freeze: frontend action canonicalization must stay aligned with backend action semantics.
  // Small bug fixes are allowed; do not broaden matching rules casually.
  const raw = toString(actionKey).toLowerCase().trim();
  if (raw.includes('business') && raw.includes('operate')) return 'operate_business';
  if (raw.includes('inventory') || raw.includes('stock')) return 'buy_inventory';
  if (raw.includes('ride') || raw.includes('delivery') || raw.includes('side_income')) return 'side_income';
  if (raw.includes('travel') || raw.includes('map_move')) return 'travel';
  // switch_job must be resolved before work_shift — 'job' appears in both but they are distinct actions.
  if (raw === 'switch_job' || (raw.includes('switch') && raw.includes('job'))) return 'switch_job';
  if (raw === 'start_training' || (raw.includes('start') && raw.includes('training'))) return 'start_training';
  if (raw.includes('work') || raw.includes('shift')) return 'work_shift';
  if (raw.includes('study') || raw.includes('train') || raw.includes('cert')) return 'study';
  if (raw.includes('debt') || raw.includes('payment')) return 'debt_payment';
  if (raw.includes('recovery')) return 'recovery_action';
  if (raw.includes('housing') || raw.includes('region') || raw.includes('move')) return 'change_region';
  if (raw.includes('rest') || raw.includes('sleep')) return 'rest';
  return actionKey;
}

function executionResponseBase(
  playerId: string,
  actionKey: GameplayActionKey,
  message: string,
  resultSummary: string,
  timeCostUnits: number,
  rawResult: Record<string, unknown>,
): ActionExecutionResponse {
  const updatedState = normalizeAuthoritativeState(
    rawResult.updated_state ?? rawResult.authoritative_state,
    playerId,
    normalizeWorkState(rawResult.work_state, playerId),
  );
  const result = rawResult.result && typeof rawResult.result === 'object'
    ? (rawResult.result as Record<string, unknown>)
    : undefined;
  return {
    player_id: playerId,
    action_key: actionKey,
    success: true,
    message,
    result_summary: resultSummary,
    time_cost_units: normalizeTimeCostUnits(timeCostUnits, 2),
    cash_delta_xgp: normalizeOptionalMoneyValue(
      rawResult.cash_delta_xgp ?? rawResult.cash_change_xgp ?? rawResult.cash_impact_xgp,
      { allowNegative: true, fallback: 0 },
    ) ?? undefined,
    stress_delta: rawResult.stress_delta != null
      ? clampDeltaRange(rawResult.stress_delta, { min: -100, max: 100, fallback: 0 })
      : undefined,
    health_delta: rawResult.health_delta != null
      ? clampDeltaRange(rawResult.health_delta, { min: -100, max: 100, fallback: 0 })
      : undefined,
    result,
    updated_state: updatedState,
    raw_result: rawResult,
  };
}

function normalizeEndDay(raw: Record<string, unknown>, playerId: string): EndDayResponse {
  return {
    player_id: toString(raw.player_id, playerId),
    settled_day: normalizeCurrentDay(raw.settled_day ?? raw.day_number ?? raw.day, 1),
    game_time: normalizeGameTime(raw.game_time),
    run_status: normalizePlayerRunStatus(raw.run_status),
    end_state: normalizeEndState(raw.end_state),
    risk_warnings: Array.isArray(raw.risk_warnings)
      ? raw.risk_warnings.map((entry) => toString(entry)).filter(Boolean)
      : [],
    black_swan_pending: Boolean(raw.black_swan_pending),
    black_swan_event_id: raw.black_swan_event_id == null ? null : toString(raw.black_swan_event_id, ''),
    tomorrow_preview_time: raw.tomorrow_preview_time == null ? null : toString(raw.tomorrow_preview_time, ''),
    next_morning_brief_at: raw.next_morning_brief_at == null ? null : toString(raw.next_morning_brief_at, ''),
    message: toString(raw.message, 'Day settled.'),
    summary_headline: toString(raw.summary_headline || raw.headline, ''),
    summary: toString(raw.summary, ''),
    ending_cash_xgp: normalizeMoneyValue(raw.ending_cash_xgp ?? raw.cash_after ?? raw.ending_cash, {
      allowNegative: true,
      fallback: 0,
    }),
    stress_change: clampDeltaRange(raw.stress_change, { min: -100, max: 100, fallback: 0 }),
    health_change: clampDeltaRange(raw.health_change, { min: -100, max: 100, fallback: 0 }),
    raw_result: raw,
  };
}

interface GameplayStateOverrideOptions {
  currentStress?: number | null;
  currentHealth?: number | null;
}

function appendGameplayStateOverrides(
  path: string,
  options?: GameplayStateOverrideOptions,
): string {
  const params = new URLSearchParams();
  if (Number.isFinite(options?.currentStress)) {
    params.set('current_stress', String(Math.max(0, Math.min(100, Math.round(Number(options?.currentStress))))));
  }
  if (Number.isFinite(options?.currentHealth)) {
    params.set('current_health', String(Math.max(0, Math.min(100, Math.round(Number(options?.currentHealth))))));
  }
  const query = params.toString();
  if (!query) return path;
  return `${path}?${query}`;
}

export async function getPlayerDashboard(
  playerId: string,
  options?: GameplayStateOverrideOptions,
): Promise<PlayerDashboardResponse> {
  const path = appendGameplayStateOverrides(`/gameplay/player/${playerId}/dashboard`, options);
  logCanonicalRoute('dashboard', playerId, path);
  const raw = await fetchApi<Record<string, unknown>>(path);
  return normalizeDashboard(raw, playerId);
}

export async function getPlayerActions(
  playerId: string,
  options?: GameplayStateOverrideOptions,
): Promise<DailyActionHubResponse> {
  const path = appendGameplayStateOverrides(`/gameplay/player/${playerId}/actions`, options);
  try {
    logCanonicalRoute('actions', playerId, path);
    const raw = await fetchApi<Record<string, unknown>>(path);
    return normalizeActionHub(raw, playerId);
  } catch (error) {
    recordWarning('gameplayApi', 'Canonical action-hub request failed; using brief-derived fallback.', {
      action: 'actions_fallback',
      context: {
        playerId,
        path,
      },
      error,
    });
    const brief = await fetchApiWithFallback<Record<string, unknown>>([`/briefs/player/${playerId}/latest`]);
    const hints = Array.isArray(brief.action_hints_json) ? brief.action_hints_json : [];
    return {
      player_id: playerId,
      as_of_date: toString(brief.day, ''),
      recommended_actions: hints.map((entry, index) => normalizeAction(entry, 'recommended', index)),
      available_actions: [],
      blocked_actions: [],
      top_tradeoffs: [],
      next_risk_warnings: [],
      debug_meta: { source: 'brief_fallback' },
    };
  }
}

export async function getPlayerLoopBundle(
  playerId: string,
  options?: GameplayStateOverrideOptions,
): Promise<GameplayLoopCoreResponse> {
  const path = appendGameplayStateOverrides(`/gameplay/player/${playerId}/loop`, options);
  logCanonicalRoute('loop_bundle', playerId, path);
  const raw = await fetchApi<Record<string, unknown>>(path);
  const dashboard = normalizeDashboard(
    raw.dashboard && typeof raw.dashboard === 'object'
      ? (raw.dashboard as Record<string, unknown>)
      : {},
    playerId,
  );
  const actionHub = normalizeActionHub(
    raw.action_hub && typeof raw.action_hub === 'object'
      ? (raw.action_hub as Record<string, unknown>)
      : {},
    playerId,
  );
  const authoritativeState = normalizeAuthoritativeState(
    raw.authoritative_state
      ?? dashboard.authoritative_state
      ?? actionHub.authoritative_state,
    playerId,
    actionHub.work_state ?? dashboard.work_state ?? null,
  );
  return {
    player_id: toString(raw.player_id, playerId),
    game_time: normalizeGameTime(raw.game_time ?? dashboard.game_time),
    run_status: normalizePlayerRunStatus(raw.run_status ?? dashboard.run_status),
    dashboard,
    action_hub: actionHub,
    authoritative_state: authoritativeState,
    absence_summary: normalizeAbsenceSummary(raw.absence_summary),
    debug_meta: (raw.debug_meta as Record<string, unknown>) || {},
  };
}

function normalizeAbsenceSummary(raw: unknown): import('@/types/gameplay').AbsenceSummary | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  const missed = Number(obj.missed_days ?? 0);
  if (!Number.isFinite(missed)) return null;
  const warningsRaw = Array.isArray(obj.warnings) ? obj.warnings : [];
  const warnings = warningsRaw.filter((w): w is string => typeof w === 'string');
  const skippedReason = obj.skipped_reason;
  return {
    missed_days: Math.max(0, Math.trunc(missed)),
    truncated_days: Math.max(0, Math.trunc(Number(obj.truncated_days ?? 0) || 0)),
    health_change: Math.trunc(Number(obj.health_change ?? 0) || 0),
    stress_change: Math.trunc(Number(obj.stress_change ?? 0) || 0),
    cash_change: Number(obj.cash_change ?? 0) || 0,
    inventory_spoilage: Number(obj.inventory_spoilage ?? 0) || 0,
    warnings,
    skipped_reason: typeof skippedReason === 'string' ? skippedReason : null,
  };
}

export async function getGameTime(): Promise<GameTimePayload> {
  const raw = await fetchApi<Record<string, unknown>>('/game-time');
  return normalizeGameTime(raw) || {
    server_now: '',
    timezone: 'America/Chicago',
    next_settlement_at: '',
    next_morning_brief_at: '',
    seconds_until_settlement: 0,
    seconds_until_morning_brief: 0,
  };
}

export async function getPlayerRunStatus(playerId: string): Promise<PlayerRunStatusResponse> {
  const raw = await fetchApi<Record<string, unknown>>(`/player/${playerId}/run-status`);
  return normalizePlayerRunStatus(raw) || {
    run_status: 'active',
    run_ended_at: null,
    run_end_day: null,
    run_end_reason: null,
    run_end_summary: null,
    can_continue: true,
    can_retire: false,
    retirement_requirement: normalizeRetirementRequirement(null),
  };
}

export async function retirePlayerRun(playerId: string): Promise<RetireRunResponse> {
  const raw = await fetchApi<Record<string, unknown>>(`/player/${playerId}/retire`, {
    method: 'POST',
    body: '{}',
  });
  return normalizeRetireRunResponse(raw);
}

export async function getPlayerAnnualRecap(
  playerId: string,
  options?: { year?: number; debug?: boolean },
): Promise<AnnualRecapResponse> {
  const year = Math.max(1, Math.round(Number(options?.year) || 1));
  const params = new URLSearchParams({ year: String(year) });
  if (options?.debug) {
    params.set('debug', 'true');
  }
  const path = `/player/${playerId}/annual-recap?${params.toString()}`;
  logCanonicalRoute('annual_recap', playerId, path);
  const raw = await fetchApi<Record<string, unknown>>(path);
  return normalizeAnnualRecap(raw);
}

export async function getPlayerTimeline(
  playerId: string,
  options?: { limit?: number },
): Promise<TimelineEventItem[]> {
  const limit = Math.max(1, Math.min(200, Math.round(Number(options?.limit) || 100)));
  const path = `/player/${playerId}/timeline?limit=${limit}`;
  logCanonicalRoute('timeline', playerId, path);
  const raw = await fetchApi<unknown>(path);
  if (!Array.isArray(raw)) return [];
  return raw.map((entry, index) => normalizeTimelineEvent(entry, index));
}

export async function getPendingBlackSwanEvent(playerId: string): Promise<BlackSwanEventResponse | null> {
  const path = `/player/${playerId}/black-swan/pending`;
  logCanonicalRoute('black_swan_pending', playerId, path);
  const raw = await fetchApi<unknown>(path);
  return normalizeBlackSwanEvent(raw);
}

export async function markBlackSwanSeen(
  playerId: string,
  eventId: string,
): Promise<BlackSwanEventResponse | null> {
  const path = `/player/${playerId}/black-swan/${eventId}/seen`;
  logCanonicalRoute('black_swan_seen', playerId, path);
  const raw = await fetchApi<unknown>(path, {
    method: 'POST',
    body: '{}',
  });
  return normalizeBlackSwanEvent(raw);
}

export async function getPlayerWorkState(playerId: string): Promise<WorkStateSnapshot | null> {
  const path = `/gameplay/player/${playerId}/work-state`;
  logCanonicalRoute('work_state', playerId, path);
  const raw = await fetchApi<Record<string, unknown>>(path);
  return normalizeWorkState(raw, playerId);
}

export async function finalizePlayerWorkState(playerId: string): Promise<WorkStateSnapshot | null> {
  const path = `/gameplay/player/${playerId}/work-state/finalize`;
  logCanonicalRoute('work_state_finalize', playerId, path);
  const raw = await fetchApi<Record<string, unknown>>(path, {
    method: 'POST',
  });
  return normalizeWorkState(raw, playerId);
}

export async function previewPlayerAction(
  playerId: string,
  payload: ActionPreviewRequest,
  init?: RequestInit,
): Promise<ActionPreviewResponse> {
  const path = `/gameplay/player/${playerId}/actions/preview`;
  logCanonicalRoute('action_preview', playerId, path);
  const raw = await fetchApi<Record<string, unknown>>(path, {
    ...(init || {}),
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return normalizePreview(raw, playerId, payload.action_key);
}

export async function getEndOfDaySummary(playerId: string): Promise<EndOfDaySummaryResponse> {
  const path = `/gameplay/player/${playerId}/end-of-day-summary`;
  logCanonicalRoute('end_of_day_summary', playerId, path);
  const raw = await fetchApi<Record<string, unknown>>(path);
  return normalizeEndOfDaySummary(raw, playerId);
}

export async function acknowledgeEndOfDaySummary(playerId: string, dayNumber?: number): Promise<Record<string, unknown>> {
  const path = `/gameplay/player/${playerId}/end-of-day-summary/ack`;
  logCanonicalRoute('end_of_day_summary_ack', playerId, path);
  return fetchApi<Record<string, unknown>>(path, {
    method: 'POST',
    body: JSON.stringify({ day_number: dayNumber ?? null }),
  });
}

export async function getTransactionHistory(playerId: string, day?: number | null): Promise<TransactionHistoryResponse> {
  const safeDay = day != null ? Math.max(1, Math.round(Number(day) || 1)) : null;
  const path = safeDay != null
    ? `/gameplay/player/${playerId}/transactions?day=${safeDay}`
    : `/gameplay/player/${playerId}/transactions`;
  logCanonicalRoute('transaction_history', playerId, path);
  const raw = await fetchApi<Record<string, unknown>>(path);
  const transactions = Array.isArray(raw.transactions)
    ? raw.transactions.map((entry, index) => normalizeTransactionHistoryItem(entry, playerId, index))
    : [];
  return {
    player_id: toString(raw.player_id, playerId),
    day: normalizeCurrentDay(raw.day, safeDay ?? 1),
    transactions,
    total_income: normalizeMoneyValue(raw.total_income, { allowNegative: false, fallback: 0 }),
    total_expense: normalizeMoneyValue(raw.total_expense, { allowNegative: false, fallback: 0 }),
    net: normalizeMoneyValue(raw.net, { allowNegative: true, fallback: 0 }),
  };
}

export async function getWeeklySummary(playerId: string): Promise<WeeklyPlayerSummaryResponse> {
  const raw = await fetchApiWithFallback<Record<string, unknown>>([
    `/gameplay/player/${playerId}/weekly-summary`,
    `/player/${playerId}/weekly-summary`,
  ]);
  return normalizeWeekly(raw, playerId);
}

export async function executeAction(
  playerId: string,
  actionKey: GameplayActionKey,
  params: Record<string, unknown> = {},
): Promise<ActionExecutionResponse> {
  const canonical = canonicalActionKey(actionKey);
  const normalizedParams = normalizeExecutionParameters(canonical, params);
  if (canonical === 'switch_job') {
    const targetJob = normalizeJobName(
      normalizedParams.new_job_key
      ?? normalizedParams.job_key
      ?? normalizedParams.job
      ?? normalizedParams.job_name
      ?? normalizedParams.target_job,
    );
    if (!targetJob) {
      throw new Error('Could not switch jobs because no destination job was selected.');
    }
    normalizedParams.new_job_key = targetJob;
  }
  if (canonical === 'start_training') {
    const certificationKey = toString(
      normalizedParams.certification_key ?? normalizedParams.track_key,
      '',
    ).trim().toLowerCase();
    if (!certificationKey) {
      throw new Error('Could not start training because no certification was selected.');
    }
    normalizedParams.certification_key = certificationKey;
  }
  if (canonical === 'debt_payment' && !normalizedParams.request_id && !normalizedParams.idempotency_key) {
    normalizedParams.request_id = `debt_payment_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  }
  const unifiedPayload = {
    action_key: canonical,
    parameters: normalizedParams,
  };
  const canonicalExecutePath = `/gameplay/player/${playerId}/actions/execute`;

  try {
    logCanonicalRoute('action_execute', playerId, canonicalExecutePath);
    if (GAMEPLAY_ROUTE_DIAGNOSTICS_ENABLED && (canonical === 'switch_job' || canonical === 'work_shift' || canonical === 'start_training')) {
      recordInfo('gameplayApi', 'Dispatching canonical gameplay action.', {
        action: `${String(canonical)}_request`,
        context: {
          playerId,
          canonicalActionKey: canonical,
          requestPayload: unifiedPayload,
        },
      });
    }
    const unified = await fetchApi<Record<string, unknown>>(canonicalExecutePath, {
      method: 'POST',
      body: JSON.stringify(unifiedPayload),
    });
    if (GAMEPLAY_ROUTE_DIAGNOSTICS_ENABLED && (canonical === 'switch_job' || canonical === 'work_shift' || canonical === 'start_training')) {
      recordInfo('gameplayApi', 'Canonical gameplay action completed.', {
        action: `${String(canonical)}_response`,
        context: {
          playerId,
          canonicalActionKey: canonical,
          resultSummary: toString(unified.result_summary || unified.summary || unified.message),
          rawResult: unified.raw_result ?? unified,
        },
      });
    }

    return executionResponseBase(
      playerId,
      canonical,
      toString(unified.message, 'Action executed'),
      toString(unified.result_summary || unified.summary || unified.message, 'Action completed.'),
      toNumber(unified.time_cost_units ?? normalizedParams.time_cost_units ?? 2, 2),
      unified,
    );
  } catch (error) {
    // Preserve canonical gameplay errors (4xx/5xx) so we don't mask the real cause
    // with legacy fallback responses like unrelated auth failures.
    const message = error instanceof Error ? error.message : String(error);
    const normalized = message.toLowerCase();
    const shouldUseFallback =
      normalized.includes('404')
      || normalized.includes('not found')
      || normalized.includes('failed to fetch')
      || normalized.includes('network request failed');
    if (GAMEPLAY_ROUTE_DIAGNOSTICS_ENABLED && (canonical === 'switch_job' || canonical === 'work_shift' || canonical === 'start_training')) {
      recordWarning('gameplayApi', 'Canonical gameplay action failed before fallback.', {
        action: `${String(canonical)}_request_failed`,
        context: {
          playerId,
          canonicalActionKey: canonical,
          requestPayload: unifiedPayload,
          message,
          shouldUseFallback,
        },
      });
    }
    if (!shouldUseFallback) {
      throw error instanceof Error ? error : new Error(message);
    }
  }

  if (canonical === 'operate_business') {
    const raw = await fetchApiWithFallback<Record<string, unknown>>(
      [`/business/player/${playerId}/operate`],
      {
        method: 'POST',
        body: JSON.stringify({ as_of_date: params.as_of_date ?? null }),
      },
    );
    return executionResponseBase(
      playerId,
      canonical,
      'Business operation completed',
      toString(raw.summary || raw.message, 'Business operation finished.'),
      toNumber(params.time_cost_units, 2),
      raw,
    );
  }

  if (canonical === 'buy_inventory') {
    const businessId = toString(params.business_id || params.businessId);
    if (!businessId) {
      throw new Error('Inventory purchase needs business_id.');
    }
    const raw = await fetchApiWithFallback<Record<string, unknown>>(
      [`/business/player/${playerId}/inventory/purchase`],
      {
        method: 'POST',
        body: JSON.stringify({
          business_id: businessId,
          produce_units: toNumber(params.produce_units, 0),
          essentials_units: toNumber(params.essentials_units, 0),
          protein_units: toNumber(params.protein_units, 0),
          as_of_date: params.as_of_date ?? null,
        }),
      },
    );
    return executionResponseBase(
      playerId,
      canonical,
      'Inventory purchased',
      toString(raw.message || raw.summary, 'Inventory updated.'),
      toNumber(params.time_cost_units, 1),
      raw,
    );
  }

  if (canonical === 'study') {
    const raw = await fetchApiWithFallback<Record<string, unknown>>(
      [`/career/player/${playerId}/training/log`],
      {
        method: 'POST',
        body: JSON.stringify({
          training_hours: Math.max(0, Math.min(4, toNumber(params.training_hours, 2))),
          as_of_date: params.as_of_date ?? null,
        }),
      },
    );
    return executionResponseBase(
      playerId,
      canonical,
      'Training logged',
      toString(raw.summary || raw.message, 'Career training applied.'),
      toNumber(params.time_cost_units, 2),
      raw,
    );
  }

  if (canonical === 'start_training') {
    const certificationKey = toString(
      normalizedParams.certification_key ?? normalizedParams.track_key,
      '',
    ).trim().toLowerCase();
    if (!certificationKey) {
      throw new Error('Could not start training because no certification was selected.');
    }
    const raw = await fetchApiWithFallback<Record<string, unknown>>(
      [`/career/player/${playerId}/certification/start`],
      {
        method: 'POST',
        body: JSON.stringify({
          track_key: certificationKey,
        }),
      },
    );
    return executionResponseBase(
      playerId,
      canonical,
      toString(raw.message, 'Training started'),
      toString(raw.message || raw.summary, 'Certification training started.'),
      toNumber(params.time_cost_units, 1),
      raw,
    );
  }

  if (canonical === 'recovery_action') {
    const raw = await fetchApiWithFallback<Record<string, unknown>>(
      [`/finance/player/${playerId}/recovery-action`],
      {
        method: 'POST',
        body: JSON.stringify({
          action_key: toString(params.action_key, 'payment_plan_enroll'),
        }),
      },
    );
    return executionResponseBase(
      playerId,
      canonical,
      'Recovery action queued',
      toString(raw.action_queued, 'Recovery action applied.'),
      toNumber(params.time_cost_units, 1),
      raw,
    );
  }

  if (canonical === 'switch_job') {
    const targetJob = normalizeJobName(
      normalizedParams.new_job_key ?? normalizedParams.job_key ?? normalizedParams.job ?? normalizedParams.job_name ?? normalizedParams.target_job,
    );
    if (!targetJob) {
      throw new Error('Job switch requires a target job identifier.');
    }
    const raw = await fetchApiWithFallback<Record<string, unknown>>(
      [
          `/career/player/${playerId}/job/switch`,
          `/jobs/player/${playerId}/switch`,
          `/career/player/${playerId}/switch-job`,
          `/player/${playerId}/switch-job`,
      ],
      {
        method: 'POST',
          body: JSON.stringify({ new_job_key: targetJob, job_key: targetJob }),
      },
    );
    return executionResponseBase(
      playerId,
      canonical,
      toString(raw.message, 'Job switch completed'),
      toString(raw.message, 'Job updated.'),
      toNumber(params.time_cost_units, 1),
      raw,
    );
  }

  if (canonical === 'change_region') {
    const regionKey = toString(params.region_key || params.regionKey);
    if (!regionKey) {
      throw new Error('Region update needs region_key.');
    }
    const raw = await fetchApiWithFallback<Record<string, unknown>>(
      [`/housing/player/${playerId}/region`],
      {
        method: 'POST',
        body: JSON.stringify({
          region_key: regionKey,
          commute_mode: toString(params.commute_mode || params.commuteMode, 'car'),
        }),
      },
    );
    return executionResponseBase(
      playerId,
      canonical,
      'Region updated',
      toString(raw.message || raw.summary, 'Housing region changed.'),
      toNumber(params.time_cost_units, 1),
      raw,
    );
  }

  if (canonical === 'side_income') {
    const requestedTripsRaw = Math.round(toNumber(params.trips, toNumber(params.trip_count, 1)));
    const requestedTrips = requestedTripsRaw === 3 || requestedTripsRaw === 5 ? requestedTripsRaw : 1;
    const raw = await fetchApiWithFallback<Record<string, unknown>>(
      [`/side-income/rideshare`],
      {
        method: 'POST',
        body: JSON.stringify({
          player_id: playerId,
          trips: requestedTrips,
          hours_worked: Math.max(1, Math.min(8, toNumber(params.hours_worked, requestedTrips))),
          on_shift: Boolean(params.on_shift),
        }),
      },
    );
    const earned = normalizeMoneyValue(
      raw.earned ?? raw.net_income_xgp ?? raw.cash_delta_xgp,
      { allowNegative: true, fallback: 0 },
    );
    const shapedRaw: Record<string, unknown> = {
      ...raw,
      cash_delta_xgp: earned,
      stress_delta: toNumber(raw.stress_change ?? raw.stress_delta, 0),
      health_delta: toNumber(raw.health_change ?? raw.health_delta, 0),
    };
    return executionResponseBase(
      playerId,
      canonical,
      toString(raw.message, 'Rideshare completed'),
      toString(raw.message, 'Side-income action applied.'),
      toNumber(raw.time_used, toNumber(raw.trips, toNumber(params.time_cost_units, requestedTrips))),
      shapedRaw,
    );
  }

  if (canonical === 'work_shift') {
    throw new Error('Canonical work shift route is unavailable. Refresh and retry.');
  }

  throw new Error(`No mapped execution endpoint for action '${String(actionKey)}'.`);
}

export async function endDay(playerId: string): Promise<EndDayResponse> {
  const canonicalEndDayPath = `/gameplay/player/${playerId}/end-day`;
  logCanonicalRoute('end_day', playerId, canonicalEndDayPath);
  const unified = await fetchApi<Record<string, unknown>>(canonicalEndDayPath, { method: 'POST', body: '{}' });
  return normalizeEndDay(unified, playerId);
}

export async function getPlayerNotifications(playerId: string): Promise<PlayerNotificationResponse> {
  try {
    const raw = await fetchApiWithFallback<Record<string, unknown>>([
      `/gameplay/player/${playerId}/notifications`,
      `/player/${playerId}/notifications`,
    ]);
    return normalizeNotifications(raw, playerId);
  } catch {
    return {
      player_id: playerId,
      as_of_date: '',
      notifications: [],
      debug_meta: { source: 'empty_fallback' },
    };
  }
}
