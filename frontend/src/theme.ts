export type Theme = 'light' | 'dark' | 'original';

const THEME_ORDER: Theme[] = ['light', 'dark', 'original'];

export const THEME_STORAGE_KEY = 'podly-theme';

export function isValidTheme(value: string | null): value is Theme {
  return value === 'light' || value === 'dark' || value === 'original';
}

export function getNextTheme(theme: Theme): Theme {
  const currentIndex = THEME_ORDER.indexOf(theme);
  const nextIndex = (currentIndex + 1) % THEME_ORDER.length;
  return THEME_ORDER[nextIndex];
}

export function getThemeLabel(theme: Theme): string {
  if (theme === 'original') return 'Blue';
  return theme === 'dark' ? 'Dark' : 'Light';
}

export function isDarkSurfaceTheme(theme: Theme): boolean {
  return theme === 'dark' || theme === 'original';
}

export function getThemeLogoPath(theme: Theme): string {
  return theme === 'original'
    ? '/images/logos/original-logo.png'
    : '/images/logos/unicorn-logo.png';
}

export function getThemeBrandName(_theme: Theme): string {
  return 'Podly';
}

export function getThemeBrandClass(theme: Theme): string {
  return theme === 'original' ? 'original-brand-text' : 'rainbow-text';
}

export function getThemeSwitchTitle(theme: Theme): string {
  const current = getThemeLabel(theme);
  const next = getThemeLabel(getNextTheme(theme));
  return `Theme: ${current}. Click to switch to ${next}.`;
}
