import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

import { commutePressureTone } from '@/lib/economyPresentationFormatters';
import { CommutePressureResponse } from '@/types/economyPresentation';

export default function CommutePressureCard({ commute }: { commute: CommutePressureResponse }) {
  const tone = commutePressureTone(commute.commute_pressure_level);

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.heading}>Commute Pressure</Text>
        <Text style={[styles.level, { color: tone }]}>{String(commute.commute_pressure_level).toUpperCase()}</Text>
      </View>
      <Text style={styles.meta}>Region: {commute.region_key}</Text>
      <Text style={styles.meta}>Estimated burden: {commute.estimated_commute_burden}</Text>
      <Text style={styles.copy}>{commute.stress_impact_label}</Text>
      <Text style={styles.copy}>{commute.time_impact_label}</Text>

      <View style={styles.tradeoffBox}>
        <Text style={styles.tradeoffTitle}>Current Practical Tradeoff</Text>
        <Text style={styles.tradeoffText}>{commute.housing_tradeoff_summary}</Text>
        {commute.suggested_current_responses.slice(0, 2).map((item, index) => (
          <Text key={`response_${index}`} style={styles.responseText}>• {item}</Text>
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
    gap: 6,
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
  copy: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  tradeoffBox: {
    marginTop: 2,
    borderWidth: 1,
    borderColor: theme.ui.info,
    borderRadius: 10,
    backgroundColor: theme.ui.bg.sheet,
    padding: 10,
    gap: 4,
  },
  tradeoffTitle: {
    color: theme.ui.action,
    fontSize: 12,
    fontWeight: '800',
  },
  tradeoffText: {
    color: theme.ui.action,
    fontSize: 12,
    lineHeight: 17,
  },
  responseText: {
    color: theme.ui.action,
    fontSize: 12,
    lineHeight: 17,
  },
});
