export const colorTokens = {
  background: '#f1f5f9',
  surface: '#ffffff',
  surfaceAlt: '#f8fafc',
  textPrimary: '#0f172a',
  textSecondary: '#475569',
  border: '#cbd5e1',
  positive: '#16a34a',
  warning: '#ca8a04',
  danger: '#dc2626',
  info: '#2563eb',
  accent: '#1d4ed8',
  muted: '#94a3b8',
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
  md: 10,
  lg: 12,
  xl: 16,
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
    shadowOpacity: 0.06,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 2 },
    elevation: 1,
  },
  md: {
    shadowColor: '#020617',
    shadowOpacity: 0.1,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 3,
  },
  lg: {
    shadowColor: '#020617',
    shadowOpacity: 0.14,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 8 },
    elevation: 5,
  },
} as const;

export const typography = {
  display: { fontSize: 28, lineHeight: 34, fontWeight: '800' },
  headingLg: { fontSize: 22, lineHeight: 28, fontWeight: '800' },
  headingMd: { fontSize: 18, lineHeight: 24, fontWeight: '700' },
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
