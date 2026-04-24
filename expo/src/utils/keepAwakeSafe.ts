import {
  activateKeepAwakeAsync,
  deactivateKeepAwake,
  isAvailableAsync,
} from 'expo-keep-awake';

function logKeepAwakeWarning(message: string, error: unknown) {
  if (!__DEV__) return;
  console.warn(`[keep-awake] ${message}`, error);
}

export async function safeActivateKeepAwake(tag?: string): Promise<boolean> {
  try {
    if (typeof isAvailableAsync === 'function' && !(await isAvailableAsync())) {
      return false;
    }
    if (typeof activateKeepAwakeAsync === 'function') {
      await activateKeepAwakeAsync(tag);
      return true;
    }
    return false;
  } catch (error) {
    logKeepAwakeWarning('failed to activate', error);
    return false;
  }
}

export async function safeDeactivateKeepAwake(tag?: string): Promise<boolean> {
  try {
    if (typeof deactivateKeepAwake === 'function') {
      await deactivateKeepAwake(tag);
      return true;
    }
    return false;
  } catch (error) {
    logKeepAwakeWarning('failed to deactivate', error);
    return false;
  }
}
