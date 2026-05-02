import { useFocusEffect } from '@react-navigation/native';
import { router } from 'expo-router';
import React, { useCallback, useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import AppShell from '@/components/layout/AppShell';
import PageContainer from '@/components/layout/PageContainer';
import EmptyStateView from '@/components/ui/EmptyStateView';
import ErrorStateView from '@/components/ui/ErrorStateView';
import LoadingSkeleton from '@/components/ui/LoadingSkeleton';
import PrimaryButton from '@/components/ui/PrimaryButton';
import { alpha, theme } from '@/design/theme';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import { getPendingBlackSwanEvent, markBlackSwanSeen } from '@/lib/api/gameplay';
import { BlackSwanEventResponse } from '@/types/gameplay';

import { useGameplayLoop } from '../context';

function normalizeError(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message.trim();
  return 'Major event details are unavailable right now.';
}

function titleCase(value: string): string {
  return String(value || 'Economy event')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function takeList(values: unknown, fallback: string[], limit = 3): string[] {
  if (!Array.isArray(values)) return fallback.slice(0, limit);
  const cleaned = values.map((value) => String(value || '').trim()).filter(Boolean);
  return (cleaned.length ? cleaned : fallback).slice(0, limit);
}

function useBlackSwanMoment(playerId: string) {
  const [event, setEvent] = useState<BlackSwanEventResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [markingSeen, setMarkingSeen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await getPendingBlackSwanEvent(playerId);
      setEvent(payload);
    } catch (loadError) {
      setEvent(null);
      setError(normalizeError(loadError));
    } finally {
      setLoading(false);
    }
  }, [playerId]);

  const markSeen = useCallback(async () => {
    if (!event) return;
    setMarkingSeen(true);
    try {
      await markBlackSwanSeen(playerId, event.id);
    } finally {
      setMarkingSeen(false);
    }
  }, [event, playerId]);

  return { event, loading, error, markingSeen, load, markSeen };
}

export default function BlackSwanMomentScreen() {
  useScreenTimer('black_swan');
  const loop = useGameplayLoop();
  const { event, loading, error, markingSeen, load, markSeen } = useBlackSwanMoment(loop.playerId);

  useFocusEffect(useCallback(() => {
    let active = true;
    void load().finally(() => {
      if (!active) return;
    });
    return () => {
      active = false;
    };
  }, [load]));

  const payload = event?.payload || null;
  const affectedSystems = useMemo(
    () => takeList(payload?.affected_systems, ['Economy', 'Cash flow', 'Daily plan'], 6),
    [payload],
  );
  const changedToday = useMemo(
    () => takeList(payload?.what_changed_today, ['A rare major event moved through the city today.'], 3),
    [payload],
  );
  const whatThisMeans = useMemo(
    () => takeList(payload?.what_this_means, [
      'Review the daily brief before committing time.',
      'Watch cash, debt, and inventory pressure.',
      'Keep today flexible until the risk is clear.',
    ], 3),
    [payload],
  );

  const handlePlanDay = useCallback(async () => {
    if (event) {
      await markSeen();
    }
    await loop.refresh({ silent: true, includeEndOfDaySummary: true });
    router.replace(`/gameplay/loop/${loop.playerId}/life`);
  }, [event, loop, markSeen]);

  return (
    <AppShell title="Major Event" subtitle="A rare shock moved through the city">
      <PageContainer>
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
        >
          {loading ? (
            <View style={styles.panel}>
              <LoadingSkeleton lines={6} />
            </View>
          ) : null}

          {!loading && error ? (
            <ErrorStateView title="Major event unavailable" message={error} onRetry={load} />
          ) : null}

          {!loading && !error && !event ? (
            <View style={styles.panel}>
              <EmptyStateView
                title="No major event pending"
                subtitle="You are clear to continue planning the day."
              />
              <PrimaryButton label="Plan My Day" onPress={handlePlanDay} style={styles.primaryButton} />
            </View>
          ) : null}

          {!loading && !error && event ? (
            <>
              <View style={styles.hero}>
                <Text style={styles.kicker}>Black Swan</Text>
                <Text style={styles.dayLabel}>Day {event.day} / {titleCase(event.event_type)}</Text>
                <Text style={styles.title}>{event.title || 'Major Event'}</Text>
                <Text style={styles.description}>
                  {event.description || 'A major event moved through the city today.'}
                </Text>
              </View>

              <View style={styles.panel}>
                <Text style={styles.sectionTitle}>Affected Systems</Text>
                <View style={styles.chipRow}>
                  {affectedSystems.map((item) => (
                    <View key={item} style={styles.systemChip}>
                      <Text style={styles.systemChipText}>{item}</Text>
                    </View>
                  ))}
                </View>
              </View>

              <View style={styles.panel}>
                <Text style={styles.sectionTitle}>What Changed Today</Text>
                {changedToday.map((item) => (
                  <Text key={item} style={styles.bodyLine}>{item}</Text>
                ))}
              </View>

              <View style={styles.panel}>
                <Text style={styles.sectionTitle}>What This Means</Text>
                {whatThisMeans.map((item) => (
                  <View key={item} style={styles.bulletRow}>
                    <View style={styles.bulletDot} />
                    <Text style={styles.bulletText}>{item}</Text>
                  </View>
                ))}
              </View>

              <PrimaryButton
                testID="black-swan-plan-day-button"
                label={markingSeen ? 'Saving...' : 'Plan My Day'}
                disabled={markingSeen}
                onPress={handlePlanDay}
                style={styles.primaryButton}
              />
            </>
          ) : null}
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
    gap: theme.spacing.md,
  },
  hero: {
    minHeight: 300,
    borderWidth: 1,
    borderColor: theme.ui.danger,
    borderRadius: theme.ui.radius.card,
    backgroundColor: theme.ui.bg.card,
    padding: theme.spacing.xl,
    justifyContent: 'flex-end',
    gap: theme.spacing.sm,
  },
  kicker: {
    color: theme.ui.danger,
    ...theme.typography.caption,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  dayLabel: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.label,
    fontWeight: '800',
  },
  title: {
    color: theme.ui.text.onDark,
    fontSize: 34,
    lineHeight: 40,
    fontWeight: '900',
  },
  description: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.bodyMd,
    fontWeight: '700',
  },
  panel: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.sm,
  },
  sectionTitle: {
    color: theme.ui.text.onDark,
    ...theme.typography.label,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.xs,
  },
  systemChip: {
    borderWidth: 1,
    borderColor: theme.ui.danger,
    borderRadius: theme.ui.radius.chip,
    backgroundColor: alpha(theme.ui.danger, 0.12),
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  systemChipText: {
    color: theme.ui.text.onDark,
    ...theme.typography.caption,
    fontWeight: '800',
  },
  bodyLine: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.bodyMd,
    fontWeight: '700',
  },
  bulletRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: theme.spacing.sm,
  },
  bulletDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginTop: 7,
    backgroundColor: theme.ui.warning,
  },
  bulletText: {
    flex: 1,
    color: theme.ui.text.onDark,
    ...theme.typography.bodyMd,
    fontWeight: '700',
  },
  primaryButton: {
    minHeight: 52,
  },
});
