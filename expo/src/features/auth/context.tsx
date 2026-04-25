import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import * as Linking from 'expo-linking';

import { createPlayerByUserId, getPlayerByUserId, LinkedPlayer } from '@/lib/api/auth';
import { recordInfo, recordWarning } from '@/lib/logger';
import { supabase } from '@/lib/supabase';
import { AuthSessionResponse, CreatePlayerProfilePayload, ForgotPasswordResponse } from '@/types/auth';

import {
  clearStoredAuthSession,
  persistAuthSession,
} from './storage';

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';

const DUPLICATE_ACCOUNT_MESSAGE = 'That email already has a Gold Penny account. Log in instead to restore your existing player.';
const LINKED_PLAYER_MESSAGE = 'This account already has a linked player profile. Log in and your saved game will load.';
const PROFILE_SERVER_MESSAGE = 'Could not reach the player-profile server. Check the backend connection, then try again.';

interface AuthContextValue {
  status: AuthStatus;
  isAuthenticated: boolean;
  session: AuthSessionResponse | null;
  hasPlayerProfile: boolean;
  signIn: (payload: { email: string; password: string }) => Promise<void>;
  signUp: (payload: { email: string; password: string }) => Promise<void>;
  createPlayerProfile: (payload?: CreatePlayerProfilePayload) => Promise<void>;
  signOut: () => Promise<void>;
  refreshSession: () => Promise<void>;
  requestPasswordReset: (email: string) => Promise<ForgotPasswordResponse>;
  resetPassword: (token: string, password: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function normalizeError(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return String(error || 'Something went wrong.');
}

function isDuplicateAccountMessage(message: string): boolean {
  const normalized = message.toLowerCase();
  return normalized.includes('user already registered')
    || normalized.includes('already registered')
    || normalized.includes('email already exists')
    || normalized.includes('email_already_exists')
    || normalized.includes('already has a gold penny account');
}

function isLinkedPlayerMessage(message: string): boolean {
  const normalized = message.toLowerCase();
  return normalized.includes('already has a linked player profile')
    || normalized.includes('already has a player profile')
    || normalized.includes('selected user already has a player profile');
}

function isNetworkFailureMessage(message: string): boolean {
  const normalized = message.toLowerCase();
  return normalized === 'failed to fetch'
    || normalized.includes('failed to fetch')
    || normalized.includes('network request failed')
    || normalized.includes('load failed');
}

function friendlyProfileError(error: unknown): Error {
  const message = normalizeError(error);
  if (isLinkedPlayerMessage(message)) return new Error(LINKED_PLAYER_MESSAGE);
  if (isNetworkFailureMessage(message)) return new Error(PROFILE_SERVER_MESSAGE);
  return error instanceof Error ? error : new Error(message);
}

function buildLegacySession(
  accessToken: string,
  expiresAtIso: string,
  email: string,
  userId: string,
  player: LinkedPlayer | null,
  createdAtIso: string,
): AuthSessionResponse {
  return {
    access_token: accessToken,
    token_type: 'bearer',
    expires_at: expiresAtIso,
    account: {
      id: userId,
      email,
      auth_provider: 'supabase',
      status: 'active',
      created_at: createdAtIso,
      last_login_at: new Date().toISOString(),
      password_updated_at: null,
    },
    player_profile: player
      ? {
          id: player.id,
          display_name: player.display_name,
          gender: null,
          region: player.region,
          cash_xgp: player.cash_xgp,
          debt_xgp: player.debt_xgp,
          health: player.health,
          stress: player.stress,
          current_job: player.main_job,
          created_at: player.created_at,
          load_ready: true,
        }
      : null,
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [session, setSession] = useState<AuthSessionResponse | null>(null);
  const lastUserIdRef = useRef<string | null>(null);

  const applyFromSupabase = useCallback(async () => {
    const { data, error } = await supabase.auth.getSession();
    if (error || !data?.session?.user) {
      lastUserIdRef.current = null;
      await clearStoredAuthSession();
      setSession(null);
      setStatus('unauthenticated');
      return;
    }

    const sb = data.session;
    const user = sb.user;
    let player: LinkedPlayer | null = null;
    try {
      player = await getPlayerByUserId(user.id);
    } catch (err) {
      // Backend may be unreachable or the new player_id migration may not
      // have been applied yet. Keep the Supabase session active so the
      // user is not bounced back to the login screen — they can retry from
      // create-player or via refreshSession().
      recordWarning('auth', 'Linked player load failed; staying signed in without a player.', {
        action: 'load_linked_player_failed',
        error: err,
      });
      console.warn('[auth] /player/by-user-id lookup failed:', err);
    }

    const expiresAtIso = sb.expires_at
      ? new Date(sb.expires_at * 1000).toISOString()
      : new Date(Date.now() + 60 * 60 * 1000).toISOString();
    const createdAtIso = user.created_at || new Date().toISOString();

    const next = buildLegacySession(
      sb.access_token,
      expiresAtIso,
      user.email || '',
      user.id,
      player,
      createdAtIso,
    );
    lastUserIdRef.current = user.id;
    await persistAuthSession(next);
    setSession(next);
    setStatus('authenticated');
  }, []);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        await applyFromSupabase();
      } catch (error) {
        if (cancelled) return;
        recordWarning('auth', 'Initial Supabase session restore failed.', {
          action: 'restore_session_failed',
          error,
        });
        await clearStoredAuthSession();
        setSession(null);
        setStatus('unauthenticated');
      }
    })();

    const sub = supabase.auth.onAuthStateChange((_event, _sb) => {
      void applyFromSupabase();
    });

    return () => {
      cancelled = true;
      sub.data.subscription.unsubscribe();
    };
  }, [applyFromSupabase]);

  const signIn = useCallback(async ({ email, password }: { email: string; password: string }) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw new Error(error.message);
    await applyFromSupabase();
    recordInfo('auth', 'Supabase login completed.', { action: 'sign_in' });
  }, [applyFromSupabase]);

  const signUp = useCallback(async ({ email, password }: { email: string; password: string }) => {
    const { data, error } = await supabase.auth.signUp({ email, password });
    if (error) {
      throw new Error(isDuplicateAccountMessage(error.message) ? DUPLICATE_ACCOUNT_MESSAGE : error.message);
    }
    const identities = data.user?.identities;
    if (data.user && Array.isArray(identities) && identities.length === 0) {
      await supabase.auth.signOut();
      throw new Error(DUPLICATE_ACCOUNT_MESSAGE);
    }
    if (!data.session) {
      // Email confirmation is required by the project. Surface a clear
      // message so the user knows to check their inbox before signing in.
      throw new Error('Account created — check your email to confirm before signing in.');
    }
    await applyFromSupabase();
    recordInfo('auth', 'Supabase sign-up completed.', { action: 'sign_up' });
  }, [applyFromSupabase]);

  const createPlayerProfile = useCallback(async (payload?: CreatePlayerProfilePayload) => {
    const { data } = await supabase.auth.getSession();
    if (!data?.session?.user?.id) {
      throw new Error('You must be signed in before creating a player profile.');
    }
    try {
      const existing = await getPlayerByUserId(data.session.user.id);
      if (existing) {
        await applyFromSupabase();
        return;
      }
    } catch (error) {
      throw friendlyProfileError(error);
    }
    try {
      await createPlayerByUserId(data.session.user.id, payload);
    } catch (error) {
      throw friendlyProfileError(error);
    }
    await applyFromSupabase();
  }, [applyFromSupabase]);

  const signOut = useCallback(async () => {
    const currentPlayerId = session?.player_profile?.id || null;
    await supabase.auth.signOut();
    lastUserIdRef.current = null;
    await clearStoredAuthSession();
    setSession(null);
    setStatus('unauthenticated');
    recordInfo('auth', 'Supabase session cleared.', {
      action: 'sign_out',
      context: { playerId: currentPlayerId },
    });
  }, [session?.player_profile?.id]);

  const refreshSession = useCallback(async () => {
    await applyFromSupabase();
  }, [applyFromSupabase]);

  const requestPasswordReset = useCallback(async (email: string): Promise<ForgotPasswordResponse> => {
    const redirectTo = Linking.createURL('/auth/reset-password');
    const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo });
    if (error) throw new Error(error.message);
    return {
      message: 'If that email exists, a password reset link is on the way.',
      reset_token: null,
      reset_url: null,
      expires_at: null,
    };
  }, []);

  const resetPassword = useCallback(async (_token: string, password: string) => {
    // Supabase exchanges the recovery link's tokens for a session via the
    // detected URL. With the active recovery session present, updating the
    // password completes the reset.
    const { error } = await supabase.auth.updateUser({ password });
    if (error) throw new Error(error.message);
    recordInfo('auth', 'Password reset completed.', { action: 'reset_password' });
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    status,
    isAuthenticated: status === 'authenticated' && Boolean(session?.access_token),
    session,
    hasPlayerProfile: Boolean(session?.player_profile?.id),
    signIn,
    signUp,
    createPlayerProfile,
    signOut,
    refreshSession,
    requestPasswordReset,
    resetPassword,
  }), [
    createPlayerProfile,
    refreshSession,
    requestPasswordReset,
    resetPassword,
    session,
    signIn,
    signOut,
    signUp,
    status,
  ]);

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider.');
  }
  return context;
}

export function getAuthErrorMessage(error: unknown): string {
  const message = normalizeError(error);
  if (isDuplicateAccountMessage(message)) return DUPLICATE_ACCOUNT_MESSAGE;
  if (isLinkedPlayerMessage(message)) return LINKED_PLAYER_MESSAGE;
  if (isNetworkFailureMessage(message)) return PROFILE_SERVER_MESSAGE;
  const colonIndex = message.indexOf(':');
  return colonIndex > -1 ? message.slice(colonIndex + 1).trim() : message;
}
