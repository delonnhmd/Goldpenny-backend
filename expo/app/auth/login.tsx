import React, { useState } from 'react';
import { Redirect, router } from 'expo-router';
import { Text } from 'react-native';

import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import TextButton from '@/components/ui/TextButton';
import { getAuthErrorMessage, useAuth } from '@/features/auth';
import { AuthField, AuthShell, authScreenStyles } from '@/features/auth/AuthShell';

export default function LoginScreen() {
  const auth = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (auth.status === 'authenticated' && auth.session?.player_profile.id) {
    return <Redirect href="/gameplay" />;
  }

  const handleLogin = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await auth.signIn({
        email: email.trim(),
        password,
      });
      router.replace('/gameplay');
    } catch (nextError) {
      setError(getAuthErrorMessage(nextError));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="Gold Penny"
      subtitle="Sign in to your account"
      cardTitle="Log In"
      cardSummary="Your account session restores your linked player profile and keeps gameplay separate from sign-in state."
    >
      <AuthField
        label="Email"
        value={email}
        onChangeText={setEmail}
        placeholder="you@example.com"
        keyboardType="email-address"
        editable={!submitting}
      />
      <AuthField
        label="Password"
        value={password}
        onChangeText={setPassword}
        placeholder="Enter your password"
        secureTextEntry
        editable={!submitting}
      />

      <Text style={authScreenStyles.helperText}>Sessions stay signed in across app restarts until you log out or reset your password.</Text>
      {error ? <Text style={authScreenStyles.errorText}>{error}</Text> : null}

      <PrimaryButton
        label={submitting ? 'Signing In...' : 'Log In'}
        onPress={submitting ? undefined : handleLogin}
        loading={submitting}
        disabled={submitting}
        style={authScreenStyles.fullWidthButton}
      />
      <SecondaryButton
        label="Create Account"
        onPress={submitting ? undefined : () => router.push('/auth/signup')}
        disabled={submitting}
        style={authScreenStyles.fullWidthButton}
      />
      <TextButton
        label="Forgot Password?"
        onPress={submitting ? undefined : () => router.push('/auth/forgot-password')}
        disabled={submitting}
      />
    </AuthShell>
  );
}
