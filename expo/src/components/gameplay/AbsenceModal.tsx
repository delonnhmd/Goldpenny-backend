import React, { useMemo } from 'react';
import { Modal, ScrollView, StyleSheet, Text, View } from 'react-native';

import TextButton from '@/components/ui/TextButton';
import { alpha, theme } from '@/design/theme';
import type { AbsenceSummary } from '@/types/gameplay';

export interface AbsenceModalProps {
  visible: boolean;
  summary: AbsenceSummary | null;
  onContinue: () => void;
}

function formatSigned(n: number, suffix = ''): string {
  if (n === 0) return `0${suffix}`;
  return `${n > 0 ? '+' : ''}${n}${suffix}`;
}

function formatCash(n: number): string {
  const abs = Math.abs(n).toFixed(2);
  if (n === 0) return '0 XGP';
  return `${n > 0 ? '+' : '-'}${abs} XGP`;
}

export default function AbsenceModal({ visible, summary, onContinue }: AbsenceModalProps) {
  const safeSummary = summary ?? null;
  const missed = safeSummary?.missed_days ?? 0;

  const rows = useMemo(() => {
    if (!safeSummary) return [];
    return [
      { label: 'Health', value: formatSigned(safeSummary.health_change) },
      { label: 'Stress', value: formatSigned(safeSummary.stress_change) },
      { label: 'Cash', value: formatCash(safeSummary.cash_change) },
      {
        label: 'Business spoilage',
        value: safeSummary.inventory_spoilage > 0
          ? `-${safeSummary.inventory_spoilage.toFixed(2)} units`
          : 'None',
      },
    ];
  }, [safeSummary]);

  if (!visible || !safeSummary || missed <= 0) {
    return null;
  }

  return (
    <Modal
      transparent
      visible={visible}
      animationType="fade"
      onRequestClose={onContinue}
      accessibilityViewIsModal
    >
      <View style={styles.backdrop}>
        <View style={styles.card} accessibilityRole="alert">
          <Text style={styles.eyebrow}>Welcome back</Text>
          <Text style={styles.title}>You were away for {missed} day{missed === 1 ? '' : 's'}</Text>

          <View style={styles.rows}>
            {rows.map((row) => (
              <View key={row.label} style={styles.row}>
                <Text style={styles.rowLabel}>{row.label}</Text>
                <Text style={styles.rowValue}>{row.value}</Text>
              </View>
            ))}
          </View>

          {safeSummary.warnings.length > 0 && (
            <ScrollView style={styles.warningsBox} contentContainerStyle={styles.warningsContent}>
              {safeSummary.warnings.map((w, idx) => (
                <Text key={`${idx}-${w}`} style={styles.warning}>
                  • {w}
                </Text>
              ))}
            </ScrollView>
          )}

          <TextButton
            label="Continue"
            onPress={onContinue}
          />
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: alpha(theme.ui.bg.app, 0.72),
    alignItems: 'center',
    justifyContent: 'center',
    padding: theme.spacing.lg,
  },
  card: {
    width: '100%',
    maxWidth: 420,
    backgroundColor: theme.ui.bg.sheet,
    borderRadius: theme.radius.lg,
    padding: theme.spacing.lg,
    gap: theme.spacing.md,
  },
  eyebrow: {
    ...theme.typography.caption,
    letterSpacing: 0,
    textTransform: 'uppercase',
    color: theme.ui.text.onLightMuted,
  },
  title: {
    ...theme.typography.headingMd,
    fontWeight: '700',
    color: theme.ui.text.onLight,
  },
  rows: {
    gap: theme.spacing.sm,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  rowLabel: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onLightMuted,
  },
  rowValue: {
    ...theme.typography.bodySm,
    fontWeight: '600',
    color: theme.ui.text.onLight,
  },
  warningsBox: {
    maxHeight: 160,
    backgroundColor: alpha(theme.ui.bg.cardRaised, 0.12),
    borderRadius: theme.radius.md,
    padding: theme.spacing.md,
  },
  warningsContent: {
    gap: theme.spacing.xs,
  },
  warning: {
    ...theme.typography.bodySm,
    lineHeight: 18,
    color: theme.ui.text.onLight,
  },
});
