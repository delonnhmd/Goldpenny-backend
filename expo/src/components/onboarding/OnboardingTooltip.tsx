import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { theme } from '@/design/theme';

export default function OnboardingTooltip({
  progressLabel,
  title,
  message,
  statusMessage,
  blockedMessage,
  continueLabel,
  onContinue,
  onSkip,
  continueDisabled,
  continueLoading,
  skipLoading,
}: {
  progressLabel: string;
  title: string;
  message: string;
  statusMessage?: string | null;
  blockedMessage?: string | null;
  continueLabel?: string | null;
  onContinue?: () => void;
  onSkip?: () => void;
  continueDisabled?: boolean;
  continueLoading?: boolean;
  skipLoading?: boolean;
}) {
  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.kicker}>Day 1 Guide</Text>
        <Text style={styles.progress}>{progressLabel}</Text>
      </View>

      <Text style={styles.title}>{title}</Text>
      <Text style={styles.message}>{message}</Text>

      {statusMessage ? <Text style={styles.status}>{statusMessage}</Text> : null}
      {blockedMessage ? <Text style={styles.blocked}>{blockedMessage}</Text> : null}

      <View style={styles.actionRow}>
        {continueLabel ? (
          <PrimaryButton
            label={continueLabel}
            onPress={onContinue}
            disabled={continueDisabled}
            loading={continueLoading}
            style={styles.primaryButton}
          />
        ) : null}
        <SecondaryButton
          label="Skip"
          onPress={onSkip}
          loading={skipLoading}
          disabled={skipLoading}
          style={styles.secondaryButton}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: theme.ui.info,
    borderRadius: theme.radius.xl,
    backgroundColor: theme.ui.bg.sheet,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  kicker: {
    ...theme.typography.caption,
    color: theme.ui.action,
    textTransform: 'uppercase',
    fontWeight: '800',
    letterSpacing: 0.7,
  },
  progress: {
    ...theme.typography.caption,
    color: theme.ui.action,
    fontWeight: '800',
  },
  title: {
    ...theme.typography.headingSm,
    color: theme.ui.text.onLight,
    fontWeight: '800',
  },
  message: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onLightMuted,
    fontWeight: '600',
  },
  status: {
    ...theme.typography.bodySm,
    color: theme.ui.action,
    fontWeight: '700',
  },
  blocked: {
    ...theme.typography.bodySm,
    color: theme.ui.danger,
    fontWeight: '700',
  },
  actionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.xs,
  },
  primaryButton: {
    flex: 1,
    minWidth: 146,
  },
  secondaryButton: {
    minWidth: 96,
  },
});