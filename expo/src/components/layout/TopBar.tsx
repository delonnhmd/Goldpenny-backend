import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { theme } from '@/design/theme';

export default function TopBar({
  title,
  subtitle,
  rightContent,
}: {
  title: string;
  subtitle?: string | null;
  rightContent?: React.ReactNode;
}) {
  return (
    <View style={styles.container}>
      <View style={styles.copy}>
        <Text style={styles.title}>{title}</Text>
        {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
      </View>
      {rightContent ? <View style={styles.right}>{rightContent}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderBottomWidth: 1,
    borderBottomColor: theme.color.border,
    backgroundColor: theme.color.surface,
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.md,
    flexWrap: 'wrap',
  },
  copy: {
    gap: theme.spacing.xxs,
    flexShrink: 1,
  },
  title: {
    color: theme.color.textPrimary,
    ...theme.typography.headingMd,
  },
  subtitle: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
  right: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.sm,
    flexWrap: 'wrap',
  },
});
