import React, { useEffect, useRef } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';

import AppShell from '@/components/layout/AppShell';
import PageContainer from '@/components/layout/PageContainer';
import PrimaryButton from '@/components/ui/PrimaryButton';
import { theme } from '@/design/theme';
import { formatMoney } from '@/lib/gameplayFormatters';
import { RunEndSummary } from '@/types/gameplay';

import { useGameplayLoop } from '../context';

function metric(label: string, value: string | number) {
  return { label, value: String(value) };
}

function summaryMetrics(status: string, summary: RunEndSummary | null) {
  if (!summary) return [];
  if (status === 'retired') {
    return [
      metric('Title', String(summary.retirement_title || 'Stable Owner')),
      metric('Net worth', formatMoney(Number(summary.net_worth || 0))),
      metric('Days survived', Number(summary.days_survived || 0)),
      metric('Cash', formatMoney(Number(summary.cash || 0))),
      metric('Debt', formatMoney(Number(summary.debt || 0))),
      metric('Businesses', Number(summary.businesses_owned || 0)),
      metric('Land', Number(summary.land_owned || 0)),
      metric('Best streak', Number(summary.best_streak || 0)),
    ];
  }
  return [
    metric('Final cash', formatMoney(Number(summary.cash || 0))),
    metric('Debt', formatMoney(Number(summary.debt || 0))),
    metric('Credit score', Number(summary.credit_score || 0)),
    metric('Net worth', formatMoney(Number(summary.net_worth || 0))),
    metric('Businesses', Number(summary.businesses_owned || 0)),
    metric('Land', Number(summary.land_owned || 0)),
    metric('Best streak', Number(summary.best_streak || 0)),
  ];
}

export default function EndOfRunScreen() {
  const loop = useGameplayLoop();
  const runStatus = loop.runStatus;
  const status = runStatus?.run_status || 'active';
  const summary = runStatus?.run_end_summary || loop.endOfDaySummary?.end_state?.summary || null;
  const isRetired = status === 'retired';
  const isBankrupt = status === 'bankrupt';
  const daysSurvived = Number(summary?.days_survived || runStatus?.run_end_day || 0);
  const refreshRef = useRef(loop.refresh);

  useEffect(() => {
    refreshRef.current = loop.refresh;
  }, [loop.refresh]);

  useEffect(() => {
    void refreshRef.current({ silent: true, includeEndOfDaySummary: true });
  }, [loop.playerId]);

  useEffect(() => {
    if (!loop.loading && status === 'active') {
      router.replace(`/gameplay/loop/${loop.playerId}/life`);
    }
  }, [loop.loading, loop.playerId, status]);

  const title = isRetired ? 'You Retired' : 'Run Ended: Bankruptcy';
  const subtitle = isRetired
    ? 'You turned survival into ownership.'
    : `You survived ${daysSurvived || 0} days before financial pressure caught up.`;
  const metrics = summaryMetrics(status, summary);

  return (
    <AppShell title="Run Complete" subtitle="Final outcome">
      <PageContainer>
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
        >
          <View style={[styles.hero, isBankrupt ? styles.bankruptHero : styles.retiredHero]}>
            <Text style={styles.kicker}>{isRetired ? 'Victory Ending' : 'Failure Ending'}</Text>
            <Text style={styles.title}>{title}</Text>
            <Text style={styles.subtitle}>{subtitle}</Text>
          </View>

          <View style={styles.metricGrid}>
            {metrics.map((item) => (
              <View key={item.label} style={styles.metricCell}>
                <Text style={styles.metricLabel}>{item.label}</Text>
                <Text style={styles.metricValue}>{item.value}</Text>
              </View>
            ))}
          </View>

          <View style={styles.actions}>
            <PrimaryButton
              testID="end-run-start-new-button"
              label="Start New Run"
              onPress={() => {
                // TODO: replace with backend run-reset/new-run endpoint once that flow exists.
                router.replace('/auth/create-player');
              }}
            />
            {isRetired ? (
              <Pressable disabled style={[styles.secondaryButton, styles.secondaryDisabled]}>
                <Text style={styles.secondaryText}>Share Summary</Text>
              </Pressable>
            ) : (
              <Pressable
                testID="end-run-review-summary-button"
                style={styles.secondaryButton}
                onPress={() => router.push(`/gameplay/loop/${loop.playerId}/summary`)}
              >
                <Text style={styles.secondaryText}>Review Final Summary</Text>
              </Pressable>
            )}
          </View>
        </ScrollView>
      </PageContainer>
    </AppShell>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flex: 1,
  },
  content: {
    paddingTop: theme.spacing.lg,
    paddingBottom: theme.spacing.xxxl,
    gap: theme.spacing.lg,
  },
  hero: {
    borderWidth: 1,
    borderRadius: theme.ui.radius.card,
    padding: theme.spacing.xl,
    gap: theme.spacing.sm,
    backgroundColor: theme.ui.bg.card,
  },
  bankruptHero: {
    borderColor: theme.ui.danger,
  },
  retiredHero: {
    borderColor: theme.ui.positive,
  },
  kicker: {
    color: theme.ui.info,
    ...theme.typography.caption,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  title: {
    color: theme.ui.text.onDark,
    fontSize: 32,
    fontWeight: '900',
  },
  subtitle: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.bodyMd,
    fontWeight: '700',
  },
  metricGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  metricCell: {
    flexGrow: 1,
    flexBasis: '46%',
    minWidth: 138,
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  metricLabel: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  metricValue: {
    color: theme.ui.text.onDark,
    ...theme.typography.headingSm,
    fontWeight: '900',
  },
  actions: {
    gap: theme.spacing.sm,
  },
  secondaryButton: {
    minHeight: 48,
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: theme.ui.bg.cardRaised,
    paddingHorizontal: theme.spacing.lg,
  },
  secondaryDisabled: {
    opacity: 0.45,
  },
  secondaryText: {
    color: theme.ui.text.onDark,
    ...theme.typography.label,
    fontWeight: '800',
    textAlign: 'center',
  },
});
