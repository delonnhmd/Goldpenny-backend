import {
  ActionRecommendationState,
  ConfidenceLevel,
  SeverityLevel,
  TrendDirection,
} from '@/types/gameplay';
import {
  clampDeltaRange,
  normalizeCreditScore,
  normalizeFiniteNumber,
  normalizeMoneyValue,
  normalizePercentageStat,
} from '@/lib/economySafety';
import { uiTokens } from '@/theme/tokens';

export function formatMoney(value: number | null | undefined, digits = 2): string {
  const safe = normalizeMoneyValue(value, { fallback: 0, allowNegative: true });
  return `${safe.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} xgp`;
}

export function formatHours(value: number | null | undefined): string {
  const safe = normalizeFiniteNumber(value, { fallback: 0, min: 0, max: 9999 });
  return `${safe.toFixed(1)}h`;
}

export function formatDelta(value: number | null | undefined, digits = 1): string {
  const safe = clampDeltaRange(value, { fallback: 0 });
  const sign = safe > 0 ? '+' : '';
  return `${sign}${safe.toFixed(digits)}`;
}

export function formatProgress(current: number | null | undefined, target: number | null | undefined): string {
  const safeCurrent = normalizeFiniteNumber(current, { fallback: 0, min: 0, max: 1000000 });
  const safeTarget = normalizeFiniteNumber(target, { fallback: 1, min: 1, max: 1000000 });
  return `${safeCurrent.toFixed(safeTarget <= 5 ? 0 : 1)}/${safeTarget.toFixed(safeTarget <= 5 ? 0 : 1)}`;
}

export function severityColor(level: SeverityLevel | null | undefined): string {
  switch (level) {
    case 'critical':
      return uiTokens.danger;
    case 'high':
      return uiTokens.danger;
    case 'medium':
      return uiTokens.warning;
    case 'low':
      return uiTokens.info;
    case 'info':
    default:
      return uiTokens.text.onDarkMuted;
  }
}

export function actionStatusColor(status: ActionRecommendationState): string {
  switch (status) {
    case 'recommended':
      return uiTokens.positive;
    case 'available':
      return uiTokens.action;
    case 'blocked':
    default:
      return uiTokens.danger;
  }
}

export function progressStatusColor(status: string | null | undefined): string {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'completed') return uiTokens.positive;
  if (normalized === 'in_progress') return uiTokens.action;
  if (normalized === 'failed') return uiTokens.danger;
  return uiTokens.text.onDarkMuted;
}

export function urgencyColor(urgency: string | null | undefined): string {
  const normalized = String(urgency || '').toLowerCase();
  if (normalized === 'high') return uiTokens.danger;
  if (normalized === 'medium') return uiTokens.warning;
  return uiTokens.info;
}

export function confidenceLabel(level: ConfidenceLevel | null | undefined): string {
  switch (level) {
    case 'high':
      return 'High confidence';
    case 'medium':
      return 'Moderate confidence';
    case 'low':
      return 'Low confidence';
    default:
      return 'Unknown confidence';
  }
}

export function trendLabel(direction: TrendDirection): string {
  switch (direction) {
    case 'up':
      return 'Likely gain';
    case 'down':
      return 'Likely loss';
    case 'flat':
      return 'Stable';
    case 'mixed':
    default:
      return 'Mixed impact';
  }
}

export function stressTone(stress: number | null | undefined): string {
  const value = normalizePercentageStat(stress, 0);
  if (value >= 80) return uiTokens.danger;
  if (value >= 65) return uiTokens.health;
  if (value >= 45) return uiTokens.warning;
  return uiTokens.positive;
}

export function healthTone(health: number | null | undefined): string {
  const value = normalizePercentageStat(health, 100);
  if (value <= 30) return uiTokens.danger;
  if (value <= 45) return uiTokens.health;
  if (value <= 65) return uiTokens.warning;
  return uiTokens.positive;
}

export function creditTone(score: number | null | undefined): string {
  const value = normalizeCreditScore(score, 650);
  if (value < 580) return uiTokens.danger;
  if (value < 670) return uiTokens.warning;
  if (value < 740) return uiTokens.info;
  return uiTokens.positive;
}
