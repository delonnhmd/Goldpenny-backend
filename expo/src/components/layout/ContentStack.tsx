import React from 'react';
import { StyleProp, StyleSheet, View, ViewProps, ViewStyle } from 'react-native';

import { theme } from '@/design/theme';

export default function ContentStack({
  children,
  gap = theme.spacing.md,
  style,
  ...viewProps
}: {
  children: React.ReactNode;
  gap?: number;
  style?: StyleProp<ViewStyle>;
} & ViewProps) {
  return (
    <View style={[styles.stack, { gap }, style]} {...viewProps}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: {
    width: '100%',
  },
});
