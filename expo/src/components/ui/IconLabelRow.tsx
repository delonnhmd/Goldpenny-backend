import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { theme } from '@/design/theme';

export default function IconLabelRow({
  icon,
  label,
  value,
}: {
  icon?: string;
  label: string;
  value?: string | null;
}) {
  return (
    <View style={styles.row}>
      <View style={styles.labelWrap}>
        {icon ? <Text style={styles.icon}>{icon}</Text> : null}
        <Text style={styles.label}>{label}</Text>
      </View>
      {value ? <Text style={styles.value}>{value}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: theme.spacing.sm,
  },
  labelWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.xs,
    flexShrink: 1,
  },
  icon: {
    color: theme.color.textSecondary,
    fontSize: theme.iconSize.sm,
  },
  label: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
  value: {
    color: theme.color.textPrimary,
    ...theme.typography.label,
    flexShrink: 1,
    textAlign: 'right',
  },
});
