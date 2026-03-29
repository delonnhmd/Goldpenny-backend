import React from 'react';
import { StyleSheet, Text } from 'react-native';

import SurfaceCard from '@/components/ui/SurfaceCard';
import { theme } from '@/design/theme';

export default function EmptyStateCard({
  title = 'No data yet',
  subtitle = 'This section will populate after more gameplay activity.',
}: {
  title?: string;
  subtitle?: string;
}) {
  return (
    <SurfaceCard>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.subtitle}>{subtitle}</Text>
    </SurfaceCard>
  );
}

const styles = StyleSheet.create({
  title: {
    color: theme.color.textPrimary,
    ...theme.typography.headingSm,
  },
  subtitle: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
});
