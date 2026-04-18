import React from 'react';
import { ActivityIndicator, Pressable, StyleProp, StyleSheet, Text, ViewStyle } from 'react-native';

import { theme } from '@/design/theme';

export default function SecondaryButton({
  label,
  onPress,
  disabled,
  loading,
  style,
}: {
  label: string;
  onPress?: () => void;
  disabled?: boolean;
  loading?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const blocked = Boolean(disabled || loading || !onPress);

  return (
    <Pressable
      onPress={onPress}
      disabled={blocked}
      style={({ pressed }) => [
        styles.button,
        style,
        blocked ? styles.disabled : null,
        loading ? styles.loading : null,
        pressed && !blocked ? styles.pressed : null,
      ]}
    >
      {loading ? <ActivityIndicator size="small" color="#cbd5e1" /> : null}
      <Text style={styles.text}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 48,
    borderWidth: 1,
    borderColor: 'rgba(148, 163, 184, 0.24)',
    borderRadius: theme.radius.lg,
    backgroundColor: 'rgba(15, 23, 42, 0.92)',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: theme.spacing.lg,
  },
  disabled: {
    opacity: 0.5,
  },
  loading: {
    opacity: 0.78,
  },
  pressed: {
    backgroundColor: 'rgba(30, 41, 59, 0.95)',
    transform: [{ scale: 0.96 }],
    opacity: 0.9,
  },
  text: {
    color: '#e2e8f0',
    ...theme.typography.label,
    fontWeight: '700',
    textAlign: 'center',
  },
});
