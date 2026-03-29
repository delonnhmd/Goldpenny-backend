import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

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
    borderColor: '#e2e8f0',
    borderRadius: 10,
    padding: 12,
    backgroundColor: '#ffffff',
    gap: 5,
  },
  title: {
    color: '#475569',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  mainMetric: {
    color: '#0f172a',
    fontSize: 17,
    fontWeight: '800',
  },
  metric: {
    color: '#1e293b',
    fontSize: 13,
    fontWeight: '600',
  },
  summary: {
    color: '#475569',
    fontSize: 12,
    lineHeight: 16,
  },
});
