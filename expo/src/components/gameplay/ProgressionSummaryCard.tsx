import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import Card from '@/components/ui/Card';
import Chip from '@/components/ui/Chip';
import { theme } from '@/design/theme';
import { ProgressionSummaryResponse } from '@/types/progression';

export default function ProgressionSummaryCard({
  summary,
}: {
  summary: ProgressionSummaryResponse;
}) {
  return (
    <Card style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.heading}>Progression Summary</Text>
        <Chip label="Progress" variant="active" />
      </View>
      <Text style={styles.copy}>{summary.motivational_summary || 'Keep compounding small wins.'}</Text>

      {summary.suggested_focus.length > 0 ? (
        <Card variant="info" padded={false} style={styles.focusBlock}>
          <Text style={styles.blockTitle}>Suggested Focus</Text>
          {summary.suggested_focus.slice(0, 4).map((line, index) => (
            <Text key={`focus_${index}`} style={styles.blockText}>
              - {line}
            </Text>
          ))}
        </Card>
      ) : null}

      {summary.recently_completed.length > 0 ? (
        <Card variant="positive" padded={false} style={styles.completedBlock}>
          <Text style={styles.blockTitle}>Recently Completed</Text>
          {summary.recently_completed.slice(0, 4).map((entry) => (
            <Text key={`${entry.scope}_${entry.key}_${entry.credited_on}`} style={styles.blockText}>
              - {entry.title} ({entry.reward_summary})
            </Text>
          ))}
        </Card>
      ) : (
        <Text style={styles.empty}>No recent completions yet. Today&apos;s goals can start your streak.</Text>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: 8,
    padding: 14,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: theme.spacing.sm,
  },
  heading: {
    color: theme.ui.text.onDark,
    fontSize: 17,
    fontWeight: '800',
    flex: 1,
  },
  copy: {
    color: theme.ui.text.onDarkMuted,
    fontSize: 13,
    lineHeight: 18,
  },
  focusBlock: {
    padding: 10,
    gap: 4,
  },
  completedBlock: {
    padding: 10,
    gap: 4,
  },
  blockTitle: {
    color: theme.ui.text.onDark,
    fontSize: 12,
    fontWeight: '700',
  },
  blockText: {
    color: theme.ui.text.onDarkMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  empty: {
    color: theme.ui.text.onDarkMuted,
    fontSize: 12,
  },
});
