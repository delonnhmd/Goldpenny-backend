import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

import { tradeoffAccentColor } from '@/lib/strategicPlanningFormatters';
import { HousingTradeoffResponse } from '@/types/strategicPlanning';

export default function HousingTradeoffCard({ tradeoff }: { tradeoff: HousingTradeoffResponse }) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Housing Tradeoff</Text>
      <Text style={styles.subheading}>Current region: {tradeoff.current_region}</Text>

      <View style={styles.grid}>
        <View style={styles.row}>
          <Text style={styles.label}>Current commute</Text>
          <Text style={styles.value}>{tradeoff.current_commute_burden}</Text>
        </View>
        <View style={styles.row}>
          <Text style={styles.label}>If you rent closer</Text>
          <Text style={[styles.value, { color: tradeoffAccentColor(tradeoff.closer_housing_cost_pressure) }]}>
            {tradeoff.closer_housing_cost_pressure}
          </Text>
        </View>
      </View>

      <Text style={styles.copy}>{tradeoff.expected_time_delta_label}</Text>
      <Text style={styles.copy}>{tradeoff.expected_stress_delta_label}</Text>
      <Text style={styles.copy}>{tradeoff.opportunity_access_label}</Text>
      <Text style={styles.recommendation}>{tradeoff.short_recommendation}</Text>
      <Text style={styles.note}>Current practical options: stay, or move/rent closer (higher housing expense).</Text>
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
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    fontWeight: '700',
  },
  grid: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: 10,
    backgroundColor: theme.ui.bg.sheet,
    padding: 10,
    gap: 6,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  label: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
  },
  value: {
    color: theme.ui.text.onLight,
    fontSize: 12,
    fontWeight: '700',
    flexShrink: 1,
    textAlign: 'right',
  },
  copy: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  recommendation: {
    color: theme.ui.text.onLight,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '700',
  },
  note: {
    color: theme.ui.text.onLightMuted,
    fontSize: 11,
    lineHeight: 16,
  },
});
