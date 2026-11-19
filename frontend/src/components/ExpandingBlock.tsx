import { useEffect, useRef, type ReactNode } from 'react';
import { gsap, prefersFullMotion, SETTLE_EASE, useGSAP } from '../utils/gsap';

interface ExpandingBlockProps {
  expanded: boolean;
  children: ReactNode;
  className?: string;
}

// Animates its own height between the collapsed and expanded content the caller
// swaps in, so "Show more" unrolls instead of snapping. The resting height is
// tracked while idle, so the tween always starts from what was on screen.
export default function ExpandingBlock({ expanded, children, className = '' }: ExpandingBlockProps) {
  const ref = useRef<HTMLDivElement>(null);
  const restingHeight = useRef<number | null>(null);
  const animating = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      if (!animating.current) restingHeight.current = el.offsetHeight;
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useGSAP(
    () => {
      const el = ref.current;
      const from = restingHeight.current;
      if (!el || from === null || !prefersFullMotion()) return;
      const to = el.offsetHeight;
      if (from === to) return;
      animating.current = true;
      gsap
        .timeline({
          onComplete: () => {
            animating.current = false;
            restingHeight.current = el.offsetHeight;
          },
        })
        .fromTo(
          el,
          { height: from, overflow: 'hidden' },
          { height: to, duration: 0.42, ease: SETTLE_EASE, clearProps: 'height,overflow' }
        )
        .from(el.firstElementChild, { autoAlpha: 0.35, duration: 0.3, ease: 'power1.out' }, 0);
    },
    { dependencies: [expanded] }
  );

  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  );
}
