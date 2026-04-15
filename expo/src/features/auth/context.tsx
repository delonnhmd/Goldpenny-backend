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

import { getOrCreatePlayerByUserId, LinkedPlayer } from '@/lib/api/auth';
import { recordInfo, recordWarning } from '@/lib/logger';
import { supabase } from '@/lib/supabase';
import { AuthSessionResponse, ForgotPasswordResponse } from '@/types/auth';

import {
  clearStoredAuthSession,
  persistAuthSession,
} from './storage';

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';

interface AuthContextValue {
  status: AuthStatus;
  isAuthenticated: boolean;
  session: AuthSessionResponse | null;
  hasPlayerProfile: boolean;
  signIn: (payload: { email: string; password: string }) => Promise<void>;
  signUp: (payload: { email: string; password: string }) => Promise<void>;
  createPlayerProfile: (payload?: { display_name?: string }) => Promise<void>;
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
      player = await getOrCreatePlayerByUserId(user.id);
    } catch (err) {
      recordWarning('auth', 'Linked player load failed; signing out.', {
        action: 'load_linked_player_failed',
        error: err,
      });
      await supabase.auth.signOut();
      lastUserIdRef.current = null;
      await clearStoredAuthSession();
      setSession(null);
      setStatus('unauthenticated');
      return;
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
    if (error) throw new Error(error.message);
    if (!data.session) {
      // Email confirmation is required by the project. Surface a clear
      // message so the user knows to check their inbox before signing in.
      throw new Error('Account created — check your email to confirm before signing in.');
    }
    await applyFromSupabase();
    recordInfo('auth', 'Supabase sign-up completed.', { action: 'sign_up' });
  }, [applyFromSupabase]);

  const createPlayerProfile = useCallback(async (_payload?: { display_name?: string }) => {
    // The backend creates the linked player automatically on first
    // /player/by-user-id/{user_id} call. Re-syncing the session is enough.
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
  return normalizeError(error);
}
