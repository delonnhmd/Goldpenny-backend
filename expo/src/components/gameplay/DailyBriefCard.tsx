import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import HighlightOnChangeView from '@/components/motion/HighlightOnChangeView';
import { theme } from '@/design/theme';
import { PlayerDashboardResponse } from '@/types/gameplay';

function firstMeaningfulLine(value: string | null | undefined): string {
  return String(value || '')
    .split(/(?<=[.!?])\s+/)
    .map((entry) => entry.trim())
    .find(Boolean) || 'No summary available.';
}

export default function DailyBriefCard({
  dashboard,
}: {
  dashboard: PlayerDashboardResponse;
}) {
  const summary = firstMeaningfulLine(dashboard.daily_brief);
  const heroWatchValue = `${dashboard.headline || ''}|${summary}`;

  return (
    <View style={styles.card}>
      <HighlightOnChangeView watchValue={heroWatchValue} style={styles.heroBlock}>
        <Text style={styles.headerLabel}>Daily Brief</Text>
        <Text style={styles.headline}>{dashboard.headline || 'Today at Gold Penny'}</Text>
        <Text style={styles.summary}>{summary}</Text>
      </HighlightOnChangeView>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: '#d6e1f2',
    borderRadius: theme.radius.xl,
    backgroundColor: '#fdfefe',
    padding: theme.spacing.lg,
  },
  heroBlock: {
    gap: theme.spacing.xs,
  },
  headerLabel: {
    ...theme.typography.caption,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    color: '#1d4ed8',
    fontWeight: '800',
  },
  headline: {
    ...theme.typography.headingLg,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  summary: {
    color: theme.color.textSecondary,
    ...theme.typography.bodyMd,
    lineHeight: 20,
  },
});
