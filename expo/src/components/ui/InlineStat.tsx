import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { theme } from '@/design/theme';

export default function InlineStat({
  label,
  value,
  tone = 'default',
}: {
  label: string;
  value: string;
  tone?: 'default' | 'positive' | 'warning' | 'danger' | 'info';
}) {
  return (
    <View style={styles.row}>
      <Text style={styles.label}>{label}</Text>
      <Text style={[styles.value, tone !== 'default' ? toneStyle[tone] : null]}>{value}</Text>
    </View>
  );
}

const toneStyle = StyleSheet.create({
  positive: { color: theme.color.positive },
  warning: { color: theme.color.warning },
  danger: { color: theme.color.danger },
  info: { color: theme.color.info },
});

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: theme.spacing.sm,
  },
  label: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
  value: {
    color: theme.color.textPrimary,
    ...theme.typography.label,
  },
});
