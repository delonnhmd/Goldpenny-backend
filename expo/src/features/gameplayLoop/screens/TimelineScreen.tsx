import { useFocusEffect } from '@react-navigation/native';
import { router } from 'expo-router';
import React, { useCallback, useMemo, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import EmptyStateView from '@/components/ui/EmptyStateView';
import ErrorStateView from '@/components/ui/ErrorStateView';
import LoadingSkeleton from '@/components/ui/LoadingSkeleton';
import PrimaryButton from '@/components/ui/PrimaryButton';
import { alpha, theme } from '@/design/theme';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import { getPlayerTimeline } from '@/lib/api/gameplay';
import { TimelineEventItem } from '@/types/gameplay';

import { useGameplayLoop } from '../context';
import { GameplaySummaryCard } from '../components/GameplayUIParts';
import GameplayLoopScaffold from '../GameplayLoopScaffold';

interface TimelineDayGroup {
  day: number;
  events: TimelineEventItem[];
}

function normalizeError(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message.trim();
  return 'Timeline is unavailable right now.';
}

export function groupTimelineEventsByDay(events: TimelineEventItem[]): TimelineDayGroup[] {
  const groups = new Map<number, TimelineEventItem[]>();
  for (const event of events) {
    const day = Math.max(1, Math.round(Number(event.day) || 1));
    groups.set(day, [...(groups.get(day) || []), event]);
  }
  return [...groups.entries()]
    .sort(([left], [right]) => right - left)
    .map(([day, dayEvents]) => ({ day, events: dayEvents }));
}

export function timelineIconLabel(icon: string | null | undefined): string {
  const clean = String(icon || '').trim();
  if (!clean) return 'EV';
  const parts = clean.split(/[-_\s]+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0] || ''}${parts[1][0] || ''}`.toUpperCase();
  }
  return clean.slice(0, 2).toUpperCase();
}

function impactColor(impactLevel: TimelineEventItem['impact_level']): string {
  if (impactLevel === 'high') return theme.ui.danger;
  if (impactLevel === 'medium') return theme.ui.warning;
  return theme.ui.info;
}

function typeLabel(type: TimelineEventItem['type']): string {
  if (type === 'economy') return 'Economy';
  if (type === 'business') return 'Business';
  if (type === 'finance') return 'Finance';
  return 'Life';
}

function TimelineEventRow({ event, last }: { event: TimelineEventItem; last: boolean }) {
  const tone = impactColor(event.impact_level);
  return (
    <View style={styles.eventRow}>
      <View style={styles.markerColumn}>
        <View style={[styles.iconBadge, { borderColor: tone, backgroundColor: alpha(tone, 0.14) }]}>
          <Text style={[styles.iconText, { color: tone }]}>{timelineIconLabel(event.icon)}</Text>
        </View>
        {!last ? <View style={styles.markerLine} /> : null}
      </View>
      <View style={styles.eventBody}>
        <View style={styles.eventMetaRow}>
          <Text style={[styles.eventType, { color: tone }]}>{typeLabel(event.type)}</Text>
          <Text style={styles.impactLabel}>{event.impact_level}</Text>
        </View>
        <Text style={styles.eventTitle}>{event.title || 'Run event'}</Text>
        <Text style={styles.eventDescription}>
          {event.description || 'A meaningful run event was recorded.'}
        </Text>
      </View>
    </View>
  );
}

function TimelineDaySection({ group }: { group: TimelineDayGroup }) {
  return (
    <View style={styles.daySection}>
      <Text style={styles.dayLabel}>Day {group.day}</Text>
      <View style={styles.dayEvents}>
        {group.events.map((event, index) => (
          <TimelineEventRow
            key={`${group.day}_${event.type}_${event.title}_${index}`}
            event={event}
            last={index === group.events.length - 1}
          />
        ))}
      </View>
    </View>
  );
}

export default function TimelineScreen() {
  useScreenTimer('timeline');
  const loop = useGameplayLoop();
  const [events, setEvents] = useState<TimelineEventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadTimeline = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await getPlayerTimeline(loop.playerId, { limit: 100 });
      setEvents(payload);
    } catch (loadError) {
      setEvents([]);
      setError(normalizeError(loadError));
    } finally {
      setLoading(false);
    }
  }, [loop.playerId]);

  useFocusEffect(useCallback(() => {
    let active = true;
    setLoading(true);
    setError(null);
    void getPlayerTimeline(loop.playerId, { limit: 100 })
      .then((payload) => {
        if (!active) return;
        setEvents(payload);
      })
      .catch((loadError) => {
        if (!active) return;
        setEvents([]);
        setError(normalizeError(loadError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [loop.playerId]));

  const groups = useMemo(() => groupTimelineEventsByDay(events), [events]);

  return (
    <GameplayLoopScaffold
      title="Timeline"
      subtitle="The key moments from this run"
      activeNavKey="portfolio"
    >
      <GameplaySummaryCard
        eyebrow="Run Story"
        title="Event Timeline"
        right={(
          <PrimaryButton
            label="Portfolio"
            onPress={() => router.push(`/gameplay/loop/${loop.playerId}/portfolio`)}
            style={styles.headerButton}
          />
        )}
      >
        {loading ? <LoadingSkeleton lines={5} /> : null}
        {!loading && error ? (
          <ErrorStateView
            title="Timeline unavailable"
            message={error}
            onRetry={() => {
              void loadTimeline();
            }}
          />
        ) : null}
        {!loading && !error && groups.length === 0 ? (
          <EmptyStateView
            title="No major events yet"
            subtitle="Meaningful economy, business, life, and finance moments will appear here as the run develops."
          />
        ) : null}
        {!loading && !error && groups.length > 0 ? (
          <View style={styles.timelineStack}>
            {groups.map((group) => (
              <TimelineDaySection key={`day_${group.day}`} group={group} />
            ))}
          </View>
        ) : null}
      </GameplaySummaryCard>
    </GameplayLoopScaffold>
  );
}

const styles = StyleSheet.create({
  headerButton: {
    minHeight: 42,
    paddingHorizontal: theme.spacing.md,
  },
  timelineStack: {
    gap: theme.spacing.lg,
  },
  daySection: {
    gap: theme.spacing.sm,
  },
  dayLabel: {
    color: theme.ui.text.onDark,
    ...theme.typography.label,
    fontWeight: '900',
  },
  dayEvents: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.sm,
    gap: theme.spacing.xs,
  },
  eventRow: {
    flexDirection: 'row',
    alignItems: 'stretch',
    gap: theme.spacing.sm,
  },
  markerColumn: {
    width: 38,
    alignItems: 'center',
  },
  iconBadge: {
    width: 34,
    height: 34,
    borderRadius: theme.ui.radius.chip,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconText: {
    ...theme.typography.caption,
    fontWeight: '900',
  },
  markerLine: {
    flex: 1,
    width: 1,
    minHeight: theme.spacing.md,
    backgroundColor: theme.ui.border,
  },
  eventBody: {
    flex: 1,
    paddingBottom: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  eventMetaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: theme.spacing.sm,
  },
  eventType: {
    ...theme.typography.caption,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  impactLabel: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  eventTitle: {
    color: theme.ui.text.onDark,
    ...theme.typography.bodyMd,
    fontWeight: '900',
  },
  eventDescription: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
});
