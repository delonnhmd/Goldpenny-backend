import React from 'react';
import { ActivityIndicator, Pressable, StyleProp, StyleSheet, Text, ViewStyle } from 'react-native';

import { alpha, theme } from '@/design/theme';

export default function PrimaryButton({
  label,
  onPress,
  disabled,
  loading,
  style,
  tone = 'primary',
}: {
  label: string;
  onPress?: () => void;
  disabled?: boolean;
  loading?: boolean;
  style?: StyleProp<ViewStyle>;
  tone?: 'primary' | 'danger';
}) {
  const blocked = Boolean(disabled || loading || !onPress);
  const palette = tone === 'danger'
    ? styles.danger
    : styles.primary;

  return (
    <Pressable
      onPress={onPress}
      disabled={blocked}
      style={({ pressed }) => [
        styles.button,
        palette,
        style,
        blocked ? styles.disabled : null,
        loading ? styles.loading : null,
        pressed && !blocked ? styles.pressed : null,
      ]}
    >
      {loading ? <ActivityIndicator size="small" color="#ffffff" /> : null}
      <Text style={styles.text}>{loading ? label : label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 52,
    borderRadius: theme.radius.lg,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: theme.spacing.xs,
    paddingHorizontal: theme.spacing.lg,
    ...theme.shadow.md,
  },
  primary: {
    backgroundColor: theme.gameUi.primary,
    borderWidth: 1,
    borderColor: alpha(theme.gameUi.primary, 0.92),
  },
  danger: {
    backgroundColor: theme.gameUi.danger,
    borderWidth: 1,
    borderColor: alpha(theme.gameUi.danger, 0.92),
  },
  disabled: {
    opacity: 0.5,
  },
  loading: {
    opacity: 0.82,
  },
  pressed: {
    opacity: 0.92,
    transform: [{ scale: 0.96 }],
    shadowOpacity: 0.03,
    elevation: 0,
  },
  text: {
    color: theme.gameUi.card,
    ...theme.typography.label,
    fontWeight: '800',
    letterSpacing: 0.3,
    textAlign: 'center',
  },
});
