import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { theme } from '@/design/theme';
import {
  formatIndexLevel,
  trendLabelText,
  trendTone,
  volatilityTone,
} from '@/lib/economyPresentationFormatters';
import { PriceTrendsResponse } from '@/types/economyPresentation';

function labelFromBasketKey(basketKey: string): string {
  return String(basketKey || '')
    .split('_')
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(' ');
}

export default function PriceTrendsCard({ trends }: { trends: PriceTrendsResponse }) {
  if (!trends.items.length) {
    return (
      <View style={styles.emptyCard}>
        <Text style={styles.emptyTitle}>Price Trends</Text>
        <Text style={styles.emptyText}>No basket movement is available right now.</Text>
      </View>
    );
  }

  return (
    <View style={styles.card}>
      <Text style={styles.heading}>Price Trends</Text>
      <Text style={styles.subheading}>Basket movement changes your costs and margins.</Text>

      <View style={styles.list}>
        {trends.items.slice(0, 5).map((item) => {
          const trendColor = trendTone(item.short_term_trend);
          const volColor = volatilityTone(item.volatility_label);
          return (
            <View key={item.basket_key} style={styles.row}>
              <View style={styles.rowHeader}>
                <Text style={styles.basketName}>{labelFromBasketKey(item.basket_key)}</Text>
                <Text style={styles.levelText}>{formatIndexLevel(item.current_level)}</Text>
              </View>
              <View style={styles.rowHeader}>
                <Text style={[styles.metaPill, { color: trendColor, borderColor: `${trendColor}55`, backgroundColor: `${trendColor}12` }]}>
                  {trendLabelText(item.short_term_trend)}
                </Text>
                <Text style={[styles.metaPill, { color: volColor, borderColor: `${volColor}55`, backgroundColor: `${volColor}12` }]}>
                  Volatility: {String(item.volatility_label)}
                </Text>
              </View>
              <Text style={styles.impactText}>{item.player_impact_summary}</Text>
            </View>
          );
        })}
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
  heading: {
    ...theme.typography.headingSm,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  subheading: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
  list: {
    gap: theme.spacing.sm,
  },
  row: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.lg,
    backgroundColor: theme.color.surfaceAlt,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xs,
  },
  rowHeader: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  basketName: {
    ...theme.typography.label,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  levelText: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
    fontWeight: '700',
  },
  metaPill: {
    ...theme.typography.caption,
    borderWidth: 1,
    borderRadius: theme.radius.pill,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 2,
    fontWeight: '800',
  },
  impactText: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
  emptyCard: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.xl,
    backgroundColor: theme.color.surface,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  emptyTitle: {
    ...theme.typography.headingSm,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  emptyText: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
});