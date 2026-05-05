import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { alpha, theme } from '@/design/theme';

export type LadderRoute = 'work' | 'business' | 'portfolio';

export interface CareerLadderProps {
  rankLabel: string;
  progressPct: number;
  nextRankLabel: string;
}

export interface BusinessLadderProps {
  label: string;
  extraCount: number;
  hasBusiness: boolean;
}

export interface NetWorthLadderProps {
  available: boolean;
  deltaPct?: number | null;
  direction: 'up' | 'down' | 'flat' | 'tracking' | string;
}

export interface LadderRowProps {
  career: CareerLadderProps;
  business: BusinessLadderProps;
  netWorth: NetWorthLadderProps;
  onNavigate: (route: LadderRoute) => void;
}

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, Math.round(Number(value) || 0)));
}

function netWorthText(netWorth: NetWorthLadderProps): string {
  if (!netWorth.available || netWorth.deltaPct == null || !Number.isFinite(Number(netWorth.deltaPct))) {
    return 'Tracking…';
  }
  const pct = Math.abs(Number(netWorth.deltaPct));
  if (netWorth.direction === 'down') return `▼ ${pct.toFixed(1)}% this week`;
  if (netWorth.direction === 'up') return `▲ ${pct.toFixed(1)}% this week`;
  return `→ ${pct.toFixed(1)}% this week`;
}

export default function LadderRow({ career, business, netWorth, onNavigate }: LadderRowProps) {
  const progressPct = clampPercent(career.progressPct);
  const businessText = business.hasBusiness
    ? `${business.label}${business.extraCount > 0 ? ` +${business.extraCount} more` : ''}`
    : 'No business — open the Map.';
  const netWorthLabel = netWorthText(netWorth);
  const netWorthTone = netWorth.direction === 'down'
    ? theme.ui.danger
    : netWorth.direction === 'up'
      ? theme.ui.positive
      : theme.ui.text.onDarkMuted;

  return (
    <View style={styles.row}>
      <Pressable testID="ladder-career" style={styles.pill} onPress={() => onNavigate('work')}>
        <Text style={styles.label}>Career</Text>
        <Text style={styles.value} numberOfLines={2}>
          Rank: {career.rankLabel} — {progressPct}% to {career.nextRankLabel}
        </Text>
      </Pressable>

      <Pressable testID="ladder-business" style={styles.pill} onPress={() => onNavigate('business')}>
        <Text style={styles.label}>Business</Text>
        <Text style={styles.value} numberOfLines={2}>{businessText}</Text>
      </Pressable>

      <Pressable testID="ladder-net-worth" style={styles.pill} onPress={() => onNavigate('portfolio')}>
        <Text style={styles.label}>Net worth</Text>
        <Text style={[styles.value, { color: netWorthTone }]} numberOfLines={2}>{netWorthLabel}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: 6,
    marginHorizontal: 12,
    marginTop: 6,
  },
  pill: {
    flex: 1,
    minHeight: 46,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: theme.gameUi.hudBorder,
    backgroundColor: alpha(theme.gameUi.cardRaised, 0.92),
    paddingHorizontal: 7,
    paddingVertical: 6,
    justifyContent: 'center',
  },
  label: {
    color: theme.gameUi.textSecondary,
    fontSize: 8,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  value: {
    color: theme.gameUi.textPrimary,
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 13,
  },
});
