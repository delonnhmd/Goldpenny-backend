// goldpenny/expo/app/_layout.tsx
import 'react-native-get-random-values';
import 'react-native-url-polyfill/auto';
import React, { useEffect } from 'react';
import { Stack } from 'expo-router';
import DiagnosticsErrorBoundary from '@/components/ui/DiagnosticsErrorBoundary';
import { BACKEND } from '@/constants';
import { recordInfo, recordWarning } from '@/lib/logger';

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
      <Stack screenOptions={{ headerShown: false }} />
    </DiagnosticsErrorBoundary>
  );
}
