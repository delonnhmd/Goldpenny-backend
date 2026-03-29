import React from 'react';
import { StyleSheet, View } from 'react-native';

import { theme } from '@/design/theme';

export default function ActionRow({
  children,
}: {
  children: React.ReactNode;
}) {
  return <View style={styles.row}>{children}</View>;
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
});
