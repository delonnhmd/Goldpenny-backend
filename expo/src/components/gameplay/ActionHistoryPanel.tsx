import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

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
    borderColor: '#e2e8f0',
    borderRadius: 12,
    backgroundColor: '#ffffff',
    padding: 14,
    gap: 10,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  heading: {
    color: '#0f172a',
    fontSize: 16,
    fontWeight: '800',
  },
  sessionBadge: {
    color: '#334155',
    fontSize: 11,
    textTransform: 'uppercase',
    fontWeight: '700',
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 3,
  },
  item: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    backgroundColor: '#f8fafc',
    padding: 10,
    gap: 4,
  },
  itemTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  itemOrder: {
    color: '#475569',
    fontSize: 11,
    fontWeight: '700',
  },
  itemStatus: {
    fontSize: 11,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
  success: {
    color: '#166534',
  },
  failure: {
    color: '#b91c1c',
  },
  itemTitle: {
    color: '#0f172a',
    fontSize: 14,
    fontWeight: '700',
  },
  itemDescription: {
    color: '#475569',
    fontSize: 12,
    lineHeight: 17,
  },
  itemMeta: {
    color: '#334155',
    fontSize: 12,
    lineHeight: 16,
  },
  errorText: {
    color: '#b91c1c',
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '600',
  },
  emptyText: {
    color: '#64748b',
    fontSize: 12,
    lineHeight: 18,
  },
});
