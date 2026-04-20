import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { theme } from '@/design/theme';
import { marketMoodColor, marketMoodLabel } from '@/lib/economyPresentationFormatters';
import { MarketOverviewResponse } from '@/types/economyPresentation';

export default function MarketOverviewCard({ overview }: { overview: MarketOverviewResponse }) {
  const moodColor = marketMoodColor(overview.current_market_mood);

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.heading}>Basket Overview</Text>
        <View style={[styles.moodChip, { borderColor: `${moodColor}55`, backgroundColor: `${moodColor}12` }]}>
          <Text style={[styles.moodText, { color: moodColor }]}>{marketMoodLabel(overview.current_market_mood)}</Text>
        </View>
      </View>
      <Text style={styles.explainer}>{overview.short_explainer}</Text>

      <View style={styles.columnList}>
        <View style={styles.column}>
          <Text style={styles.columnTitle}>Headline Drivers</Text>
          {overview.headline_drivers.slice(0, 3).map((item, index) => (
            <Text key={`driver_${index}`} style={styles.itemText}>- {item}</Text>
          ))}
        </View>
        <View style={styles.column}>
          <Text style={[styles.columnTitle, styles.winnerTitle]}>Top Winners</Text>
          {overview.top_winners.slice(0, 3).map((item, index) => (
            <Text key={`winner_${index}`} style={styles.itemText}>- {item}</Text>
          ))}
        </View>
        <View style={styles.column}>
          <Text style={[styles.columnTitle, styles.loserTitle]}>Top Losers</Text>
          {overview.top_losers.slice(0, 3).map((item, index) => (
            <Text key={`loser_${index}`} style={styles.itemText}>- {item}</Text>
          ))}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.xl,
    backgroundColor: theme.color.surface,
    padding: theme.spacing.md,
    gap: theme.spacing.sm,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  heading: {
    ...theme.typography.headingSm,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  moodChip: {
    borderWidth: 1,
    borderRadius: theme.radius.pill,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  moodText: {
    ...theme.typography.caption,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  explainer: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
  columnList: {
    gap: theme.spacing.sm,
  },
  column: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.navTile,
    backgroundColor: theme.ui.bg.cardRaised,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  columnTitle: {
    ...theme.typography.caption,
    color: theme.color.textPrimary,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
  winnerTitle: {
    color: theme.ui.positive,
  },
  loserTitle: {
    color: theme.ui.danger,
  },
  itemText: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
});
