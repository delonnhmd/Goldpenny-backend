import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

import { formatMoney } from '@/lib/gameplayFormatters';

export interface BusinessStatusInput {
  count?: number;
  netProfitXgp?: number;
  summary?: string;
}

export default function BusinessStatusCard({ input }: { input: BusinessStatusInput }) {
  const profit = Number(input.netProfitXgp ?? 0);
  return (
    <View style={styles.card}>
      <Text style={styles.title}>Business</Text>
      <Text style={styles.mainMetric}>Active: {Math.max(0, Math.round(Number(input.count ?? 0)))}</Text>
      <Text style={[styles.metric, { color: profit >= 0 ? theme.ui.positive : theme.ui.danger }]}>
        Net: {formatMoney(profit)}
      </Text>
      <Text style={styles.summary}>
        {input.summary || 'Business operations are tied to current economy conditions.'}
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
    fontSize: 14,
    fontWeight: '700',
  },
  summary: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 16,
  },
});
