import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { StreakItem } from '@/types/progression';

function riskColor(resetRisk: string): string {
  const normalized = String(resetRisk || '').toLowerCase();
  if (normalized === 'high') return '#b91c1c';
  if (normalized === 'medium') return '#b45309';
  return '#166534';
}

export default function StreaksCard({ streaks }: { streaks: StreakItem[] }) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Streaks</Text>
      <Text style={styles.subheading}>Consistency signals that reinforce good habits.</Text>
      {streaks.length > 0 ? (
        streaks.map((streak) => (
          <View key={streak.streak_key} style={styles.streakRow}>
            <View style={styles.streakMain}>
              <Text style={styles.streakTitle}>{streak.title}</Text>
              <Text style={styles.streakCounts}>
                Current {streak.current_count} | Best {streak.best_count}
              </Text>
            </View>
            <View style={styles.streakSide}>
              <Text style={[styles.riskLabel, { color: riskColor(streak.reset_risk) }]}>
                {streak.reset_risk} reset risk
              </Text>
              <Text style={styles.conditionText}>{streak.next_credit_condition}</Text>
            </View>
          </View>
        ))
      ) : (
        <Text style={styles.empty}>No streak data yet.</Text>
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
  subheading: {
    color: '#475569',
    fontSize: 12,
    lineHeight: 17,
  },
  streakRow: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    backgroundColor: '#f8fafc',
    padding: 10,
    gap: 5,
  },
  streakMain: {
    gap: 2,
  },
  streakTitle: {
    color: '#0f172a',
    fontSize: 13,
    fontWeight: '700',
  },
  streakCounts: {
    color: '#334155',
    fontSize: 12,
    fontWeight: '600',
  },
  streakSide: {
    gap: 2,
  },
  riskLabel: {
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  conditionText: {
    color: '#475569',
    fontSize: 11,
    lineHeight: 15,
  },
  empty: {
    color: '#64748b',
    fontSize: 12,
  },
});
