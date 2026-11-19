import { gsap } from 'gsap';
import { useGSAP } from '@gsap/react';

gsap.registerPlugin(useGSAP);

// Matches the `out` timing function in tailwind.config.js: settles, never overshoots.
export const SETTLE_EASE = 'power3.out';

export const FULL_MOTION = '(prefers-reduced-motion: no-preference)';

export const prefersFullMotion = () => window.matchMedia(FULL_MOTION).matches;

export { gsap, useGSAP };
