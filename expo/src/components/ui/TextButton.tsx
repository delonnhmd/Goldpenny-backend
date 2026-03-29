import React from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';

import { theme } from '@/design/theme';

export default function TextButton({
  label,
  onPress,
  disabled,
}: {
  label: string;
  onPress?: () => void;
  disabled?: boolean;
}) {
  const blocked = Boolean(disabled || !onPress);

  return (
    <Pressable
      onPress={onPress}
      disabled={blocked}
      style={({ pressed }) => [styles.button, blocked ? styles.disabled : null, pressed && !blocked ? styles.pressed : null]}
    >
      <Text style={styles.text}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 36,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: theme.spacing.sm,
    borderRadius: theme.radius.sm,
  },
  disabled: {
    opacity: 0.45,
  },
  pressed: {
    backgroundColor: '#eff6ff',
  },
  text: {
    color: theme.color.info,
    ...theme.typography.label,
  },
});
