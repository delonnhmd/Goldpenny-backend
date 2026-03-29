import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { theme } from '@/design/theme';

import Divider from './Divider';
import SurfaceCard, { SurfaceCardVariant } from './SurfaceCard';

export default function SectionCard({
  title,
  summary,
  children,
  variant = 'default',
}: {
  title: string;
  summary?: string | null;
  children: React.ReactNode;
  variant?: SurfaceCardVariant;
}) {
  return (
    <SurfaceCard variant={variant}>
      <View style={styles.header}>
        <Text style={styles.title}>{title}</Text>
        {summary ? <Text style={styles.summary}>{summary}</Text> : null}
      </View>
      <Divider />
      <View style={styles.body}>{children}</View>
    </SurfaceCard>
  );
}

const styles = StyleSheet.create({
  header: {
    gap: theme.spacing.xs,
  },
  title: {
    color: theme.color.textPrimary,
    ...theme.typography.headingSm,
  },
  summary: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
  body: {
    gap: theme.spacing.sm,
  },
});
