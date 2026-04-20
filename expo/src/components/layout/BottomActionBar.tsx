import React from 'react';
import { StyleSheet, View } from 'react-native';

import { alpha, theme } from '@/design/theme';

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
    borderTopColor: alpha(theme.ui.border, 0.58),
    backgroundColor: theme.ui.bg.card,
    paddingHorizontal: theme.spacing.lg,
    paddingTop: theme.spacing.md,
    paddingBottom: theme.spacing.md,
    gap: theme.spacing.md,
    ...theme.shadow.md,
  },
});
