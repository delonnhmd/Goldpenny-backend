import React from 'react';
import { StyleProp, StyleSheet, View, ViewStyle } from 'react-native';

import { theme } from '@/design/theme';

export type SurfaceCardVariant = 'default' | 'highlighted' | 'warning' | 'muted';

function variantStyle(variant: SurfaceCardVariant): ViewStyle {
  if (variant === 'highlighted') {
    return {
      borderColor: 'rgba(34, 211, 238, 0.3)',
      backgroundColor: 'rgba(8, 47, 73, 0.35)',
    };
  }
  if (variant === 'warning') {
    return {
      borderColor: 'rgba(251, 191, 36, 0.34)',
      backgroundColor: 'rgba(69, 39, 3, 0.5)',
    };
  }
  if (variant === 'muted') {
    return {
      borderColor: 'rgba(148, 163, 184, 0.16)',
      backgroundColor: 'rgba(9, 17, 31, 0.92)',
    };
  }
  return {
    borderColor: 'rgba(148, 163, 184, 0.14)',
    backgroundColor: theme.color.surface,
  };
}

export default function SurfaceCard({
  children,
  style,
  variant = 'default',
  padded = true,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  variant?: SurfaceCardVariant;
  padded?: boolean;
}) {
  return (
    <View
      style={[
        styles.card,
        variantStyle(variant),
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
    borderRadius: theme.radius.xl,
    ...theme.shadow.md,
  },
  padded: {
    padding: theme.spacing.lg,
  },
});
