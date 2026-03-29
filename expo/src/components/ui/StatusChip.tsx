import React from 'react';

import Badge, { BadgeTone } from './Badge';

export default function StatusChip({
  label,
  status = 'neutral',
}: {
  label: string;
  status?: BadgeTone;
}) {
  return <Badge label={label} tone={status} />;
}
