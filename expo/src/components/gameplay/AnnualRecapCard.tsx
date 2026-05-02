import React, { useMemo, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import PrimaryButton from '@/components/ui/PrimaryButton';
import { theme } from '@/design/theme';
import { formatMoney } from '@/lib/gameplayFormatters';
import { AnnualRecapResponse } from '@/types/gameplay';

type RecapInput = Partial<AnnualRecapResponse> | null | undefined;

export interface AnnualRecapDisplayRow {
  key: string;
  label: string;
  value: string;
}

function safeNumber(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function safeText(value: unknown, fallback: string): string {
  const raw = typeof value === 'string' ? value.trim() : '';
  return raw || fallback;
}

function formatCount(value: unknown): string {
  return String(Math.max(0, Math.round(safeNumber(value, 0))));
}

function formatSignedMoney(value: unknown): string {
  const amount = safeNumber(value, 0);
  if (amount === 0) return formatMoney(0);
  return `${amount > 0 ? '+' : '-'}${formatMoney(Math.abs(amount))}`;
}

export function buildAnnualRecapDisplayRows(recap: RecapInput): AnnualRecapDisplayRow[] {
  return [
    { key: 'days_survived', label: 'Days survived', value: formatCount(recap?.days_survived) },
    { key: 'net_worth_change', label: 'Net worth change', value: formatSignedMoney(recap?.net_worth_change) },
    { key: 'cash', label: 'Cash', value: formatMoney(safeNumber(recap?.cash, 0)) },
    { key: 'debt', label: 'Debt', value: formatMoney(safeNumber(recap?.debt, 0)) },
    { key: 'credit_score', label: 'Credit score', value: formatCount(recap?.credit_score ?? 650) },
    { key: 'businesses_owned', label: 'Businesses owned', value: formatCount(recap?.businesses_owned) },
    { key: 'land_owned', label: 'Land owned', value: formatCount(recap?.land_owned) },
    { key: 'best_streak', label: 'Best streak', value: `${formatCount(recap?.best_streak)} days` },
  ];
}

export default function AnnualRecapCard({
  recap,
  preview = false,
  onViewFullStory,
}: {
  recap: RecapInput;
  preview?: boolean;
  onViewFullStory?: () => void;
}) {
  const [shareMessage, setShareMessage] = useState<string | null>(null);
  const rows = useMemo(() => buildAnnualRecapDisplayRows(recap), [recap]);
  const title = safeText(recap?.title, 'Year Recap');
  const biggestWin = safeText(recap?.biggest_win, 'No major win recorded yet.');
  const biggestLoss = safeText(recap?.biggest_loss, 'No major loss recorded yet.');
  const topEvent = safeText(recap?.top_event, 'No major event recorded yet.');
  const year = Math.max(1, Math.round(safeNumber(recap?.year, 1)));

  return (
    <View style={styles.card} testID="annual-recap-card">
      <View style={styles.header}>
        <Text style={styles.kicker}>{preview ? '30-Day Preview' : `Year ${year} Recap`}</Text>
        <Text style={styles.title}>{title}</Text>
      </View>

      <View style={styles.grid}>
        {rows.map((row) => (
          <View key={row.key} style={styles.metric}>
            <Text style={styles.metricLabel}>{row.label}</Text>
            <Text style={styles.metricValue}>{row.value}</Text>
          </View>
        ))}
      </View>

      <View style={styles.storyStack}>
        <View style={styles.storyPanel}>
          <Text style={styles.storyLabel}>Biggest win</Text>
          <Text style={styles.storyText}>{biggestWin}</Text>
        </View>
        <View style={styles.storyPanel}>
          <Text style={styles.storyLabel}>Biggest loss</Text>
          <Text style={styles.storyText}>{biggestLoss}</Text>
        </View>
        <View style={styles.storyPanel}>
          <Text style={styles.storyLabel}>Top event</Text>
          <Text style={styles.storyText}>{topEvent}</Text>
        </View>
      </View>

      <View style={styles.actionRow}>
        {onViewFullStory ? (
          <PrimaryButton
            testID="annual-recap-full-story-button"
            label="View Full Story"
            onPress={onViewFullStory}
            style={styles.actionButton}
          />
        ) : null}
        <PrimaryButton
          testID="annual-recap-share-button"
          label="Share Recap"
          onPress={() => setShareMessage('Sharing coming soon')}
          style={styles.actionButton}
        />
      </View>
      {shareMessage ? <Text style={styles.shareMessage}>{shareMessage}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.card,
    backgroundColor: theme.ui.bg.card,
    padding: theme.spacing.lg,
    gap: theme.spacing.md,
  },
  header: {
    gap: theme.spacing.xs,
  },
  kicker: {
    color: theme.ui.info,
    ...theme.typography.caption,
    fontWeight: '900',
    letterSpacing: 0,
    textTransform: 'uppercase',
  },
  title: {
    color: theme.ui.text.onDark,
    ...theme.typography.headingMd,
    fontWeight: '900',
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  metric: {
    flexGrow: 1,
    minWidth: 128,
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
    letterSpacing: 0,
    textTransform: 'uppercase',
  },
  metricValue: {
    color: theme.ui.text.onDark,
    ...theme.typography.bodyMd,
    fontWeight: '900',
  },
  storyStack: {
    gap: theme.spacing.sm,
  },
  storyPanel: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  storyLabel: {
    color: theme.ui.text.onDarkMuted,
    ...theme.typography.caption,
    fontWeight: '800',
    letterSpacing: 0,
    textTransform: 'uppercase',
  },
  storyText: {
    color: theme.ui.text.onDark,
    ...theme.typography.bodySm,
    fontWeight: '800',
  },
  actionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  actionButton: {
    flexGrow: 1,
    minWidth: 150,
  },
  shareMessage: {
    color: theme.ui.info,
    ...theme.typography.bodySm,
    fontWeight: '800',
    textAlign: 'center',
  },
});
