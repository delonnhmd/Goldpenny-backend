import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { theme } from '@/design/theme';

import SurfaceCard from './SurfaceCard';

export default function EmptyStateView({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <SurfaceCard variant="muted">
      <View style={styles.wrap}>
        <Text style={styles.title}>{title}</Text>
        {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
      </View>
    </SurfaceCard>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: theme.spacing.xs,
  },
  title: {
    color: theme.color.textPrimary,
    ...theme.typography.headingSm,
  },
  subtitle: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
});
