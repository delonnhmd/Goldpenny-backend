import { useEffect, useState } from 'react';
import { AccessibilityInfo, Easing } from 'react-native';

import { theme } from './theme';

export const motion = {
  duration: {
    fast: theme.animation.duration.fast,
    base: theme.animation.duration.base,
    slow: theme.animation.duration.slow,
  },
  easing: {
    standard: Easing.out(Easing.cubic),
    emphasized: Easing.out(Easing.poly(5)),
    gentle: Easing.inOut(Easing.sin),
  },
} as const;

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    let mounted = true;
    AccessibilityInfo.isReduceMotionEnabled()
      .then((enabled) => {
        if (mounted) setReduced(Boolean(enabled));
      })
      .catch(() => {
        if (mounted) setReduced(false);
      });

    const subscription = AccessibilityInfo.addEventListener('reduceMotionChanged', (enabled) => {
      setReduced(Boolean(enabled));
    });

    return () => {
      mounted = false;
      subscription.remove();
    };
  }, []);

  return reduced;
}
