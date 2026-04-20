import { uiTokens } from '@/theme/tokens';

import { animation, iconSize, shadow, spacing, typography, zIndex } from './tokens';

function makeColorScale() {
  return {
    background: uiTokens.bg.app,
    surface: uiTokens.bg.card,
    surfaceAlt: uiTokens.bg.cardRaised,
    sheet: uiTokens.bg.sheet,
    textPrimary: uiTokens.text.onDark,
    textSecondary: uiTokens.text.onDarkMuted,
    textPrimaryOnLight: uiTokens.text.onLight,
    textSecondaryOnLight: uiTokens.text.onLightMuted,
    positive: uiTokens.positive,
    danger: uiTokens.danger,
    warning: uiTokens.warning,
    info: uiTokens.info,
    accent: uiTokens.action,
    health: uiTokens.health,
    border: uiTokens.border,
    muted: uiTokens.text.onDarkMuted,
  } as const;
}

export function alpha(hex: string, opacity: number): string {
  const normalized = Math.max(0, Math.min(1, opacity));
  const value = Math.round(normalized * 255)
    .toString(16)
    .padStart(2, '0');
  return `${hex}${value}`;
}

const color = makeColorScale();
const radius = {
  sm: 6,
  md: 12,
  lg: uiTokens.radius.navTile,
  xl: uiTokens.radius.card,
  pill: uiTokens.radius.chip,
} as const;

const gameUi = {
  primary: uiTokens.action,
  success: uiTokens.positive,
  danger: uiTokens.danger,
  warning: uiTokens.warning,
  background: uiTokens.bg.app,
  card: uiTokens.bg.card,
  cardRaised: uiTokens.bg.cardRaised,
  sheet: uiTokens.bg.sheet,
  textPrimary: uiTokens.text.onDark,
  textSecondary: uiTokens.text.onDarkMuted,
  textPrimaryOnLight: uiTokens.text.onLight,
  textSecondaryOnLight: uiTokens.text.onLightMuted,
  border: uiTokens.border,
  cardBorder: uiTokens.border,
  secondaryButton: uiTokens.bg.cardRaised,
  secondaryButtonBorder: uiTokens.border,
  hudGlass: alpha(uiTokens.bg.card, 0.96),
  hudBorder: alpha(uiTokens.border, 0.96),
  hudShadow: alpha(uiTokens.text.onLight, 0.16),
  mapBackdrop: uiTokens.bg.app,
  mapBackdropDeep: uiTokens.bg.card,
  mapGrid: alpha(uiTokens.border, 0.42),
  road: uiTokens.border,
  roadStripe: alpha(uiTokens.text.onDark, 0.74),
  lowActivityOverlay: alpha(uiTokens.text.onDarkMuted, 0.2),
  district: {
    suburban: {
      base: alpha(uiTokens.positive, 0.18),
      accent: uiTokens.positive,
      label: uiTokens.text.onDark,
      badgeBackground: alpha(uiTokens.bg.card, 0.9),
    },
    downtown: {
      base: alpha(uiTokens.action, 0.2),
      accent: uiTokens.action,
      highlight: uiTokens.info,
      label: uiTokens.text.onDark,
      badgeBackground: alpha(uiTokens.bg.card, 0.92),
    },
    commercial: {
      base: alpha(uiTokens.warning, 0.18),
      accent: uiTokens.warning,
      label: uiTokens.text.onDark,
      badgeBackground: alpha(uiTokens.bg.card, 0.92),
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
    neutral: uiTokens.text.onDarkMuted,
    openSlot: uiTokens.info,
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
  color,
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
