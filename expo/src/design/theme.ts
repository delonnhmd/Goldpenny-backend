import { animation, colorTokens, iconSize, radius, shadow, spacing, typography, zIndex } from './tokens';

export const theme = {
  color: colorTokens,
  spacing,
  radius,
  shadow,
  typography,
  iconSize,
  zIndex,
  animation,
} as const;

export type AppTheme = typeof theme;

export function alpha(hex: string, opacity: number): string {
  const normalized = Math.max(0, Math.min(1, opacity));
  const value = Math.round(normalized * 255)
    .toString(16)
    .padStart(2, '0');
  return `${hex}${value}`;
}
