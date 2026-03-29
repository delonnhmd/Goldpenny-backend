import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, Text, View } from 'react-native';

import { motion, useReducedMotion } from '@/design/motion';
import { theme } from '@/design/theme';

export default function ProgressMeter({
  progress,
  label,
}: {
  progress: number;
  label?: string;
}) {
  const pct = Math.round(Math.max(0, Math.min(1, progress)) * 100);
  const reduced = useReducedMotion();
  const animatedProgress = useRef(new Animated.Value(pct)).current;

  useEffect(() => {
    if (reduced) {
      animatedProgress.setValue(pct);
      return;
    }

    Animated.timing(animatedProgress, {
      toValue: pct,
      duration: motion.duration.base,
      easing: motion.easing.standard,
      useNativeDriver: false,
    }).start();
  }, [animatedProgress, pct, reduced]);

  return (
    <View style={styles.wrap}>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      <View style={styles.track}>
        <Animated.View
          style={[
            styles.fill,
            {
              width: animatedProgress.interpolate({
                inputRange: [0, 100],
                outputRange: ['0%', '100%'],
              }),
            },
          ]}
        />
      </View>
      <Text style={styles.meta}>{pct}%</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: theme.spacing.xs,
  },
  label: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
  track: {
    height: 8,
    borderRadius: theme.radius.pill,
    overflow: 'hidden',
    backgroundColor: '#e2e8f0',
  },
  fill: {
    height: 8,
    borderRadius: theme.radius.pill,
    backgroundColor: theme.color.accent,
  },
  meta: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
  },
});
