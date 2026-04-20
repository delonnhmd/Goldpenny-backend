import React, { useEffect, useMemo, useRef } from 'react';
import { Animated, Easing, StyleProp, StyleSheet, View, ViewStyle } from 'react-native';

import { useReducedMotion } from '@/design/motion';
import { theme } from '@/design/theme';

type PulseTone = 'warning' | 'danger' | 'info';
type PulseStrength = 'soft' | 'strong';

function toneColor(tone: PulseTone): string {
  if (tone === 'danger') return theme.ui.danger;
  if (tone === 'info') return theme.ui.action;
  return theme.ui.warning;
}

function maxOpacity(strength: PulseStrength): number {
  return strength === 'strong' ? 0.24 : 0.14;
}

export default function PulseAlertView({
  active,
  tone = 'warning',
  strength = 'soft',
  intervalMs = 2200,
  style,
  children,
}: {
  active: boolean;
  tone?: PulseTone;
  strength?: PulseStrength;
  intervalMs?: number;
  style?: StyleProp<ViewStyle>;
  children: React.ReactNode;
}) {
  const reducedMotion = useReducedMotion();
  const pulse = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    pulse.stopAnimation();
    pulse.setValue(0);
    if (!active || reducedMotion) {
      return;
    }
    const idleDelay = Math.max(200, Math.round(intervalMs));
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1,
          duration: 480,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 0,
          duration: 620,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.delay(idleDelay),
      ]),
    );
    loop.start();
    return () => {
      loop.stop();
      pulse.stopAnimation();
    };
  }, [active, intervalMs, pulse, reducedMotion]);

  const overlayOpacity = useMemo(
    () => pulse.interpolate({
      inputRange: [0, 1],
      outputRange: [0, maxOpacity(strength)],
    }),
    [pulse, strength],
  );

  return (
    <View style={[styles.wrap, style]}>
      <Animated.View
        pointerEvents="none"
        style={[
          StyleSheet.absoluteFillObject,
          styles.overlay,
          {
            backgroundColor: toneColor(tone),
            opacity: overlayOpacity,
          },
        ]}
      />
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderRadius: theme.radius.lg,
    overflow: 'hidden',
  },
  overlay: {
    borderRadius: theme.radius.lg,
  },
});

