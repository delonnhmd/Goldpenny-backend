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
