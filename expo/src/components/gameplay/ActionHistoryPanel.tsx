import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

import { DailyActionHistoryEntry } from '@/types/gameplay';

function HistoryItem({ entry }: { entry: DailyActionHistoryEntry }) {
  return (
    <View style={styles.item}>
      <View style={styles.itemTopRow}>
        <Text style={styles.itemOrder}>#{entry.order}</Text>
        <Text style={[styles.itemStatus, entry.success ? styles.success : styles.failure]}>
          {entry.success ? 'success' : 'failed'}
        </Text>
      </View>
      <Text style={styles.itemTitle}>{entry.title}</Text>
      <Text style={styles.itemDescription}>{entry.description}</Text>
      <Text style={styles.itemMeta}>Time cost: {entry.time_cost_units} units</Text>
      {entry.result_summary ? <Text style={styles.itemMeta}>Result: {entry.result_summary}</Text> : null}
      {entry.error_message ? <Text style={styles.errorText}>Error: {entry.error_message}</Text> : null}
    </View>
  );
}

export default function ActionHistoryPanel({
  entries,
  sessionStatus,
}: {
  entries: DailyActionHistoryEntry[];
  sessionStatus: 'active' | 'ended';
}) {
  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.heading}>Today&apos;s Action History</Text>
        <Text style={styles.sessionBadge}>{sessionStatus}</Text>
      </View>
      {entries.length > 0 ? (
        entries.map((entry) => <HistoryItem key={entry.id} entry={entry} />)
      ) : (
        <Text style={styles.emptyText}>No actions executed yet. Preview and run an action to start the day loop.</Text>
      )}
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
    gap: 10,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  heading: {
    color: theme.ui.text.onLight,
    fontSize: 16,
    fontWeight: '800',
  },
  sessionBadge: {
    color: theme.ui.text.onLightMuted,
    fontSize: 11,
    textTransform: 'uppercase',
    fontWeight: '700',
    borderWidth: 1,
    borderColor: theme.ui.text.onLightMuted,
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 3,
  },
  item: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: 10,
    backgroundColor: theme.ui.bg.sheet,
    padding: 10,
    gap: 4,
  },
  itemTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  itemOrder: {
    color: theme.ui.text.onLightMuted,
    fontSize: 11,
    fontWeight: '700',
  },
  itemStatus: {
    fontSize: 11,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
  success: {
    color: theme.ui.positive,
  },
  failure: {
    color: theme.ui.danger,
  },
  itemTitle: {
    color: theme.ui.text.onLight,
    fontSize: 14,
    fontWeight: '700',
  },
  itemDescription: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  itemMeta: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 16,
  },
  errorText: {
    color: theme.ui.danger,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '600',
  },
  emptyText: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 18,
  },
});
