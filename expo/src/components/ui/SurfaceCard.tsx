import React from 'react';
import { StyleProp, ViewStyle } from 'react-native';

import Card, { CardVariant } from './Card';

export type SurfaceCardVariant = 'default' | 'highlighted' | 'warning' | 'muted';

function variantStyle(variant: SurfaceCardVariant): CardVariant {
  if (variant === 'highlighted') return 'info';
  if (variant === 'warning') return 'warning';
  return 'default';
}

export default function SurfaceCard({
  children,
  style,
  variant = 'default',
  padded = true,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  variant?: SurfaceCardVariant;
  padded?: boolean;
}) {
  return (
    <Card variant={variantStyle(variant)} padded={padded} style={style}>
      {children}
    </Card>
  );
}
