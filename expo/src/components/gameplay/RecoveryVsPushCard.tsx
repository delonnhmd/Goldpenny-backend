import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { pressureLevelColor } from '@/lib/strategicPlanningFormatters';
import { RecoveryVsPushResponse } from '@/types/strategicPlanning';

export default function RecoveryVsPushCard({ analysis }: { analysis: RecoveryVsPushResponse }) {
  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.heading}>Recovery vs Push</Text>
        <Text style={[styles.level, { color: pressureLevelColor(analysis.current_pressure_level) }]}>
          Pressure: {analysis.current_pressure_level}
        </Text>
      </View>
      <Text style={styles.copy}>{analysis.recommendation_summary}</Text>

      <View style={styles.block}>
        <Text style={styles.blockTitle}>Push case</Text>
        <Text style={styles.blockText}>{analysis.push_case}</Text>
      </View>
      <View style={styles.block}>
        <Text style={styles.blockTitle}>Recovery case</Text>
        <Text style={styles.blockText}>{analysis.recovery_case}</Text>
      </View>
      <Text style={styles.line}>Near-term cost: {analysis.likely_near_term_cost}</Text>
      <Text style={styles.line}>Near-term benefit: {analysis.likely_near_term_benefit}</Text>
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
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
  },
  heading: {
    color: '#0f172a',
    fontSize: 17,
    fontWeight: '800',
  },
  level: {
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  copy: {
    color: '#0f172a',
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '700',
  },
  block: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    backgroundColor: '#f8fafc',
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
  line: {
    color: '#334155',
    fontSize: 12,
    lineHeight: 17,
  },
});
