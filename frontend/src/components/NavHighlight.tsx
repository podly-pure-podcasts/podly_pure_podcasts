import { useEffect, useRef, type RefObject } from 'react';
import { gsap, prefersFullMotion, SETTLE_EASE, useGSAP } from '../utils/gsap';

interface NavHighlightProps {
  /** The nav whose `aria-current="page"` item the highlight sits behind. */
  navRef: RefObject<HTMLElement | null>;
  /** Changes whenever the current item may have moved (the route). */
  activeKey: string;
}

const currentItem = (nav: HTMLElement) => nav.querySelector<HTMLElement>('[aria-current="page"]');

// The active nav fill as one shared surface. On a route change it stretches to
// span both items, then contracts onto the new one, so the eye follows it.
// First paint and resizes place it without motion.
export default function NavHighlight({ navRef, activeKey }: NavHighlightProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const placed = useRef(false);

  useEffect(() => {
    const nav = navRef.current;
    const highlight = ref.current;
    if (!nav || !highlight) return;
    const ro = new ResizeObserver(() => {
      const el = currentItem(nav);
      if (el) gsap.set(highlight, { x: el.offsetLeft, width: el.offsetWidth });
    });
    ro.observe(nav);
    return () => ro.disconnect();
  }, [navRef]);

  useGSAP(
    () => {
      const highlight = ref.current;
      const nav = navRef.current;
      if (!highlight || !nav) return;
      const el = currentItem(nav);

      if (!el) {
        gsap.to(highlight, { autoAlpha: 0, duration: 0.15 });
        return;
      }
      const toX = el.offsetLeft;
      const toW = el.offsetWidth;
      const visible = gsap.getProperty(highlight, 'autoAlpha') !== 0;

      if (!placed.current || !visible || !prefersFullMotion()) {
        gsap.set(highlight, { x: toX, width: toW });
        gsap.to(highlight, { autoAlpha: 1, duration: placed.current ? 0.2 : 0 });
      } else {
        const fromX = gsap.getProperty(highlight, 'x') as number;
        const fromW = gsap.getProperty(highlight, 'width') as number;
        const spanX = Math.min(fromX, toX);
        const spanW = Math.max(fromX + fromW, toX + toW) - spanX;
        gsap
          .timeline()
          .to(highlight, { x: spanX, width: spanW, duration: 0.16, ease: 'power2.in' })
          .to(highlight, { x: toX, width: toW, duration: 0.26, ease: SETTLE_EASE });
      }
      placed.current = true;
    },
    { dependencies: [activeKey] }
  );

  return (
    <span
      ref={ref}
      aria-hidden="true"
      className="pointer-events-none invisible absolute left-0 top-1/2 -mt-4 h-8 rounded-md bg-gray-100 opacity-0"
    />
  );
}
