import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

import { lockedBadgeText, pressureTone } from '@/lib/worldMemoryFormatters';
import { LocalPressureSummaryResponse } from '@/types/worldMemory';

export default function LocalPressureCard({ local }: { local: LocalPressureSummaryResponse }) {
  const tone = pressureTone(local.local_pressure_level);

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.heading}>Local Pressure</Text>
        <Text style={[styles.level, { color: tone }]}>{String(local.local_pressure_level).toUpperCase()}</Text>
      </View>
      <Text style={styles.meta}>Region: {local.region_key}</Text>
      <Text style={styles.summary}>{local.short_summary}</Text>

      <View style={styles.grid}>
        <Text style={styles.meta}>Congestion: {local.congestion_label}</Text>
        <Text style={styles.meta}>Opportunity: {local.opportunity_label}</Text>
        <Text style={styles.meta}>Cost pressure: {local.cost_pressure_label}</Text>
        <Text style={styles.meta}>Business climate: {local.business_climate_label}</Text>
      </View>

      <View style={styles.responsesBox}>
        <Text style={styles.sectionTitle}>Current Practical Responses</Text>
        {local.practical_response_options.slice(0, 3).map((item, index) => (
          <Text key={`response_${index}`} style={styles.responseText}>- {item}</Text>
        ))}
      </View>

      <View style={styles.lockedBox}>
        <Text style={styles.lockedBadge}>{lockedBadgeText()}</Text>
        {local.future_locked_solution_teasers.slice(0, 3).map((item, index) => (
          <Text key={`locked_${index}`} style={styles.lockedText}>- {item}</Text>
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
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  heading: {
    color: theme.ui.text.onLight,
    fontSize: 17,
    fontWeight: '800',
  },
  level: {
    fontSize: 11,
    fontWeight: '900',
  },
  meta: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    fontWeight: '600',
  },
  summary: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  grid: {
    gap: 2,
  },
  responsesBox: {
    borderWidth: 1,
    borderColor: theme.ui.info,
    borderRadius: 10,
    backgroundColor: theme.ui.bg.sheet,
    padding: 10,
    gap: 3,
  },
  sectionTitle: {
    color: theme.ui.action,
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  responseText: {
    color: theme.ui.action,
    fontSize: 12,
    lineHeight: 16,
  },
  lockedBox: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: 10,
    backgroundColor: theme.ui.bg.sheet,
    padding: 10,
    gap: 3,
  },
  lockedBadge: {
    color: theme.ui.text.onLightMuted,
    fontSize: 10,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  lockedText: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 16,
  },
});
