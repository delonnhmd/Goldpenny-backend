import React from 'react';
import { StyleSheet, View } from 'react-native';

import { theme } from '@/design/theme';

export default function ActionPreviewTemplate({
  header,
  body,
  footer,
}: {
  header: React.ReactNode;
  body: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <View style={styles.wrap}>
      <View style={styles.header}>{header}</View>
      <View style={styles.body}>{body}</View>
      {footer ? <View style={styles.footer}>{footer}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    width: '100%',
    backgroundColor: theme.color.surface,
  },
  header: {
    borderBottomWidth: 1,
    borderBottomColor: theme.color.border,
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.md,
  },
  body: {
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.md,
    gap: theme.spacing.sm,
  },
  footer: {
    borderTopWidth: 1,
    borderTopColor: theme.color.border,
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.md,
  },
});
