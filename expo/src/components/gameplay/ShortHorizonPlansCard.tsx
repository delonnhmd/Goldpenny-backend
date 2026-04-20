import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

import { confidenceColor, confidenceLabel } from '@/lib/strategicPlanningFormatters';
import { ShortHorizonPlansResponse } from '@/types/strategicPlanning';

export default function ShortHorizonPlansCard({ plans }: { plans: ShortHorizonPlansResponse }) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>3-7 Day Plan Options</Text>
      <Text style={styles.copy}>Choose one path and stay consistent for a few days before pivoting.</Text>

      {plans.options.slice(0, 4).map((item) => (
        <View key={item.plan_key} style={styles.item}>
          <View style={styles.itemHeader}>
            <Text style={styles.itemTitle}>{item.title}</Text>
            <Text style={[styles.confidence, { color: confidenceColor(item.confidence_label) }]}>
              {confidenceLabel(item.confidence_label)}
            </Text>
          </View>
          <Text style={styles.duration}>Suggested horizon: {item.suggested_duration_days} days</Text>
          <Text style={styles.itemCopy}>{item.short_description}</Text>
          <Text style={styles.tradeoff}>Tradeoff: {item.primary_tradeoff}</Text>
          <Text style={styles.upside}>Upside: {item.likely_upside}</Text>
          <Text style={styles.downside}>Downside: {item.likely_downside}</Text>
        </View>
      ))}
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
    gap: 10,
  },
  heading: {
    color: theme.ui.text.onLight,
    fontSize: 17,
    fontWeight: '800',
  },
  copy: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  item: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: 10,
    backgroundColor: theme.ui.bg.sheet,
    padding: 10,
    gap: 4,
  },
  itemHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  itemTitle: {
    color: theme.ui.text.onLight,
    fontSize: 14,
    fontWeight: '800',
    flex: 1,
  },
  confidence: {
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  duration: {
    color: theme.ui.text.onLightMuted,
    fontSize: 11,
    fontWeight: '700',
  },
  itemCopy: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  tradeoff: {
    color: theme.ui.text.onLight,
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 17,
  },
  upside: {
    color: theme.ui.positive,
    fontSize: 12,
    lineHeight: 17,
  },
  downside: {
    color: theme.ui.danger,
    fontSize: 12,
    lineHeight: 17,
  },
});
