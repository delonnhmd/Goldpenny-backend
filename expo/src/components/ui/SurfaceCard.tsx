import React from 'react';
import { StyleProp, ViewStyle } from 'react-native';

import Card, { CardVariant } from './Card';

export type SurfaceCardVariant = 'default' | 'highlighted' | 'warning' | 'muted';

function mapVariant(variant: SurfaceCardVariant): CardVariant {
  if (variant === 'highlighted') return 'info';
  if (variant === 'warning') return 'warning';
  if (variant === 'muted') return 'default';
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
    <Card variant={mapVariant(variant)} padded={padded} style={style}>
      {children}
    </Card>
  );
}
