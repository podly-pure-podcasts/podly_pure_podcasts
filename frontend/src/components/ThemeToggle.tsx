import { useTheme } from '../contexts/ThemeContext';
import { MoonIcon, SunIcon } from './icons';

type ThemeToggleProps = {
  className?: string;
};

export default function ThemeToggle({ className = '' }: ThemeToggleProps) {
  const { isDark, preference, toggleTheme } = useTheme();

  const nextThemeLabel = isDark ? 'light' : 'dark';
  const title =
    preference === 'system'
      ? `Following your OS theme. Switch to ${nextThemeLabel} mode.`
      : `Switch to ${nextThemeLabel} mode`;

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={`btn btn-secondary btn-icon ${className}`.trim()}
      aria-label={title}
      aria-pressed={isDark}
      title={title}
    >
      {isDark ? <SunIcon className="h-4 w-4" /> : <MoonIcon className="h-4 w-4" />}
    </button>
  );
}
