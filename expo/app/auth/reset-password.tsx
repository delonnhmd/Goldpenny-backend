import React, { useMemo, useState } from 'react';
import { router, useLocalSearchParams } from 'expo-router';
import { Text } from 'react-native';

import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { getAuthErrorMessage, useAuth } from '@/features/auth';
import { AuthField, AuthShell, authScreenStyles } from '@/features/auth/AuthShell';

export default function ResetPasswordScreen() {
  const auth = useAuth();
  const params = useLocalSearchParams<{ token?: string }>();
  const tokenFromParams = useMemo(() => {
    const rawToken = Array.isArray(params.token) ? params.token[0] : params.token;
    return String(rawToken || '').trim();
  }, [params.token]);
  const [token, setToken] = useState(tokenFromParams);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleReset = async () => {
    setSubmitting(true);
    setError(null);
    setSuccess(null);

    if (!token.trim()) {
      setError('Enter the reset token before updating your password.');
      setSubmitting(false);
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords must match before saving the new password.');
      setSubmitting(false);
      return;
    }

    try {
      await auth.resetPassword(token.trim(), password);
      await auth.signOut();
      setSuccess('Password updated successfully. Log in with your new password.');
    } catch (nextError) {
      setError(getAuthErrorMessage(nextError));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="Gold Penny"
      subtitle="Set a new password"
      cardTitle="Reset Password"
      cardSummary="Use the reset token from the previous step to create a new password and then sign back in."
    >
      <AuthField
        label="Reset Token"
        value={token}
        onChangeText={setToken}
        placeholder="Paste your reset token"
        editable={!submitting}
      />
      <AuthField
        label="New Password"
        value={password}
        onChangeText={setPassword}
        placeholder="At least 8 characters"
        secureTextEntry
        editable={!submitting}
      />
      <AuthField
        label="Confirm New Password"
        value={confirmPassword}
        onChangeText={setConfirmPassword}
        placeholder="Re-enter your new password"
        secureTextEntry
        editable={!submitting}
      />

      {error ? <Text style={authScreenStyles.errorText}>{error}</Text> : null}
      {success ? <Text style={authScreenStyles.successText}>{success}</Text> : null}

      <PrimaryButton
        label={submitting ? 'Updating Password...' : 'Reset Password'}
        onPress={submitting ? undefined : handleReset}
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
