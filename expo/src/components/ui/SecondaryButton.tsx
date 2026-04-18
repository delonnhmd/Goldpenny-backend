import React from 'react';
import { ActivityIndicator, Pressable, StyleProp, StyleSheet, Text, ViewStyle } from 'react-native';

import { alpha, theme } from '@/design/theme';

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
      {loading ? <ActivityIndicator size="small" color={theme.gameUi.textSecondary} /> : null}
      <Text style={styles.text}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 48,
    borderWidth: 1,
    borderColor: alpha(theme.gameUi.secondaryButtonBorder, 0.92),
    borderRadius: theme.radius.lg,
    backgroundColor: theme.gameUi.secondaryButton,
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
    backgroundColor: '#DCE1E8',
    transform: [{ scale: 0.96 }],
    opacity: 0.9,
  },
  text: {
    color: theme.gameUi.textPrimary,
    ...theme.typography.label,
    fontWeight: '700',
    textAlign: 'center',
  },
});
