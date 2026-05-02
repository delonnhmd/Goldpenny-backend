import React, { useMemo } from 'react';
import { Modal, ScrollView, StyleSheet, Text, View } from 'react-native';

import TextButton from '@/components/ui/TextButton';
import { theme } from '@/design/theme';
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
            accessibilityLabel="Dismiss absence summary and continue"
          />
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.72)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
  },
  card: {
    width: '100%',
    maxWidth: 420,
    backgroundColor: theme.colors?.surface ?? '#ffffff',
    borderRadius: 16,
    padding: 20,
    gap: 14,
  },
  eyebrow: {
    fontSize: 12,
    letterSpacing: 1.2,
    textTransform: 'uppercase',
    color: theme.colors?.textMuted ?? '#64748b',
  },
  title: {
    fontSize: 20,
    fontWeight: '600',
    color: theme.colors?.text ?? '#0f172a',
  },
  rows: {
    gap: 8,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  rowLabel: {
    fontSize: 14,
    color: theme.colors?.textMuted ?? '#64748b',
  },
  rowValue: {
    fontSize: 14,
    fontWeight: '600',
    color: theme.colors?.text ?? '#0f172a',
  },
  warningsBox: {
    maxHeight: 160,
    backgroundColor: theme.colors?.surfaceMuted ?? '#f1f5f9',
    borderRadius: 10,
    padding: 12,
  },
  warningsContent: {
    gap: 6,
  },
  warning: {
    fontSize: 13,
    lineHeight: 18,
    color: theme.colors?.text ?? '#0f172a',
  },
});
