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
      {loading ? <ActivityIndicator size="small" color={theme.color.textPrimary} /> : null}
      <Text style={styles.text}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 48,
    borderWidth: 1,
    borderColor: '#d5deea',
    borderRadius: theme.radius.lg,
    backgroundColor: '#ffffff',
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
    backgroundColor: '#f8fafc',
    transform: [{ scale: 0.975 }],
  },
  text: {
    color: theme.color.textPrimary,
    ...theme.typography.label,
    fontWeight: '700',
  },
});
