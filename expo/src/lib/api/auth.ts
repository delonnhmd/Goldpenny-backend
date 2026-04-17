import { fetchApi } from '@/lib/apiClient';
import {
  AccountSummary,
  AuthSessionResponse,
  AuthSessionStateResponse,
  CreatePlayerProfilePayload,
  ForgotPasswordResponse,
  PlayerProfileSummary,
} from '@/types/auth';

interface SignUpRequest {
  email: string;
  password: string;
}

interface SignInRequest {
  email: string;
  password: string;
}

function toString(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value;
  if (value == null) return fallback;
  return String(value);
}

function toNullableString(value: unknown): string | null {
  if (value == null) return null;
  const text = toString(value).trim();
  return text ? text : null;
}

function toNumber(value: unknown, fallback = 0): number {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

function toBoolean(value: unknown, fallback = false): boolean {
  if (typeof value === 'boolean') return value;
  if (value === 'true') return true;
  if (value === 'false') return false;
  return fallback;
}

function toRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function normalizeAccount(raw: unknown): AccountSummary {
  const obj = toRecord(raw);
  return {
    id: toString(obj.id),
    email: toString(obj.email),
    auth_provider: toString(obj.auth_provider, 'password'),
    status: toString(obj.status, 'active'),
    created_at: toString(obj.created_at),
    last_login_at: toNullableString(obj.last_login_at),
    password_updated_at: toNullableString(obj.password_updated_at),
  };
}

function normalizePlayerProfile(raw: unknown): PlayerProfileSummary {
  const obj = toRecord(raw);
  return {
    id: toString(obj.id),
    display_name: toNullableString(obj.display_name),
    gender: toNullableString(obj.gender),
    region: toNullableString(obj.region),
    cash_xgp: toNumber(obj.cash_xgp, 0),
    debt_xgp: toNumber(obj.debt_xgp, 0),
    health: Math.round(toNumber(obj.health, 100)),
    stress: Math.round(toNumber(obj.stress, 0)),
    current_job: toNullableString(obj.current_job),
    created_at: toNullableString(obj.created_at),
    load_ready: toBoolean(obj.load_ready, true),
  };
}

function normalizeOptionalPlayerProfile(raw: unknown): PlayerProfileSummary | null {
  const obj = toRecord(raw);
  if (!obj.id) return null;
  return normalizePlayerProfile(obj);
}

function normalizeSession(raw: unknown): AuthSessionResponse {
  const obj = toRecord(raw);
  return {
    access_token: toString(obj.access_token),
    token_type: toString(obj.token_type, 'bearer'),
    expires_at: toString(obj.expires_at),
    account: normalizeAccount(obj.account),
    player_profile: normalizeOptionalPlayerProfile(obj.player_profile),
  };
}

function normalizeSessionState(raw: unknown): AuthSessionStateResponse {
  const obj = toRecord(raw);
  return {
    account: normalizeAccount(obj.account),
    player_profile: normalizeOptionalPlayerProfile(obj.player_profile),
  };
}

function normalizeForgotPassword(raw: unknown): ForgotPasswordResponse {
  const obj = toRecord(raw);
  return {
    message: toString(obj.message, 'If that email exists, a password reset link is ready.'),
    reset_token: toNullableString(obj.reset_token),
    reset_url: toNullableString(obj.reset_url),
    expires_at: toNullableString(obj.expires_at),
  };
}

export async function registerAccount(payload: SignUpRequest): Promise<AuthSessionResponse> {
  const raw = await fetchApi<unknown>('/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return normalizeSession(raw);
}

export async function loginAccount(payload: SignInRequest): Promise<AuthSessionResponse> {
  const raw = await fetchApi<unknown>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return normalizeSession(raw);
}

export async function getCurrentSessionState(): Promise<AuthSessionStateResponse> {
  const raw = await fetchApi<unknown>('/auth/session');
  return normalizeSessionState(raw);
}

export async function createPlayerProfile(payload?: CreatePlayerProfilePayload): Promise<AuthSessionStateResponse> {
  const raw = await fetchApi<unknown>('/auth/player-profile', {
    method: 'POST',
    body: JSON.stringify(payload || {}),
  });
  return normalizeSessionState(raw);
}

export async function requestPasswordReset(email: string): Promise<ForgotPasswordResponse> {
  const raw = await fetchApi<unknown>('/auth/forgot-password', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
  return normalizeForgotPassword(raw);
}

export async function submitPasswordReset(token: string, password: string): Promise<void> {
  await fetchApi<unknown>('/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({ token, password }),
  });
}

export interface LinkedPlayer {
  id: string;
  user_id: string | null;
  display_name: string | null;
  region: string | null;
  cash_xgp: number;
  debt_xgp: number;
  health: number;
  stress: number;
  main_job: string | null;
  account_created_day: number;
  created_at: string | null;
}

function normalizeLinkedPlayer(raw: unknown): LinkedPlayer {
  const obj = toRecord(raw);
  return {
    id: toString(obj.id),
    user_id: toNullableString(obj.user_id),
    display_name: toNullableString(obj.display_name),
    region: toNullableString(obj.region),
    cash_xgp: toNumber(obj.cash_xgp, 0),
    debt_xgp: toNumber(obj.debt_xgp, 0),
    health: Math.round(toNumber(obj.health, 100)),
    stress: Math.round(toNumber(obj.stress, 0)),
    main_job: toNullableString(obj.main_job),
    account_created_day: Math.round(toNumber(obj.account_created_day, 1)),
    created_at: toNullableString(obj.created_at),
  };
}

export async function getPlayerByUserId(userId: string): Promise<LinkedPlayer | null> {
  if (!userId) throw new Error('userId is required.');
  try {
    const raw = await fetchApi<unknown>(`/player/by-user-id/${encodeURIComponent(userId)}`);
    return normalizeLinkedPlayer(raw);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error || '');
    if (message.toLowerCase().includes('player profile not found')) {
      return null;
    }
    throw error;
  }
}

export async function createPlayerByUserId(
  userId: string,
  payload?: CreatePlayerProfilePayload,
): Promise<LinkedPlayer> {
  if (!userId) throw new Error('userId is required.');
  const raw = await fetchApi<unknown>(`/player/by-user-id/${encodeURIComponent(userId)}`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
  });
  return normalizeLinkedPlayer(raw);
}
