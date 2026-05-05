import AsyncStorage from '@react-native-async-storage/async-storage';

import { recordInfo, recordWarning } from '@/lib/logger';
import { createDefaultTimedActivityState, sanitizeTimedActivityState, TimedActivityState } from '@/lib/realtimeActivity';
import { DailySessionStatus } from '@/types/gameplay';

// Core logic freeze: this snapshot shape and canonical key are part of gameplay continuity.
// Change only for a proven persistence bug and version the payload deliberately.
export const GAMEPLAY_PERSISTENCE_VERSION = 2;

const GAMEPLAY_STATE_STORAGE_KEY = (playerId: string) => `goldpenny:gameplay:state:${playerId}`;

const LEGACY_DAY_STORAGE_KEY = (playerId: string) => `goldpenny:gameplay:day:${playerId}`;
const LEGACY_LAST_PROCESSED_STORAGE_KEY = (playerId: string) => `goldpenny:gameplay:lastProcessedDay:${playerId}`;
const LEGACY_SESSION_STORAGE_KEY = (playerId: string) => `goldpenny:gameplay:session:${playerId}`;

export interface PersistedGameplaySessionState {
  currentDay: number;
  remainingTimeUnits: number;
  actionCounts: Record<string, number>;
  sessionStatus: DailySessionStatus;
  totalTimeUnits: number;
  timedActivity: TimedActivityState;
}

export interface PersistedGameplayState {
  version: typeof GAMEPLAY_PERSISTENCE_VERSION;
  playerId: string;
  currentDay: number;
  lastProcessedDay: number | null;
  session: PersistedGameplaySessionState | null;
}

type PersistedGameplayUpdater = (
  current: PersistedGameplayState | null,
) => PersistedGameplayState | null;

const writeQueue = new Map<string, Promise<void>>();

function parsePositiveInteger(value: unknown): number | null {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  const normalized = Math.round(parsed);
  return normalized >= 1 ? normalized : null;
}

function sanitizeSessionState(value: unknown, expectedDay: number): PersistedGameplaySessionState | null {
  if (!value || typeof value !== 'object') return null;

  const currentDay = parsePositiveInteger((value as { currentDay?: unknown }).currentDay);
  const remainingTimeUnits = Number((value as { remainingTimeUnits?: unknown }).remainingTimeUnits);
  const totalTimeUnits = Number((value as { totalTimeUnits?: unknown }).totalTimeUnits);
  const sessionStatus = (value as { sessionStatus?: unknown }).sessionStatus;
  const actionCounts = (value as { actionCounts?: unknown }).actionCounts;

  if (currentDay == null || currentDay !== expectedDay) return null;
  if (!Number.isFinite(remainingTimeUnits) || !Number.isFinite(totalTimeUnits)) return null;
  if (sessionStatus !== 'active' && sessionStatus !== 'ended') return null;
  if (!actionCounts || typeof actionCounts !== 'object' || Array.isArray(actionCounts)) return null;

  const normalizedCounts: Record<string, number> = {};
  for (const [key, rawValue] of Object.entries(actionCounts as Record<string, unknown>)) {
    const normalizedKey = String(key || '').trim().toLowerCase();
    const parsedCount = Number(rawValue);
    if (!normalizedKey || !Number.isFinite(parsedCount)) continue;
    normalizedCounts[normalizedKey] = Math.max(0, Math.min(99, Math.round(parsedCount)));
  }

  return {
    currentDay,
    remainingTimeUnits: Math.max(0, Math.round(remainingTimeUnits * 100) / 100),
    totalTimeUnits: Math.max(0, Math.round(totalTimeUnits * 100) / 100),
    sessionStatus,
    actionCounts: normalizedCounts,
    timedActivity: sanitizeTimedActivityState((value as { timedActivity?: unknown }).timedActivity),
  };
}

function sanitizeGameplayState(value: unknown, playerId: string): PersistedGameplayState | null {
  if (!value || typeof value !== 'object') return null;

  const version = Number((value as { version?: unknown }).version);
  const storedPlayerId = String((value as { playerId?: unknown }).playerId || '').trim();
  const currentDay = parsePositiveInteger((value as { currentDay?: unknown }).currentDay);

  if (version !== 1 && version !== GAMEPLAY_PERSISTENCE_VERSION) return null;
  if (!storedPlayerId || storedPlayerId !== playerId || currentDay == null) return null;

  const parsedLastProcessed = (value as { lastProcessedDay?: unknown }).lastProcessedDay;
  const lastProcessedDay =
    parsedLastProcessed == null
      ? null
      : Math.min(currentDay, parsePositiveInteger(parsedLastProcessed) || currentDay);

  return {
    version: GAMEPLAY_PERSISTENCE_VERSION,
    playerId,
    currentDay,
    lastProcessedDay,
    session: sanitizeSessionState((value as { session?: unknown }).session, currentDay),
  };
}

function parseLegacySessionState(raw: string | null, currentDay: number): PersistedGameplaySessionState | null {
  if (!raw) return null;
  try {
    return sanitizeSessionState(JSON.parse(raw), currentDay);
  } catch {
    return null;
  }
}

function createLegacySnapshot(
  playerId: string,
  values: {
    currentDayRaw: string | null;
    lastProcessedRaw: string | null;
    sessionRaw: string | null;
  },
): PersistedGameplayState | null {
  const legacyDay = parsePositiveInteger(values.currentDayRaw);
  const legacyLastProcessed = parsePositiveInteger(values.lastProcessedRaw);
  const session = parseLegacySessionState(values.sessionRaw, legacyDay || 1);
  const currentDay = legacyDay || session?.currentDay || 1;

  if (!values.currentDayRaw && !values.lastProcessedRaw && !values.sessionRaw) {
    return null;
  }

  return {
    version: GAMEPLAY_PERSISTENCE_VERSION,
    playerId,
    currentDay,
    lastProcessedDay: legacyLastProcessed == null ? null : Math.min(currentDay, legacyLastProcessed),
    session: session && session.currentDay === currentDay ? session : null,
  };
}

export function createEmptyPersistedGameplayState(
  playerId: string,
  currentDay = 1,
): PersistedGameplayState {
  return {
    version: GAMEPLAY_PERSISTENCE_VERSION,
    playerId,
    currentDay: Math.max(1, Math.round(Number(currentDay) || 1)),
    lastProcessedDay: null,
    session: {
      currentDay: Math.max(1, Math.round(Number(currentDay) || 1)),
      remainingTimeUnits: 20,
      actionCounts: {},
      sessionStatus: 'active',
      totalTimeUnits: 20,
      timedActivity: createDefaultTimedActivityState(),
    },
  };
}

async function loadLegacyGameplayState(playerId: string): Promise<PersistedGameplayState | null> {
  const [currentDayRaw, lastProcessedRaw, sessionRaw] = await Promise.all([
    AsyncStorage.getItem(LEGACY_DAY_STORAGE_KEY(playerId)),
    AsyncStorage.getItem(LEGACY_LAST_PROCESSED_STORAGE_KEY(playerId)),
    AsyncStorage.getItem(LEGACY_SESSION_STORAGE_KEY(playerId)),
  ]);

  const migrated = createLegacySnapshot(playerId, {
    currentDayRaw,
    lastProcessedRaw,
    sessionRaw,
  });

  if (!migrated) return null;

  await AsyncStorage.setItem(GAMEPLAY_STATE_STORAGE_KEY(playerId), JSON.stringify(migrated));
  recordInfo('gameplayPersistence', 'Migrated legacy gameplay persistence into canonical snapshot.', {
    action: 'migrate_legacy_snapshot',
    context: {
      currentDay: migrated.currentDay,
      hasSession: Boolean(migrated.session),
    },
  });
  return migrated;
}

export async function readPersistedGameplayState(playerId: string): Promise<PersistedGameplayState | null> {
  if (!playerId) return null;

  const key = GAMEPLAY_STATE_STORAGE_KEY(playerId);
  try {
    const raw = await AsyncStorage.getItem(key);
    if (raw) {
      try {
        const parsed = sanitizeGameplayState(JSON.parse(raw), playerId);
        if (parsed) return parsed;
      } catch (error) {
        recordWarning('gameplayPersistence', 'Canonical gameplay snapshot could not be parsed.', {
          action: 'read_snapshot',
          context: {
            hasPlayerId: Boolean(playerId),
          },
          error,
        });
      }

      recordWarning('gameplayPersistence', 'Canonical gameplay snapshot was invalid and will be reset.', {
        action: 'read_snapshot',
        context: {
          hasPlayerId: Boolean(playerId),
        },
      });
      await AsyncStorage.removeItem(key);
    }

    return await loadLegacyGameplayState(playerId);
  } catch (error) {
    recordWarning('gameplayPersistence', 'Failed to hydrate canonical gameplay snapshot.', {
      action: 'read_snapshot',
      context: {
        hasPlayerId: Boolean(playerId),
      },
      error,
    });
    return null;
  }
}

async function enqueueWrite<T>(key: string, task: () => Promise<T>): Promise<T> {
  const previous = writeQueue.get(key) || Promise.resolve();
  const next = previous.catch(() => undefined).then(task);
  writeQueue.set(key, next.then(() => undefined, () => undefined));
  return next;
}

export async function updatePersistedGameplayState(
  playerId: string,
  updater: PersistedGameplayUpdater,
): Promise<PersistedGameplayState | null> {
  if (!playerId) return null;

  const key = GAMEPLAY_STATE_STORAGE_KEY(playerId);
  return enqueueWrite(key, async () => {
    const current = await readPersistedGameplayState(playerId);
    const next = updater(current);
    if (!next) {
      await AsyncStorage.removeItem(key);
      return null;
    }

    const sanitized = sanitizeGameplayState(next, playerId);
    if (!sanitized) {
      throw new Error('Gameplay snapshot update produced an invalid state.');
    }

    await AsyncStorage.setItem(key, JSON.stringify(sanitized));
    return sanitized;
  });
}
