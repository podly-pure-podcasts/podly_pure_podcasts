// Web Animations run on the compositor, so they keep full frame rate (120Hz
// included) while React renders. Use them for transform/opacity/filter moves
// that coincide with heavy main-thread work; GSAP stays for sequenced timelines.

// CSS equivalents of the GSAP eases used across the app.
export const EASE = {
  /** power3.out */
  settle: 'cubic-bezier(0.25, 1, 0.5, 1)',
  /** power2.in */
  in: 'cubic-bezier(0.32, 0, 0.67, 0)',
  /** power2.out */
  out: 'cubic-bezier(0.33, 1, 0.68, 1)',
  /** back.out(~1.7): a light overshoot for arrivals */
  pop: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
} as const;

interface StaggerOptions {
  /** Milliseconds. */
  duration: number;
  /** Milliseconds between consecutive elements. */
  stagger: number;
  easing: string;
  delay?: number;
}

const restingValue = (property: string) =>
  property === 'opacity' ? 1 : property === 'filter' ? 'blur(0px)' : 'none';

// Animates each element from `from` to its resting style, one after another.
// `fill: 'backwards'` holds later elements at `from` until their turn; once an
// animation finishes nothing is left behind on the element.
export function staggerIn(
  elements: Element[],
  from: Keyframe,
  { duration, stagger, easing, delay = 0 }: StaggerOptions
): Animation[] {
  const to: Keyframe = {};
  for (const property of Object.keys(from)) to[property] = restingValue(property);
  return elements.map((element, index) =>
    element.animate([from, to], { duration, easing, delay: delay + index * stagger, fill: 'backwards' })
  );
}
