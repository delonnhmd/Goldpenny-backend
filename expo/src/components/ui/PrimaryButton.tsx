import React from 'react';
import { ActivityIndicator, Pressable, StyleProp, StyleSheet, Text, ViewStyle } from 'react-native';

import { theme } from '@/design/theme';

export default function PrimaryButton({
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
      {loading ? <ActivityIndicator size="small" color="#ffffff" /> : null}
      <Text style={styles.text}>{loading ? label : label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 52,
    borderRadius: theme.radius.lg,
    backgroundColor: theme.color.accent,
    borderWidth: 1,
    borderColor: '#1e40af',
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: theme.spacing.xs,
    paddingHorizontal: theme.spacing.lg,
    ...theme.shadow.sm,
  },
  disabled: {
    opacity: 0.5,
  },
  loading: {
    opacity: 0.82,
  },
  pressed: {
    opacity: 0.94,
    transform: [{ scale: 0.975 }],
  },
  text: {
    color: '#ffffff',
    ...theme.typography.label,
    fontWeight: '800',
  },
});
