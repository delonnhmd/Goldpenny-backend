import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

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
    borderColor: theme.ui.text.onLightMuted,
    borderRadius: 12,
    backgroundColor: theme.ui.bg.sheet,
    padding: 14,
    gap: 8,
  },
  heading: {
    color: theme.ui.text.onLightMuted,
    fontSize: 16,
    fontWeight: '800',
  },
  copy: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  item: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: 10,
    backgroundColor: theme.ui.bg.sheet,
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
    color: theme.ui.text.onLight,
    fontSize: 13,
    fontWeight: '700',
  },
  badge: {
    color: theme.ui.text.onLightMuted,
    fontSize: 10,
    fontWeight: '800',
    textTransform: 'uppercase',
    borderWidth: 1,
    borderColor: theme.ui.text.onLightMuted,
    borderRadius: 999,
    paddingHorizontal: 7,
    paddingVertical: 2,
    overflow: 'hidden',
  },
  line: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  signal: {
    color: theme.ui.action,
    fontSize: 12,
    lineHeight: 17,
  },
});
