export const colorTokens = {
  background: '#07101d',
  surface: '#0c1729',
  surfaceAlt: '#122033',
  textPrimary: '#f8fafc',
  textSecondary: '#a8b6c9',
  border: '#243348',
  positive: '#4ade80',
  warning: '#fbbf24',
  danger: '#f87171',
  info: '#60a5fa',
  accent: '#22d3ee',
  muted: '#7f8ea3',
} as const;

export const gameUiTokens = {
  primary: '#3A7DFF',
  success: '#22C55E',
  danger: '#EF4444',
  warning: '#F59E0B',
  background: '#F5F7FA',
  card: '#FFFFFF',
  textPrimary: '#111827',
  textSecondary: '#6B7280',
  border: '#D7DEE8',
  cardBorder: '#E5E7EB',
  secondaryButton: '#E5E7EB',
  secondaryButtonBorder: '#D1D5DB',
  hudGlass: 'rgba(255, 255, 255, 0.88)',
  hudBorder: 'rgba(255, 255, 255, 0.74)',
  hudShadow: 'rgba(17, 24, 39, 0.12)',
  mapBackdrop: '#EEF3FA',
  mapBackdropDeep: '#E1E9F6',
  mapGrid: '#E5EBF3',
  road: '#9CA3AF',
  roadStripe: 'rgba(255, 255, 255, 0.74)',
  lowActivityOverlay: 'rgba(107, 114, 128, 0.20)',
  district: {
    suburban: {
      base: '#D1FAE5',
      accent: '#A7F3D0',
      label: '#0F766E',
      badgeBackground: 'rgba(255, 255, 255, 0.72)',
    },
    downtown: {
      base: '#1E3A8A',
      accent: '#1E40AF',
      highlight: '#3B82F6',
      label: '#EFF6FF',
      badgeBackground: 'rgba(15, 23, 42, 0.26)',
    },
    commercial: {
      base: '#FDE68A',
      accent: '#FBBF24',
      label: '#92400E',
      badgeBackground: 'rgba(255, 251, 235, 0.78)',
    },
  },
  signals: {
    demand: '#FB923C',
    profit: '#4ADE80',
    lowActivity: '#6B7280',
  },
  icons: {
    player: '#3A7DFF',
    ownedBusiness: '#22C55E',
    neutral: '#6B7280',
    openSlot: '#FBBF24',
    hotspot: '#FB923C',
  },
  status: {
    cash: '#22C55E',
    stress: '#EF4444',
    health: '#F59E0B',
  },
} as const;

export const spacing = {
  xxs: 2,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
} as const;

export const radius = {
  sm: 6,
  md: 12,
  lg: 16,
  xl: 22,
  pill: 999,
} as const;

export const shadow = {
  none: {
    shadowColor: '#000000',
    shadowOpacity: 0,
    shadowRadius: 0,
    shadowOffset: { width: 0, height: 0 },
    elevation: 0,
  },
  sm: {
    shadowColor: '#020617',
    shadowOpacity: 0.18,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 2,
  },
  md: {
    shadowColor: '#020617',
    shadowOpacity: 0.24,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 8 },
    elevation: 6,
  },
  lg: {
    shadowColor: '#020617',
    shadowOpacity: 0.34,
    shadowRadius: 22,
    shadowOffset: { width: 0, height: 12 },
    elevation: 10,
  },
} as const;

export const typography = {
  display: { fontSize: 28, lineHeight: 34, fontWeight: '800' },
  headingLg: { fontSize: 22, lineHeight: 28, fontWeight: '800' },
  headingMd: { fontSize: 18, lineHeight: 24, fontWeight: '800' },
  headingSm: { fontSize: 16, lineHeight: 22, fontWeight: '700' },
  bodyLg: { fontSize: 16, lineHeight: 24, fontWeight: '400' },
  bodyMd: { fontSize: 14, lineHeight: 20, fontWeight: '400' },
  bodySm: { fontSize: 12, lineHeight: 18, fontWeight: '400' },
  label: { fontSize: 12, lineHeight: 16, fontWeight: '700' },
  caption: { fontSize: 11, lineHeight: 14, fontWeight: '600' },
} as const;

export const iconSize = {
  xs: 12,
  sm: 16,
  md: 20,
  lg: 24,
  xl: 28,
} as const;

export const zIndex = {
  base: 0,
  sticky: 100,
  header: 200,
  drawer: 300,
  modal: 400,
  toast: 500,
} as const;

export const animation = {
  duration: {
    fast: 140,
    base: 200,
    slow: 260,
  },
  easing: {
    standard: 'easeOutCubic',
    emphasized: 'easeOutQuint',
    gentle: 'easeInOutSine',
  },
} as const;

export type ColorTokenKey = keyof typeof colorTokens;
export type SpacingTokenKey = keyof typeof spacing;
export type RadiusTokenKey = keyof typeof radius;
export type TypographyTokenKey = keyof typeof typography;
