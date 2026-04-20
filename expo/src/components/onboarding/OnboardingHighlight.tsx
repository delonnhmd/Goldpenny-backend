import React from 'react';
import { StyleProp, StyleSheet, Text, View, ViewStyle } from 'react-native';

import { theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';

export default function OnboardingHighlight({
  target,
  children,
  style,
}: {
  target: string;
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  const onboarding = useOnboarding();
  const active = onboarding.isActive && onboarding.highlightTarget === target;

  return (
    <View style={[style, active ? styles.activeWrap : null]}>
      {active ? <Text style={styles.badge}>Focus</Text> : null}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  activeWrap: {
    borderWidth: 2,
    borderColor: theme.ui.action,
    borderRadius: theme.radius.xl,
    padding: theme.spacing.xs,
    backgroundColor: theme.ui.bg.sheet,
    ...theme.shadow.sm,
  },
  badge: {
    alignSelf: 'flex-start',
    marginBottom: theme.spacing.xs,
    borderWidth: 1,
    borderColor: theme.ui.info,
    borderRadius: theme.radius.pill,
    backgroundColor: theme.ui.info,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 2,
    color: theme.ui.action,
    ...theme.typography.caption,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
});
