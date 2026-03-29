import AsyncStorage from '@react-native-async-storage/async-storage';

import { recordWarning } from '@/lib/logger';

const ONBOARDING_PERSISTENCE_VERSION = 1;

function onboardingStorageKey(playerId: string): string {
  return `goldpenny:onboarding:state:${playerId}`;
}

export type PersistedOnboardingStatus = 'in_progress' | 'completed' | 'skipped';

export interface PersistedOnboardingState {
  version: typeof ONBOARDING_PERSISTENCE_VERSION;
  playerId: string;
  status: PersistedOnboardingStatus;
  stepIndex: number;
  updatedAt: string;
}

function sanitizePersistedOnboardingState(
  value: unknown,
  playerId: string,
): PersistedOnboardingState | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const row = value as Record<string, unknown>;

  const version = Number(row.version);
  const storedPlayerId = String(row.playerId || '').trim();
  const status = String(row.status || '').trim();
  const stepIndex = Number(row.stepIndex);
  const updatedAt = String(row.updatedAt || '').trim();

  if (version !== ONBOARDING_PERSISTENCE_VERSION) return null;
  if (!storedPlayerId || storedPlayerId !== playerId) return null;
  if (status !== 'in_progress' && status !== 'completed' && status !== 'skipped') return null;
  if (!Number.isFinite(stepIndex) || stepIndex < 0) return null;

  return {
    version: ONBOARDING_PERSISTENCE_VERSION,
    playerId,
    status,
    stepIndex: Math.floor(stepIndex),
    updatedAt: updatedAt || new Date().toISOString(),
  };
}

export async function readPersistedOnboardingState(
  playerId: string,
): Promise<PersistedOnboardingState | null> {
  if (!playerId) return null;

  const storageKey = onboardingStorageKey(playerId);

  try {
    const raw = await AsyncStorage.getItem(storageKey);
    if (!raw) return null;

    const parsed = sanitizePersistedOnboardingState(JSON.parse(raw), playerId);
    if (parsed) return parsed;

    await AsyncStorage.removeItem(storageKey);
    return null;
  } catch (error) {
    recordWarning('onboardingPersistence', 'Failed to read persisted onboarding state.', {
      action: 'read_onboarding_state',
      context: {
        playerId,
      },
      error,
    });
    return null;
  }
}

export async function writePersistedOnboardingState(
  playerId: string,
  payload: {
    status: PersistedOnboardingStatus;
    stepIndex: number;
  },
): Promise<void> {
  if (!playerId) return;

  const storageKey = onboardingStorageKey(playerId);
  const nextState: PersistedOnboardingState = {
    version: ONBOARDING_PERSISTENCE_VERSION,
    playerId,
    status: payload.status,
    stepIndex: Math.max(0, Math.floor(Number(payload.stepIndex) || 0)),
    updatedAt: new Date().toISOString(),
  };

  try {
    await AsyncStorage.setItem(storageKey, JSON.stringify(nextState));
  } catch (error) {
    recordWarning('onboardingPersistence', 'Failed to write persisted onboarding state.', {
      action: 'write_onboarding_state',
      context: {
        playerId,
        status: payload.status,
      },
      error,
    });
  }
}