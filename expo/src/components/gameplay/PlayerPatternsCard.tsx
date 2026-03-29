import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { PlayerPatternSummaryResponse } from '@/types/worldMemory';

export default function PlayerPatternsCard({ patterns }: { patterns: PlayerPatternSummaryResponse }) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Player Patterns</Text>
      <Text style={styles.dominantLabel}>Dominant Pattern</Text>
      <Text style={styles.dominantValue}>{patterns.dominant_player_pattern}</Text>
      <Text style={styles.summary}>{patterns.summary}</Text>

      {patterns.risk_patterns.length > 0 ? (
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: '#b91c1c' }]}>Risk Patterns</Text>
          {patterns.risk_patterns.slice(0, 3).map((item, index) => (
            <Text key={`risk_${index}`} style={styles.itemText}>- {item}</Text>
          ))}
        </View>
      ) : null}

      {patterns.improving_patterns.length > 0 ? (
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: '#166534' }]}>Improving Patterns</Text>
          {patterns.improving_patterns.slice(0, 3).map((item, index) => (
            <Text key={`improving_${index}`} style={styles.itemText}>- {item}</Text>
          ))}
        </View>
      ) : null}

      <View style={styles.correctionBox}>
        <Text style={styles.correctionTitle}>Suggested Correction</Text>
        <Text style={styles.correctionText}>{patterns.suggested_correction}</Text>
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
    gap: 8,
  },
  heading: {
    color: '#0f172a',
    fontSize: 17,
    fontWeight: '800',
  },
  dominantLabel: {
    color: '#475569',
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  dominantValue: {
    color: '#0f172a',
    fontSize: 14,
    fontWeight: '800',
  },
  summary: {
    color: '#334155',
    fontSize: 12,
    lineHeight: 17,
  },
  section: {
    gap: 3,
  },
  sectionTitle: {
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  itemText: {
    color: '#475569',
    fontSize: 12,
    lineHeight: 16,
  },
  correctionBox: {
    borderWidth: 1,
    borderColor: '#dbeafe',
    borderRadius: 10,
    backgroundColor: '#eff6ff',
    padding: 10,
    gap: 4,
  },
  correctionTitle: {
    color: '#1e3a8a',
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  correctionText: {
    color: '#1e40af',
    fontSize: 12,
    lineHeight: 17,
  },
});
