import { useLayoutEffect, useRef, type RefObject } from 'react';
import { prefersFullMotion } from '../utils/gsap';
import { EASE, staggerIn } from '../utils/nativeMotion';

interface CascadeOptions {
  /** Replays the entrance whenever this changes (a tab, a route, a feed). */
  playKey?: string | number;
  /** Holds the entrance until the content is real, not a loading state. */
  ready?: boolean;
  /** Elements to animate, scoped to the container. Defaults to its direct children. */
  selector?: string;
  /** Cards pop in with a bounce instead of rising and unblurring. */
  pop?: boolean;
  /** Only the first N items animate, so long lists don't drag. */
  limit?: number;
  /** Skip the first play, when a page transition already covers the arrival. */
  skipFirst?: boolean;
}

// The house entrance: items arrive one after another once their content is
// on screen, once per `playKey`.
export function useCascade(
  containerRef: RefObject<HTMLElement | null>,
  { playKey = 'once', ready = true, selector, pop = false, limit = 12, skipFirst = false }: CascadeOptions = {}
) {
  const playedFor = useRef<string | number | null>(null);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!ready || !container || playedFor.current === playKey) return;
    const isFirst = playedFor.current === null;
    playedFor.current = playKey;
    if ((skipFirst && isFirst) || !prefersFullMotion()) return;

    const items = (selector
      ? Array.from(container.querySelectorAll<HTMLElement>(selector))
      : Array.from(container.children as HTMLCollectionOf<HTMLElement>)
    ).slice(0, limit);
    if (!items.length) return;

    const animations = pop
      ? staggerIn(items, { opacity: 0, transform: 'translateY(16px) scale(0.9)' }, {
        duration: 500, stagger: 50, easing: EASE.pop,
      })
      : staggerIn(items, { opacity: 0, transform: 'translateY(16px)', filter: 'blur(6px)' }, {
        duration: 450, stagger: 70, easing: EASE.settle,
      });
    return () => animations.forEach((animation) => animation.cancel());
  }, [containerRef, playKey, ready, selector, pop, limit, skipFirst]);
}
