import React from 'react';
import { Redirect } from 'expo-router';
import { Text } from 'react-native';

import { useAuth } from '@/features/auth';
import { AuthShell, authScreenStyles } from '@/features/auth/AuthShell';

export default function RootIndexRoute() {
  const auth = useAuth();

  if (auth.status === 'loading') {
    return (
      <AuthShell
        title="Gold Penny"
        subtitle="Restoring your account session"
        cardTitle="Loading account"
        cardSummary="Checking your saved session and linked player profile."
      >
        <Text style={authScreenStyles.helperText}>One moment while we reconnect you to your saved game.</Text>
      </AuthShell>
    );
  }

  return <Redirect href={auth.isAuthenticated ? '/gameplay' : '/auth/login'} />;
}
