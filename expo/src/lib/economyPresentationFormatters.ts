import { formatMoney } from '@/lib/gameplayFormatters';
import { uiTokens } from '@/theme/tokens';
import {
  CommutePressureLevel,
  CostPressure,
  MarginOutlook,
  MarketMood,
  TrendLabel,
  VolatilityLabel,
} from '@/types/economyPresentation';

export function marketMoodLabel(mood: MarketMood): string {
  const normalized = String(mood || '').toLowerCase();
  if (normalized === 'supportive') return 'Supportive';
  if (normalized === 'pressured') return 'Pressured';
  return 'Mixed';
}

export function marketMoodColor(mood: MarketMood): string {
  const normalized = String(mood || '').toLowerCase();
  if (normalized === 'supportive') return uiTokens.positive;
  if (normalized === 'pressured') return uiTokens.danger;
  return uiTokens.action;
}

export function trendLabelText(trend: TrendLabel): string {
  const normalized = String(trend || '').toLowerCase();
  if (normalized === 'rising') return 'Rising';
  if (normalized === 'falling') return 'Falling';
  return 'Stable';
}

export function trendTone(trend: TrendLabel): string {
  const normalized = String(trend || '').toLowerCase();
  if (normalized === 'rising') return uiTokens.danger;
  if (normalized === 'falling') return uiTokens.positive;
  return uiTokens.text.onDarkMuted;
}

export function volatilityTone(label: VolatilityLabel): string {
  const normalized = String(label || '').toLowerCase();
  if (normalized === 'high') return uiTokens.danger;
  if (normalized === 'moderate') return uiTokens.warning;
  return uiTokens.action;
}

export function marginTone(label: MarginOutlook): string {
  const normalized = String(label || '').toLowerCase();
  if (normalized === 'favorable') return uiTokens.positive;
  if (normalized === 'pressured') return uiTokens.danger;
  return uiTokens.action;
}

export function costPressureTone(label: CostPressure): string {
  const normalized = String(label || '').toLowerCase();
  if (normalized === 'high') return uiTokens.danger;
  if (normalized === 'moderate') return uiTokens.warning;
  return uiTokens.positive;
}

export function commutePressureTone(level: CommutePressureLevel): string {
  const normalized = String(level || '').toLowerCase();
  if (normalized === 'high') return uiTokens.danger;
  if (normalized === 'moderate') return uiTokens.warning;
  return uiTokens.positive;
}

export function lockedBadgeText(): string {
  return 'Locked Future';
}

export function levelBadgeText(value: string): string {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (v) => v.toUpperCase());
}

export function formatIndexLevel(level: number): string {
  const safe = Number.isFinite(level) ? level : 0;
  return formatMoney(safe, 1);
}
