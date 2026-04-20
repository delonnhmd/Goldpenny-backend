import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  Easing,
  StyleProp,
  StyleSheet,
  Text,
  TextStyle,
  View,
  ViewStyle,
} from 'react-native';

import { useReducedMotion } from '@/design/motion';
import { alpha, theme } from '@/design/theme';
import { formatMoney } from '@/lib/gameplayFormatters';

type Tone = 'neutral' | 'positive' | 'danger' | 'warning' | 'info';

function toneColorForValue(value: number, tone: Tone): string {
  if (tone === 'positive') return theme.color.positive;
  if (tone === 'danger') return theme.color.danger;
  if (tone === 'warning') return theme.color.warning;
  if (tone === 'info') return theme.color.info;
  if (value > 0) return theme.color.positive;
  if (value < 0) return theme.color.danger;
  return theme.color.textPrimary;
}

function pulseColor(delta: number, invertDeltaTone: boolean): string {
  const effective = invertDeltaTone ? -delta : delta;
  if (effective > 0) return alpha(theme.ui.positive, 0.22);
  if (effective < 0) return alpha(theme.ui.danger, 0.22);
  return alpha(theme.ui.action, 0.16);
}

export default function AnimatedMoneyValue({
  value,
  style,
  tone = 'neutral',
  durationMs = 760,
  threshold = 0.25,
  invertDeltaTone = false,
  showSign = false,
  formatter,
  pulseOnChange = true,
  containerStyle,
  animateOnMountFrom = null,
}: {
  value: number;
  style?: StyleProp<TextStyle>;
  tone?: Tone;
  durationMs?: number;
  threshold?: number;
  invertDeltaTone?: boolean;
  showSign?: boolean;
  formatter?: (next: number) => string;
  pulseOnChange?: boolean;
  containerStyle?: StyleProp<ViewStyle>;
  animateOnMountFrom?: number | null;
}) {
  const reducedMotion = useReducedMotion();
  const initial = Number.isFinite(value) ? Number(value) : 0;
  const [displayValue, setDisplayValue] = useState(initial);
  const hasHydratedRef = useRef(false);
  const previousValueRef = useRef(initial);
  const countValue = useRef(new Animated.Value(initial)).current;
  const pulseOpacity = useRef(new Animated.Value(0)).current;
  const pulseTintRef = useRef<string>(alpha(theme.ui.action, 0.16));

  const formatted = useMemo(() => {
    const current = Number.isFinite(displayValue) ? displayValue : 0;
    if (formatter) return formatter(current);
    const abs = formatMoney(Math.abs(current));
    if (!showSign) return current < 0 ? `-${abs}` : abs;
    if (current > 0) return `+${abs}`;
    if (current < 0) return `-${abs}`;
    return abs;
  }, [displayValue, formatter, showSign]);

  const textColor = useMemo(
    () => toneColorForValue(Number.isFinite(value) ? value : 0, tone),
    [tone, value],
  );

  useEffect(() => {
    const next = Number.isFinite(value) ? Number(value) : 0;
    const previous = hasHydratedRef.current
      ? (Number.isFinite(previousValueRef.current) ? Number(previousValueRef.current) : 0)
      : (Number.isFinite(animateOnMountFrom) ? Number(animateOnMountFrom) : (Number.isFinite(previousValueRef.current) ? Number(previousValueRef.current) : 0));
    hasHydratedRef.current = true;
    const delta = next - previous;
    previousValueRef.current = next;

    if (!pulseOnChange || Math.abs(delta) < Number(threshold || 0) || reducedMotion) {
      pulseOpacity.stopAnimation();
      pulseOpacity.setValue(0);
    } else {
      pulseTintRef.current = pulseColor(delta, invertDeltaTone);
      pulseOpacity.stopAnimation();
      pulseOpacity.setValue(0);
      Animated.sequence([
        Animated.timing(pulseOpacity, {
          toValue: 1,
          duration: 150,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: true,
        }),
        Animated.timing(pulseOpacity, {
          toValue: 0,
          duration: 450,
          easing: Easing.out(Easing.quad),
          useNativeDriver: true,
        }),
      ]).start();
    }

    if (reducedMotion || Math.abs(delta) < Number(threshold || 0)) {
      countValue.stopAnimation();
      countValue.setValue(next);
      setDisplayValue(next);
      return;
    }

    let mounted = true;
    countValue.stopAnimation();
    countValue.setValue(previous);
    const listenerId = countValue.addListener(({ value: frameValue }) => {
      if (mounted) {
        setDisplayValue(frameValue);
      }
    });

    Animated.timing(countValue, {
      toValue: next,
      duration: Math.max(300, Math.min(1000, Math.round(durationMs))),
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start(({ finished }) => {
      if (finished && mounted) {
        setDisplayValue(next);
      }
      countValue.removeListener(listenerId);
    });

    return () => {
      mounted = false;
      countValue.removeListener(listenerId);
    };
  }, [animateOnMountFrom, countValue, durationMs, invertDeltaTone, pulseOnChange, pulseOpacity, reducedMotion, threshold, value]);

  return (
    <View style={[styles.wrap, containerStyle]}>
      <Animated.View
        pointerEvents="none"
        style={[
          StyleSheet.absoluteFillObject,
          styles.pulseLayer,
          {
            opacity: pulseOpacity.interpolate({
              inputRange: [0, 1],
              outputRange: [0, 1],
            }),
            backgroundColor: pulseTintRef.current,
          },
        ]}
      />
      <Text style={[styles.valueText, { color: textColor }, style]} numberOfLines={1}>
        {formatted}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    overflow: 'hidden',
    borderRadius: theme.radius.sm,
    paddingHorizontal: 2,
    paddingVertical: 1,
    alignSelf: 'flex-end',
  },
  pulseLayer: {
    borderRadius: theme.radius.sm,
  },
  valueText: {
    ...theme.typography.bodySm,
    fontWeight: '700',
    textAlign: 'right',
  },
});
