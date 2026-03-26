import { useState } from 'react';
import type { FormEvent } from 'react';
import { createPortal } from 'react-dom';
import { toast } from 'react-hot-toast';
import axios from 'axios';
import { authApi } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { useEscapeKey } from '../hooks/useEscapeKey';

interface UserProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function UserProfileModal({ isOpen, onClose }: UserProfileModalProps) {
  const { user, changePassword, logout } = useAuth();
  useEscapeKey(isOpen, onClose);
  
  const [activeTab, setActiveTab] = useState<'password' | 'delete'>('password');
  
  // Password change state
  const [passwordForm, setPasswordForm] = useState({ current: '', next: '', confirm: '' });
  const [passwordSubmitting, setPasswordSubmitting] = useState(false);
  
  // Delete account state
  const [deletePassword, setDeletePassword] = useState('');
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);

  const getErrorMessage = (error: unknown, fallback = 'Request failed.') => {
    if (axios.isAxiosError(error)) {
      return error.response?.data?.error || error.response?.data?.message || error.message || fallback;
    }
    if (error instanceof Error) {
      return error.message;
    }
    return fallback;
  };

  const handlePasswordSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (passwordForm.next !== passwordForm.confirm) {
      toast.error('New passwords do not match.');
      return;
    }
    if (passwordForm.next.length < 8) {
      toast.error('Password must be at least 8 characters.');
      return;
    }

    setPasswordSubmitting(true);
    try {
      await changePassword(passwordForm.current, passwordForm.next);
      toast.success('Password updated successfully.');
      setPasswordForm({ current: '', next: '', confirm: '' });
      onClose();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to update password.'));
    } finally {
      setPasswordSubmitting(false);
    }
  };

  const handleDeleteSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (deleteConfirmText !== 'DELETE') {
      toast.error('Please type DELETE to confirm.');
      return;
    }
    if (!deletePassword) {
      toast.error('Password is required.');
      return;
    }

    setDeleteSubmitting(true);
    try {
      await authApi.deleteOwnAccount(deletePassword);
      toast.success('Account deleted.');
      await logout();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to delete account.'));
    } finally {
      setDeleteSubmitting(false);
    }
  };

  if (!isOpen) return null;

  const modalContent = (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div 
        className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-purple-200 dark:border-purple-700 w-full max-w-md overflow-hidden"
        style={{ backgroundColor: 'white' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-purple-100 dark:border-purple-700 bg-gradient-to-r from-pink-50 via-purple-50 to-cyan-50 dark:from-slate-800 dark:via-purple-900/30 dark:to-slate-800">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-purple-900 dark:text-purple-100">
              Account Settings
            </h2>
            <button
              onClick={onClose}
              className="p-1 rounded-lg hover:bg-purple-100 dark:hover:bg-purple-800 transition-colors"
            >
              <svg className="w-5 h-5 text-purple-600 dark:text-purple-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <p className="text-sm text-purple-600 dark:text-purple-300 mt-1">
            {user?.email || user?.username}
          </p>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-purple-100 dark:border-purple-700">
          <button
            onClick={() => setActiveTab('password')}
            className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
              activeTab === 'password'
                ? 'text-purple-700 dark:text-purple-300 border-b-2 border-purple-500'
                : 'text-gray-500 dark:text-gray-400 hover:text-purple-600 dark:hover:text-purple-300'
            }`}
          >
            Change Password
          </button>
          <button
            onClick={() => setActiveTab('delete')}
            className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
              activeTab === 'delete'
                ? 'text-red-600 dark:text-red-400 border-b-2 border-red-500'
                : 'text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400'
            }`}
          >
            Delete Account
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {activeTab === 'password' && (
            <form onSubmit={handlePasswordSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-purple-200 mb-1">
                  Current Password
                </label>
                <input
                  type="password"
                  value={passwordForm.current}
                  onChange={(e) => setPasswordForm({ ...passwordForm, current: e.target.value })}
                  className="w-full rounded-xl border border-purple-200 dark:border-purple-700 bg-white dark:bg-slate-700 px-4 py-2.5 text-gray-900 dark:text-white focus:border-purple-400 focus:outline-none focus:ring-2 focus:ring-purple-400/20"
                  required
                  disabled={passwordSubmitting}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-purple-200 mb-1">
                  New Password
                </label>
                <input
                  type="password"
                  value={passwordForm.next}
                  onChange={(e) => setPasswordForm({ ...passwordForm, next: e.target.value })}
                  className="w-full rounded-xl border border-purple-200 dark:border-purple-700 bg-white dark:bg-slate-700 px-4 py-2.5 text-gray-900 dark:text-white focus:border-purple-400 focus:outline-none focus:ring-2 focus:ring-purple-400/20"
                  required
                  disabled={passwordSubmitting}
                  minLength={8}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-purple-200 mb-1">
                  Confirm New Password
                </label>
                <input
                  type="password"
                  value={passwordForm.confirm}
                  onChange={(e) => setPasswordForm({ ...passwordForm, confirm: e.target.value })}
                  className="w-full rounded-xl border border-purple-200 dark:border-purple-700 bg-white dark:bg-slate-700 px-4 py-2.5 text-gray-900 dark:text-white focus:border-purple-400 focus:outline-none focus:ring-2 focus:ring-purple-400/20"
                  required
                  disabled={passwordSubmitting}
                />
              </div>
              <button
                type="submit"
                disabled={passwordSubmitting}
                className="w-full py-2.5 rounded-xl bg-gradient-to-r from-pink-500 via-purple-500 to-cyan-500 text-white font-semibold shadow-lg hover:shadow-purple-500/30 hover:scale-[1.02] transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
              >
                {passwordSubmitting ? 'Updating...' : 'Update Password'}
              </button>
            </form>
          )}

          {activeTab === 'delete' && (
            <form onSubmit={handleDeleteSubmit} className="space-y-4">
              <div className="p-4 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-xl">
                <div className="flex items-start gap-3">
                  <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                  <div>
                    <h4 className="text-sm font-semibold text-red-800 dark:text-red-200">
                      This action cannot be undone
                    </h4>
                    <p className="text-xs text-red-700 dark:text-red-300 mt-1">
                      Deleting your account will permanently remove all your data, including subscriptions and download history.
                    </p>
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-purple-200 mb-1">
                  Enter your password
                </label>
                <input
                  type="password"
                  value={deletePassword}
                  onChange={(e) => setDeletePassword(e.target.value)}
                  className="w-full rounded-xl border border-purple-200 dark:border-purple-700 bg-white dark:bg-slate-700 px-4 py-2.5 text-gray-900 dark:text-white focus:border-purple-400 focus:outline-none focus:ring-2 focus:ring-purple-400/20"
                  required
                  disabled={deleteSubmitting}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-purple-200 mb-1">
                  Type <span className="font-mono font-bold text-red-600">DELETE</span> to confirm
                </label>
                <input
                  type="text"
                  value={deleteConfirmText}
                  onChange={(e) => setDeleteConfirmText(e.target.value)}
                  className="w-full rounded-xl border border-purple-200 dark:border-purple-700 bg-white dark:bg-slate-700 px-4 py-2.5 text-gray-900 dark:text-white focus:border-purple-400 focus:outline-none focus:ring-2 focus:ring-purple-400/20"
                  placeholder="DELETE"
                  required
                  disabled={deleteSubmitting}
                />
              </div>

              <button
                type="submit"
                disabled={deleteSubmitting || deleteConfirmText !== 'DELETE'}
                className="w-full py-2.5 rounded-xl bg-red-600 hover:bg-red-700 text-white font-semibold shadow-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {deleteSubmitting ? 'Deleting...' : 'Delete My Account'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
}
