// Gold Penny — useScreenTimer (Step 67).
// Convenience hook that calls trackScreenView on mount for a given screen key.
// Designed to be dropped into any screen with one line.

import { useEffect } from 'react';

import { usePlaytest } from '@/features/playtest';

/**
 * Call this at the top of any gameplay screen component.
 * It emits a screen-view event and starts a screen-time timer on mount.
 * The timer is flushed automatically when the screen unmounts or the next
 * screen view is tracked.
 *
 * @param screenKey - lowercase screen identifier (brief | dashboard | work | market | business | summary)
 */
export function useScreenTimer(screenKey: string): void {
  const { trackScreenView } = usePlaytest();

  useEffect(() => {
    trackScreenView(screenKey);
    // Intentionally not tracking unmount flush here — PlaytestProvider
    // flushes the previous screen automatically on each new trackScreenView call.
    // An explicit cleanup would double-flush.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screenKey]);
}
