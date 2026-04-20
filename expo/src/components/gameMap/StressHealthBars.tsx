import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { theme } from '@/design/theme';

interface StressHealthBarsProps {
  stress: number;
  health: number;
  maxStress?: number;
  maxHealth?: number;
  compact?: boolean;
}

function stressColor(pct: number): string {
  if (pct <= 0.4) return theme.ui.positive;
  if (pct <= 0.7) return theme.ui.warning;
  return theme.ui.danger;
}

function healthColor(pct: number): string {
  if (pct >= 0.6) return theme.ui.positive;
  if (pct >= 0.3) return theme.ui.warning;
  return theme.ui.danger;
}

function stressEmoji(pct: number): string {
  if (pct <= 0.3) return '\u{1F642}';
  if (pct <= 0.6) return '\u{1F610}';
  return '\u{1F62B}';
}

function healthEmoji(pct: number): string {
  if (pct >= 0.6) return '\u{1F4AA}';
  if (pct >= 0.3) return '\u{1FA79}';
  return '\u{1F915}';
}

export default function StressHealthBars({
  stress,
  health,
  maxStress = 100,
  maxHealth = 100,
  compact = false,
}: StressHealthBarsProps) {
  const stressPct = Math.min(1, Math.max(0, stress / maxStress));
  const healthPct = Math.min(1, Math.max(0, health / maxHealth));

  const sColor = stressColor(stressPct);
  const hColor = healthColor(healthPct);

  if (compact) {
    return (
      <View style={styles.compactRow}>
        <View style={styles.compactItem}>
          <Text style={styles.compactEmoji}>{stressEmoji(stressPct)}</Text>
          <View style={styles.compactTrack}>
            <View style={[styles.compactFill, { width: `${stressPct * 100}%`, backgroundColor: sColor }]} />
          </View>
        </View>
        <View style={styles.compactItem}>
          <Text style={styles.compactEmoji}>{healthEmoji(healthPct)}</Text>
          <View style={styles.compactTrack}>
            <View style={[styles.compactFill, { width: `${healthPct * 100}%`, backgroundColor: hColor }]} />
          </View>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Stress bar */}
      <View style={styles.barRow}>
        <Text style={styles.emoji}>{stressEmoji(stressPct)}</Text>
        <View style={styles.barMeta}>
          <View style={styles.barLabelRow}>
            <Text style={styles.barLabel}>Stress</Text>
            <Text style={[styles.barValue, { color: sColor }]}>{Math.round(stress)}/{maxStress}</Text>
          </View>
          <View style={styles.track}>
            <View style={[styles.fill, { width: `${stressPct * 100}%`, backgroundColor: sColor }]} />
          </View>
        </View>
      </View>

      {/* Health bar */}
      <View style={styles.barRow}>
        <Text style={styles.emoji}>{healthEmoji(healthPct)}</Text>
        <View style={styles.barMeta}>
          <View style={styles.barLabelRow}>
            <Text style={styles.barLabel}>Health</Text>
            <Text style={[styles.barValue, { color: hColor }]}>{Math.round(health)}/{maxHealth}</Text>
          </View>
          <View style={styles.track}>
            <View style={[styles.fill, { width: `${healthPct * 100}%`, backgroundColor: hColor }]} />
          </View>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 8,
    paddingHorizontal: 4,
  },
  barRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  emoji: {
    fontSize: 18,
    width: 24,
    textAlign: 'center',
  },
  barMeta: {
    flex: 1,
    gap: 3,
  },
  barLabelRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  barLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: theme.gameUi.textSecondary,
  },
  barValue: {
    fontSize: 10,
    fontWeight: '800',
  },
  track: {
    height: 8,
    borderRadius: 999,
    backgroundColor: theme.ui.bg.cardRaised,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    borderRadius: 999,
  },
  // Compact
  compactRow: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'center',
  },
  compactItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  compactEmoji: {
    fontSize: 12,
  },
  compactTrack: {
    width: 36,
    height: 5,
    borderRadius: 999,
    backgroundColor: theme.ui.bg.cardRaised,
    overflow: 'hidden',
  },
  compactFill: {
    height: '100%',
    borderRadius: 999,
  },
});
