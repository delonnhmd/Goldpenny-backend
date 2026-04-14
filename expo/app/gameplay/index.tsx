import React from 'react';
import { Redirect } from 'expo-router';
import { Text } from 'react-native';

import { useAuth } from '@/features/auth';
import { AuthShell, authScreenStyles } from '@/features/auth/AuthShell';

export default function GameplayEntryRoute() {
  const auth = useAuth();

  if (auth.status === 'loading') {
    return (
      <AuthShell
        title="Gold Penny"
        subtitle="Restoring your game"
        cardTitle="Loading gameplay"
        cardSummary="Checking the signed-in account and linked player profile."
      >
        <Text style={authScreenStyles.helperText}>One moment while we reconnect your account to the correct player.</Text>
      </AuthShell>
    );
  }

  if (!auth.isAuthenticated || !auth.session) {
    return <Redirect href="/auth/login" />;
  }

  if (!auth.session.player_profile?.id) {
    return <Redirect href="/auth/create-player" />;
  }

  return <Redirect href={`/gameplay/loop/${auth.session.player_profile.id}/brief`} />;
}
