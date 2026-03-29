export const breakpoints = {
  mobile: 0,
  largeMobile: 420,
  tablet: 768,
  desktop: 1100,
} as const;

export type BreakpointKey = keyof typeof breakpoints;

export function getBreakpoint(width: number): BreakpointKey {
  if (width >= breakpoints.desktop) return 'desktop';
  if (width >= breakpoints.tablet) return 'tablet';
  if (width >= breakpoints.largeMobile) return 'largeMobile';
  return 'mobile';
}

export function isAtLeast(width: number, key: BreakpointKey): boolean {
  return width >= breakpoints[key];
}
