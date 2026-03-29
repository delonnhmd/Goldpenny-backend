// Gold Penny — Soft Launch: SoftLaunchGate
// Shown when a user is not yet a soft launch member.  They enter an invite
// code or, in dev builds with EXPO_PUBLIC_SOFT_LAUNCH_BYPASS=true, the gate
// is skipped automatically by the parent (see useSoftLaunch).

import React, { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';

import { theme } from '@/design/theme';

interface Props {
  onJoin: (code: string) => Promise<boolean>;
  error: string | null;
  isLoading?: boolean;
}

export function SoftLaunchGate({ onJoin, error, isLoading = false }: Props) {
  const [code, setCode] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    const trimmed = code.trim();
    if (!trimmed) return;
    setSubmitting(true);
    await onJoin(trimmed);
    setSubmitting(false);
  }

  const busy = submitting || isLoading;

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.card}>
        <Text style={styles.heading}>Early Access</Text>
        <Text style={styles.body}>
          Gold Penny is in a limited soft launch. Enter your invite code to continue.
        </Text>

        <TextInput
          style={styles.input}
          placeholder="Invite code"
          placeholderTextColor={theme.color.muted}
          autoCapitalize="none"
          autoCorrect={false}
          value={code}
          onChangeText={setCode}
          editable={!busy}
          onSubmitEditing={handleSubmit}
          returnKeyType="go"
        />

        {error ? <Text style={styles.errorText}>{error}</Text> : null}

        <TouchableOpacity
          style={[styles.button, busy && styles.buttonDisabled]}
          onPress={handleSubmit}
          disabled={busy}
          activeOpacity={0.75}
        >
          {busy ? (
            <ActivityIndicator color="#ffffff" size="small" />
          ) : (
            <Text style={styles.buttonLabel}>Join</Text>
          )}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.color.background,
    alignItems: 'center',
    justifyContent: 'center',
    padding: theme.spacing.xl,
  },
  card: {
    width: '100%',
    maxWidth: 380,
    backgroundColor: theme.color.surface,
    borderRadius: theme.radius.lg,
    padding: theme.spacing.xxl,
    ...theme.shadow.md,
  },
  heading: {
    ...theme.typography.headingLg,
    color: theme.color.textPrimary,
    marginBottom: theme.spacing.sm,
  },
  body: {
    ...theme.typography.bodyMd,
    color: theme.color.textSecondary,
    marginBottom: theme.spacing.xl,
  },
  input: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.md,
    ...theme.typography.bodyMd,
    color: theme.color.textPrimary,
    marginBottom: theme.spacing.sm,
  },
  errorText: {
    ...theme.typography.bodySm,
    color: theme.color.danger,
    marginBottom: theme.spacing.sm,
  },
  button: {
    backgroundColor: theme.color.accent,
    borderRadius: theme.radius.md,
    paddingVertical: theme.spacing.md,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: theme.spacing.sm,
    minHeight: 44,
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonLabel: {
    ...theme.typography.headingSm,
    color: '#ffffff',
  },
});
