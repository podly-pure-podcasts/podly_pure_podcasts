import { useLayoutEffect, useRef, useState } from 'react';
import { prefersFullMotion } from '../utils/gsap';
import { EASE, staggerIn } from '../utils/nativeMotion';

// Entrance for a Stats pop-up's overview, once per opening and only after the
// stats have arrived: the sections rise and unblur in turn, and the
// `[data-stats-tile]` key-metric tiles pop in with a bounce when scrolled into view.
// Returns a callback ref for the overview: ModalShell mounts its content a render
// after opening, so the element itself has to be a dependency.
export function useStatsReveal(open: boolean, ready: boolean) {
  const played = useRef(false);
  const [overview, setOverview] = useState<HTMLElement | null>(null);

  useLayoutEffect(() => {
    if (!open) {
      played.current = false;
      return;
    }
    if (!ready || !overview || played.current) return;
    played.current = true;
    if (!prefersFullMotion()) return;

    const sections = staggerIn(
      Array.from(overview.children),
      { opacity: 0, transform: 'translateY(18px)', filter: 'blur(6px)' },
      { duration: 450, stagger: 80, easing: EASE.settle }
    );
    const cancelAll = (animations: Animation[]) => animations.forEach((animation) => animation.cancel());

    // The tiles usually sit below the fold, so they pop when scrolled to.
    const tiles = overview.querySelectorAll('[data-stats-tile]');
    const grid = tiles[0]?.parentElement;
    if (!grid) return () => cancelAll(sections);
    const pop = staggerIn(
      Array.from(tiles),
      { opacity: 0, transform: 'translateY(22px) scale(0.8)' },
      { duration: 550, stagger: 80, easing: EASE.pop }
    );
    pop.forEach((animation) => animation.pause());
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          pop.forEach((animation) => animation.play());
          io.disconnect();
        }
      },
      { root: overview.closest('.overflow-y-auto'), threshold: 0.25 }
    );
    io.observe(grid);
    return () => {
      io.disconnect();
      cancelAll(sections);
      cancelAll(pop);
    };
  }, [open, ready, overview]);

  return setOverview;
}
