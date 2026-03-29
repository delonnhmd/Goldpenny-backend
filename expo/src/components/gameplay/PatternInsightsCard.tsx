import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import {
  patternSeverityColor,
  patternStatusLabel,
  persistenceLabel,
  trendLabel,
} from '@/lib/worldMemoryFormatters';
import { WorldPatternsResponse } from '@/types/worldMemory';

export default function PatternInsightsCard({ patterns }: { patterns: WorldPatternsResponse }) {
  const topItems = patterns.items.slice(0, 5);

  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Pattern Insights</Text>
      {topItems.length === 0 ? (
        <Text style={styles.empty}>No persistent pattern detected yet.</Text>
      ) : (
        topItems.map((item) => {
          const severityColor = patternSeverityColor(item.severity);
          return (
            <View key={item.pattern_key} style={styles.itemRow}>
              <View style={styles.itemHeader}>
                <Text style={styles.itemTitle}>{item.title}</Text>
                <Text style={[styles.badge, { color: severityColor }]}>
                  {persistenceLabel(item.persistence_score)} · {patternStatusLabel(item.current_status)}
                </Text>
              </View>
              <Text style={styles.itemMeta}>
                {String(item.category).toUpperCase()} · {trendLabel(item.direction)} · {item.consecutive_days}d
              </Text>
              <Text style={styles.itemDescription}>{item.short_description}</Text>
            </View>
          );
        })
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
  empty: {
    color: '#64748b',
    fontSize: 12,
    fontWeight: '600',
  },
  itemRow: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    backgroundColor: '#f8fafc',
    padding: 10,
    gap: 4,
  },
  itemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 6,
  },
  itemTitle: {
    color: '#0f172a',
    fontSize: 12,
    fontWeight: '800',
    flex: 1,
  },
  badge: {
    fontSize: 10,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  itemMeta: {
    color: '#475569',
    fontSize: 11,
    fontWeight: '700',
  },
  itemDescription: {
    color: '#334155',
    fontSize: 12,
    lineHeight: 16,
  },
});
