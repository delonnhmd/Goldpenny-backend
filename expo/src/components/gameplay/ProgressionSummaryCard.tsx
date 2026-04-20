import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { ProgressionSummaryResponse } from '@/types/progression';

export default function ProgressionSummaryCard({
  summary,
}: {
  summary: ProgressionSummaryResponse;
}) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Progression Summary</Text>
      <Text style={styles.copy}>{summary.motivational_summary || 'Keep compounding small wins.'}</Text>

      {summary.suggested_focus.length > 0 ? (
        <View style={styles.focusBlock}>
          <Text style={styles.focusTitle}>Suggested Focus</Text>
          {summary.suggested_focus.slice(0, 4).map((line, index) => (
            <Text key={`focus_${index}`} style={styles.focusText}>
              - {line}
            </Text>
          ))}
        </View>
      ) : null}

      {summary.recently_completed.length > 0 ? (
        <View style={styles.completedBlock}>
          <Text style={styles.completedTitle}>Recently Completed</Text>
          {summary.recently_completed.slice(0, 4).map((entry) => (
            <Text key={`${entry.scope}_${entry.key}_${entry.credited_on}`} style={styles.completedText}>
              - {entry.title} ({entry.reward_summary})
            </Text>
          ))}
        </View>
      ) : (
        <Text style={styles.empty}>No recent completions yet. Today&apos;s goals can start your streak.</Text>
      )}
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
  copy: {
    color: '#334155',
    fontSize: 13,
    lineHeight: 18,
  },
  focusBlock: {
    borderWidth: 1,
    borderColor: '#dbeafe',
    borderRadius: 10,
    backgroundColor: '#eff6ff',
    padding: 10,
    gap: 4,
  },
  focusTitle: {
    color: '#1e40af',
    fontSize: 12,
    fontWeight: '700',
  },
  focusText: {
    color: '#1e3a8a',
    fontSize: 12,
    lineHeight: 17,
  },
  completedBlock: {
    borderWidth: 1,
    borderColor: '#86efac',
    borderRadius: 10,
    backgroundColor: '#f0fdf4',
    padding: 10,
    gap: 4,
  },
  completedTitle: {
    color: '#166534',
    fontSize: 12,
    fontWeight: '700',
  },
  completedText: {
    color: '#14532d',
    fontSize: 12,
    lineHeight: 17,
  },
  empty: {
    color: '#64748b',
    fontSize: 12,
  },
});
