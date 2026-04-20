import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { theme } from '@/design/theme';

import { actionStatusColor, confidenceLabel } from '@/lib/gameplayFormatters';
import { BALANCE } from '@/lib/balanceConfig';
import { isTimedActivityActionKey } from '@/lib/realtimeActivity';
import { DailyActionItem } from '@/types/gameplay';
import { ActionExecutionGuard } from '@/hooks/useDailySession';

export default function ActionCard({
  action,
  onExecute,
  executionGuard,
}: {
  action: DailyActionItem;
  onExecute: (action: DailyActionItem) => void;
  executionGuard: ActionExecutionGuard;
}) {
  const statusColor = actionStatusColor(action.status);
  const disabled = !executionGuard.allowed;
  const priorityTone = action.status === 'recommended' ? styles.cardRecommended : null;
  const primaryWarning = action.warnings?.[0] || action.tradeoffs?.[0] || null;
  const metaSummary = confidenceLabel(action.confidence_level);
  const normalizedActionKey = String(action.action_key || '').trim().toLowerCase();
  const isTimedAction = isTimedActivityActionKey(normalizedActionKey);
  const timeCostLabel = isTimedAction
    ? `1u/${BALANCE.REALTIME.MINUTES_PER_UNIT}m`
    : `${Math.max(0, executionGuard.timeCostUnits)}u`;
  const buttonLabel = `Start (${timeCostLabel})`;

  return (
    <View style={[styles.card, priorityTone]}>
      <View style={styles.topRow}>
        <View style={styles.titleBlock}>
          <Text style={styles.title}>{action.title}</Text>
          <Text style={styles.reason} numberOfLines={2}>{metaSummary}</Text>
        </View>
        <View style={[styles.badge, { borderColor: statusColor, backgroundColor: `${statusColor}12` }]}>
          <Text style={[styles.badgeText, { color: statusColor }]}>{action.status}</Text>
        </View>
      </View>

      <Text style={styles.description} numberOfLines={3}>{action.description}</Text>
      {action.blocker_text ? <Text style={styles.blocker}>Blocked: {action.blocker_text}</Text> : null}
      {!action.blocker_text && !executionGuard.allowed && executionGuard.reason ? (
        <Text style={styles.blocker}>Blocked: {executionGuard.reason}</Text>
      ) : null}

      <View style={styles.metaRow}>
        <View style={styles.metaChip}>
          <Text style={styles.metaChipLabel}>Time</Text>
          <Text style={styles.metaChipValue}>{isTimedAction ? `${BALANCE.REALTIME.MINUTES_PER_UNIT} min per unit` : `${executionGuard.timeCostUnits} units`}</Text>
        </View>
        <View style={styles.metaChip}>
          <Text style={styles.metaChipLabel}>Read</Text>
          <Text style={styles.metaChipValue}>{confidenceLabel(action.confidence_level)}</Text>
        </View>
      </View>

      {primaryWarning ? (
        <View style={styles.calloutBox}>
          <Text style={styles.calloutLabel}>{action.warnings?.length ? 'Watch' : 'Tradeoff'}</Text>
          <Text style={styles.calloutText} numberOfLines={2}>{primaryWarning}</Text>
        </View>
      ) : null}

      <TouchableOpacity
        onPress={() => onExecute(action)}
        disabled={disabled}
        style={[styles.button, disabled ? styles.buttonDisabled : null]}
      >
        <Text style={styles.buttonText}>{buttonLabel}</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: 'rgba(148, 163, 184, 0.14)',
    borderRadius: theme.radius.xl,
    backgroundColor: '#0c1729',
    padding: theme.spacing.md,
    gap: theme.spacing.sm,
  },
  cardRecommended: {
    borderColor: 'rgba(34, 211, 238, 0.28)',
    backgroundColor: 'rgba(8, 47, 73, 0.34)',
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  titleBlock: {
    flex: 1,
    gap: theme.spacing.xxs,
  },
  title: {
    color: theme.color.textPrimary,
    ...theme.typography.headingSm,
    fontWeight: '800',
  },
  reason: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
  },
  badge: {
    borderWidth: 1,
    borderRadius: 999,
    paddingVertical: 4,
    paddingHorizontal: 9,
  },
  badgeText: {
    textTransform: 'uppercase',
    ...theme.typography.caption,
    fontWeight: '800',
  },
  description: {
    color: theme.color.textPrimary,
    ...theme.typography.bodySm,
  },
  blocker: {
    color: '#fca5a5',
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  metaRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    flexWrap: 'wrap',
  },
  metaChip: {
    borderRadius: theme.radius.md,
    backgroundColor: 'rgba(15, 23, 42, 0.92)',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
    gap: 2,
  },
  metaChipLabel: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
    textTransform: 'uppercase',
    fontWeight: '700',
  },
  metaChipValue: {
    color: theme.color.textPrimary,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  calloutBox: {
    borderWidth: 1,
    borderColor: 'rgba(251, 191, 36, 0.18)',
    borderRadius: theme.radius.lg,
    backgroundColor: 'rgba(120, 53, 15, 0.2)',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  calloutLabel: {
    color: '#fcd34d',
    ...theme.typography.caption,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
  calloutText: {
    color: theme.color.textPrimary,
    ...theme.typography.bodySm,
  },
  button: {
    marginTop: theme.spacing.xs,
    alignSelf: 'flex-start',
    minHeight: 46,
    borderRadius: theme.radius.lg,
    backgroundColor: '#0f3c52',
    borderWidth: 1,
    borderColor: '#22d3ee',
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    justifyContent: 'center',
    ...theme.shadow.sm,
  },
  buttonDisabled: {
    opacity: 0.45,
  },
  buttonText: {
    color: '#ffffff',
    ...theme.typography.label,
    fontWeight: '700',
    textAlign: 'center',
  },
});
