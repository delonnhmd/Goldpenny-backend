import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { alpha, theme } from '@/design/theme';

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
    borderBottomColor: alpha(theme.ui.border, 0.92),
    backgroundColor: theme.ui.bg.card,
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
    color: theme.ui.text.onDark,
    ...theme.typography.headingMd,
  },
  subtitle: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.bodySm,
  },
  right: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.sm,
    flexWrap: 'wrap',
  },
});
