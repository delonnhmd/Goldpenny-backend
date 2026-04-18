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
    backgroundColor: '#0f3c52',
    borderWidth: 1,
    borderColor: '#22d3ee',
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: theme.spacing.xs,
    paddingHorizontal: theme.spacing.lg,
    ...theme.shadow.md,
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
    color: '#ecfeff',
    ...theme.typography.label,
    fontWeight: '800',
    letterSpacing: 0.3,
    textAlign: 'center',
  },
});
