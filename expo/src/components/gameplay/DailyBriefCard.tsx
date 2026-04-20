import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import HighlightOnChangeView from '@/components/motion/HighlightOnChangeView';
import SlideFadeInOnChange from '@/components/motion/SlideFadeInOnChange';
import { alpha, theme } from '@/design/theme';
import { PlayerDashboardResponse } from '@/types/gameplay';

function firstMeaningfulLine(value: string | null | undefined): string {
  return String(value || '')
    .split(/(?<=[.!?])\s+/)
    .map((entry) => entry.trim())
    .find(Boolean) || 'No summary available.';
}

export default function DailyBriefCard({
  dashboard,
  impactBullets = [],
  dayKey,
}: {
  dashboard: PlayerDashboardResponse;
  impactBullets?: string[];
  dayKey?: string | number;
}) {
  const summary = firstMeaningfulLine(dashboard.daily_brief);
  const heroWatchValue = `${dashboard.headline || ''}|${summary}`;
  const revealKey = `${String(dayKey ?? '')}|${heroWatchValue}`;
  const visibleBullets = impactBullets.filter((entry) => String(entry || '').trim()).slice(0, 3);

  return (
    <View style={styles.card}>
      <HighlightOnChangeView watchValue={heroWatchValue} style={styles.heroBlock}>
        <SlideFadeInOnChange watchValue={`${revealKey}_headline`} delayMs={0}>
          <Text style={styles.headerLabel}>Daily Brief</Text>
          <Text style={styles.headline}>{dashboard.headline || 'Today at Gold Penny'}</Text>
        </SlideFadeInOnChange>
        <SlideFadeInOnChange watchValue={`${revealKey}_summary`} delayMs={100}>
          <Text style={styles.summary}>{summary}</Text>
        </SlideFadeInOnChange>
        {visibleBullets.length > 0 ? (
          <SlideFadeInOnChange watchValue={`${revealKey}_macro`} delayMs={200}>
            <View style={styles.bulletList}>
              {visibleBullets.map((entry) => (
                <Text key={entry} style={styles.bulletItem}>
                  {'- '}
                  {entry}
                </Text>
              ))}
            </View>
          </SlideFadeInOnChange>
        ) : null}
      </HighlightOnChangeView>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: alpha(theme.ui.info, 0.18),
    borderRadius: theme.radius.xl,
    backgroundColor: theme.ui.bg.card,
    padding: theme.spacing.lg,
    ...theme.shadow.md,
  },
  heroBlock: {
    gap: theme.spacing.xs,
  },
  headerLabel: {
    ...theme.typography.caption,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    color: theme.ui.info,
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
  bulletList: {
    gap: theme.spacing.xxs,
    paddingTop: theme.spacing.xs,
  },
  bulletItem: {
    color: theme.ui.text.onLightMuted,
    ...theme.typography.bodySm,
    lineHeight: 18,
  },
});
