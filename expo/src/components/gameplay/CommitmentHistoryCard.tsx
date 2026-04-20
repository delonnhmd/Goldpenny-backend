import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

import { statusBadgeColor } from '@/lib/commitmentFormatters';
import { CommitmentHistoryResponse } from '@/types/commitment';

export default function CommitmentHistoryCard({
  history,
}: {
  history: CommitmentHistoryResponse;
}) {
  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Commitment History</Text>
      <Text style={styles.subheading}>Recent completed, failed, replaced, or cancelled plans.</Text>

      {history.entries.length > 0 ? (
        history.entries.slice(0, 8).map((entry, index) => (
          <View key={`${entry.commitment_key}_${entry.completed_on_date || index}`} style={styles.item}>
            <View style={styles.itemHeader}>
              <Text style={styles.itemTitle}>{entry.title}</Text>
              <Text style={[styles.status, { color: statusBadgeColor(entry.status) }]}>{entry.status}</Text>
            </View>
            <Text style={styles.meta}>
              {entry.start_date || 'n/a'} to {entry.target_end_date || 'n/a'}
            </Text>
            <Text style={styles.meta}>
              Adherence {Math.round(entry.adherence_score)} | Momentum {Math.round(entry.momentum_score)}
            </Text>
            {entry.completion_summary ? <Text style={styles.summary}>{entry.completion_summary}</Text> : null}
            {entry.reward_summary ? <Text style={styles.reward}>Reward: {entry.reward_summary}</Text> : null}
          </View>
        ))
      ) : (
        <Text style={styles.empty}>No commitment history yet.</Text>
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
    gap: 8,
  },
  heading: {
    color: theme.ui.text.onLight,
    fontSize: 17,
    fontWeight: '800',
  },
  subheading: {
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
  },
  itemTitle: {
    color: theme.ui.text.onLight,
    fontSize: 13,
    fontWeight: '700',
    flex: 1,
  },
  status: {
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  meta: {
    color: theme.ui.text.onLightMuted,
    fontSize: 11,
    fontWeight: '700',
  },
  summary: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  reward: {
    color: theme.ui.positive,
    fontSize: 12,
    lineHeight: 17,
  },
  empty: {
    color: theme.ui.text.onLightMuted,
    fontSize: 12,
  },
});
