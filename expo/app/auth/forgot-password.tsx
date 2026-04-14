import React, { useState } from 'react';
import { router } from 'expo-router';
import { Text } from 'react-native';

import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { getAuthErrorMessage, useAuth } from '@/features/auth';
import { AuthField, AuthShell, authScreenStyles } from '@/features/auth/AuthShell';
import { ForgotPasswordResponse } from '@/types/auth';

export default function ForgotPasswordScreen() {
  const auth = useAuth();
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ForgotPasswordResponse | null>(null);

  const handleRequestReset = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const nextResult = await auth.requestPasswordReset(email.trim());
      setResult(nextResult);
    } catch (nextError) {
      setError(getAuthErrorMessage(nextError));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="Gold Penny"
      subtitle="Recover your password"
      cardTitle="Forgot Password"
      cardSummary="Request a reset link for your account. Until email delivery is wired in, the app surfaces the reset token directly so you can complete the flow."
    >
      <AuthField
        label="Email"
        value={email}
        onChangeText={setEmail}
        placeholder="you@example.com"
        keyboardType="email-address"
        editable={!submitting}
      />

      <Text style={authScreenStyles.helperText}>Resetting your password signs out existing sessions because auth identity stays separate from gameplay state.</Text>
      {error ? <Text style={authScreenStyles.errorText}>{error}</Text> : null}
      {result?.message ? <Text style={authScreenStyles.successText}>{result.message}</Text> : null}
      {result?.reset_url ? <Text style={authScreenStyles.helperText}>Reset link: {result.reset_url}</Text> : null}

      <PrimaryButton
        label={submitting ? 'Preparing Reset Link...' : 'Send Reset Link'}
        onPress={submitting ? undefined : handleRequestReset}
        loading={submitting}
        disabled={submitting}
        style={authScreenStyles.fullWidthButton}
      />

      {result?.reset_token ? (
        <SecondaryButton
          label="Continue To Reset Password"
          onPress={() => router.push(`/auth/reset-password?token=${encodeURIComponent(result.reset_token || '')}`)}
          style={authScreenStyles.fullWidthButton}
        />
      ) : null}

      <SecondaryButton
        label="Back To Login"
        onPress={submitting ? undefined : () => router.replace('/auth/login')}
        disabled={submitting}
        style={authScreenStyles.fullWidthButton}
      />
    </AuthShell>
  );
}
