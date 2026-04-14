import AsyncStorage from '@react-native-async-storage/async-storage';

import { AuthSessionResponse } from '@/types/auth';

export const KEY_AUTH_SESSION = 'goldpenny:auth:session';
export const KEY_AUTH_ACCESS_TOKEN = 'goldpenny:auth:accessToken';
export const KEY_LAST_PLAYER_ID = 'goldpenny:gameplay:lastPlayerId';

export async function readStoredAuthSession(): Promise<AuthSessionResponse | null> {
  try {
    const raw = await AsyncStorage.getItem(KEY_AUTH_SESSION);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AuthSessionResponse;
    if (!parsed?.access_token) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export async function persistAuthSession(session: AuthSessionResponse): Promise<void> {
  await AsyncStorage.multiSet([
    [KEY_AUTH_SESSION, JSON.stringify(session)],
    [KEY_AUTH_ACCESS_TOKEN, session.access_token],
  ]);

  if (session.player_profile?.id) {
    await AsyncStorage.setItem(KEY_LAST_PLAYER_ID, session.player_profile.id);
    return;
  }

  await AsyncStorage.removeItem(KEY_LAST_PLAYER_ID);
}

export async function clearStoredAuthSession(): Promise<void> {
  await AsyncStorage.multiRemove([
    KEY_AUTH_SESSION,
    KEY_AUTH_ACCESS_TOKEN,
    KEY_LAST_PLAYER_ID,
  ]);
}
