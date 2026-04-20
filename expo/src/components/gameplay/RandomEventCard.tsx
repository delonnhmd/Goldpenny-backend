import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { theme } from '@/design/theme';

import { ActiveRandomEvent, RecoveryActionDefinition } from '@/types/randomEvent';

interface RandomEventCardProps {
  event: ActiveRandomEvent;
  availableRecoveryActions: RecoveryActionDefinition[];
  onApplyRecoveryAction: (action: RecoveryActionDefinition) => void;
  onDismiss: () => void;
}

type EventTone = 'positive' | 'negative_high' | 'negative_medium' | 'negative_low';

function deriveTone(event: ActiveRandomEvent): EventTone {
  const isPositive = event.cashDelta > 0 || event.debtDelta < 0;
  if (isPositive) return 'positive';
  if (event.severity === 'high') return 'negative_high';
  if (event.severity === 'medium') return 'negative_medium';
  return 'negative_low';
}

const TONE_STYLES: Record<
  EventTone,
  {
    borderColor: string;
    backgroundColor: string;
    badgeBackground: string;
    badgeColor: string;
    effectColor: string;
    label: string;
  }
> = {
  positive: {
    borderColor: theme.ui.positive,
    backgroundColor: theme.ui.bg.sheet,
    badgeBackground: theme.ui.bg.sheet,
    badgeColor: theme.ui.positive,
    effectColor: theme.ui.positive,
    label: 'Good Fortune',
  },
  negative_high: {
    borderColor: theme.ui.danger,
    backgroundColor: theme.ui.bg.sheet,
    badgeBackground: theme.ui.bg.sheet,
    badgeColor: theme.ui.danger,
    effectColor: theme.ui.danger,
    label: 'High Impact',
  },
  negative_medium: {
    borderColor: theme.ui.warning,
    backgroundColor: theme.ui.bg.sheet,
    badgeBackground: theme.ui.bg.sheet,
    badgeColor: theme.ui.warning,
    effectColor: theme.ui.warning,
    label: 'Unexpected',
  },
  negative_low: {
    borderColor: theme.ui.border,
    backgroundColor: theme.ui.bg.sheet,
    badgeBackground: theme.ui.bg.sheet,
    badgeColor: theme.ui.text.onLightMuted,
    effectColor: theme.ui.text.onLightMuted,
    label: 'Minor Event',
  },
};

export default function RandomEventCard({
  event,
  availableRecoveryActions,
  onApplyRecoveryAction,
  onDismiss,
}: RandomEventCardProps) {
  const tone = deriveTone(event);
  const ts = TONE_STYLES[tone];
  // Cap at 3 recovery actions to avoid overwhelming the card.
  const visibleActions = availableRecoveryActions.slice(0, 3);

  return (
    <View
      style={[
        styles.card,
        { borderColor: ts.borderColor, backgroundColor: ts.backgroundColor },
      ]}
    >
      <View style={styles.header}>
        <View style={[styles.badge, { backgroundColor: ts.badgeBackground }]}>
          <Text style={[styles.badgeText, { color: ts.badgeColor }]}>
            {ts.label}
          </Text>
        </View>
        <Text style={styles.title}>{event.title}</Text>
      </View>

      <Text style={styles.description}>{event.description}</Text>

      <Text style={[styles.effectSummary, { color: ts.effectColor }]}>
        Effect: {event.effectSummary}
      </Text>

      {visibleActions.length > 0 ? (
        <View style={styles.actionsSection}>
          <Text style={styles.actionsLabel}>Recovery Options</Text>
          <View style={styles.actionsGrid}>
            {visibleActions.map((action) => (
              <TouchableOpacity
                key={action.recoveryActionId}
                style={styles.actionButton}
                onPress={() => onApplyRecoveryAction(action)}
                activeOpacity={0.75}
              >
                <Text style={styles.actionButtonLabel}>{action.label}</Text>
                <Text style={styles.actionButtonEffect}>{action.effectSummary}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      ) : null}

      <TouchableOpacity
        style={styles.dismissButton}
        onPress={onDismiss}
        activeOpacity={0.7}
      >
        <Text style={styles.dismissText}>Dismiss</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderRadius: 12,
    padding: 14,
    gap: 10,
  },
  header: {
    gap: 6,
  },
  badge: {
    alignSelf: 'flex-start',
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  badgeText: {
    fontSize: 10,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  title: {
    fontSize: 17,
    fontWeight: '800',
    color: theme.ui.text.onLight,
    lineHeight: 22,
  },
  description: {
    fontSize: 14,
    color: theme.ui.text.onLightMuted,
    lineHeight: 20,
  },
  effectSummary: {
    fontSize: 13,
    fontWeight: '700',
  },
  actionsSection: {
    gap: 8,
  },
  actionsLabel: {
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    color: theme.ui.text.onLightMuted,
    fontWeight: '700',
  },
  actionsGrid: {
    gap: 6,
  },
  actionButton: {
    backgroundColor: theme.ui.bg.sheet,
    borderWidth: 1,
    borderColor: theme.ui.text.onLightMuted,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  actionButtonLabel: {
    fontSize: 14,
    fontWeight: '700',
    color: theme.ui.text.onLight,
  },
  actionButtonEffect: {
    fontSize: 12,
    color: theme.ui.text.onLightMuted,
    marginTop: 2,
  },
  dismissButton: {
    alignSelf: 'flex-end',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: theme.ui.text.onLightMuted,
  },
  dismissText: {
    fontSize: 13,
    color: theme.ui.text.onLightMuted,
    fontWeight: '600',
  },
});
