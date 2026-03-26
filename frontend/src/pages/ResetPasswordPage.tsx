import type { FormEvent } from 'react';
import { useMemo, useState } from 'react';
import axios from 'axios';
import { Link, useSearchParams } from 'react-router-dom';
import { authApi } from '../services/api';
import { useTheme } from '../contexts/ThemeContext';
import { getThemeSwitchTitle } from '../theme';

export default function ResetPasswordPage() {
  const { theme, toggleTheme } = useTheme();
  const [params] = useSearchParams();
  const token = useMemo(() => (params.get('token') ?? '').trim(), [params]);

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    if (!token) {
      setError('Missing reset token.');
      return;
    }
    if (!password) {
      setError('Password is required.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }

    setSubmitting(true);
    try {
      await authApi.confirmPasswordReset(token, password);
      setSuccess(true);
      setPassword('');
      setConfirm('');
    } catch (err) {
      if (axios.isAxiosError(err)) {
        const message = err.response?.data?.error ?? 'Reset failed.';
        setError(message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Reset failed. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="bg-gradient-to-br from-pink-50 via-purple-50 to-cyan-50 dark:from-slate-900 dark:via-purple-950 dark:to-slate-900"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        overflowY: 'auto',
        overflowX: 'hidden',
        WebkitOverflowScrolling: 'touch',
      }}
    >
      <button
        onClick={toggleTheme}
        style={{ position: 'fixed', top: 16, right: 16, zIndex: 100 }}
        className="p-3 rounded-xl bg-white/80 dark:bg-slate-800/80 border border-purple-200 dark:border-purple-700 text-purple-600 dark:text-purple-300 shadow-lg"
        title={getThemeSwitchTitle(theme)}
      >
        {theme === 'light' ? (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
          </svg>
        ) : theme === 'dark' ? (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.073 3.306a1 1 0 00.95.69h3.476c.969 0 1.371 1.24.588 1.81l-2.812 2.043a1 1 0 00-.364 1.118l1.074 3.305c.3.922-.755 1.688-1.538 1.118l-2.812-2.043a1 1 0 00-1.176 0l-2.812 2.043c-.784.57-1.838-.196-1.539-1.118l1.074-3.305a1 1 0 00-.363-1.118L4.962 8.733c-.783-.57-.38-1.81.588-1.81h3.476a1 1 0 00.95-.69l1.073-3.306z" />
          </svg>
        ) : (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
          </svg>
        )}
      </button>

      <div className="max-w-xl mx-auto px-4 py-10">
        <div className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-sm shadow-xl rounded-2xl border border-purple-100 dark:border-purple-800 p-8">
          <div className="text-center mb-6">
            <h1 className="text-2xl font-bold text-purple-900 dark:text-purple-100">Choose a new password</h1>
            <p className="text-sm text-purple-600/70 dark:text-purple-300/70 mt-1">
              This link is valid for 1 hour.
            </p>
          </div>

          {!token && (
            <div className="rounded-xl bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-300">
              Missing reset token.
            </div>
          )}

          {token && (
            <form className="space-y-5" onSubmit={handleSubmit}>
              <div>
                <label htmlFor="password" className="block text-sm font-medium text-purple-700 dark:text-purple-300 mb-1">New password</label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="block w-full rounded-xl border border-purple-200 dark:border-purple-700 bg-white/50 dark:bg-slate-700/50 px-4 py-3 shadow-sm focus:border-purple-400 focus:outline-none focus:ring-2 focus:ring-purple-400/20 transition-all dark:text-white dark:placeholder-purple-300/50"
                  placeholder="New password"
                  disabled={submitting || success}
                  required
                />
              </div>

              <div>
                <label htmlFor="confirm" className="block text-sm font-medium text-purple-700 dark:text-purple-300 mb-1">Confirm new password</label>
                <input
                  id="confirm"
                  name="confirm"
                  type="password"
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(event) => setConfirm(event.target.value)}
                  className="block w-full rounded-xl border border-purple-200 dark:border-purple-700 bg-white/50 dark:bg-slate-700/50 px-4 py-3 shadow-sm focus:border-purple-400 focus:outline-none focus:ring-2 focus:ring-purple-400/20 transition-all dark:text-white dark:placeholder-purple-300/50"
                  placeholder="Repeat password"
                  disabled={submitting || success}
                  required
                />
              </div>

              {error && (
                <div className="rounded-xl bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-300">
                  {error}
                </div>
              )}

              {success && (
                <div className="rounded-xl bg-emerald-50 dark:bg-emerald-900/30 border border-emerald-200 dark:border-emerald-800 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300">
                  Password updated. You can now sign in.
                </div>
              )}

              <button
                type="submit"
                disabled={submitting || success}
                className="w-full flex justify-center items-center gap-2 rounded-xl bg-gradient-to-r from-pink-500 via-purple-500 to-cyan-500 px-4 py-3 text-white font-semibold shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 hover:scale-[1.02] transition-all disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:scale-100"
              >
                {submitting && <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />}
                {submitting ? 'Updating…' : 'Update password'}
              </button>
            </form>
          )}

          <div className="mt-6 pt-6 border-t border-purple-100 dark:border-purple-800 text-sm text-center">
            <Link className="text-purple-700 dark:text-purple-200 font-medium hover:underline" to="/login">
              Back to sign in
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
