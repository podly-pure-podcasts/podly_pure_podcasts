import { useEffect, useState } from 'react';

// Ticks once per second while `enabled`; otherwise the last value is frozen.
export function useNow(enabled: boolean): number {
  const [now, setNow] = useState<number>(() => Date.now());

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }
    setNow(Date.now());
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [enabled]);

  return now;
}
