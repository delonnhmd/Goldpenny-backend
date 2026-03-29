import { useMemo } from 'react';
import { useWindowDimensions } from 'react-native';

import { BreakpointKey, breakpoints, getBreakpoint } from '@/design/breakpoints';

export function useBreakpoint() {
  const { width, height } = useWindowDimensions();

  return useMemo(() => {
    const current = getBreakpoint(width);
    const atLeast = (key: BreakpointKey): boolean => width >= breakpoints[key];

    return {
      width,
      height,
      current,
      isMobile: current === 'mobile' || current === 'largeMobile',
      isTablet: current === 'tablet',
      isDesktop: current === 'desktop',
      atLeast,
    };
  }, [height, width]);
}
