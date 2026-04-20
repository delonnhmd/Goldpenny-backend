import React from 'react';

import Chip, { ChipVariant } from './Chip';

export type BadgeTone = 'info' | 'success' | 'warning' | 'danger' | 'locked' | 'neutral' | 'active';

function toneVariant(tone: BadgeTone): ChipVariant {
  if (tone === 'success') return 'positive';
  if (tone === 'danger') return 'danger';
  if (tone === 'warning') return 'warning';
  if (tone === 'info') return 'info';
  if (tone === 'active') return 'active';
  return 'neutral';
}

export default function Badge({
  label,
  tone = 'neutral',
}: {
  label: string;
  tone?: BadgeTone;
}) {
  return <Chip label={label} variant={toneVariant(tone)} />;
}
