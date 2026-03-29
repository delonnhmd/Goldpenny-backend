import React from 'react';
import { StyleProp, StyleSheet, View, ViewStyle } from 'react-native';

import { theme } from '@/design/theme';

export type SurfaceCardVariant = 'default' | 'highlighted' | 'warning' | 'muted';

function variantStyle(variant: SurfaceCardVariant): ViewStyle {
  if (variant === 'highlighted') {
    return {
      borderColor: '#c7d2fe',
      backgroundColor: '#f8faff',
    };
  }
  if (variant === 'warning') {
    return {
      borderColor: '#fcd34d',
      backgroundColor: '#fffbeb',
    };
  }
  if (variant === 'muted') {
    return {
      borderColor: '#dbe4ef',
      backgroundColor: '#f8fafc',
    };
  }
  return {
    borderColor: theme.color.border,
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
    ...theme.shadow.sm,
  },
  padded: {
    padding: theme.spacing.lg,
  },
});
