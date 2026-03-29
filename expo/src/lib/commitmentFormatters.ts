export function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

export function adherenceLabel(value: number): string {
  const score = clampPercent(value);
  if (score >= 78) return 'Strong';
  if (score >= 62) return 'Good';
  if (score >= 46) return 'Watch';
  return 'Weak';
}

export function momentumLabel(value: number): string {
  const score = clampPercent(value);
  if (score >= 76) return 'High';
  if (score >= 58) return 'Building';
  if (score >= 42) return 'Flat';
  return 'Falling';
}

export function driftSeverityLabel(level: string): string {
  const normalized = String(level || '').toLowerCase();
  if (normalized === 'high') return 'High drift';
  if (normalized === 'moderate') return 'Moderate drift';
  if (normalized === 'low') return 'Low drift';
  return 'On track';
}

export function alignmentLabel(value: string): string {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'aligned') return 'Aligned';
  if (normalized === 'mostly_aligned') return 'Mostly aligned';
  if (normalized === 'drifting') return 'Drifting';
  if (normalized === 'off_track') return 'Off track';
  return 'Not set';
}

export function driftColor(level: string): string {
  const normalized = String(level || '').toLowerCase();
  if (normalized === 'high') return '#b91c1c';
  if (normalized === 'moderate') return '#b45309';
  if (normalized === 'low') return '#0369a1';
  return '#166534';
}

export function statusBadgeColor(status: string): string {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'active') return '#1d4ed8';
  if (normalized === 'completed') return '#166534';
  if (normalized === 'failed') return '#b91c1c';
  if (normalized === 'cancelled' || normalized === 'replaced' || normalized === 'expired') return '#7c3aed';
  return '#475569';
}

export function feedbackSeverityColor(severity: string): string {
  const normalized = String(severity || '').toLowerCase();
  if (normalized === 'success') return '#166534';
  if (normalized === 'warning') return '#b45309';
  if (normalized === 'critical') return '#b91c1c';
  return '#1e40af';
}
