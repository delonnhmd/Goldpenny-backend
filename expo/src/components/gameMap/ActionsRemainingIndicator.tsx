import React, { useEffect, useRef } from 'react';
import { Animated, Pressable, StyleSheet, Text } from 'react-native';

import { alpha, theme } from '@/design/theme';

export interface ActionsRemainingIndicatorProps {
  actionsRemainingToday: number;
  onPress?: () => void;
}

export default function ActionsRemainingIndicator({
  actionsRemainingToday,
  onPress,
}: ActionsRemainingIndicatorProps) {
  const safeRemaining = Math.max(0, Math.round(Number(actionsRemainingToday) || 0));
  const readyToSettle = safeRemaining === 0;
  const scale = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (!readyToSettle) {
      scale.stopAnimation();
      scale.setValue(1);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(scale, { toValue: 1.04, duration: 640, useNativeDriver: true }),
        Animated.timing(scale, { toValue: 1, duration: 640, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => {
      loop.stop();
    };
  }, [readyToSettle, scale]);

  // PHASE-3-B: add brief countdown mode after End Day when morning notifications ship.
  const label = readyToSettle ? 'Ready to settle' : `${safeRemaining} moves left today`;

  return (
    <Animated.View style={{ transform: [{ scale }] }}>
      <Pressable
        testID="actions-remaining-indicator"
        accessibilityRole="button"
        accessibilityLabel={label}
        style={[styles.indicator, readyToSettle ? styles.ready : null]}
        onPress={onPress}
      >
        <Text style={styles.icon}>{'\u{1F551}'}</Text>
        <Text style={styles.label} numberOfLines={1}>{label}</Text>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  indicator: {
    minWidth: 82,
    maxWidth: 108,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: alpha(theme.ui.info, 0.42),
    backgroundColor: alpha(theme.ui.info, 0.12),
  },
  ready: {
    borderColor: alpha(theme.ui.warning, 0.52),
    backgroundColor: alpha(theme.ui.warning, 0.16),
  },
  icon: {
    fontSize: 11,
  },
  label: {
    flexShrink: 1,
    color: theme.gameUi.textPrimary,
    fontSize: 9,
    fontWeight: '800',
  },
});
