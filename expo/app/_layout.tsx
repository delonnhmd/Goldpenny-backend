// goldpenny/expo/app/_layout.tsx
import 'react-native-get-random-values';
import 'react-native-url-polyfill/auto';
import React, { useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import { Stack } from 'expo-router';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import DiagnosticsErrorBoundary from '@/components/ui/DiagnosticsErrorBoundary';
import { BACKEND } from '@/constants';
import { AuthProvider, useAuth } from '@/features/auth';
import { recordInfo, recordWarning } from '@/lib/logger';
import { registerPushDeepLinkHandlers } from '@/lib/pushDeepLinks';

function PushDeepLinkBridge() {
  const auth = useAuth();
  const playerIdRef = useRef<string | null>(null);
  playerIdRef.current = String(auth.session?.player_profile?.id || '').trim() || null;

  useEffect(() => {
    if (Platform.OS === 'web') {
      return;
    }
    const cleanup = registerPushDeepLinkHandlers(() => playerIdRef.current);
    return cleanup;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}

export default function Layout() {
  useEffect(() => {
    recordInfo('app.startup', 'Root layout mounted.', {
      action: 'mount',
      context: {
        hasBackend: Boolean(BACKEND),
      },
    });

    if (!BACKEND) {
      recordWarning('app.startup', 'Public runtime configuration is incomplete.', {
        action: 'config_check',
        context: {
          hasBackend: Boolean(BACKEND),
        },
      });
    }
  }, []);

  return (
    <DiagnosticsErrorBoundary>
      <GestureHandlerRootView style={{ flex: 1 }}>
        <AuthProvider>
          <PushDeepLinkBridge />
          <Stack screenOptions={{ headerShown: false }} />
        </AuthProvider>
      </GestureHandlerRootView>
    </DiagnosticsErrorBoundary>
  );
}
