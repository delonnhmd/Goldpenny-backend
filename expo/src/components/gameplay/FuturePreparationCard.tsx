import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { lockedBadgeLabel } from '@/lib/strategicPlanningFormatters';
import { FuturePreparationResponse } from '@/types/strategicPlanning';

export default function FuturePreparationCard({ future }: { future: FuturePreparationResponse }) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Future Path Preparation</Text>
      <Text style={styles.copy}>
        These are long-term signals only. They are intentionally locked and not playable yet.
      </Text>

      {future.items.slice(0, 4).map((item) => (
        <View key={item.path_key} style={styles.item}>
          <View style={styles.itemHeader}>
            <Text style={styles.itemTitle}>{item.title}</Text>
            <Text style={styles.badge}>{lockedBadgeLabel()}</Text>
          </View>
          <Text style={styles.line}>{item.why_it_matters_now}</Text>
          <Text style={styles.signal}>Preparation signal: {item.current_preparation_signal}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 12,
    backgroundColor: '#f8fafc',
    padding: 14,
    gap: 8,
  },
  heading: {
    color: '#334155',
    fontSize: 16,
    fontWeight: '800',
  },
  copy: {
    color: '#64748b',
    fontSize: 12,
    lineHeight: 17,
  },
  item: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    backgroundColor: '#ffffff',
    padding: 10,
    gap: 4,
  },
  itemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
  },
  itemTitle: {
    color: '#0f172a',
    fontSize: 13,
    fontWeight: '700',
  },
  badge: {
    color: '#475569',
    fontSize: 10,
    fontWeight: '800',
    textTransform: 'uppercase',
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 999,
    paddingHorizontal: 7,
    paddingVertical: 2,
    overflow: 'hidden',
  },
  line: {
    color: '#334155',
    fontSize: 12,
    lineHeight: 17,
  },
  signal: {
    color: '#1e3a8a',
    fontSize: 12,
    lineHeight: 17,
  },
});
