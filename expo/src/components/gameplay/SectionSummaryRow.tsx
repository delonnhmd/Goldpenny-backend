import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import StatusChip from '@/components/ui/StatusChip';
import { theme } from '@/design/theme';

export default function SectionSummaryRow({
  summary,
  statusLabel,
}: {
  summary: string;
  statusLabel?: string | null;
}) {
  return (
    <View style={styles.row}>
      <Text style={styles.summary}>{summary}</Text>
      {statusLabel ? <StatusChip label={statusLabel} status="neutral" /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.sm,
    flexWrap: 'wrap',
    paddingTop: theme.spacing.xs,
  },
  summary: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
    flexShrink: 1,
    lineHeight: 18,
  },
});
