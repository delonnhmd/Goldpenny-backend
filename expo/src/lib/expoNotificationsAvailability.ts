import Constants, { ExecutionEnvironment } from 'expo-constants';
import { requireOptionalNativeModule } from 'expo-modules-core';
import { Platform } from 'react-native';

import { recordWarning } from '@/lib/logger';

const REQUIRED_EXPO_NOTIFICATIONS_MODULES = [
  'ExpoBackgroundNotificationTasksModule',
  'ExpoBadgeModule',
  'ExpoNotificationCategoriesModule',
  'ExpoNotificationChannelGroupManager',
  'ExpoNotificationChannelManager',
  'ExpoNotificationPermissionsModule',
  'ExpoNotificationPresenter',
  'ExpoNotificationScheduler',
  'ExpoNotificationsEmitter',
  'ExpoNotificationsHandlerModule',
  'ExpoPushTokenManager',
  'NotificationsServerRegistrationModule',
];

let missingNativeModules: string[] | null = null;
const warningSources = new Set<string>();

export function isExpoGo(): boolean {
  return (
    Constants.executionEnvironment === ExecutionEnvironment.StoreClient ||
    Constants.appOwnership === 'expo'
  );
}

function getMissingNativeModules(): string[] {
  if (missingNativeModules) {
    return missingNativeModules;
  }
  missingNativeModules = REQUIRED_EXPO_NOTIFICATIONS_MODULES.filter((moduleName) => {
    try {
      return !requireOptionalNativeModule(moduleName);
    } catch {
      return true;
    }
  });
  return missingNativeModules;
}

export function canLoadExpoNotifications(source: string): boolean {
  if (Platform.OS === 'web' || isExpoGo()) {
    return false;
  }

  const missing = getMissingNativeModules();
  if (missing.length === 0) {
    return true;
  }

  if (!warningSources.has(source)) {
    warningSources.add(source);
    recordWarning(source, 'expo-notifications native modules are unavailable; push features disabled for this build.', {
      action: 'check_native_modules',
      context: {
        missingNativeModules: missing,
      },
    });
  }
  return false;
}
