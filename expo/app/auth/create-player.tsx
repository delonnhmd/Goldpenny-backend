import React, { useMemo, useState } from 'react';
import { Redirect, router } from 'expo-router';
import { Text, View } from 'react-native';

import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { getAuthErrorMessage, useAuth } from '@/features/auth';
import { AuthShell, authScreenStyles } from '@/features/auth/AuthShell';

function suggestedDisplayName(email: string | null | undefined): string {
  const localPart = String(email || '').split('@', 1)[0] || '';
  const normalized = localPart.replace(/[._-]+/g, ' ').trim();
  return normalized || 'Gold Penny Player';
}

export default function CreatePlayerScreen() {
  const auth = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const displayName = useMemo(
    () => suggestedDisplayName(auth.session?.account.email),
    [auth.session?.account.email],
  );

  if (auth.status === 'loading') {
    return (
      <AuthShell
        title="Gold Penny"
        subtitle="Restoring your account"
        cardTitle="Loading"
        cardSummary="Checking whether this account already has a linked player profile."
      >
        <Text style={authScreenStyles.helperText}>One moment while we verify your fresh-start status.</Text>
      </AuthShell>
    );
  }

  if (!auth.isAuthenticated || !auth.session) {
    return <Redirect href="/auth/login" />;
  }

  if (auth.hasPlayerProfile) {
    return <Redirect href="/gameplay" />;
  }

  const handleCreatePlayer = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await auth.createPlayerProfile({ display_name: displayName });
      router.replace('/gameplay');
    } catch (nextError) {
      setError(getAuthErrorMessage(nextError));
    } finally {
      setSubmitting(false);
    }
  };

  const handleLogout = async () => {
    await auth.signOut();
    router.replace('/auth/login');
  };

  return (
    <AuthShell
      title="Gold Penny"
      subtitle="Start a fresh player"
      cardTitle="Create New Player"
      cardSummary="This account is signed in, but it does not have a linked gameplay profile yet."
    >
      <Text style={authScreenStyles.helperText}>
        Creating your player starts a clean Day 1 profile with starter cash, starter debt, baseline health and stress, and no old local test state.
      </Text>
      <View style={authScreenStyles.buttonRow}>
        <Text style={authScreenStyles.helperText}>Account: {auth.session.account.email}</Text>
        <Text style={authScreenStyles.helperText}>Player name: {displayName}</Text>
        <Text style={authScreenStyles.helperText}>Start state: Suburban region, no main job selected yet, onboarding ready.</Text>
      </View>
      {error ? <Text style={authScreenStyles.errorText}>{error}</Text> : null}

      <PrimaryButton
        label={submitting ? 'Creating Player...' : 'Create New Player'}
        onPress={submitting ? undefined : handleCreatePlayer}
        loading={submitting}
        disabled={submitting}
        style={authScreenStyles.fullWidthButton}
      />
      <SecondaryButton
        label="Log Out"
        onPress={submitting ? undefined : handleLogout}
        disabled={submitting}
        style={authScreenStyles.fullWidthButton}
      />
    </AuthShell>
  );
}
