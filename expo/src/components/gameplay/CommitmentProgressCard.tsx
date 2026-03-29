import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

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
      <ProgressBar value={active.adherence_score} color="#1d4ed8" />

      <View style={styles.row}>
        <Text style={styles.label}>Momentum</Text>
        <Text style={styles.value}>{Math.round(active.momentum_score)}%</Text>
      </View>
      <ProgressBar value={active.momentum_score} color="#0369a1" />

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
    borderColor: '#e2e8f0',
    borderRadius: 12,
    backgroundColor: '#ffffff',
    padding: 14,
    gap: 8,
  },
  heading: {
    color: '#0f172a',
    fontSize: 17,
    fontWeight: '800',
  },
  subheading: {
    color: '#1e3a8a',
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
    color: '#475569',
    fontSize: 12,
    fontWeight: '700',
  },
  value: {
    color: '#0f172a',
    fontSize: 12,
    fontWeight: '800',
  },
  track: {
    height: 8,
    borderRadius: 999,
    backgroundColor: '#e2e8f0',
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
    color: '#334155',
    fontSize: 12,
    lineHeight: 17,
  },
  empty: {
    color: '#64748b',
    fontSize: 12,
  },
});
