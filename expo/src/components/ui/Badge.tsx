import React from 'react';

import Chip from './Chip';

export type BadgeTone = 'info' | 'success' | 'warning' | 'danger' | 'locked' | 'neutral';

function toChipVariant(tone: BadgeTone): 'neutral' | 'positive' | 'danger' | 'warning' | 'info' {
  if (tone === 'success') return 'positive';
  if (tone === 'danger') return 'danger';
  if (tone === 'warning') return 'warning';
  if (tone === 'info') return 'info';
  return 'neutral';
}

export default function Badge({
  label,
  tone = 'neutral',
}: {
  label: string;
  tone?: BadgeTone;
}) {
  return <Chip label={label} variant={toChipVariant(tone)} />;
}
