/** @type {import('tailwindcss').Config} */
const colors = require('tailwindcss/colors');
const plugin = require('tailwindcss/plugin');

// Theme-aware palette. Gray and the status hues resolve to CSS variables, so a
// class such as `bg-gray-50` or `text-red-700` means the same role in both
// themes and dark mode needs no per-class overrides. Light values are
// Tailwind's own; dark values invert the role: tints (50-300) become dark
// tints of the hue, text shades (600-900) become light shades. 400 and 500 are
// mid-tones that read on both grounds and stay fixed.
const THEMED_HUES = ['red', 'orange', 'amber', 'yellow', 'green', 'emerald', 'sky', 'blue', 'rose'];
const THEMED_SHADES = [50, 100, 200, 300, 600, 700, 800, 900];
const GRAY_SHADES = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];

// Navy dark theme. Text tiers stay bright so secondary copy keeps its contrast.
const DARK_CANVAS = [4, 10, 24];
const DARK_SURFACE = [15, 23, 42];
const DARK_GRAY = {
  50: [19, 28, 47],
  100: [35, 48, 69],
  200: [49, 63, 86],
  300: [100, 116, 139],
  400: [167, 180, 198],
  500: [180, 192, 208],
  600: [214, 223, 236],
  700: [226, 232, 240],
  800: [235, 239, 245],
  900: [248, 250, 252],
  950: [250, 251, 253],
};

const hexToRgb = (hex) => {
  const n = parseInt(hex.replace('#', ''), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
const mix = (from, to, amount) => from.map((c, i) => Math.round(c + (to[i] - c) * amount));
const triplet = (rgb) => rgb.join(' ');
const themed = (name) => `rgb(var(--${name}) / <alpha-value>)`;

function darkShade(hue, shade) {
  const scale = colors[hue];
  const tintAmount = { 50: 0.2, 100: 0.3, 200: 0.6, 300: 0.75 }[shade];
  if (tintAmount !== undefined) {
    return mix(DARK_SURFACE, hexToRgb(scale[500]), tintAmount);
  }
  const lighter = { 600: 200, 700: 200, 800: 200, 900: 100 }[shade];
  return hexToRgb(scale[lighter]);
}

function paletteVariables() {
  const light = {
    '--canvas': triplet(hexToRgb(colors.gray[50])),
    '--surface': '255 255 255',
  };
  const dark = {
    '--canvas': triplet(DARK_CANVAS),
    '--surface': triplet(DARK_SURFACE),
  };
  for (const shade of GRAY_SHADES) {
    light[`--gray-${shade}`] = triplet(hexToRgb(colors.gray[shade]));
    dark[`--gray-${shade}`] = triplet(DARK_GRAY[shade]);
  }
  for (const hue of THEMED_HUES) {
    for (const shade of THEMED_SHADES) {
      light[`--${hue}-${shade}`] = triplet(hexToRgb(colors[hue][shade]));
      dark[`--${hue}-${shade}`] = triplet(darkShade(hue, shade));
    }
  }
  return { light, dark };
}

function themedScale(hue, shades) {
  const scale = { ...colors[hue] };
  for (const shade of shades) {
    scale[shade] = themed(`${hue}-${shade}`);
  }
  return scale;
}

const themedColors = { gray: themedScale('gray', GRAY_SHADES) };
for (const hue of THEMED_HUES) {
  themedColors[hue] = themedScale(hue, THEMED_SHADES);
}

module.exports = {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        ...themedColors,
        canvas: themed('canvas'),
        surface: themed('surface'),
        // Fixed in both themes: white labels sit on these fills.
        accent: { DEFAULT: colors.blue[600], hover: colors.blue[700] },
        danger: { DEFAULT: colors.red[600], hover: colors.red[700] },
      },
      ringOffsetColor: {
        DEFAULT: 'rgb(var(--canvas))',
      },
      transitionProperty: {
        // `scale` carries the press feedback on buttons (see index.css).
        colors: 'color, background-color, border-color, text-decoration-color, fill, stroke, scale',
        DEFAULT:
          'color, background-color, border-color, text-decoration-color, fill, stroke, opacity, box-shadow, transform, filter, backdrop-filter, scale',
      },
      transitionTimingFunction: {
        out: 'cubic-bezier(0.23, 1, 0.32, 1)',
        drawer: 'cubic-bezier(0.32, 0.72, 0, 1)',
      },
      keyframes: {
        // Per-digit entrance for live timers, retriggered by remounting the
        // changed character via a key change.
        'digit-tick': {
          '0%': { transform: 'translateY(0.4em) scale(0.9)', opacity: '0', filter: 'blur(4px)' },
          '100%': { transform: 'translateY(0) scale(1)', opacity: '1', filter: 'blur(0)' },
        },
        'pop-in': {
          '0%': { transform: 'scale(0.88)', opacity: '0' },
          '60%': { opacity: '1' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
      },
      animation: {
        'digit-tick': 'digit-tick 350ms cubic-bezier(0.34, 1.56, 0.64, 1)',
        'pop-in': 'pop-in 320ms cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
    },
  },
  plugins: [
    plugin(({ addBase }) => {
      const { light, dark } = paletteVariables();
      addBase({ ':root': light, 'html.dark': dark });
    }),
  ],
};
