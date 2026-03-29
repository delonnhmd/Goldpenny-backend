import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { PlayerEconomyExplainerResponse } from '@/types/economyPresentation';

export default function EconomyExplainerCard({ explainer }: { explainer: PlayerEconomyExplainerResponse }) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Why Things Changed</Text>
      <Text style={styles.line}>• {explainer.why_costs_changed}</Text>
      <Text style={styles.line}>• {explainer.why_business_changed}</Text>
      <Text style={styles.line}>• {explainer.why_commute_changed}</Text>
      <Text style={styles.line}>• {explainer.why_stress_changed}</Text>

      <View style={styles.focusBox}>
        <Text style={styles.focusTitle}>This Week Focus</Text>
        <Text style={styles.focusText}>{explainer.this_week_focus}</Text>
        <Text style={styles.moveText}>Defensive move: {explainer.suggested_defensive_move}</Text>
        <Text style={styles.moveText}>Growth move: {explainer.suggested_growth_move}</Text>
      </View>
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
    gap: 6,
  },
  heading: {
    color: '#0f172a',
    fontSize: 17,
    fontWeight: '800',
  },
  line: {
    color: '#334155',
    fontSize: 12,
    lineHeight: 17,
  },
  focusBox: {
    borderWidth: 1,
    borderColor: '#dbeafe',
    borderRadius: 10,
    backgroundColor: '#eff6ff',
    padding: 10,
    gap: 3,
    marginTop: 4,
  },
  focusTitle: {
    color: '#1e3a8a',
    fontSize: 12,
    fontWeight: '800',
  },
  focusText: {
    color: '#1e40af',
    fontSize: 12,
    lineHeight: 17,
  },
  moveText: {
    color: '#1d4ed8',
    fontSize: 12,
    lineHeight: 17,
  },
});
