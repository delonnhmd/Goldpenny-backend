// Gold Penny — Soft Launch: useSoftLaunch hook
// Manages cohort membership state with a 24-hour AsyncStorage cache so every
// app open does not require a network round-trip for non-members.

import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useEffect, useRef, useState } from 'react';

import { fetchSoftLaunchStatus, joinSoftLaunch, submitFeedback, submitIssue } from './api';
import { FeedbackPayload, IssuePayload, SoftLaunchStatus } from './types';

const CACHE_KEY = '@goldpenny/soft_launch_status';
const CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours
const SOFT_LAUNCH_REQUIRED =
  process.env.EXPO_PUBLIC_SOFT_LAUNCH_REQUIRED === 'true'
  || process.env.EXPO_PUBLIC_SOFT_LAUNCH_REQUIRED === '1';

interface CachedStatus {
  status: SoftLaunchStatus;
  cachedAt: number;
}

interface UseSoftLaunchReturn {
  isLoading: boolean;
  isMember: boolean;
  cohortTag: string | null;
  joinError: string | null;
  joinWithCode: (code: string) => Promise<boolean>;
  submitFeedback: (payload: FeedbackPayload) => Promise<boolean>;
  submitIssue: (payload: IssuePayload) => Promise<boolean>;
  refreshStatus: () => Promise<void>;
}

export function useSoftLaunch(): UseSoftLaunchReturn {
  const [isLoading, setIsLoading] = useState(true);
  const [status, setStatus] = useState<SoftLaunchStatus | null>(null);
  const [joinError, setJoinError] = useState<string | null>(null);
  const loadedRef = useRef(false);

  const loadStatus = useCallback(async (forceRefresh = false) => {
    if (!SOFT_LAUNCH_REQUIRED) {
      setStatus({
        is_member: true,
        cohort_tag: 'open_access',
        joined_at: new Date().toISOString(),
      });
      setJoinError(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    try {
      if (!forceRefresh) {
        const raw = await AsyncStorage.getItem(CACHE_KEY);
        if (raw) {
          const cached: CachedStatus = JSON.parse(raw);
          if (Date.now() - cached.cachedAt < CACHE_TTL_MS) {
            setStatus(cached.status);
            setIsLoading(false);
            return;
          }
        }
      }
      const fresh = await fetchSoftLaunchStatus();
      setStatus(fresh);
      const toCache: CachedStatus = { status: fresh, cachedAt: Date.now() };
      await AsyncStorage.setItem(CACHE_KEY, JSON.stringify(toCache));
    } catch {
      // If the check fails, treat as non-member so the gate isn't accidentally bypassed.
      setStatus({ is_member: false, cohort_tag: null, joined_at: null });
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    loadStatus();
  }, [loadStatus]);

  const joinWithCode = useCallback(
    async (code: string): Promise<boolean> => {
      if (!SOFT_LAUNCH_REQUIRED) {
        setJoinError(null);
        return true;
      }

      setJoinError(null);
      try {
        const result = await joinSoftLaunch(code);
        const newStatus: SoftLaunchStatus = {
          is_member: result.is_approved,
          cohort_tag: result.cohort_tag,
          joined_at: new Date().toISOString(),
        };
        setStatus(newStatus);
        const toCache: CachedStatus = { status: newStatus, cachedAt: Date.now() };
        await AsyncStorage.setItem(CACHE_KEY, JSON.stringify(toCache));
        return true;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to join.';
        setJoinError(msg);
        return false;
      }
    },
    [],
  );

  const handleSubmitFeedback = useCallback(async (payload: FeedbackPayload): Promise<boolean> => {
    if (!SOFT_LAUNCH_REQUIRED) {
      return true;
    }

    try {
      await submitFeedback(payload);
      return true;
    } catch {
      return false;
    }
  }, []);

  const handleSubmitIssue = useCallback(async (payload: IssuePayload): Promise<boolean> => {
    if (!SOFT_LAUNCH_REQUIRED) {
      return true;
    }

    try {
      await submitIssue(payload);
      return true;
    } catch {
      return false;
    }
  }, []);

  const refreshStatus = useCallback(() => loadStatus(true), [loadStatus]);

  return {
    isLoading,
    isMember: status?.is_member ?? false,
    cohortTag: status?.cohort_tag ?? null,
    joinError,
    joinWithCode,
    submitFeedback: handleSubmitFeedback,
    submitIssue: handleSubmitIssue,
    refreshStatus,
  };
}
