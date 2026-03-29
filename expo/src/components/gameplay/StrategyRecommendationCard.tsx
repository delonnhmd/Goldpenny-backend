import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { StrategyRecommendationResponse } from '@/types/strategicPlanning';

export default function StrategyRecommendationCard({
  recommendation,
}: {
  recommendation: StrategyRecommendationResponse;
}) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Strategy Recommendation</Text>
      <Text style={styles.planTitle}>{recommendation.recommended_plan_title}</Text>
      <Text style={styles.reason}>{recommendation.recommendation_reason}</Text>

      <View style={styles.block}>
        <Text style={styles.blockTitle}>Biggest risk</Text>
        <Text style={styles.blockText}>{recommendation.biggest_risk}</Text>
      </View>
      <View style={styles.block}>
        <Text style={styles.blockTitle}>Biggest opportunity</Text>
        <Text style={styles.blockText}>{recommendation.biggest_opportunity}</Text>
      </View>

      <Text style={styles.move}>Defensive move: {recommendation.defensive_move}</Text>
      <Text style={styles.move}>Growth move: {recommendation.growth_move}</Text>
      <Text style={styles.warning}>Avoid: {recommendation.avoid_warning}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: '#bfdbfe',
    borderRadius: 12,
    backgroundColor: '#eff6ff',
    padding: 14,
    gap: 8,
  },
  heading: {
    color: '#1e3a8a',
    fontSize: 17,
    fontWeight: '800',
  },
  planTitle: {
    color: '#1d4ed8',
    fontSize: 14,
    fontWeight: '900',
  },
  reason: {
    color: '#1e3a8a',
    fontSize: 12,
    lineHeight: 17,
  },
  block: {
    borderWidth: 1,
    borderColor: '#dbeafe',
    borderRadius: 10,
    backgroundColor: '#ffffff',
    padding: 10,
    gap: 4,
  },
  blockTitle: {
    color: '#334155',
    fontSize: 12,
    fontWeight: '700',
  },
  blockText: {
    color: '#334155',
    fontSize: 12,
    lineHeight: 17,
  },
  move: {
    color: '#1e3a8a',
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '700',
  },
  warning: {
    color: '#b91c1c',
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '700',
  },
});
