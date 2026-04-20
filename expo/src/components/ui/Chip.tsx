import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { alpha, theme } from '@/design/theme';

export type ChipVariant = 'neutral' | 'active' | 'positive' | 'danger' | 'warning' | 'info';

function semanticTone(variant: ChipVariant): string {
  if (variant === 'positive') return theme.ui.positive;
  if (variant === 'danger') return theme.ui.danger;
  if (variant === 'warning') return theme.ui.warning;
  return theme.ui.info;
}

export default function Chip({
  label,
  variant = 'neutral',
}: {
  label: string;
  variant?: ChipVariant;
}) {
  if (variant === 'active') {
    return (
      <View style={[styles.base, styles.activeWrap]}>
        <Text style={[styles.text, styles.activeText]}>{label}</Text>
      </View>
    );
  }

  if (variant === 'neutral') {
    return (
      <View style={[styles.base, styles.neutralWrap]}>
        <Text style={[styles.text, styles.neutralText]}>{label}</Text>
      </View>
    );
  }

  const tone = semanticTone(variant);
  return (
    <View style={[styles.base, { borderColor: tone, backgroundColor: alpha(tone, 0.14) }]}>
      <Text style={[styles.text, { color: tone }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    alignSelf: 'flex-start',
    borderRadius: theme.ui.radius.chip,
    borderWidth: 1,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xxs,
  },
  neutralWrap: {
    borderColor: theme.ui.border,
    backgroundColor: theme.ui.bg.cardRaised,
  },
  activeWrap: {
    borderColor: theme.ui.action,
    backgroundColor: theme.ui.action,
  },
  text: {
    ...theme.typography.caption,
    textTransform: 'uppercase',
    fontWeight: '700',
  },
  neutralText: {
    color: theme.ui.text.onDarkMuted,
  },
  activeText: {
    color: theme.ui.text.onDark,
  },
});
