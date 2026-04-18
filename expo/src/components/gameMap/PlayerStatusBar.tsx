import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, Text, View } from 'react-native';

import { alpha, theme } from '@/design/theme';
import { formatMoney } from '@/lib/gameplayFormatters';

interface PlayerStatusBarProps {
  cash: number;
  stress: number;
  health: number;
  dayNumber: number;
  maxStress?: number;
  maxHealth?: number;
}

function stressColor(stress: number, max: number): string {
  const pct = Math.min(1, Math.max(0, stress / max));
  if (pct <= 0.4) return '#22C55E';
  if (pct <= 0.7) return '#EAB308';
  return '#EF4444';
}

function healthColor(health: number, max: number): string {
  const pct = Math.min(1, Math.max(0, health / max));
  if (pct >= 0.6) return '#22C55E';
  if (pct >= 0.3) return '#F97316';
  return '#EF4444';
}

function stressEmoji(stress: number, max: number): string {
  const pct = Math.min(1, Math.max(0, stress / max));
  if (pct <= 0.3) return '\u{1F642}';
  if (pct <= 0.6) return '\u{1F610}';
  return '\u{1F62B}';
}

export default function PlayerStatusBar({
  cash,
  stress,
  health,
  dayNumber,
  maxStress = 100,
  maxHealth = 100,
}: PlayerStatusBarProps) {
  const cashPulse = useRef(new Animated.Value(1)).current;
  const prevCashRef = useRef(cash);

  useEffect(() => {
    if (prevCashRef.current !== cash) {
      prevCashRef.current = cash;
      Animated.sequence([
        Animated.timing(cashPulse, { toValue: 1.08, duration: 120, useNativeDriver: true }),
        Animated.timing(cashPulse, { toValue: 1.0, duration: 180, useNativeDriver: true }),
      ]).start();
    }
  }, [cash, cashPulse]);

  const sColor = stressColor(stress, maxStress);
  const hColor = healthColor(health, maxHealth);

  return (
    <View style={styles.bar}>
      {/* Cash */}
      <Animated.View style={[styles.statItem, styles.cashItem, { transform: [{ scale: cashPulse }] }]}>
        <Text style={styles.statIcon}>{'\u{1F4B0}'}</Text>
        <Text style={styles.cashValue}>{formatMoney(cash)}</Text>
      </Animated.View>

      {/* Stress */}
      <View style={styles.statItem}>
        <Text style={styles.statIcon}>{stressEmoji(stress, maxStress)}</Text>
        <View style={styles.miniBarTrack}>
          <View style={[styles.miniBarFill, { width: `${Math.min(100, (stress / maxStress) * 100)}%`, backgroundColor: sColor }]} />
        </View>
      </View>

      {/* Health */}
      <View style={styles.statItem}>
        <Text style={styles.statIcon}>{'\u{2764}\u{FE0F}'}</Text>
        <View style={styles.miniBarTrack}>
          <View style={[styles.miniBarFill, { width: `${Math.min(100, (health / maxHealth) * 100)}%`, backgroundColor: hColor }]} />
        </View>
      </View>

      {/* Day */}
      <View style={styles.statItem}>
        <Text style={styles.statIcon}>{'\u{1F4C5}'}</Text>
        <Text style={styles.dayValue}>Day {dayNumber}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 14,
    paddingVertical: 8,
    marginHorizontal: 12,
    marginTop: 4,
    borderRadius: 16,
    backgroundColor: theme.gameUi.hudGlass,
    borderWidth: 1,
    borderColor: theme.gameUi.hudBorder,
    gap: 6,
    ...theme.shadow.sm,
  },
  statItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  cashItem: {
    backgroundColor: alpha(theme.gameUi.success, 0.12),
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 12,
  },
  statIcon: {
    fontSize: 14,
  },
  cashValue: {
    fontSize: 14,
    fontWeight: '800',
    color: theme.gameUi.status.cash,
  },
  dayValue: {
    fontSize: 11,
    fontWeight: '700',
    color: theme.gameUi.textPrimary,
  },
  miniBarTrack: {
    width: 40,
    height: 6,
    borderRadius: 999,
    backgroundColor: '#E5E7EB',
    overflow: 'hidden',
  },
  miniBarFill: {
    height: '100%',
    borderRadius: 999,
  },
});
