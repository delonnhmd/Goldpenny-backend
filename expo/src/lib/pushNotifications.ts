import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import { Platform } from 'react-native';

import {
  registerPushToken,
  RegisterPushTokenResponse,
} from '@/lib/api/notifications';
import { canLoadExpoNotifications, isExpoGo } from '@/lib/expoNotificationsAvailability';
import { recordInfo, recordWarning } from '@/lib/logger';


export const KEY_EXPO_PUSH_TOKEN = 'goldpenny:notifications:expoPushToken';

// Expo Go (SDK 53+) does not ship the native push token module. Load
// `expo-notifications` lazily so a missing native module does not break
// import-time evaluation of this file (which would cascade into route load
// failures for any screen that imports it).
type NotificationsModule = typeof import('expo-notifications');

function loadNotifications(): NotificationsModule | null {
  if (Platform.OS === 'web' || !canLoadExpoNotifications('pushNotifications')) {
    return null;
  }
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('expo-notifications') as NotificationsModule;
  } catch (error) {
    recordWarning('pushNotifications', 'expo-notifications native module unavailable (likely Expo Go).', {
      action: 'load_native_module',
      error,
    });
    return null;
  }
}

export interface PushRegistrationSyncResult {
  ok: boolean;
  pushToken: string | null;
  backend?: RegisterPushTokenResponse;
  message?: string;
}

function getEasProjectId(): string | undefined {
  const extraProjectId = Constants.expoConfig?.extra?.eas?.projectId;
  if (typeof extraProjectId === 'string' && extraProjectId.trim()) {
    return extraProjectId.trim();
  }
  const easProjectId = Constants.easConfig?.projectId;
  return typeof easProjectId === 'string' && easProjectId.trim() ? easProjectId.trim() : undefined;
}

export async function registerForPushNotificationsAsync(): Promise<string | null> {
  if (Platform.OS === 'web') {
    recordWarning('pushNotifications', 'Push notifications are not supported on web.', {
      action: 'register_push_token',
    });
    return null;
  }

  if (isExpoGo()) {
    recordWarning('pushNotifications', 'Push tokens are not available in Expo Go; use a development build.', {
      action: 'register_push_token',
    });
    return null;
  }

  const Notifications = loadNotifications();
  if (!Notifications) {
    return null;
  }

  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('default', {
      name: 'Default',
      importance: Notifications.AndroidImportance.DEFAULT,
    });
  }

  const permissions = await Notifications.getPermissionsAsync();
  let finalStatus = permissions.status;
  if (finalStatus !== 'granted') {
    const requested = await Notifications.requestPermissionsAsync();
    finalStatus = requested.status;
  }

  if (finalStatus !== 'granted') {
    recordInfo('pushNotifications', 'Push notification permission denied.', {
      action: 'register_push_token',
    });
    return null;
  }

  try {
    const projectId = getEasProjectId();
    const tokenResponse = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined,
    );
    const pushToken = tokenResponse.data;
    await AsyncStorage.setItem(KEY_EXPO_PUSH_TOKEN, pushToken);
    return pushToken;
  } catch (error) {
    recordWarning('pushNotifications', 'Failed to get Expo push token.', {
      action: 'register_push_token',
      error,
    });
    return null;
  }
}

export async function registerAndSyncPushTokenAsync(playerId: string): Promise<PushRegistrationSyncResult> {
  const normalizedPlayerId = playerId.trim();
  if (!normalizedPlayerId) {
    return {
      ok: false,
      pushToken: null,
      message: 'Player ID is required before registering push notifications.',
    };
  }

  const pushToken = await registerForPushNotificationsAsync();
  if (!pushToken) {
    return {
      ok: false,
      pushToken: null,
      message: 'Push notification permission was denied or the device cannot create an Expo push token.',
    };
  }

  const platform = Platform.OS === 'ios' || Platform.OS === 'android' ? Platform.OS : 'unknown';
  const backend = await registerPushToken({
    player_id: normalizedPlayerId,
    push_token: pushToken,
    platform,
  });

  return {
    ok: true,
    pushToken,
    backend,
  };
}
