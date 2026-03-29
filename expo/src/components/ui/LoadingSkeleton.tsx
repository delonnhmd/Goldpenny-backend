import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, View } from 'react-native';

import { theme } from '@/design/theme';

export default function LoadingSkeleton({
  lines = 1,
}: {
  lines?: number;
}) {
  const opacity = useRef(new Animated.Value(0.5)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, {
          toValue: 1,
          duration: 200,
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          toValue: 0.45,
          duration: 200,
          useNativeDriver: true,
        }),
      ]),
    );

    loop.start();
    return () => loop.stop();
  }, [opacity]);

  return (
    <View style={styles.wrap}>
      {Array.from({ length: lines }).map((_, index) => (
        <Animated.View
          key={`skeleton_${index}`}
          style={[styles.line, { opacity, width: index === lines - 1 ? '78%' : '100%' }]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: theme.spacing.xs,
  },
  line: {
    height: 12,
    borderRadius: theme.radius.sm,
    backgroundColor: '#dbe3ee',
  },
});
