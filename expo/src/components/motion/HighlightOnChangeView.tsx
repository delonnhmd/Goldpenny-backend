import React, { useEffect, useRef } from 'react';
import { Animated, StyleProp, ViewStyle } from 'react-native';

import { motion, useReducedMotion } from '@/design/motion';

export default function HighlightOnChangeView({
  watchValue,
  children,
  style,
}: {
  watchValue: string | number;
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  const reduced = useReducedMotion();
  const scale = useRef(new Animated.Value(1)).current;
  const flash = useRef(new Animated.Value(0)).current;
  const previousValue = useRef(watchValue);

  useEffect(() => {
    if (previousValue.current === watchValue) {
      return;
    }
    previousValue.current = watchValue;

    if (reduced) {
      scale.setValue(1);
      flash.setValue(0);
      return;
    }

    scale.setValue(0.985);
    flash.setValue(0.18);

    Animated.parallel([
      Animated.timing(scale, {
        toValue: 1,
        duration: motion.duration.base,
        easing: motion.easing.emphasized,
        useNativeDriver: true,
      }),
      Animated.sequence([
        Animated.timing(flash, {
          toValue: 0.28,
          duration: motion.duration.fast,
          easing: motion.easing.standard,
          useNativeDriver: false,
        }),
        Animated.timing(flash, {
          toValue: 0,
          duration: motion.duration.slow,
          easing: motion.easing.gentle,
          useNativeDriver: false,
        }),
      ]),
    ]).start();
  }, [flash, reduced, scale, watchValue]);

  return (
    <Animated.View
      style={[
        style,
        {
          transform: [{ scale }],
          backgroundColor: flash.interpolate({
            inputRange: [0, 1],
            outputRange: ['rgba(255,255,255,0)', 'rgba(29,78,216,0.12)'],
          }),
        },
      ]}
    >
      {children}
    </Animated.View>
  );
}