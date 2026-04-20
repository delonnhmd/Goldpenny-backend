export function confidenceColor(label: string | null | undefined): string {
  const normalized = String(label || '').toLowerCase();
  if (normalized === 'high') return '#166534';
  if (normalized === 'moderate' || normalized === 'medium') return '#b45309';
  if (normalized === 'low') return '#b91c1c';
  return '#475569';
}

export function confidenceLabel(label: string | null | undefined): string {
  const normalized = String(label || '').toLowerCase();
  if (normalized === 'high') return 'High confidence';
  if (normalized === 'moderate' || normalized === 'medium') return 'Moderate confidence';
  if (normalized === 'low') return 'Low confidence';
  return 'Unknown confidence';
}

export function liquidityRiskColor(label: string | null | undefined): string {
  const normalized = String(label || '').toLowerCase();
  if (normalized === 'high') return '#b91c1c';
  if (normalized === 'moderate' || normalized === 'medium') return '#b45309';
  return '#166534';
}

export function pressureLevelColor(label: string | null | undefined): string {
  const normalized = String(label || '').toLowerCase();
  if (normalized === 'high') return '#b91c1c';
  if (normalized === 'moderate' || normalized === 'medium') return '#b45309';
  return '#166534';
}

export function tradeoffAccentColor(text: string | null | undefined): string {
  const normalized = String(text || '').toLowerCase();
  if (normalized.includes('higher') || normalized.includes('cost')) return '#b91c1c';
  if (normalized.includes('gain') || normalized.includes('improve')) return '#166534';
  return '#334155';
}

export function scoreLabel(value: number | null | undefined): string {
  const safe = Number.isFinite(Number(value)) ? Number(value) : 0;
  if (safe >= 75) return 'Strong';
  if (safe >= 50) return 'Balanced';
  if (safe >= 25) return 'Limited';
  return 'Weak';
}

export function lockedBadgeLabel(): string {
  return 'Locked - Future';
}
