import type { FormEvent } from 'react';
import { useState, useEffect } from 'react';
import axios from 'axios';
import { Link, useNavigate } from 'react-router-dom';
import { authApi } from '../services/api';
import { useTheme } from '../contexts/ThemeContext';
import {
  getThemeBrandClass,
  getThemeBrandName,
  getThemeLogoPath,
  getThemeSwitchTitle,
} from '../theme';

export default function SignupPage() {
  const { theme, toggleTheme } = useTheme();
  const logoPath = getThemeLogoPath(theme);
  const brandName = getThemeBrandName(theme);
  const brandClass = getThemeBrandClass(theme);
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    authApi.getStatus().then((status) => {
      if (!status.allow_signup) {
        navigate('/login', { replace: true });
      } else {
        setLoading(false);
      }
    }).catch(() => {
      navigate('/login', { replace: true });
    });
  }, [navigate]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-pink-50 via-purple-50 to-cyan-50 dark:from-slate-900 dark:via-purple-950 dark:to-slate-900">
        <div className="animate-spin h-8 w-8 border-4 border-purple-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail || !trimmedEmail.includes('@')) {
      setError('Please enter a valid email address.');
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
      await authApi.signup(trimmedEmail, password);
      setSuccess(true);
      setEmail('');
      setPassword('');
      setConfirm('');
    } catch (err) {
      if (axios.isAxiosError(err)) {
        const message = err.response?.data?.error ?? 'Signup failed.';
        setError(message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Signup failed. Please try again.');
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

      <div className="max-w-5xl mx-auto px-4 py-8 flex flex-col md:flex-row gap-8 md:gap-12 items-start md:min-h-screen md:justify-center md:items-center">
        <div className="flex-1 text-center md:text-left flex flex-col justify-center">
          <div className="flex items-center justify-center md:justify-start gap-3 mb-6">
            <div className="relative">
              <div className="absolute inset-0 bg-gradient-to-r from-pink-400 via-purple-400 to-cyan-400 rounded-full blur-lg opacity-40" />
              <img src={logoPath} alt={brandName} className="relative h-16 w-16 object-contain" />
            </div>
            <h1 className={`text-3xl md:text-4xl font-bold ${brandClass}`}>{brandName}</h1>
          </div>
          <p className="text-lg md:text-xl text-purple-700 dark:text-purple-300 mb-8 max-w-md mx-auto md:mx-0">
            Request access to the closed beta. You’ll receive an email once approved.
          </p>
        </div>

        <div className="w-full max-w-md bg-white/80 dark:bg-slate-800/80 backdrop-blur-sm shadow-xl rounded-2xl border border-purple-100 dark:border-purple-800 p-8 md:self-center">
          <div className="text-center mb-6">
            <h2 className="text-xl font-bold text-purple-900 dark:text-purple-100 mb-2">Request Access</h2>
            <p className="text-sm text-purple-600/70 dark:text-purple-300/70">Create an account (admin approval required)</p>
          </div>

          <form className="space-y-5" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-purple-700 dark:text-purple-300 mb-1">Email</label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="block w-full rounded-xl border border-purple-200 dark:border-purple-700 bg-white/50 dark:bg-slate-700/50 px-4 py-3 shadow-sm focus:border-purple-400 focus:outline-none focus:ring-2 focus:ring-purple-400/20 transition-all dark:text-white dark:placeholder-purple-300/50"
                placeholder="you@example.com"
                disabled={submitting || success}
                required
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-purple-700 dark:text-purple-300 mb-1">Password</label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="block w-full rounded-xl border border-purple-200 dark:border-purple-700 bg-white/50 dark:bg-slate-700/50 px-4 py-3 shadow-sm focus:border-purple-400 focus:outline-none focus:ring-2 focus:ring-purple-400/20 transition-all dark:text-white dark:placeholder-purple-300/50"
                placeholder="Create a password"
                disabled={submitting || success}
                required
              />
            </div>

            <div>
              <label htmlFor="confirm" className="block text-sm font-medium text-purple-700 dark:text-purple-300 mb-1">Confirm password</label>
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
              <div className="rounded-xl bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-300 flex items-center gap-2">
                <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || success}
              className="w-full flex justify-center items-center gap-2 rounded-xl bg-gradient-to-r from-pink-500 via-purple-500 to-cyan-500 px-4 py-3 text-white font-semibold shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 hover:scale-[1.02] transition-all disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:scale-100"
            >
              {submitting && <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />}
              {submitting ? 'Submitting…' : 'Request access'}
            </button>
          </form>

          <div className="mt-6 pt-6 border-t border-purple-100 dark:border-purple-800 text-sm text-center">
            <span className="text-purple-600/70 dark:text-purple-300/70">Already have an account?</span>{' '}
            <Link className="text-purple-700 dark:text-purple-200 font-medium hover:underline" to="/login">
              Sign in
            </Link>
          </div>
        </div>
      </div>

      {/* Success splash overlay */}
      {success && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-purple-200 dark:border-purple-700 p-8 max-w-md mx-4 text-center">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-r from-pink-500 via-purple-500 to-cyan-500 flex items-center justify-center">
              <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h3 className="text-xl font-bold text-purple-900 dark:text-purple-100 mb-2">Request Submitted!</h3>
            <p className="text-purple-600 dark:text-purple-300 mb-6">
              Your access request has been received. An administrator will review your request and you'll receive an email once approved.
            </p>
            <p className="text-sm text-purple-500 dark:text-purple-400 mb-4">
              This may take up to 24-48 hours.
            </p>
            <Link
              to="/login"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-pink-500 via-purple-500 to-cyan-500 text-white font-semibold shadow-lg hover:shadow-purple-500/40 hover:scale-[1.02] transition-all"
            >
              Back to Login
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
