import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

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
    borderColor: theme.ui.info,
    borderRadius: 12,
    backgroundColor: theme.ui.bg.sheet,
    padding: 14,
    gap: 8,
  },
  heading: {
    color: theme.ui.action,
    fontSize: 17,
    fontWeight: '800',
  },
  planTitle: {
    color: theme.ui.action,
    fontSize: 14,
    fontWeight: '900',
  },
  reason: {
    color: theme.ui.action,
    fontSize: 12,
    lineHeight: 17,
  },
  block: {
    borderWidth: 1,
    borderColor: theme.ui.info,
    borderRadius: 10,
    backgroundColor: theme.ui.bg.sheet,
    padding: 10,
    gap: 4,
  },
  blockTitle: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    fontWeight: '700',
  },
  blockText: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  move: {
    color: theme.ui.action,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '700',
  },
  warning: {
    color: theme.ui.danger,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '700',
  },
});
