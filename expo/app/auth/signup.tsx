import React, { useState } from 'react';
import { Redirect, router } from 'expo-router';
import { Text } from 'react-native';

import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { getAuthErrorMessage, useAuth } from '@/features/auth';
import { AuthField, AuthShell, authScreenStyles } from '@/features/auth/AuthShell';

export default function SignupScreen() {
  const auth = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (auth.status === 'authenticated' && auth.session?.player_profile.id) {
    return <Redirect href="/gameplay" />;
  }

  const handleSignup = async () => {
    setSubmitting(true);
    setError(null);

    if (password !== confirmPassword) {
      setError('Passwords must match before creating the account.');
      setSubmitting(false);
      return;
    }

    try {
      await auth.signUp({
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
      subtitle="Create an account"
      cardTitle="Sign Up"
      cardSummary="Each account maps to one linked player profile so session restore and gameplay state stay stable."
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
        placeholder="At least 8 characters"
        secureTextEntry
        editable={!submitting}
      />
      <AuthField
        label="Confirm Password"
        value={confirmPassword}
        onChangeText={setConfirmPassword}
        placeholder="Re-enter your password"
        secureTextEntry
        editable={!submitting}
      />

      <Text style={authScreenStyles.helperText}>New signups create one linked player profile and starter gameplay state exactly once.</Text>
      {error ? <Text style={authScreenStyles.errorText}>{error}</Text> : null}

      <PrimaryButton
        label={submitting ? 'Creating Account...' : 'Create Account'}
        onPress={submitting ? undefined : handleSignup}
        loading={submitting}
        disabled={submitting}
        style={authScreenStyles.fullWidthButton}
      />
      <SecondaryButton
        label="Back To Login"
        onPress={submitting ? undefined : () => router.replace('/auth/login')}
        disabled={submitting}
        style={authScreenStyles.fullWidthButton}
      />
    </AuthShell>
  );
}
