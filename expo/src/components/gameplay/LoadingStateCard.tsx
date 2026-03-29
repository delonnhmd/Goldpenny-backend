import React, { useEffect, useRef } from 'react';
import { ActivityIndicator, Animated, StyleSheet, Text, View } from 'react-native';

import SurfaceCard from '@/components/ui/SurfaceCard';
import { motion, useReducedMotion } from '@/design/motion';
import { theme } from '@/design/theme';

export default function LoadingStateCard({
  label = 'Loading...',
  compact = false,
}: {
  label?: string;
  compact?: boolean;
}) {
  const reduced = useReducedMotion();
  const shimmer = useRef(new Animated.Value(0.35)).current;

  useEffect(() => {
    if (reduced) {
      shimmer.setValue(0.5);
      return;
    }

    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(shimmer, {
          toValue: 0.7,
          duration: motion.duration.slow,
          easing: motion.easing.gentle,
          useNativeDriver: true,
        }),
        Animated.timing(shimmer, {
          toValue: 0.35,
          duration: motion.duration.slow,
          easing: motion.easing.gentle,
          useNativeDriver: true,
        }),
      ]),
    );

    loop.start();
    return () => {
      loop.stop();
    };
  }, [reduced, shimmer]);

  return (
    <SurfaceCard variant="muted" style={[styles.card, compact ? styles.cardCompact : null]}>
      <ActivityIndicator size="small" color="#1d4ed8" />
      <View style={styles.copyWrap}>
        <Text style={styles.label}>{label}</Text>
        <Animated.View style={[styles.skeletonRow, { opacity: shimmer }]} />
      </View>
    </SurfaceCard>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.sm,
  },
  cardCompact: {
    paddingVertical: theme.spacing.sm,
  },
  copyWrap: {
    flex: 1,
    gap: theme.spacing.xs,
  },
  label: {
    color: theme.color.textSecondary,
    ...theme.typography.bodyMd,
    fontWeight: '600',
  },
  skeletonRow: {
    height: 8,
    width: '62%',
    borderRadius: theme.radius.pill,
    backgroundColor: '#dbe7f5',
  },
});
