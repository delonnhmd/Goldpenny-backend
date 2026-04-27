import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { alpha, theme } from '@/design/theme';

export interface StreakBadgeProps {
  currentStreak: number;
  longestStreak: number;
}

export default function StreakBadge({ currentStreak, longestStreak }: StreakBadgeProps) {
  const safeCurrent = Math.max(0, Math.round(Number(currentStreak) || 0));
  const safeLongest = Math.max(0, Math.round(Number(longestStreak) || 0));
  const showLongest = safeLongest > safeCurrent;

  return (
    <View style={styles.badge} accessibilityLabel={`Current streak ${safeCurrent} days`}>
      <Text style={styles.icon}>{'\u{1F525}'}</Text>
      <View style={styles.copy}>
        <Text style={styles.count}>{safeCurrent}</Text>
        {showLongest ? <Text style={styles.subtitle}>longest {safeLongest}</Text> : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    minWidth: 42,
    maxWidth: 68,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: 999,
    backgroundColor: alpha(theme.ui.warning, 0.14),
    borderWidth: 1,
    borderColor: alpha(theme.ui.warning, 0.42),
  },
  icon: {
    fontSize: 12,
  },
  copy: {
    flexShrink: 1,
  },
  count: {
    color: theme.gameUi.textPrimary,
    fontSize: 11,
    fontWeight: '900',
    lineHeight: 12,
    fontVariant: ['tabular-nums'],
  },
  subtitle: {
    color: theme.gameUi.textSecondary,
    fontSize: 7,
    fontWeight: '700',
    lineHeight: 9,
  },
});
