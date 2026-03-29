import { fetchApiWithFallback } from '@/lib/apiClient';
import {
  ActiveCommitmentResponse,
  AvailableCommitmentItem,
  AvailableCommitmentsResponse,
  CommitmentActivationRequest,
  CommitmentFeedbackItem,
  CommitmentFeedbackResponse,
  CommitmentHistoryItem,
  CommitmentHistoryResponse,
  CommitmentSummaryResponse,
} from '@/types/commitment';


function toNumber(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toString(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value;
  if (value == null) return fallback;
  return String(value);
}

function toObject(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function withDateParam(path: string, asOfDate?: string | null): string {
  if (!asOfDate) return path;
  const joiner = path.includes('?') ? '&' : '?';
  return `${path}${joiner}as_of_date=${encodeURIComponent(asOfDate)}`;
}

function normalizeAvailableItem(raw: unknown, index: number): AvailableCommitmentItem {
  const obj = toObject(raw);
  return {
    commitment_key: toString(obj.commitment_key, `commitment_${index}`),
    title: toString(obj.title, 'Commitment'),
    description: toString(obj.description, ''),
    suggested_duration_days: Math.max(3, Math.min(7, Math.round(toNumber(obj.suggested_duration_days, 5)))),
    expected_upside: toString(obj.expected_upside, ''),
    expected_downside: toString(obj.expected_downside, ''),
    adherence_focus: Array.isArray(obj.adherence_focus) ? obj.adherence_focus.map((x) => toString(x)).filter(Boolean) : [],
    current_fit_label: toString(obj.current_fit_label, 'moderate'),
    risk_label: toString(obj.risk_label, 'moderate'),
    debug_meta: toObject(obj.debug_meta),
  };
}

function normalizeActiveCommitment(raw: unknown, playerId = '', asOfDate = ''): ActiveCommitmentResponse {
  const obj = toObject(raw);
  return {
    player_id: toString(obj.player_id, playerId),
    as_of_date: toString(obj.as_of_date, asOfDate),
    status: toString(obj.status, 'inactive'),
    commitment_key: toString(obj.commitment_key, ''),
    title: toString(obj.title, 'No active commitment'),
    description: toString(obj.description, ''),
    duration_days: Math.max(0, Math.round(toNumber(obj.duration_days, 0))),
    start_date: obj.start_date == null ? null : toString(obj.start_date),
    target_end_date: obj.target_end_date == null ? null : toString(obj.target_end_date),
    days_remaining: Math.max(0, Math.round(toNumber(obj.days_remaining, 0))),
    adherence_score: toNumber(obj.adherence_score, 0),
    momentum_score: toNumber(obj.momentum_score, 0),
    alignment_label: toString(obj.alignment_label, 'none'),
    drift_level: toString(obj.drift_level, 'none'),
    days_followed: Math.max(0, Math.round(toNumber(obj.days_followed, 0))),
    days_drifted: Math.max(0, Math.round(toNumber(obj.days_drifted, 0))),
    likely_payoff: toString(obj.likely_payoff, ''),
    likely_downside: toString(obj.likely_downside, ''),
    summary: toString(obj.summary, ''),
    suggested_correction: obj.suggested_correction == null ? null : toString(obj.suggested_correction),
    reward_summary: obj.reward_summary == null ? null : toString(obj.reward_summary),
    debug_meta: toObject(obj.debug_meta),
  };
}

function normalizeFeedbackItem(raw: unknown, index: number): CommitmentFeedbackItem {
  const obj = toObject(raw);
  return {
    severity: toString(obj.severity, 'info'),
    title: toString(obj.title, `Feedback ${index + 1}`),
    body: toString(obj.body, ''),
    commitment_key: toString(obj.commitment_key, ''),
    feedback_type: toString(obj.feedback_type, 'info'),
    suggested_correction: obj.suggested_correction == null ? null : toString(obj.suggested_correction),
    debug_meta: toObject(obj.debug_meta),
  };
}

function normalizeHistoryItem(raw: unknown, index: number): CommitmentHistoryItem {
  const obj = toObject(raw);
  return {
    commitment_key: toString(obj.commitment_key, `history_${index}`),
    title: toString(obj.title, 'Commitment'),
    status: toString(obj.status, 'inactive'),
    start_date: obj.start_date == null ? null : toString(obj.start_date),
    target_end_date: obj.target_end_date == null ? null : toString(obj.target_end_date),
    completed_on_date: obj.completed_on_date == null ? null : toString(obj.completed_on_date),
    adherence_score: toNumber(obj.adherence_score, 0),
    momentum_score: toNumber(obj.momentum_score, 0),
    days_followed: Math.max(0, Math.round(toNumber(obj.days_followed, 0))),
    days_drifted: Math.max(0, Math.round(toNumber(obj.days_drifted, 0))),
    completion_summary: obj.completion_summary == null ? null : toString(obj.completion_summary),
    reward_summary: obj.reward_summary == null ? null : toString(obj.reward_summary),
    debug_meta: toObject(obj.debug_meta),
  };
}

function normalizeAvailableResponse(raw: unknown, playerId: string): AvailableCommitmentsResponse {
  const obj = toObject(raw);
  const items = Array.isArray(obj.items) ? obj.items : [];
  return {
    player_id: toString(obj.player_id, playerId),
    as_of_date: toString(obj.as_of_date, ''),
    items: items.map((item, index) => normalizeAvailableItem(item, index)),
    debug_meta: toObject(obj.debug_meta),
  };
}

function normalizeSummaryResponse(raw: unknown, playerId: string): CommitmentSummaryResponse {
  const obj = toObject(raw);
  const asOfDate = toString(obj.as_of_date, '');
  return {
    player_id: toString(obj.player_id, playerId),
    as_of_date: asOfDate,
    active_commitment: normalizeActiveCommitment(obj.active_commitment, playerId, asOfDate),
    debug_meta: toObject(obj.debug_meta),
  };
}

function normalizeFeedbackResponse(raw: unknown, playerId: string): CommitmentFeedbackResponse {
  const obj = toObject(raw);
  const items = Array.isArray(obj.items) ? obj.items : [];
  return {
    player_id: toString(obj.player_id, playerId),
    as_of_date: toString(obj.as_of_date, ''),
    items: items.map((item, index) => normalizeFeedbackItem(item, index)),
    debug_meta: toObject(obj.debug_meta),
  };
}

function normalizeHistoryResponse(raw: unknown, playerId: string): CommitmentHistoryResponse {
  const obj = toObject(raw);
  const entries = Array.isArray(obj.entries) ? obj.entries : [];
  return {
    player_id: toString(obj.player_id, playerId),
    as_of_date: toString(obj.as_of_date, ''),
    entries: entries.map((entry, index) => normalizeHistoryItem(entry, index)),
    debug_meta: toObject(obj.debug_meta),
  };
}

export async function getAvailableCommitments(
  playerId: string,
  asOfDate?: string | null,
): Promise<AvailableCommitmentsResponse> {
  const raw = await fetchApiWithFallback<unknown>([
    withDateParam(`/commitment/player/${playerId}/available`, asOfDate),
  ]);
  return normalizeAvailableResponse(raw, playerId);
}

export async function getActiveCommitment(
  playerId: string,
  asOfDate?: string | null,
): Promise<ActiveCommitmentResponse> {
  const raw = await fetchApiWithFallback<unknown>([
    withDateParam(`/commitment/player/${playerId}/active`, asOfDate),
  ]);
  return normalizeActiveCommitment(raw, playerId, asOfDate || '');
}

export async function activateCommitment(
  playerId: string,
  payload: CommitmentActivationRequest,
  asOfDate?: string | null,
): Promise<ActiveCommitmentResponse> {
  const raw = await fetchApiWithFallback<unknown>(
    [withDateParam(`/commitment/player/${playerId}/activate`, asOfDate)],
    {
      method: 'POST',
      body: JSON.stringify({
        commitment_key: payload.commitment_key,
        duration_days: Math.max(3, Math.min(7, Math.round(toNumber(payload.duration_days, 5)))),
        replace_active: Boolean(payload.replace_active),
      }),
    },
  );
  return normalizeActiveCommitment(raw, playerId, asOfDate || '');
}

export async function cancelCommitment(
  playerId: string,
  asOfDate?: string | null,
): Promise<CommitmentSummaryResponse> {
  const raw = await fetchApiWithFallback<unknown>(
    [withDateParam(`/commitment/player/${playerId}/cancel`, asOfDate)],
    {
      method: 'POST',
      body: '{}',
    },
  );
  return normalizeSummaryResponse(raw, playerId);
}

export async function replaceCommitment(
  playerId: string,
  payload: CommitmentActivationRequest,
  asOfDate?: string | null,
): Promise<ActiveCommitmentResponse> {
  const raw = await fetchApiWithFallback<unknown>(
    [withDateParam(`/commitment/player/${playerId}/replace`, asOfDate)],
    {
      method: 'POST',
      body: JSON.stringify({
        commitment_key: payload.commitment_key,
        duration_days: Math.max(3, Math.min(7, Math.round(toNumber(payload.duration_days, 5)))),
        replace_active: true,
      }),
    },
  );
  return normalizeActiveCommitment(raw, playerId, asOfDate || '');
}

export async function getCommitmentSummary(
  playerId: string,
  asOfDate?: string | null,
): Promise<CommitmentSummaryResponse> {
  const raw = await fetchApiWithFallback<unknown>([
    withDateParam(`/commitment/player/${playerId}/summary`, asOfDate),
  ]);
  return normalizeSummaryResponse(raw, playerId);
}

export async function getCommitmentFeedback(
  playerId: string,
  asOfDate?: string | null,
): Promise<CommitmentFeedbackResponse> {
  const raw = await fetchApiWithFallback<unknown>([
    withDateParam(`/commitment/player/${playerId}/feedback`, asOfDate),
  ]);
  return normalizeFeedbackResponse(raw, playerId);
}

export async function getCommitmentHistory(
  playerId: string,
  options?: { asOfDate?: string | null; limit?: number },
): Promise<CommitmentHistoryResponse> {
  const limit = Math.max(1, Math.min(100, Math.round(toNumber(options?.limit, 20))));
  const path = withDateParam(`/commitment/player/${playerId}/history?limit=${limit}`, options?.asOfDate);
  const raw = await fetchApiWithFallback<unknown>([path]);
  return normalizeHistoryResponse(raw, playerId);
}

export async function refreshCommitment(
  playerId: string,
  options?: { asOfDate?: string | null; actionKey?: string | null },
): Promise<CommitmentSummaryResponse> {
  const params: string[] = [];
  if (options?.actionKey) params.push(`action_key=${encodeURIComponent(options.actionKey)}`);
  if (options?.asOfDate) params.push(`as_of_date=${encodeURIComponent(options.asOfDate)}`);
  const suffix = params.length > 0 ? `?${params.join('&')}` : '';

  const raw = await fetchApiWithFallback<unknown>(
    [`/commitment/player/${playerId}/refresh${suffix}`],
    {
      method: 'POST',
      body: '{}',
    },
  );
  return normalizeSummaryResponse(raw, playerId);
}
