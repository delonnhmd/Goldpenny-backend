import React from 'react';
import { StyleProp, StyleSheet, View, ViewStyle } from 'react-native';

import { theme } from '@/design/theme';

export type CardVariant = 'default' | 'positive' | 'danger' | 'warning' | 'info';

function variantAccent(variant: CardVariant): string {
  if (variant === 'positive') return theme.ui.positive;
  if (variant === 'danger') return theme.ui.danger;
  if (variant === 'warning') return theme.ui.warning;
  if (variant === 'info') return theme.ui.info;
  return 'transparent';
}

export default function Card({
  children,
  style,
  variant = 'default',
  padded = true,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  variant?: CardVariant;
  padded?: boolean;
}) {
  const accent = variantAccent(variant);
  return (
    <View style={[styles.root, padded ? styles.padded : null, style]}>
      {variant !== 'default' ? (
        <View style={[styles.leftAccent, { backgroundColor: accent }]} />
      ) : null}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    borderRadius: theme.ui.radius.card,
    borderWidth: 1,
    borderColor: theme.ui.border,
    backgroundColor: theme.ui.bg.card,
    overflow: 'hidden',
  },
  padded: {
    padding: theme.spacing.lg,
  },
  leftAccent: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: 3,
  },
});
