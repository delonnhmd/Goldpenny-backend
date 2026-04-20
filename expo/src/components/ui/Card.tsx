import React from 'react';
import { StyleProp, StyleSheet, View, ViewStyle } from 'react-native';

import { theme } from '@/design/theme';

export type CardVariant = 'default' | 'positive' | 'danger' | 'warning' | 'info';

const variantBorderColor: Record<CardVariant, string> = {
  default: theme.ui.border,
  positive: theme.ui.positive,
  danger: theme.ui.danger,
  warning: theme.ui.warning,
  info: theme.ui.info,
};

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
  const accentColor = variantBorderColor[variant];

  return (
    <View
      style={[
        styles.card,
        variant !== 'default' ? { borderLeftWidth: 3, borderLeftColor: accentColor } : null,
        padded ? styles.padded : null,
        style,
      ]}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: theme.ui.border,
    borderRadius: theme.ui.radius.card,
    backgroundColor: theme.ui.bg.card,
    ...theme.shadow.md,
  },
  padded: {
    padding: theme.spacing.lg,
  },
});
