import { useMemo } from 'react';

import { BreakpointKey } from '@/design/breakpoints';
import { useBreakpoint } from '@/hooks/useBreakpoint';

type ResponsiveMap<T> = {
  mobile?: T;
  largeMobile?: T;
  tablet?: T;
  desktop?: T;
};

const fallbackOrder: BreakpointKey[] = ['desktop', 'tablet', 'largeMobile', 'mobile'];

export function useResponsiveValue<T>(values: ResponsiveMap<T>, fallback: T): T {
  const { current } = useBreakpoint();

  return useMemo(() => {
    const direct = values[current];
    if (direct !== undefined) return direct;

    const currentIndex = fallbackOrder.indexOf(current);
    const keys = [
      ...fallbackOrder.slice(currentIndex + 1),
      ...fallbackOrder.slice(0, currentIndex),
    ];

    for (const key of keys) {
      const candidate = values[key];
      if (candidate !== undefined) return candidate;
    }

    return fallback;
  }, [current, fallback, values]);
}
