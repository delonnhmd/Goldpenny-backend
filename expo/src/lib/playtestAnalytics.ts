// Gold Penny — Playtest instrumentation and balance feedback layer (Step 67).
// Lightweight, AsyncStorage-backed analytics designed for dev/QA inspection.
// No external vendor dependencies. All data stays local to the device for now.

import AsyncStorage from '@react-native-async-storage/async-storage';

// ─── Storage keys ─────────────────────────────────────────────────────────────

const KEY_EVENTS = (playerId: string) => `goldpenny:playtest:events:${playerId}`;
const KEY_FUNNEL = (playerId: string, gameDay: number) =>
  `goldpenny:playtest:funnel:${playerId}:${gameDay}`;
const KEY_SCREEN_TIMES = (sessionId: string) =>
  `goldpenny:playtest:screentime:${sessionId}`;
const KEY_BALANCE = (playerId: string, gameDay: number) =>
  `goldpenny:playtest:balance:${playerId}:${gameDay}`;
const KEY_FRICTION = (sessionId: string) =>
  `goldpenny:playtest:friction:${sessionId}`;
const KEY_SESSION_INDEX = (playerId: string) =>
  `goldpenny:playtest:sessions:${playerId}`;

const MAX_EVENTS_PER_PLAYER = 200;
const MAX_SESSION_INDEX_ENTRIES = 50;

// ─── Types ────────────────────────────────────────────────────────────────────

export type PlaytestEventName =
  | 'session_started'
  | 'onboarding_started'
  | 'onboarding_skipped'
  | 'onboarding_completed'
  | 'brief_viewed'
  | 'dashboard_viewed'
  | 'work_action_taken'
  | 'market_viewed'
  | 'business_viewed'
  | 'summary_viewed'
  | 'day_completed'
  | 'session_abandoned';

export interface PlaytestEvent {
  id: string;
  eventName: PlaytestEventName;
  sessionId: string;
  playerId: string;
  gameDay: number;
  timestamp: string;
  properties?: Record<string, unknown>;
}

export interface ScreenTimingEntry {
  screen: string;
  enteredAt: string;
  durationMs: number;
}

export interface ScreenTimingRecord {
  sessionId: string;
  playerId: string;
  gameDay: number;
  screens: ScreenTimingEntry[];
  totalSessionMs: number;
  timeToFirstActionMs: number | null;
}

export interface Day1FunnelState {
  sessionId: string;
  playerId: string;
  gameDay: number;
  sessionStartedAt: string | null;
  briefSeenAt: string | null;
  dashboardSeenAt: string | null;
  firstWorkActionAt: string | null;
  marketSeenAt: string | null;
  summarySeenAt: string | null;
  dayCompletedAt: string | null;
}

export interface Day1BalanceTelemetry {
  sessionId: string;
  playerId: string;
  gameDay: number;
  startingCash: number | null;
  endingCash: number | null;
  cashDelta: number | null;
  startingStress: number | null;
  endingStress: number | null;
  stressDelta: number | null;
  startingHealth: number | null;
  endingHealth: number | null;
  healthDelta: number | null;
  expensePressure: string | null;
  incomeEarned: number | null;
  opportunityFlagsSurfaced: number;
  endedPositive: boolean | null;
  capturedAt: string;
}

export interface FrictionSignals {
  sessionId: string;
  playerId: string;
  onboardingSkipped: boolean;
  noWorkActionTaken: boolean;
  noMarketVisit: boolean;
  noBusinessVisit: boolean;
  exitedBeforeSummary: boolean;
  longIdleCount: number;
}

export interface SessionIndexEntry {
  sessionId: string;
  playerId: string;
  startedAt: string;
  gameDay: number;
}

// ─── Internal helpers ─────────────────────────────────────────────────────────

function nowIso(): string {
  return new Date().toISOString();
}

/** nano-UUID (not crypto-quality, but fine for local event IDs) */
export function generateSessionId(): string {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).slice(2, 8);
  return `gp_${timestamp}_${random}`;
}

function safeParseJson<T>(raw: string | null, fallback: T): T {
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function safeNumber(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

// ─── Event ingestion ──────────────────────────────────────────────────────────

/**
 * Emit a single playtest event. Fire-and-forget; errors are swallowed so
 * analytics never disrupts gameplay.
 */
export async function emitPlaytestEvent(
  event: Omit<PlaytestEvent, 'id' | 'timestamp'>,
): Promise<void> {
  try {
    const entry: PlaytestEvent = {
      ...event,
      id: generateSessionId(),
      timestamp: nowIso(),
    };
    const key = KEY_EVENTS(event.playerId);
    const raw = await AsyncStorage.getItem(key);
    const events = safeParseJson<PlaytestEvent[]>(raw, []);
    events.push(entry);
    // Keep only most recent N events as ring buffer
    const trimmed = events.slice(-MAX_EVENTS_PER_PLAYER);
    await AsyncStorage.setItem(key, JSON.stringify(trimmed));
  } catch {
    // intentionally silent
  }
}

// ─── Session index ────────────────────────────────────────────────────────────

export async function registerSession(entry: SessionIndexEntry): Promise<void> {
  try {
    const key = KEY_SESSION_INDEX(entry.playerId);
    const raw = await AsyncStorage.getItem(key);
    const sessions = safeParseJson<SessionIndexEntry[]>(raw, []);
    sessions.push(entry);
    const trimmed = sessions.slice(-MAX_SESSION_INDEX_ENTRIES);
    await AsyncStorage.setItem(key, JSON.stringify(trimmed));
  } catch {
    // intentionally silent
  }
}

// ─── Screen timing ────────────────────────────────────────────────────────────

export async function recordScreenTime(
  sessionId: string,
  playerId: string,
  gameDay: number,
  entry: ScreenTimingEntry,
): Promise<void> {
  try {
    const key = KEY_SCREEN_TIMES(sessionId);
    const raw = await AsyncStorage.getItem(key);
    const record = safeParseJson<ScreenTimingRecord>(raw, {
      sessionId,
      playerId,
      gameDay,
      screens: [],
      totalSessionMs: 0,
      timeToFirstActionMs: null,
    });
    record.screens.push(entry);
    record.totalSessionMs += entry.durationMs;
    await AsyncStorage.setItem(key, JSON.stringify(record));
  } catch {
    // intentionally silent
  }
}

export async function recordTimeToFirstAction(
  sessionId: string,
  playerId: string,
  gameDay: number,
  sessionStartedAt: string,
): Promise<void> {
  try {
    const key = KEY_SCREEN_TIMES(sessionId);
    const raw = await AsyncStorage.getItem(key);
    const record = safeParseJson<ScreenTimingRecord>(raw, {
      sessionId,
      playerId,
      gameDay,
      screens: [],
      totalSessionMs: 0,
      timeToFirstActionMs: null,
    });
    if (record.timeToFirstActionMs === null) {
      const now = Date.now();
      const started = new Date(sessionStartedAt).getTime();
      record.timeToFirstActionMs = Number.isFinite(started) ? now - started : null;
    }
    await AsyncStorage.setItem(key, JSON.stringify(record));
  } catch {
    // intentionally silent
  }
}

// ─── Funnel tracking ──────────────────────────────────────────────────────────

const FUNNEL_FALLBACK = (
  sessionId: string,
  playerId: string,
  gameDay: number,
): Day1FunnelState => ({
  sessionId,
  playerId,
  gameDay,
  sessionStartedAt: null,
  briefSeenAt: null,
  dashboardSeenAt: null,
  firstWorkActionAt: null,
  marketSeenAt: null,
  summarySeenAt: null,
  dayCompletedAt: null,
});

export type FunnelCheckpointKey = keyof Omit<
  Day1FunnelState,
  'sessionId' | 'playerId' | 'gameDay'
>;

/**
 * Mark a funnel checkpoint if not already set (first-touch only).
 */
export async function markFunnelCheckpoint(
  sessionId: string,
  playerId: string,
  gameDay: number,
  checkpoint: FunnelCheckpointKey,
): Promise<void> {
  try {
    const key = KEY_FUNNEL(playerId, gameDay);
    const raw = await AsyncStorage.getItem(key);
    const funnel = safeParseJson<Day1FunnelState>(
      raw,
      FUNNEL_FALLBACK(sessionId, playerId, gameDay),
    );
    if (!funnel[checkpoint]) {
      funnel[checkpoint] = nowIso();
      await AsyncStorage.setItem(key, JSON.stringify(funnel));
    }
  } catch {
    // intentionally silent
  }
}

export async function readFunnel(
  playerId: string,
  gameDay: number,
): Promise<Day1FunnelState | null> {
  try {
    const raw = await AsyncStorage.getItem(KEY_FUNNEL(playerId, gameDay));
    return safeParseJson<Day1FunnelState | null>(raw, null);
  } catch {
    return null;
  }
}

// ─── Balance telemetry ────────────────────────────────────────────────────────

export async function recordStartingStats(
  sessionId: string,
  playerId: string,
  gameDay: number,
  stats: {
    cash: number | null;
    stress: number | null;
    health: number | null;
    expensePressure: string | null;
    opportunityFlagsSurfaced: number;
  },
): Promise<void> {
  try {
    const key = KEY_BALANCE(playerId, gameDay);
    const raw = await AsyncStorage.getItem(key);
    const existing = safeParseJson<Day1BalanceTelemetry | null>(raw, null);
    // Only set starting stats if not already captured
    if (existing?.startingCash !== null && existing?.startingCash !== undefined) return;
    const record: Day1BalanceTelemetry = {
      sessionId,
      playerId,
      gameDay,
      startingCash: safeNumber(stats.cash),
      endingCash: null,
      cashDelta: null,
      startingStress: safeNumber(stats.stress),
      endingStress: null,
      stressDelta: null,
      startingHealth: safeNumber(stats.health),
      endingHealth: null,
      healthDelta: null,
      expensePressure: stats.expensePressure ?? null,
      incomeEarned: null,
      opportunityFlagsSurfaced: stats.opportunityFlagsSurfaced,
      endedPositive: null,
      capturedAt: nowIso(),
    };
    await AsyncStorage.setItem(key, JSON.stringify(record));
  } catch {
    // intentionally silent
  }
}

export async function recordEndingStats(
  sessionId: string,
  playerId: string,
  gameDay: number,
  stats: {
    cash: number | null;
    stress: number | null;
    health: number | null;
    incomeEarned: number | null;
    expensePressure: string | null;
  },
): Promise<void> {
  try {
    const key = KEY_BALANCE(playerId, gameDay);
    const raw = await AsyncStorage.getItem(key);
    const record = safeParseJson<Day1BalanceTelemetry | null>(raw, null);
    if (!record) return;

    const endingCash = safeNumber(stats.cash);
    const endingStress = safeNumber(stats.stress);
    const endingHealth = safeNumber(stats.health);

    record.endingCash = endingCash;
    record.endingStress = endingStress;
    record.endingHealth = endingHealth;
    record.incomeEarned = safeNumber(stats.incomeEarned);
    record.expensePressure = stats.expensePressure ?? record.expensePressure;
    record.cashDelta =
      record.startingCash !== null && endingCash !== null
        ? endingCash - record.startingCash
        : null;
    record.stressDelta =
      record.startingStress !== null && endingStress !== null
        ? endingStress - record.startingStress
        : null;
    record.healthDelta =
      record.startingHealth !== null && endingHealth !== null
        ? endingHealth - record.startingHealth
        : null;
    record.endedPositive =
      record.cashDelta !== null ? record.cashDelta >= 0 : null;
    record.capturedAt = nowIso();

    await AsyncStorage.setItem(key, JSON.stringify(record));
  } catch {
    // intentionally silent
  }
}

export async function readBalanceTelemetry(
  playerId: string,
  gameDay: number,
): Promise<Day1BalanceTelemetry | null> {
  try {
    const raw = await AsyncStorage.getItem(KEY_BALANCE(playerId, gameDay));
    return safeParseJson<Day1BalanceTelemetry | null>(raw, null);
  } catch {
    return null;
  }
}

// ─── Friction signals ─────────────────────────────────────────────────────────

const FRICTION_FALLBACK = (
  sessionId: string,
  playerId: string,
): FrictionSignals => ({
  sessionId,
  playerId,
  onboardingSkipped: false,
  noWorkActionTaken: true,
  noMarketVisit: true,
  noBusinessVisit: true,
  exitedBeforeSummary: true,
  longIdleCount: 0,
});

type FrictionBooleanKey = Exclude<
  keyof FrictionSignals,
  'sessionId' | 'playerId' | 'longIdleCount'
>;

export async function updateFrictionSignal(
  sessionId: string,
  playerId: string,
  signal: FrictionBooleanKey,
  value: boolean,
): Promise<void> {
  try {
    const key = KEY_FRICTION(sessionId);
    const raw = await AsyncStorage.getItem(key);
    const record = safeParseJson<FrictionSignals>(
      raw,
      FRICTION_FALLBACK(sessionId, playerId),
    );
    record[signal] = value;
    await AsyncStorage.setItem(key, JSON.stringify(record));
  } catch {
    // intentionally silent
  }
}

export async function incrementLongIdleCount(
  sessionId: string,
  playerId: string,
): Promise<void> {
  try {
    const key = KEY_FRICTION(sessionId);
    const raw = await AsyncStorage.getItem(key);
    const record = safeParseJson<FrictionSignals>(
      raw,
      FRICTION_FALLBACK(sessionId, playerId),
    );
    record.longIdleCount = (record.longIdleCount || 0) + 1;
    await AsyncStorage.setItem(key, JSON.stringify(record));
  } catch {
    // intentionally silent
  }
}

export async function readFrictionSignals(
  sessionId: string,
): Promise<FrictionSignals | null> {
  try {
    const raw = await AsyncStorage.getItem(KEY_FRICTION(sessionId));
    return safeParseJson<FrictionSignals | null>(raw, null);
  } catch {
    return null;
  }
}

// ─── Dev review report ────────────────────────────────────────────────────────

export interface PlaytestScreenTimeSummary {
  screen: string;
  count: number;
  averageMs: number;
  totalMs: number;
}

export interface PlaytestReport {
  playerId: string;
  generatedAt: string;
  totalEventCount: number;
  recentEvents: PlaytestEvent[];
  funnel: Day1FunnelState | null;
  funnelCompletionRate: FunnelCompletionRate;
  screenTimeSummary: PlaytestScreenTimeSummary[];
  balanceTelemetry: Day1BalanceTelemetry | null;
  frictionSignals: FrictionSignals | null;
  sessionCount: number;
}

export interface FunnelCompletionRate {
  sessionStarted: boolean;
  briefSeen: boolean;
  dashboardSeen: boolean;
  firstWorkAction: boolean;
  marketSeen: boolean;
  summarySeen: boolean;
  dayCompleted: boolean;
  completionLabel: string;
}

function buildFunnelCompletionRate(funnel: Day1FunnelState | null): FunnelCompletionRate {
  const sessionStarted = Boolean(funnel?.sessionStartedAt);
  const briefSeen = Boolean(funnel?.briefSeenAt);
  const dashboardSeen = Boolean(funnel?.dashboardSeenAt);
  const firstWorkAction = Boolean(funnel?.firstWorkActionAt);
  const marketSeen = Boolean(funnel?.marketSeenAt);
  const summarySeen = Boolean(funnel?.summarySeenAt);
  const dayCompleted = Boolean(funnel?.dayCompletedAt);

  const steps = [sessionStarted, briefSeen, dashboardSeen, firstWorkAction, marketSeen, summarySeen, dayCompleted];
  const completed = steps.filter(Boolean).length;
  const completionLabel = `${completed}/7 funnel steps reached`;

  return {
    sessionStarted,
    briefSeen,
    dashboardSeen,
    firstWorkAction,
    marketSeen,
    summarySeen,
    dayCompleted,
    completionLabel,
  };
}

function buildScreenTimeSummary(screenRecord: ScreenTimingRecord | null): PlaytestScreenTimeSummary[] {
  if (!screenRecord) return [];
  const map = new Map<string, { count: number; totalMs: number }>();
  for (const entry of screenRecord.screens) {
    const existing = map.get(entry.screen) ?? { count: 0, totalMs: 0 };
    map.set(entry.screen, {
      count: existing.count + 1,
      totalMs: existing.totalMs + entry.durationMs,
    });
  }
  return Array.from(map.entries()).map(([screen, data]) => ({
    screen,
    count: data.count,
    totalMs: data.totalMs,
    averageMs: data.count > 0 ? Math.round(data.totalMs / data.count) : 0,
  }));
}

/**
 * Build a full dev-facing playtest report for a given player + session.
 * Reads all local storage slices and aggregates.
 */
export async function buildPlaytestReport(
  playerId: string,
  sessionId: string,
  gameDay: number,
): Promise<PlaytestReport> {
  const [eventsRaw, sessionIndexRaw, screenTimingRaw, funnelRaw, balanceRaw, frictionRaw] =
    await Promise.all([
      AsyncStorage.getItem(KEY_EVENTS(playerId)).catch(() => null),
      AsyncStorage.getItem(KEY_SESSION_INDEX(playerId)).catch(() => null),
      AsyncStorage.getItem(KEY_SCREEN_TIMES(sessionId)).catch(() => null),
      AsyncStorage.getItem(KEY_FUNNEL(playerId, gameDay)).catch(() => null),
      AsyncStorage.getItem(KEY_BALANCE(playerId, gameDay)).catch(() => null),
      AsyncStorage.getItem(KEY_FRICTION(sessionId)).catch(() => null),
    ]);

  const allEvents = safeParseJson<PlaytestEvent[]>(eventsRaw, []);
  const sessionIndex = safeParseJson<SessionIndexEntry[]>(sessionIndexRaw, []);
  const screenRecord = safeParseJson<ScreenTimingRecord | null>(screenTimingRaw, null);
  const funnel = safeParseJson<Day1FunnelState | null>(funnelRaw, null);
  const balance = safeParseJson<Day1BalanceTelemetry | null>(balanceRaw, null);
  const friction = safeParseJson<FrictionSignals | null>(frictionRaw, null);

  const recentEvents = [...allEvents].reverse().slice(0, 30);

  return {
    playerId,
    generatedAt: nowIso(),
    totalEventCount: allEvents.length,
    recentEvents,
    funnel,
    funnelCompletionRate: buildFunnelCompletionRate(funnel),
    screenTimeSummary: buildScreenTimeSummary(screenRecord),
    balanceTelemetry: balance,
    frictionSignals: friction,
    sessionCount: sessionIndex.length,
  };
}

/**
 * Clear all playtest data for a player (for reset/debug purposes).
 */
export async function clearPlaytestData(playerId: string): Promise<void> {
  try {
    await AsyncStorage.removeItem(KEY_EVENTS(playerId));
    await AsyncStorage.removeItem(KEY_SESSION_INDEX(playerId));
  } catch {
    // intentionally silent
  }
}
