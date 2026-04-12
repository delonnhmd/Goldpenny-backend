import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, Text, View } from 'react-native';

export type OpportunityType = 'delivery' | 'produce' | 'job' | 'stress';

interface OpportunityIndicatorProps {
  type: OpportunityType;
  label: string;
  x: number;
  y: number;
}

const TYPE_CONFIG: Record<OpportunityType, { emoji: string; color: string; glowColor: string }> = {
  delivery: { emoji: '\u{1F69A}', color: '#3B82F6', glowColor: 'rgba(59, 130, 246, 0.35)' },
  produce: { emoji: '\u{1F34E}', color: '#22C55E', glowColor: 'rgba(34, 197, 94, 0.35)' },
  job: { emoji: '\u{1F4BC}', color: '#F59E0B', glowColor: 'rgba(245, 158, 11, 0.35)' },
  stress: { emoji: '\u{1F525}', color: '#EF4444', glowColor: 'rgba(239, 68, 68, 0.35)' },
};

export default function OpportunityIndicator({ type, label, x, y }: OpportunityIndicatorProps) {
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const glowAnim = useRef(new Animated.Value(0.5)).current;
  const config = TYPE_CONFIG[type] || TYPE_CONFIG.delivery;

  useEffect(() => {
    // Staggered start based on position for visual variety
    const delay = (x * 17 + y * 13) % 600;

    const pulseLoop = Animated.loop(
      Animated.sequence([
        Animated.delay(delay),
        Animated.timing(pulseAnim, { toValue: 1.12, duration: 700, useNativeDriver: true }),
        Animated.timing(pulseAnim, { toValue: 1.0, duration: 700, useNativeDriver: true }),
      ]),
    );

    const glowLoop = Animated.loop(
      Animated.sequence([
        Animated.delay(delay),
        Animated.timing(glowAnim, { toValue: 1, duration: 800, useNativeDriver: true }),
        Animated.timing(glowAnim, { toValue: 0.4, duration: 800, useNativeDriver: true }),
      ]),
    );

    pulseLoop.start();
    glowLoop.start();

    return () => {
      pulseLoop.stop();
      glowLoop.stop();
    };
  }, [glowAnim, pulseAnim, x, y]);

  return (
    <Animated.View
      style={[
        styles.container,
        {
          left: `${x}%`,
          top: `${y}%`,
          transform: [{ scale: pulseAnim }],
        },
      ]}
    >
      {/* Glow circle */}
      <Animated.View
        style={[
          styles.glow,
          {
            backgroundColor: config.glowColor,
            opacity: glowAnim,
          },
        ]}
      />
      {/* Icon */}
      <View style={[styles.iconWrap, { backgroundColor: config.color }]}>
        <Text style={styles.emoji}>{config.emoji}</Text>
      </View>
      {/* Label */}
      <View style={[styles.labelWrap, { backgroundColor: config.color }]}>
        <Text style={styles.label} numberOfLines={1}>{label}</Text>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    alignItems: 'center',
    marginLeft: -16,
    marginTop: -16,
    zIndex: 20,
  },
  glow: {
    position: 'absolute',
    width: 42,
    height: 42,
    borderRadius: 21,
    top: -5,
    left: -5,
  },
  iconWrap: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: 'rgba(255, 255, 255, 0.8)',
    shadowColor: '#000',
    shadowOpacity: 0.15,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 2 },
    elevation: 3,
  },
  emoji: {
    fontSize: 15,
  },
  labelWrap: {
    marginTop: 2,
    paddingHorizontal: 5,
    paddingVertical: 1,
    borderRadius: 6,
    maxWidth: 70,
  },
  label: {
    fontSize: 7,
    fontWeight: '800',
    color: '#ffffff',
    textAlign: 'center',
    textTransform: 'uppercase',
    letterSpacing: 0.3,
  },
});
