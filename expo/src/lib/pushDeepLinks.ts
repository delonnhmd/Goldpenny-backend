/**
 * Phase 3-C Push Scheduling: deep link handling for daily-loop pushes.
 *
 * Push payloads carry `{ screen, type }` in `data`. We translate the
 * `screen` value into an in-app gameplay-loop route. If the player id
 * is not yet known (e.g. cold launch before auth resolves) we fall back
 * to the main gameplay screen, which then routes the user into their
 * loop after auth bootstraps.
 */

import * as Notifications from 'expo-notifications';
import { router } from 'expo-router';

import { recordInfo, recordWarning } from '@/lib/logger';

export type PushDeepLinkScreen = 'Life' | 'Summary' | string;

export interface PushDeepLinkPayload {
  screen?: PushDeepLinkScreen;
  type?: string;
}

const FALLBACK_ROUTE = '/gameplay';

function routeForScreen(screen: PushDeepLinkScreen | undefined, playerId: string | null): string {
  if (!playerId) {
    return FALLBACK_ROUTE;
  }
  switch (screen) {
    case 'Life':
      return `/gameplay/loop/${playerId}/life`;
    case 'Summary':
      return `/gameplay/loop/${playerId}/summary`;
    default:
      return FALLBACK_ROUTE;
  }
}

export function navigateForPushPayload(
  payload: PushDeepLinkPayload | null | undefined,
  playerId: string | null,
): void {
  const screen = payload?.screen;
  const target = routeForScreen(screen, playerId);
  try {
    router.push(target as never);
    recordInfo('pushDeepLinks', 'Navigated for push payload.', {
      action: 'deep_link_navigate',
      context: { screen, type: payload?.type, target, hasPlayerId: Boolean(playerId) },
    });
  } catch (error) {
    recordWarning('pushDeepLinks', 'Push deep link navigation failed; using fallback.', {
      action: 'deep_link_navigate_failed',
      context: { screen, target, error: String(error) },
    });
    try {
      router.push(FALLBACK_ROUTE as never);
    } catch (fallbackError) {
      recordWarning('pushDeepLinks', 'Fallback navigation also failed.', {
        action: 'deep_link_fallback_failed',
        context: { error: String(fallbackError) },
      });
    }
  }
}

function extractPayload(
  response: Notifications.NotificationResponse | null | undefined,
): PushDeepLinkPayload | null {
  const data = response?.notification?.request?.content?.data;
  if (!data || typeof data !== 'object') {
    return null;
  }
  const screen = (data as Record<string, unknown>).screen;
  const type = (data as Record<string, unknown>).type;
  return {
    screen: typeof screen === 'string' ? screen : undefined,
    type: typeof type === 'string' ? type : undefined,
  };
}

export function registerPushDeepLinkHandlers(getPlayerId: () => string | null): () => void {
  Notifications.getLastNotificationResponseAsync()
    .then((response) => {
      const payload = extractPayload(response);
      if (payload) {
        navigateForPushPayload(payload, getPlayerId());
      }
    })
    .catch((error) => {
      recordWarning('pushDeepLinks', 'Failed to read last notification response.', {
        action: 'deep_link_bootstrap_failed',
        context: { error: String(error) },
      });
    });

  const subscription = Notifications.addNotificationResponseReceivedListener((response) => {
    const payload = extractPayload(response);
    navigateForPushPayload(payload, getPlayerId());
  });

  return () => {
    try {
      subscription.remove();
    } catch (error) {
      recordWarning('pushDeepLinks', 'Failed to remove push response listener.', {
        action: 'deep_link_unsubscribe_failed',
        context: { error: String(error) },
      });
    }
  };
}
