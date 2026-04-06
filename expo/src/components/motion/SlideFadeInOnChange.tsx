import React, { useEffect, useRef } from 'react';
import { Animated, Easing, StyleProp, ViewStyle } from 'react-native';

import { useReducedMotion } from '@/design/motion';

export default function SlideFadeInOnChange({
  watchValue,
  children,
  style,
  delayMs = 0,
  durationMs = 200,
  slidePx = 10,
}: {
  watchValue: string | number;
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  delayMs?: number;
  durationMs?: number;
  slidePx?: number;
}) {
  const reducedMotion = useReducedMotion();
  const opacity = useRef(new Animated.Value(reducedMotion ? 1 : 0)).current;
  const translateY = useRef(new Animated.Value(reducedMotion ? 0 : slidePx)).current;
  const previousValueRef = useRef<string | number>(watchValue);

  useEffect(() => {
    const changed = previousValueRef.current !== watchValue;
    previousValueRef.current = watchValue;
    if (!changed) return;
    if (reducedMotion) {
      opacity.setValue(1);
      translateY.setValue(0);
      return;
    }

    opacity.stopAnimation();
    translateY.stopAnimation();
    opacity.setValue(0);
    translateY.setValue(slidePx);

    Animated.parallel([
      Animated.timing(opacity, {
        toValue: 1,
        duration: Math.max(150, Math.min(260, Math.round(durationMs))),
        delay: Math.max(0, Math.round(delayMs)),
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
      Animated.timing(translateY, {
        toValue: 0,
        duration: Math.max(150, Math.min(260, Math.round(durationMs))),
        delay: Math.max(0, Math.round(delayMs)),
        easing: Easing.out(Easing.quad),
        useNativeDriver: true,
      }),
    ]).start();
  }, [delayMs, durationMs, opacity, reducedMotion, slidePx, translateY, watchValue]);

  useEffect(() => {
    if (reducedMotion) return;
    opacity.setValue(1);
    translateY.setValue(0);
  }, [opacity, reducedMotion, translateY]);

  return (
    <Animated.View
      style={[
        style,
        {
          opacity,
          transform: [{ translateY }],
        },
      ]}
    >
      {children}
    </Animated.View>
  );
}

