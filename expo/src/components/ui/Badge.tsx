import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { theme } from '@/design/theme';

export type BadgeTone = 'info' | 'success' | 'warning' | 'danger' | 'locked' | 'neutral';

const toneStyles = StyleSheet.create({
  info: { borderColor: '#bfdbfe', backgroundColor: '#eff6ff', color: '#1d4ed8' },
  success: { borderColor: '#bbf7d0', backgroundColor: '#f0fdf4', color: '#15803d' },
  warning: { borderColor: '#fde68a', backgroundColor: '#fffbeb', color: '#a16207' },
  danger: { borderColor: '#fecaca', backgroundColor: '#fef2f2', color: '#b91c1c' },
  locked: { borderColor: '#e2e8f0', backgroundColor: '#f8fafc', color: '#475569' },
  neutral: { borderColor: '#cbd5e1', backgroundColor: '#f8fafc', color: '#334155' },
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
