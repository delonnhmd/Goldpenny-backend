import React from 'react';
import { StyleProp, StyleSheet, View, ViewStyle } from 'react-native';

import { theme } from '@/design/theme';
import { useResponsiveValue } from '@/hooks/useResponsiveValue';

export default function PageContainer({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  const horizontal = useResponsiveValue<number>(
    {
      mobile: theme.spacing.md,
      largeMobile: theme.spacing.lg,
      tablet: theme.spacing.xl,
      desktop: theme.spacing.xxl,
    },
    theme.spacing.lg,
  );

  const maxWidth = useResponsiveValue<number>(
    {
      mobile: 900,
      tablet: 1040,
      desktop: 1180,
    },
    1040,
  );

  return (
    <View style={[styles.outer, { paddingHorizontal: horizontal }, style]}>
      <View style={[styles.inner, { maxWidth }]}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  outer: {
    flex: 1,
    width: '100%',
    alignItems: 'center',
  },
  inner: {
    flex: 1,
    width: '100%',
  },
});
