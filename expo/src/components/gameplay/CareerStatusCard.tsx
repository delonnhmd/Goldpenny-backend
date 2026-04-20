import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

export interface CareerStatusInput {
  currentJob?: string | null;
  growthTrend?: string;
  stressLoad?: number;
  summary?: string;
}

export default function CareerStatusCard({ input }: { input: CareerStatusInput }) {
  return (
    <View style={styles.card}>
      <Text style={styles.title}>Career</Text>
      <Text style={styles.mainMetric}>{input.currentJob || 'Unassigned'}</Text>
      <Text style={styles.metric}>Growth: {input.growthTrend || 'steady'}</Text>
      <Text style={styles.metric}>Stress Load: {Math.round(Number(input.stressLoad ?? 0))}</Text>
      <Text style={styles.summary}>
        {input.summary || 'Your job path reacts to confidence, region, and life pressure.'}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: 10,
    padding: 12,
    backgroundColor: theme.ui.bg.sheet,
    gap: 5,
  },
  title: {
    color: theme.ui.text.onLightMuted,
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  mainMetric: {
    color: theme.ui.text.onLight,
    fontSize: 17,
    fontWeight: '800',
  },
  metric: {
    color: theme.ui.text.onLight,
    fontSize: 13,
    fontWeight: '600',
  },
  summary: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 16,
  },
});
