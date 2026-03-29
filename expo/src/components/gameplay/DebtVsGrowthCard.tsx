import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { liquidityRiskColor, scoreLabel } from '@/lib/strategicPlanningFormatters';
import { DebtVsGrowthResponse } from '@/types/strategicPlanning';

export default function DebtVsGrowthCard({ analysis }: { analysis: DebtVsGrowthResponse }) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Debt vs Growth</Text>
      <Text style={styles.copy}>Use this when deciding where extra cash should go this week.</Text>

      {analysis.items.slice(0, 4).map((item) => (
        <View key={item.option_key} style={styles.item}>
          <Text style={styles.itemTitle}>{item.option_label}</Text>
          <View style={styles.scoreRow}>
            <Text style={styles.score}>Defensive: {scoreLabel(item.defensive_score)} ({item.defensive_score.toFixed(1)})</Text>
            <Text style={styles.score}>Growth: {scoreLabel(item.growth_score)} ({item.growth_score.toFixed(1)})</Text>
          </View>
          <Text style={[styles.risk, { color: liquidityRiskColor(item.liquidity_risk) }]}>
            Liquidity risk: {item.liquidity_risk}
          </Text>
          <Text style={styles.line}>{item.distress_impact_label}</Text>
          <Text style={styles.note}>{item.recommendation_note}</Text>
        </View>
      ))}
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
    gap: 10,
  },
  heading: {
    color: '#0f172a',
    fontSize: 17,
    fontWeight: '800',
  },
  copy: {
    color: '#475569',
    fontSize: 12,
    lineHeight: 17,
  },
  item: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    backgroundColor: '#f8fafc',
    padding: 10,
    gap: 4,
  },
  itemTitle: {
    color: '#0f172a',
    fontSize: 13,
    fontWeight: '800',
  },
  scoreRow: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
  },
  score: {
    color: '#334155',
    fontSize: 11,
    fontWeight: '700',
  },
  risk: {
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  line: {
    color: '#1e3a8a',
    fontSize: 12,
    lineHeight: 17,
  },
  note: {
    color: '#334155',
    fontSize: 12,
    lineHeight: 17,
  },
});
