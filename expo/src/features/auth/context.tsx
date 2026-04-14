import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import {
  createPlayerProfile as createPlayerProfileApi,
  getCurrentSessionState,
  loginAccount,
  registerAccount,
  requestPasswordReset as requestPasswordResetApi,
  submitPasswordReset,
} from '@/lib/api/auth';
import { recordInfo, recordWarning } from '@/lib/logger';
import { AuthSessionResponse, ForgotPasswordResponse } from '@/types/auth';

import {
  clearStoredAuthSession,
  persistAuthSession,
  readStoredAuthSession,
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

function isExpired(session: AuthSessionResponse): boolean {
  const expiresAt = Date.parse(String(session.expires_at || ''));
  if (!Number.isFinite(expiresAt)) return true;
  return expiresAt <= Date.now();
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [session, setSession] = useState<AuthSessionResponse | null>(null);

  const applyAuthenticatedSession = useCallback(async (nextSession: AuthSessionResponse) => {
    await persistAuthSession(nextSession);
    setSession(nextSession);
    setStatus('authenticated');
  }, []);

  const clearSession = useCallback(async () => {
    await clearStoredAuthSession();
    setSession(null);
    setStatus('unauthenticated');
  }, []);

  const refreshSession = useCallback(async () => {
    const current = await readStoredAuthSession();
    if (!current || !current.access_token || isExpired(current)) {
      await clearSession();
      return;
    }

    const state = await getCurrentSessionState();
    const merged: AuthSessionResponse = {
      ...current,
      account: state.account,
      player_profile: state.player_profile,
    };
    await applyAuthenticatedSession(merged);
  }, [applyAuthenticatedSession, clearSession]);

  useEffect(() => {
    let cancelled = false;

    async function hydrate() {
      try {
        const stored = await readStoredAuthSession();
        if (!stored || !stored.access_token || isExpired(stored)) {
          await clearStoredAuthSession();
          if (!cancelled) {
            setSession(null);
            setStatus('unauthenticated');
          }
          return;
        }

        const state = await getCurrentSessionState();
        const merged: AuthSessionResponse = {
          ...stored,
          account: state.account,
          player_profile: state.player_profile,
        };
        await persistAuthSession(merged);
        if (!cancelled) {
          setSession(merged);
          setStatus('authenticated');
        }
      recordInfo('auth', 'Session restored from persisted auth state.', {
        action: 'restore_session',
        context: {
          playerId: merged.player_profile?.id || null,
        },
      });
      } catch (error) {
        await clearStoredAuthSession();
        if (!cancelled) {
          setSession(null);
          setStatus('unauthenticated');
        }
        recordWarning('auth', 'Session restore failed; clearing stored auth state.', {
          action: 'restore_session_failed',
          error,
        });
      }
    }

    void hydrate();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (payload: { email: string; password: string }) => {
    const nextSession = await loginAccount(payload);
    await applyAuthenticatedSession(nextSession);
      recordInfo('auth', 'Account login completed.', {
      action: 'sign_in',
      context: {
        playerId: nextSession.player_profile?.id || null,
      },
    });
  }, [applyAuthenticatedSession]);

  const signUp = useCallback(async (payload: { email: string; password: string }) => {
    const nextSession = await registerAccount(payload);
    await applyAuthenticatedSession(nextSession);
      recordInfo('auth', 'Account registration completed.', {
      action: 'sign_up',
      context: {
        playerId: nextSession.player_profile?.id || null,
      },
    });
  }, [applyAuthenticatedSession]);

  const createPlayerProfile = useCallback(async (payload?: { display_name?: string }) => {
    const current = session;
    if (!current) {
      throw new Error('You must be signed in before creating a player profile.');
    }

    const state = await createPlayerProfileApi(payload);
    const nextSession: AuthSessionResponse = {
      ...current,
      account: state.account,
      player_profile: state.player_profile,
    };
    await applyAuthenticatedSession(nextSession);
    recordInfo('auth', 'Fresh player profile created for account.', {
      action: 'create_player_profile',
      context: {
        playerId: nextSession.player_profile?.id || null,
      },
    });
  }, [applyAuthenticatedSession, session]);

  const signOut = useCallback(async () => {
    const currentPlayerId = session?.player_profile?.id || null;
    await clearSession();
    recordInfo('auth', 'Account session cleared locally.', {
      action: 'sign_out',
      context: {
        playerId: currentPlayerId,
      },
    });
  }, [clearSession, session?.player_profile?.id]);

  const requestPasswordReset = useCallback(async (email: string) => (
    requestPasswordResetApi(email)
  ), []);

  const resetPassword = useCallback(async (token: string, password: string) => {
    await submitPasswordReset(token, password);
    recordInfo('auth', 'Password reset completed.', {
      action: 'reset_password',
    });
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
