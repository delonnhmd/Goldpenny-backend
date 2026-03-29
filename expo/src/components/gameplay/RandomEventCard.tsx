import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

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
    borderColor: '#bbf7d0',
    backgroundColor: '#f0fdf4',
    badgeBackground: '#dcfce7',
    badgeColor: '#166534',
    effectColor: '#16a34a',
    label: 'Good Fortune',
  },
  negative_high: {
    borderColor: '#fecaca',
    backgroundColor: '#fef2f2',
    badgeBackground: '#fee2e2',
    badgeColor: '#b91c1c',
    effectColor: '#dc2626',
    label: 'High Impact',
  },
  negative_medium: {
    borderColor: '#fde68a',
    backgroundColor: '#fffbeb',
    badgeBackground: '#fef3c7',
    badgeColor: '#92400e',
    effectColor: '#d97706',
    label: 'Unexpected',
  },
  negative_low: {
    borderColor: '#e2e8f0',
    backgroundColor: '#f8fafc',
    badgeBackground: '#f1f5f9',
    badgeColor: '#475569',
    effectColor: '#64748b',
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
    color: '#0f172a',
    lineHeight: 22,
  },
  description: {
    fontSize: 14,
    color: '#334155',
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
    color: '#475569',
    fontWeight: '700',
  },
  actionsGrid: {
    gap: 6,
  },
  actionButton: {
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  actionButtonLabel: {
    fontSize: 14,
    fontWeight: '700',
    color: '#1e293b',
  },
  actionButtonEffect: {
    fontSize: 12,
    color: '#64748b',
    marginTop: 2,
  },
  dismissButton: {
    alignSelf: 'flex-end',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: '#cbd5e1',
  },
  dismissText: {
    fontSize: 13,
    color: '#64748b',
    fontWeight: '600',
  },
});
