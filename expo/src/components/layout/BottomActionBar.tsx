import React from 'react';
import { StyleSheet, View } from 'react-native';

import { theme } from '@/design/theme';

export default function BottomActionBar({
  children,
}: {
  children: React.ReactNode;
}) {
  return <View style={styles.bar}>{children}</View>;
}

const styles = StyleSheet.create({
  bar: {
    borderTopWidth: 1,
    borderTopColor: '#dbe4ef',
    backgroundColor: '#fcfdff',
    paddingHorizontal: theme.spacing.lg,
    paddingTop: theme.spacing.md,
    paddingBottom: theme.spacing.md,
    gap: theme.spacing.md,
    ...theme.shadow.md,
  },
});
