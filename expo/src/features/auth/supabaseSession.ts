/**
 * Supabase auth → linked-player session bridge (Step 95E).
 *
 * Flow:
 *   - login/register via supabase.auth
 *   - getCurrentSupabaseUserId()
 *   - getOrCreatePlayerByUserId(userId) on the backend
 *   - persist player_id locally for fast restore (always re-confirmed by backend)
 *   - logout clears all local state and signs out of Supabase
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { getOrCreatePlayerByUserId, LinkedPlayer } from '@/lib/api/auth';
import { getCurrentSupabaseUserId, signOutSupabase, supabase } from '@/lib/supabase';

import { KEY_LAST_PLAYER_ID } from './storage';

const KEY_SUPABASE_USER_ID = 'goldpenny:auth:supabaseUserId';

export interface LinkedSession {
  userId: string;
  player: LinkedPlayer;
}

export async function loadLinkedSessionFromSupabase(): Promise<LinkedSession | null> {
  const userId = await getCurrentSupabaseUserId();
  if (!userId) return null;
  const player = await getOrCreatePlayerByUserId(userId);
  await AsyncStorage.multiSet([
    [KEY_SUPABASE_USER_ID, userId],
    [KEY_LAST_PLAYER_ID, player.id],
  ]);
  return { userId, player };
}

export async function signInWithPassword(email: string, password: string): Promise<LinkedSession> {
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw new Error(error.message);
  const session = await loadLinkedSessionFromSupabase();
  if (!session) throw new Error('Login succeeded but no Supabase user was returned.');
  return session;
}

export async function signUpWithPassword(email: string, password: string): Promise<LinkedSession> {
  const { error } = await supabase.auth.signUp({ email, password });
  if (error) throw new Error(error.message);
  const session = await loadLinkedSessionFromSupabase();
  if (!session) throw new Error('Sign-up succeeded but no Supabase user was returned.');
  return session;
}

export async function clearLinkedSessionLocal(): Promise<void> {
  await AsyncStorage.multiRemove([KEY_SUPABASE_USER_ID, KEY_LAST_PLAYER_ID]);
}

export async function signOutLinkedSession(): Promise<void> {
  await clearLinkedSessionLocal();
  await signOutSupabase();
}
