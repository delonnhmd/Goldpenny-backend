import { uiTokens } from '@/theme/tokens';

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
  if (normalized === 'high') return uiTokens.danger;
  if (normalized === 'moderate') return uiTokens.warning;
  if (normalized === 'low') return uiTokens.info;
  return uiTokens.positive;
}

export function statusBadgeColor(status: string): string {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'active') return uiTokens.action;
  if (normalized === 'completed') return uiTokens.positive;
  if (normalized === 'failed') return uiTokens.danger;
  if (normalized === 'cancelled' || normalized === 'replaced' || normalized === 'expired') return uiTokens.warning;
  return uiTokens.text.onDarkMuted;
}

export function feedbackSeverityColor(severity: string): string {
  const normalized = String(severity || '').toLowerCase();
  if (normalized === 'success') return uiTokens.positive;
  if (normalized === 'warning') return uiTokens.warning;
  if (normalized === 'critical') return uiTokens.danger;
  return uiTokens.action;
}
