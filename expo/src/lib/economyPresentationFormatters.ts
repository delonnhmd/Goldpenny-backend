import { formatMoney } from '@/lib/gameplayFormatters';
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
  if (normalized === 'supportive') return '#166534';
  if (normalized === 'pressured') return '#b91c1c';
  return '#1d4ed8';
}

export function trendLabelText(trend: TrendLabel): string {
  const normalized = String(trend || '').toLowerCase();
  if (normalized === 'rising') return 'Rising';
  if (normalized === 'falling') return 'Falling';
  return 'Stable';
}

export function trendTone(trend: TrendLabel): string {
  const normalized = String(trend || '').toLowerCase();
  if (normalized === 'rising') return '#dc2626';
  if (normalized === 'falling') return '#166534';
  return '#475569';
}

export function volatilityTone(label: VolatilityLabel): string {
  const normalized = String(label || '').toLowerCase();
  if (normalized === 'high') return '#b91c1c';
  if (normalized === 'moderate') return '#b45309';
  return '#2563eb';
}

export function marginTone(label: MarginOutlook): string {
  const normalized = String(label || '').toLowerCase();
  if (normalized === 'favorable') return '#166534';
  if (normalized === 'pressured') return '#b91c1c';
  return '#1d4ed8';
}

export function costPressureTone(label: CostPressure): string {
  const normalized = String(label || '').toLowerCase();
  if (normalized === 'high') return '#b91c1c';
  if (normalized === 'moderate') return '#b45309';
  return '#166534';
}

export function commutePressureTone(level: CommutePressureLevel): string {
  const normalized = String(level || '').toLowerCase();
  if (normalized === 'high') return '#b91c1c';
  if (normalized === 'moderate') return '#b45309';
  return '#166534';
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
