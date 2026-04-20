import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, Text, View } from 'react-native';
import { theme } from '@/design/theme';

export type PlayerState = 'idle' | 'working' | 'driving' | 'stressed';

interface PlayerAvatarProps {
  state: PlayerState;
  x: number;
  y: number;
  stressLevel: number;
}

const STATE_EMOJI: Record<PlayerState, string> = {
  idle: '\u{1F9D1}',
  working: '\u{1F477}',
  driving: '\u{1F698}',
  stressed: '\u{1F625}',
};

const STATE_GLOW: Record<PlayerState, string> = {
  idle: theme.ui.action,
  working: theme.ui.warning,
  driving: theme.ui.positive,
  stressed: theme.ui.danger,
};

export default function PlayerAvatar({ state, x, y, stressLevel }: PlayerAvatarProps) {
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const glowAnim = useRef(new Animated.Value(0.3)).current;
  const bobAnim = useRef(new Animated.Value(0)).current;

  // Pulse animation for stressed state
  useEffect(() => {
    if (state === 'stressed') {
      const loop = Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 1.15, duration: 400, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1.0, duration: 400, useNativeDriver: true }),
        ]),
      );
      loop.start();
      return () => loop.stop();
    }
    pulseAnim.setValue(1);
    return undefined;
  }, [state, pulseAnim]);

  // Glow ring animation
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(glowAnim, { toValue: 0.7, duration: 1200, useNativeDriver: true }),
        Animated.timing(glowAnim, { toValue: 0.3, duration: 1200, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [glowAnim]);

  // Idle bob animation
  useEffect(() => {
    if (state === 'idle') {
      const loop = Animated.loop(
        Animated.sequence([
          Animated.timing(bobAnim, { toValue: -3, duration: 1000, useNativeDriver: true }),
          Animated.timing(bobAnim, { toValue: 0, duration: 1000, useNativeDriver: true }),
        ]),
      );
      loop.start();
      return () => loop.stop();
    }
    bobAnim.setValue(0);
    return undefined;
  }, [state, bobAnim]);

  const glowColor = STATE_GLOW[state];

  return (
    <Animated.View
      style={[
        styles.container,
        {
          left: `${x}%`,
          top: `${y}%`,
          transform: [
            { scale: pulseAnim },
            { translateY: bobAnim },
          ],
        },
      ]}
    >
      {/* Glow ring */}
      <Animated.View
        style={[
          styles.glowRing,
          {
            backgroundColor: glowColor,
            opacity: glowAnim,
          },
        ]}
      />
      {/* Avatar circle */}
      <View style={[styles.avatar, { borderColor: glowColor }]}>
        <Text style={styles.avatarEmoji}>{STATE_EMOJI[state]}</Text>
      </View>
      {/* State label */}
      {state !== 'idle' ? (
        <View style={[styles.stateBadge, { backgroundColor: glowColor }]}>
          <Text style={styles.stateBadgeText}>
            {state === 'working' ? 'Working' : state === 'driving' ? 'Driving' : 'Stressed!'}
          </Text>
        </View>
      ) : null}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    alignItems: 'center',
    marginLeft: -22,
    marginTop: -22,
    zIndex: 50,
  },
  glowRing: {
    position: 'absolute',
    width: 52,
    height: 52,
    borderRadius: 26,
    top: -4,
    left: -4,
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: theme.ui.bg.sheet,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    shadowColor: theme.ui.text.onLight,
    shadowOpacity: 0.2,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 3 },
    elevation: 6,
  },
  avatarEmoji: {
    fontSize: 22,
  },
  stateBadge: {
    marginTop: 2,
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 8,
  },
  stateBadgeText: {
    fontSize: 8,
    fontWeight: '800',
    color: theme.ui.bg.sheet,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
});
