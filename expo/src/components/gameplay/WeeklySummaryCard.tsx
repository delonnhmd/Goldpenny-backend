import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { formatMoney } from '@/lib/gameplayFormatters';
import { WeeklyPlayerSummaryResponse } from '@/types/gameplay';

export default function WeeklySummaryCard({ summary }: { summary: WeeklyPlayerSummaryResponse }) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Weekly Summary</Text>
      <Text style={styles.subheading}>
        {summary.week_start} → {summary.week_end}
      </Text>

      <Text style={styles.copy}>Strategy: {summary.strategy_classification}</Text>
      <Text style={styles.copy}>Top Pressure: {summary.top_pressure}</Text>
      <Text style={styles.copy}>Strongest Opportunity: {summary.strongest_opportunity}</Text>
      <Text style={styles.copy}>Risk Trend: {summary.risk_trend}</Text>
      <Text style={styles.copy}>Growth Trend: {summary.growth_trend}</Text>
      {summary.notable_event_chain ? <Text style={styles.copy}>Notable Chain: {summary.notable_event_chain}</Text> : null}

      {summary.weekly_income_mix.length > 0 ? (
        <View style={styles.infoBox}>
          <Text style={styles.infoTitle}>Income Mix</Text>
          {summary.weekly_income_mix.map((item) => (
            <Text key={item.source} style={styles.infoText}>
              • {item.source}: {formatMoney(item.amount_xgp)}
            </Text>
          ))}
        </View>
      ) : null}

      {summary.suggested_next_moves.length > 0 ? (
        <View style={styles.infoBox}>
          <Text style={styles.infoTitle}>Suggested Next Moves</Text>
          {summary.suggested_next_moves.map((item, index) => (
            <Text key={`move_${index}`} style={styles.infoText}>
              • {item}
            </Text>
          ))}
        </View>
      ) : null}
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
    fontSize: 18,
    fontWeight: '800',
  },
  subheading: {
    color: '#64748b',
    fontSize: 12,
    fontWeight: '600',
  },
  copy: {
    color: '#334155',
    fontSize: 13,
    lineHeight: 18,
  },
  infoBox: {
    borderWidth: 1,
    borderColor: '#dbeafe',
    borderRadius: 10,
    backgroundColor: '#eff6ff',
    padding: 10,
    gap: 4,
  },
  infoTitle: {
    color: '#1e40af',
    fontSize: 12,
    fontWeight: '700',
  },
  infoText: {
    color: '#1e3a8a',
    fontSize: 12,
    lineHeight: 17,
  },
});
