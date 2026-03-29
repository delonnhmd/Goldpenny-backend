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
    borderColor: '#3b82f6',
    borderRadius: theme.radius.xl,
    padding: theme.spacing.xs,
    backgroundColor: '#f0f7ff',
    ...theme.shadow.sm,
  },
  badge: {
    alignSelf: 'flex-start',
    marginBottom: theme.spacing.xs,
    borderWidth: 1,
    borderColor: '#93c5fd',
    borderRadius: theme.radius.pill,
    backgroundColor: '#dbeafe',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 2,
    color: '#1e3a8a',
    ...theme.typography.caption,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
});