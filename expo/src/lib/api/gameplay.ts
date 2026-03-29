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
  ActionRecommendationState,
  ConfidenceLevel,
  DailyActionHubResponse,
  DailyActionItem,
  EndDayResponse,
  EndOfDaySummaryResponse,
  GameplayActionKey,
  PlayerDashboardResponse,
  PlayerNotificationItem,
  PlayerNotificationResponse,
  TransactionHistoryItem,
  TransactionHistoryResponse,
  TrendDirection,
  WeeklyPlayerSummaryResponse,
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

function normalizeDashboard(raw: Record<string, unknown>, playerId: string): PlayerDashboardResponse {
  const stats = (raw.stats as Record<string, unknown>) || {};
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

  return {
    player_id: toString(raw.player_id, playerId),
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
    job_progress: jobProgressRaw
      ? {
        job_key: toString(jobProgressRaw.job_key || stats.current_job || ''),
        job_level: Math.max(1, Math.min(40, toNumber(jobProgressRaw.job_level ?? jobProgressRaw.skill_level, 1))),
        skill_level: Math.max(1, Math.min(40, toNumber(jobProgressRaw.skill_level ?? jobProgressRaw.job_level, 1))),
        job_xp: Math.max(0, Math.round(toNumber(jobProgressRaw.job_xp, 0))),
        job_xp_to_next_level: Math.max(0, Math.round(toNumber(jobProgressRaw.job_xp_to_next_level, 0))),
        max_job_level: Math.max(1, Math.round(toNumber(jobProgressRaw.max_job_level, 40))),
        monthly_pay_xgp: normalizeMoneyValue(jobProgressRaw.monthly_pay_xgp, { allowNegative: false, fallback: 0 }),
        employer_company_symbol: toString(jobProgressRaw.employer_company_symbol, ''),
        employer_company_name: toString(jobProgressRaw.employer_company_name, ''),
        position_title: toString(jobProgressRaw.position_title, ''),
        shift_type: toString(jobProgressRaw.shift_type, ''),
      }
      : null,
    debug_meta: (raw.debug_meta as Record<string, unknown>) || {},
  };
}

function normalizeActionHub(raw: Record<string, unknown>, playerId: string): DailyActionHubResponse {
  const recommendedRaw = Array.isArray(raw.recommended_actions) ? raw.recommended_actions : [];
  const availableRaw = Array.isArray(raw.available_actions) ? raw.available_actions : [];
  const blockedRaw = Array.isArray(raw.blocked_actions) ? raw.blocked_actions : [];

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
    debug_meta: (raw.debug_meta as Record<string, unknown>) || {},
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
  const metadata = row.metadata_json && typeof row.metadata_json === 'object'
    ? (row.metadata_json as Record<string, unknown>)
    : {};

  return {
    id: toString(row.id, `tx_${index}`),
    player_id: toString(row.player_id, playerId),
    day: row.day == null ? null : normalizeCurrentDay(row.day, 0),
    type: toString(row.type, 'unknown'),
    category: toString(row.category, 'general'),
    symbol: row.symbol == null ? null : toString(row.symbol, '').toUpperCase() || null,
    quantity: row.quantity == null ? null : normalizeFiniteNumber(row.quantity, { fallback: 0 }),
    unit_price: row.unit_price == null ? null : normalizeMoneyValue(row.unit_price, { allowNegative: false, fallback: 0 }),
    gross_amount: normalizeMoneyValue(row.gross_amount, { allowNegative: true, fallback: 0 }),
    fee_amount: normalizeMoneyValue(row.fee_amount, { allowNegative: false, fallback: 0 }),
    net_cash_delta: normalizeMoneyValue(row.net_cash_delta, { allowNegative: true, fallback: 0 }),
    resulting_cash_balance: normalizeMoneyValue(row.resulting_cash_balance, { allowNegative: true, fallback: 0 }),
    metadata_json: metadata,
    created_at: row.created_at == null ? null : toString(row.created_at),
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
  // switch_job must be resolved before work_shift — 'job' appears in both but they are distinct actions.
  if (raw === 'switch_job' || (raw.includes('switch') && raw.includes('job'))) return 'switch_job';
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
    raw_result: rawResult,
  };
}

function normalizeEndDay(raw: Record<string, unknown>, playerId: string): EndDayResponse {
  return {
    player_id: toString(raw.player_id, playerId),
    settled_day: normalizeCurrentDay(raw.settled_day ?? raw.day_number ?? raw.day, 1),
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

export async function getPlayerDashboard(playerId: string): Promise<PlayerDashboardResponse> {
  const path = `/gameplay/player/${playerId}/dashboard`;
  logCanonicalRoute('dashboard', playerId, path);
  const raw = await fetchApi<Record<string, unknown>>(path);
  return normalizeDashboard(raw, playerId);
}

export async function getPlayerActions(playerId: string): Promise<DailyActionHubResponse> {
  const path = `/gameplay/player/${playerId}/actions`;
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

export async function getTransactionHistory(playerId: string, limit = 50): Promise<TransactionHistoryResponse> {
  const safeLimit = Math.max(1, Math.min(Math.round(Number(limit) || 50), 200));
  const path = `/gameplay/player/${playerId}/transactions?limit=${safeLimit}`;
  logCanonicalRoute('transaction_history', playerId, path);
  const raw = await fetchApi<Record<string, unknown>>(path);
  const transactions = Array.isArray(raw.transactions)
    ? raw.transactions.map((entry, index) => normalizeTransactionHistoryItem(entry, playerId, index))
    : [];
  return {
    player_id: toString(raw.player_id, playerId),
    count: toNumber(raw.count, transactions.length),
    transactions,
  };
}

export async function getWeeklySummary(playerId: string): Promise<WeeklyPlayerSummaryResponse> {
  const raw = await fetchApiWithFallback<Record<string, unknown>>([
    `/gameplay/player/${playerId}/weekly-summary`,
    `/player/${playerId}/weekly-summary`,
    `/strategy/player/${playerId}/weekly`,
  ]);
  return normalizeWeekly(raw, playerId);
}

export async function executeAction(
  playerId: string,
  actionKey: GameplayActionKey,
  params: Record<string, unknown> = {},
): Promise<ActionExecutionResponse> {
  const canonical = canonicalActionKey(actionKey);
  const unifiedPayload = {
    action_key: canonical,
    parameters: params,
  };
  const canonicalExecutePath = `/gameplay/player/${playerId}/actions/execute`;

  try {
    logCanonicalRoute('action_execute', playerId, canonicalExecutePath);
    const unified = await fetchApi<Record<string, unknown>>(canonicalExecutePath, {
      method: 'POST',
      body: JSON.stringify(unifiedPayload),
    });

    return executionResponseBase(
      playerId,
      canonical,
      toString(unified.message, 'Action executed'),
      toString(unified.result_summary || unified.summary || unified.message, 'Action completed.'),
      toNumber(unified.time_cost_units ?? params.time_cost_units ?? 2, 2),
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

  if (canonical === 'debt_payment' || canonical === 'recovery_action') {
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
      params.job_key ?? params.job ?? params.job_name ?? params.target_job,
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

  if (canonical === 'work_shift') {
    const jobName = normalizeJobName(
      params.job_name ?? params.job ?? params.current_job,
    );
    if (!jobName) {
      throw new Error(
        'Work shift requires an active job assignment. Acquire a job before performing a work shift.',
      );
    }
    const raw = await fetchApiWithFallback<Record<string, unknown>>(
      [`/jobs/work`],
      {
        method: 'POST',
        body: JSON.stringify({
          job_name: jobName,
          hours_worked: Math.max(1, Math.min(12, Math.round(toNumber(params.hours_worked, 4)))),
        }),
      },
    );
    return executionResponseBase(
      playerId,
      canonical,
      toString(raw.message, 'Work shift completed'),
      toString(raw.message, 'Work shift applied.'),
      toNumber(params.time_cost_units, 3),
      raw,
    );
  }

  if (canonical === 'side_income') {
    const raw = await fetchApiWithFallback<Record<string, unknown>>(
      [`/side-income/rideshare`],
      {
        method: 'POST',
        body: JSON.stringify({
          player_id: playerId,
          hours_worked: Math.max(1, Math.min(8, toNumber(params.hours_worked, 3))),
        }),
      },
    );
    return executionResponseBase(
      playerId,
      canonical,
      toString(raw.message, 'Rideshare completed'),
      toString(raw.message, 'Side-income action applied.'),
      toNumber(params.time_cost_units, 3),
      raw,
    );
  }

  throw new Error(`No mapped execution endpoint for action '${String(actionKey)}'.`);
}

export async function endDay(playerId: string): Promise<EndDayResponse> {
  const canonicalEndDayPath = `/gameplay/player/${playerId}/end-day`;
  try {
    logCanonicalRoute('end_day', playerId, canonicalEndDayPath);
    const unified = await fetchApi<Record<string, unknown>>(canonicalEndDayPath, { method: 'POST', body: '{}' });
    return normalizeEndDay(unified, playerId);
  } catch {
    // Fallback to legacy day progression endpoints below.
  }

  const raw = await fetchApiWithFallback<Record<string, unknown>>(
    [
      `/day/run/${playerId}`,
      `/day/settle/${playerId}`,
    ],
    { method: 'POST', body: '{}' },
  );
  return normalizeEndDay(raw, playerId);
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
