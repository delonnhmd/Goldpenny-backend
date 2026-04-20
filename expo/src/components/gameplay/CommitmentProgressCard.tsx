import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

import { clampPercent, driftColor, driftSeverityLabel } from '@/lib/commitmentFormatters';
import { CommitmentSummaryResponse } from '@/types/commitment';

function ProgressBar({ value, color }: { value: number; color: string }) {
  const width = `${Math.round(clampPercent(value))}%` as `${number}%`;
  return (
    <View style={styles.track}>
      <View style={[styles.fill, { width, backgroundColor: color }]} />
    </View>
  );
}

export default function CommitmentProgressCard({
  summary,
}: {
  summary: CommitmentSummaryResponse;
}) {
  const active = summary.active_commitment;
  if (active.status !== 'active' || !active.commitment_key) {
    return (
      <View style={styles.card}>
        <Text style={styles.heading}>Commitment Progress</Text>
        <Text style={styles.empty}>No active commitment to track yet.</Text>
      </View>
    );
  }

  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Commitment Progress</Text>
      <Text style={styles.subheading}>{active.title}</Text>

      <View style={styles.row}>
        <Text style={styles.label}>Adherence</Text>
        <Text style={styles.value}>{Math.round(active.adherence_score)}%</Text>
      </View>
      <ProgressBar value={active.adherence_score} color={theme.ui.action} />

      <View style={styles.row}>
        <Text style={styles.label}>Momentum</Text>
        <Text style={styles.value}>{Math.round(active.momentum_score)}%</Text>
      </View>
      <ProgressBar value={active.momentum_score} color={theme.ui.action} />

      <View style={styles.row}>
        <Text style={styles.label}>Followed</Text>
        <Text style={styles.value}>{active.days_followed} days</Text>
      </View>
      <View style={styles.row}>
        <Text style={styles.label}>Drifted</Text>
        <Text style={styles.value}>{active.days_drifted} days</Text>
      </View>

      <Text style={[styles.drift, { color: driftColor(active.drift_level) }]}>
        {driftSeverityLabel(active.drift_level)}
      </Text>
      <Text style={styles.summary}>{active.summary}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: 12,
    backgroundColor: theme.ui.bg.sheet,
    padding: 14,
    gap: 8,
  },
  heading: {
    color: theme.ui.text.onLight,
    fontSize: 17,
    fontWeight: '800',
  },
  subheading: {
    color: theme.ui.action,
    fontSize: 13,
    fontWeight: '700',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  label: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    fontWeight: '700',
  },
  value: {
    color: theme.ui.text.onLight,
    fontSize: 12,
    fontWeight: '800',
  },
  track: {
    height: 8,
    borderRadius: 999,
    backgroundColor: theme.ui.border,
    overflow: 'hidden',
  },
  fill: {
    height: 8,
    borderRadius: 999,
  },
  drift: {
    fontSize: 12,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  summary: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  empty: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
  },
});
