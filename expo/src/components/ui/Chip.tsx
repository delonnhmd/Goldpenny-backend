import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { alpha, theme } from '@/design/theme';

export type ChipVariant = 'neutral' | 'active' | 'positive' | 'danger' | 'warning' | 'info';

function paletteFor(variant: ChipVariant) {
  if (variant === 'neutral') {
    return {
      backgroundColor: theme.ui.bg.cardRaised,
      borderColor: theme.ui.border,
      color: theme.ui.text.onDarkMuted,
    };
  }

  if (variant === 'active') {
    return {
      backgroundColor: theme.ui.action,
      borderColor: theme.ui.action,
      color: theme.ui.text.onDark,
    };
  }

  const semantic = variant === 'positive'
    ? theme.ui.positive
    : variant === 'danger'
      ? theme.ui.danger
      : variant === 'warning'
        ? theme.ui.warning
        : theme.ui.info;

  return {
    backgroundColor: alpha(semantic, 0.14),
    borderColor: semantic,
    color: semantic,
  };
}

export default function Chip({
  label,
  variant = 'neutral',
}: {
  label: string;
  variant?: ChipVariant;
}) {
  const palette = paletteFor(variant);

  return (
    <View
      style={[
        styles.chip,
        {
          backgroundColor: palette.backgroundColor,
          borderColor: palette.borderColor,
        },
      ]}
    >
      <Text style={[styles.text, { color: palette.color }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderRadius: theme.ui.radius.chip,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  text: {
    ...theme.typography.caption,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
});
