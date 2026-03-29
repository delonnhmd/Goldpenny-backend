import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

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
    color: '#334155',
    fontSize: 12,
    fontWeight: '700',
  },
  grid: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    backgroundColor: '#f8fafc',
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
    color: '#475569',
    fontSize: 12,
  },
  value: {
    color: '#0f172a',
    fontSize: 12,
    fontWeight: '700',
    flexShrink: 1,
    textAlign: 'right',
  },
  copy: {
    color: '#334155',
    fontSize: 12,
    lineHeight: 17,
  },
  recommendation: {
    color: '#0f172a',
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '700',
  },
  note: {
    color: '#64748b',
    fontSize: 11,
    lineHeight: 16,
  },
});
