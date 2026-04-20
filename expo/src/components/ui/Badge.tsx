import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { theme } from '@/design/theme';

export type BadgeTone = 'info' | 'success' | 'warning' | 'danger' | 'locked' | 'neutral';

const toneStyles = StyleSheet.create({
  info: { borderColor: 'rgba(96, 165, 250, 0.34)', backgroundColor: 'rgba(30, 64, 175, 0.2)', color: '#93c5fd' },
  success: { borderColor: 'rgba(74, 222, 128, 0.34)', backgroundColor: 'rgba(20, 83, 45, 0.32)', color: '#86efac' },
  warning: { borderColor: 'rgba(251, 191, 36, 0.34)', backgroundColor: 'rgba(120, 53, 15, 0.28)', color: '#fcd34d' },
  danger: { borderColor: 'rgba(248, 113, 113, 0.34)', backgroundColor: 'rgba(127, 29, 29, 0.3)', color: '#fca5a5' },
  locked: { borderColor: 'rgba(148, 163, 184, 0.18)', backgroundColor: 'rgba(15, 23, 42, 0.9)', color: '#94a3b8' },
  neutral: { borderColor: 'rgba(148, 163, 184, 0.18)', backgroundColor: 'rgba(15, 23, 42, 0.9)', color: '#cbd5e1' },
});

export default function Badge({
  label,
  tone = 'neutral',
}: {
  label: string;
  tone?: BadgeTone;
}) {
  const style = toneStyles[tone];
  return (
    <View style={[styles.badge, { borderColor: style.borderColor, backgroundColor: style.backgroundColor }]}>
      <Text style={[styles.text, { color: style.color }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    borderWidth: 1,
    borderRadius: theme.radius.pill,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xxs,
    alignSelf: 'flex-start',
  },
  text: {
    ...theme.typography.caption,
    textTransform: 'uppercase',
  },
});
