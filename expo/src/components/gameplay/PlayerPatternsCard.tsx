import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

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
          <Text style={[styles.sectionTitle, { color: theme.ui.danger }]}>Risk Patterns</Text>
          {patterns.risk_patterns.slice(0, 3).map((item, index) => (
            <Text key={`risk_${index}`} style={styles.itemText}>- {item}</Text>
          ))}
        </View>
      ) : null}

      {patterns.improving_patterns.length > 0 ? (
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: theme.ui.positive }]}>Improving Patterns</Text>
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
  dominantLabel: {
    color: theme.ui.text.onLightMuted,
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  dominantValue: {
    color: theme.ui.text.onLight,
    fontSize: 14,
    fontWeight: '800',
  },
  summary: {
    color: theme.ui.text.onLightMuted,
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
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 16,
  },
  correctionBox: {
    borderWidth: 1,
    borderColor: theme.ui.info,
    borderRadius: 10,
    backgroundColor: theme.ui.bg.sheet,
    padding: 10,
    gap: 4,
  },
  correctionTitle: {
    color: theme.ui.action,
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  correctionText: {
    color: theme.ui.action,
    fontSize: 12,
    lineHeight: 17,
  },
});
