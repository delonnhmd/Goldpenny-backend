import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

import { RegionMemorySummaryResponse } from '@/types/worldMemory';

export default function RegionMemoryCard({ region }: { region: RegionMemorySummaryResponse }) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Region Memory</Text>
      <Text style={styles.meta}>Region: {region.region_key}</Text>
      <Text style={styles.identity}>{region.current_tradeoff_identity}</Text>
      <Text style={styles.summary}>{region.recent_change_summary}</Text>

      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: theme.ui.danger }]}>Dominant Pressures</Text>
        {region.dominant_region_pressures.slice(0, 3).map((item, index) => (
          <Text key={`pressure_${index}`} style={styles.itemText}>- {item}</Text>
        ))}
      </View>

      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: theme.ui.positive }]}>Dominant Opportunities</Text>
        {region.dominant_region_opportunities.slice(0, 3).map((item, index) => (
          <Text key={`opportunity_${index}`} style={styles.itemText}>- {item}</Text>
        ))}
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
  meta: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    fontWeight: '700',
  },
  identity: {
    color: theme.ui.action,
    fontSize: 13,
    fontWeight: '700',
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
});
