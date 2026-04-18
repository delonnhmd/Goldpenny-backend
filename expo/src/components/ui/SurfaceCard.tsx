import React from 'react';
import { StyleProp, StyleSheet, View, ViewStyle } from 'react-native';

import { alpha, theme } from '@/design/theme';

export type SurfaceCardVariant = 'default' | 'highlighted' | 'warning' | 'muted';

function variantStyle(variant: SurfaceCardVariant): ViewStyle {
  if (variant === 'highlighted') {
    return {
      borderColor: alpha(theme.gameUi.primary, 0.26),
      backgroundColor: alpha(theme.gameUi.primary, 0.08),
    };
  }
  if (variant === 'warning') {
    return {
      borderColor: alpha(theme.gameUi.warning, 0.34),
      backgroundColor: alpha(theme.gameUi.warning, 0.1),
    };
  }
  if (variant === 'muted') {
    return {
      borderColor: alpha(theme.gameUi.cardBorder, 0.92),
      backgroundColor: '#F9FAFB',
    };
  }
  return {
    borderColor: alpha(theme.gameUi.cardBorder, 0.92),
    backgroundColor: theme.gameUi.card,
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
