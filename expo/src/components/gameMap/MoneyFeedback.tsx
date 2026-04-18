import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, Text, View } from 'react-native';

import { theme } from '@/design/theme';
import { formatMoney } from '@/lib/gameplayFormatters';

export interface MoneyFeedbackItem {
  id: string;
  amount: number;
  x?: number;
  y?: number;
}

interface MoneyFeedbackPopupProps {
  item: MoneyFeedbackItem;
  onComplete: (id: string) => void;
}

function MoneyFeedbackPopup({ item, onComplete }: MoneyFeedbackPopupProps) {
  const translateY = useRef(new Animated.Value(0)).current;
  const opacity = useRef(new Animated.Value(1)).current;
  const scale = useRef(new Animated.Value(0.5)).current;
  const shakeX = useRef(new Animated.Value(0)).current;
  const isGain = item.amount >= 0;

  useEffect(() => {
    const animations: Animated.CompositeAnimation[] = [
      // Scale in
      Animated.timing(scale, { toValue: 1, duration: 150, useNativeDriver: true }),
      // Float up
      Animated.timing(translateY, { toValue: -40, duration: 1200, useNativeDriver: true }),
      // Fade out
      Animated.timing(opacity, { toValue: 0, duration: 400, useNativeDriver: true }),
    ];

    // Add shake for losses
    if (!isGain) {
      animations.splice(1, 0,
        Animated.sequence([
          Animated.timing(shakeX, { toValue: 4, duration: 50, useNativeDriver: true }),
          Animated.timing(shakeX, { toValue: -4, duration: 50, useNativeDriver: true }),
          Animated.timing(shakeX, { toValue: 3, duration: 50, useNativeDriver: true }),
          Animated.timing(shakeX, { toValue: 0, duration: 50, useNativeDriver: true }),
        ]),
      );
    }

    Animated.sequence(animations).start(() => {
      onComplete(item.id);
    });
  }, [isGain, item.id, onComplete, opacity, scale, shakeX, translateY]);

  const label = isGain
    ? `+${formatMoney(item.amount)}`
    : `-${formatMoney(Math.abs(item.amount))}`;

  return (
    <Animated.View
      style={[
        styles.popup,
        {
          left: item.x ?? '50%',
          top: item.y ?? '40%',
          transform: [
            { translateY },
            { translateX: shakeX },
            { scale },
          ],
          opacity,
        },
      ]}
    >
      <Text style={[styles.text, isGain ? styles.textGain : styles.textLoss]}>
        {label}
      </Text>
    </Animated.View>
  );
}

interface MoneyFeedbackLayerProps {
  items: MoneyFeedbackItem[];
  onItemComplete: (id: string) => void;
}

export default function MoneyFeedbackLayer({ items, onItemComplete }: MoneyFeedbackLayerProps) {
  if (items.length === 0) return null;

  return (
    <View style={styles.layer} pointerEvents="none">
      {items.map((item) => (
        <MoneyFeedbackPopup key={item.id} item={item} onComplete={onItemComplete} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  layer: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 60,
    pointerEvents: 'none',
  },
  popup: {
    position: 'absolute',
    alignItems: 'center',
    marginLeft: -40,
  },
  text: {
    fontSize: 20,
    fontWeight: '900',
    textShadowColor: 'rgba(0, 0, 0, 0.15)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 3,
  },
  textGain: {
    color: theme.gameUi.success,
  },
  textLoss: {
    color: theme.gameUi.danger,
  },
});
