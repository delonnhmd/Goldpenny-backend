import { uiTokens } from '@/theme/tokens';

import { animation, colorTokens, iconSize, radius, shadow, spacing, typography, zIndex } from './tokens';

export function alpha(hex: string, opacity: number): string {
  const normalized = Math.max(0, Math.min(1, opacity));
  const value = Math.round(normalized * 255)
    .toString(16)
    .padStart(2, '0');
  return `${hex}${value}`;
}

const gameUi = {
  primary: uiTokens.action,
  success: uiTokens.positive,
  danger: uiTokens.danger,
  warning: uiTokens.warning,
  info: uiTokens.info,
  background: uiTokens.bg.app,
  card: uiTokens.bg.sheet,
  textPrimary: uiTokens.text.onLight,
  textSecondary: uiTokens.text.onLightMuted,
  border: uiTokens.border,
  cardBorder: uiTokens.border,
  secondaryButton: uiTokens.bg.cardRaised,
  secondaryButtonBorder: uiTokens.border,
  hudGlass: alpha(uiTokens.bg.card, 0.96),
  hudBorder: alpha(uiTokens.border, 0.92),
  mapBackdrop: uiTokens.bg.app,
  mapBackdropDeep: uiTokens.bg.card,
  road: uiTokens.bg.cardRaised,
  roadStripe: uiTokens.text.onDarkMuted,
  lowActivityOverlay: alpha(uiTokens.text.onDarkMuted, 0.2),
  district: {
    suburban: {
      base: alpha(uiTokens.positive, 0.16),
      accent: alpha(uiTokens.positive, 0.48),
      label: uiTokens.text.onDark,
      badgeBackground: alpha(uiTokens.bg.cardRaised, 0.9),
    },
    downtown: {
      base: alpha(uiTokens.action, 0.24),
      accent: uiTokens.action,
      highlight: uiTokens.info,
      label: uiTokens.text.onDark,
      badgeBackground: alpha(uiTokens.bg.card, 0.84),
    },
    commercial: {
      base: alpha(uiTokens.warning, 0.22),
      accent: uiTokens.warning,
      label: uiTokens.text.onDark,
      badgeBackground: alpha(uiTokens.bg.cardRaised, 0.88),
    },
  },
  signals: {
    demand: uiTokens.warning,
    profit: uiTokens.positive,
    lowActivity: uiTokens.text.onDarkMuted,
  },
  icons: {
    player: uiTokens.action,
    ownedBusiness: uiTokens.positive,
    neutral: uiTokens.tab.inactive,
    openSlot: uiTokens.warning,
    hotspot: uiTokens.warning,
  },
  status: {
    cash: uiTokens.positive,
    stress: uiTokens.danger,
    health: uiTokens.health,
  },
} as const;

export const theme = {
  ui: uiTokens,
  color: colorTokens,
  gameUi,
  spacing,
  radius,
  shadow,
  typography,
  iconSize,
  zIndex,
  animation,
} as const;

export type AppTheme = typeof theme;
