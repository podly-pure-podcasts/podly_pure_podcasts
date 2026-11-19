import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';

export type ThemePreference = 'system' | 'light' | 'dark';
export type ResolvedTheme = 'light' | 'dark';

const THEME_STORAGE_KEY = 'podly-theme';
const THEME_MEDIA_QUERY = '(prefers-color-scheme: dark)';

type ThemeContextValue = {
  isDark: boolean;
  preference: ThemePreference;
  resolvedTheme: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
  toggleTheme: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function getSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined') {
    return 'light';
  }

  return window.matchMedia(THEME_MEDIA_QUERY).matches ? 'dark' : 'light';
}

function readStoredPreference(): ThemePreference {
  if (typeof window === 'undefined') {
    return 'system';
  }

  const storedPreference = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (
    storedPreference === 'system'
    || storedPreference === 'light'
    || storedPreference === 'dark'
  ) {
    return storedPreference;
  }

  return 'system';
}

function applyThemeToDocument(
  preference: ThemePreference,
  resolvedTheme: ResolvedTheme,
) {
  if (typeof document === 'undefined') {
    return;
  }

  const root = document.documentElement;
  root.classList.add('theme-switching');
  root.classList.toggle('dark', resolvedTheme === 'dark');
  root.style.colorScheme = resolvedTheme;
  root.dataset.themePreference = preference;
  // Commit the new palette with transitions off, then re-enable them.
  void root.offsetHeight;
  window.requestAnimationFrame(() => root.classList.remove('theme-switching'));
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState<ThemePreference>(readStoredPreference);
  const [systemTheme, setSystemTheme] = useState<ResolvedTheme>(getSystemTheme);

  const resolvedTheme = preference === 'system' ? systemTheme : preference;

  useEffect(() => {
    if (typeof window === 'undefined') {
      return undefined;
    }

    const mediaQueryList = window.matchMedia(THEME_MEDIA_QUERY);
    const handleChange = (event: MediaQueryListEvent) => {
      setSystemTheme(event.matches ? 'dark' : 'light');
    };

    setSystemTheme(mediaQueryList.matches ? 'dark' : 'light');
    mediaQueryList.addEventListener('change', handleChange);

    return () => {
      mediaQueryList.removeEventListener('change', handleChange);
    };
  }, []);

  useEffect(() => {
    applyThemeToDocument(preference, resolvedTheme);

    if (typeof window === 'undefined') {
      return;
    }

    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  }, [preference, resolvedTheme]);

  const toggleTheme = () => {
    setPreference((currentPreference) => {
      const activeTheme =
        currentPreference === 'system' ? systemTheme : currentPreference;
      return activeTheme === 'dark' ? 'light' : 'dark';
    });
  };

  return (
    <ThemeContext.Provider
      value={{
        isDark: resolvedTheme === 'dark',
        preference,
        resolvedTheme,
        setPreference,
        toggleTheme,
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }

  return context;
}
