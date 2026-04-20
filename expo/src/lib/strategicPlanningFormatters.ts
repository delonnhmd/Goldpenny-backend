import { uiTokens } from '@/theme/tokens';

export function confidenceColor(label: string | null | undefined): string {
  const normalized = String(label || '').toLowerCase();
  if (normalized === 'high') return uiTokens.positive;
  if (normalized === 'moderate' || normalized === 'medium') return uiTokens.warning;
  if (normalized === 'low') return uiTokens.danger;
  return uiTokens.text.onDarkMuted;
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
  if (normalized === 'high') return uiTokens.danger;
  if (normalized === 'moderate' || normalized === 'medium') return uiTokens.warning;
  return uiTokens.positive;
}

export function pressureLevelColor(label: string | null | undefined): string {
  const normalized = String(label || '').toLowerCase();
  if (normalized === 'high') return uiTokens.danger;
  if (normalized === 'moderate' || normalized === 'medium') return uiTokens.warning;
  return uiTokens.positive;
}

export function tradeoffAccentColor(text: string | null | undefined): string {
  const normalized = String(text || '').toLowerCase();
  if (normalized.includes('higher') || normalized.includes('cost')) return uiTokens.danger;
  if (normalized.includes('gain') || normalized.includes('improve')) return uiTokens.positive;
  return uiTokens.text.onDarkMuted;
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
