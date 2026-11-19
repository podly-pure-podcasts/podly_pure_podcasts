import { useEffect, useState } from 'react';

// True only once `active` has stayed true for `delayMs`. Used to hold back
// loading skeletons so a fast response goes straight to content without a
// flash of placeholders.
export function useDelayedFlag(active: boolean, delayMs = 400): boolean {
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (!active) {
      setShown(false);
      return;
    }
    const timeout = window.setTimeout(() => setShown(true), delayMs);
    return () => window.clearTimeout(timeout);
  }, [active, delayMs]);

  return active && shown;
}
