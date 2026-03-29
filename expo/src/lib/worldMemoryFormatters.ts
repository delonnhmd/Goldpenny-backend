export function patternSeverityColor(severity?: string | null): string {
  const value = String(severity || '').toLowerCase();
  if (value === 'high') return '#b91c1c';
  if (value === 'moderate') return '#b45309';
  return '#166534';
}

export function patternStatusLabel(status?: string | null): string {
  const value = String(status || '').toLowerCase();
  if (value === 'active') return 'Active';
  if (value === 'fading') return 'Fading';
  if (value === 'resolved') return 'Resolved';
  return status ? String(status) : 'Unknown';
}

export function persistenceLabel(score?: number | null): string {
  const value = Number(score || 0);
  if (value >= 70) return 'Persistent';
  if (value >= 40) return 'Building';
  return 'Early';
}

export function pressureTone(level?: string | null): string {
  const value = String(level || '').toLowerCase();
  if (value === 'high') return '#b91c1c';
  if (value === 'moderate') return '#b45309';
  return '#166534';
}

export function trendLabel(direction?: string | null): string {
  const value = String(direction || '').toLowerCase();
  if (value === 'rising') return 'Rising';
  if (value === 'falling') return 'Falling';
  if (value === 'stable') return 'Stable';
  return direction ? String(direction) : 'Unknown';
}

export function lockedBadgeText(): string {
  return 'Locked Future Path';
}
