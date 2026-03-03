import { useQuery } from '@tanstack/react-query';
import { createPortal } from 'react-dom';
import { authApi } from '../services/api';
import type { UserStats } from '../services/api';
import { useState } from 'react';
import { useEscapeKey } from '../hooks/useEscapeKey';
import { useTheme } from '../contexts/ThemeContext';

interface AdminUserStatsProps {
  onRoleChange?: (username: string, newRole: string) => Promise<void>;
  onDeleteUser?: (username: string) => Promise<void>;
  onResetPassword?: (username: string, password: string) => Promise<void>;
  adminCount?: number;
  currentUsername?: string;
}

export default function AdminUserStats({ onRoleChange, onDeleteUser, onResetPassword, adminCount = 1, currentUsername }: AdminUserStatsProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-user-stats'],
    queryFn: authApi.getUserStats,
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  if (isLoading) {
    return (
      <div className="bg-white/80 backdrop-blur-sm rounded-xl border border-purple-200/50 p-6 shadow-sm">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-purple-100 rounded w-1/3"></div>
          <div className="h-20 bg-purple-50 rounded"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white/80 backdrop-blur-sm rounded-xl border border-red-200/50 p-6 shadow-sm">
        <p className="text-red-600">Failed to load user statistics</p>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-purple-900">User Statistics 👥</h2>
        <div className="text-sm text-purple-500">
          {data.global_stats.total_feeds} feeds • {data.global_stats.total_processed}/{data.global_stats.total_episodes} processed
        </div>
      </div>

      {/* User List */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {data.users.map((user) => (
          <UserStatCard 
            key={user.id} 
            user={user}
            onRoleChange={onRoleChange}
            onDeleteUser={onDeleteUser}
            onResetPassword={onResetPassword}
            adminCount={adminCount}
            isCurrentUser={user.username === currentUsername}
          />
        ))}
      </div>
    </div>
  );
}

interface UserStatCardProps {
  user: UserStats;
  onRoleChange?: (username: string, newRole: string) => Promise<void>;
  onDeleteUser?: (username: string) => Promise<void>;
  onResetPassword?: (username: string, password: string) => Promise<void>;
  adminCount: number;
  isCurrentUser?: boolean;
}

interface DownloadAttemptsModalProps {
  userId: number;
  username: string;
  onClose: () => void;
}

function DownloadAttemptsModal({ userId, username, onClose }: DownloadAttemptsModalProps) {
  useEscapeKey(true, onClose);

  const { data, isLoading, error } = useQuery({
    queryKey: ['download-attempts', userId],
    queryFn: () => authApi.getDownloadAttempts({ user_id: userId, limit: 500 }),
  });

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Unknown';
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  const getAuthTypeBadge = (authType: string | null) => {
    switch (authType) {
      case 'combined':
        return <span className="px-2 py-0.5 rounded-full text-xs bg-pink-100 dark:bg-pink-900/50 text-pink-700 dark:text-pink-300">Combined</span>;
      case 'feed_scoped':
        return <span className="px-2 py-0.5 rounded-full text-xs bg-cyan-100 dark:bg-cyan-900/50 text-cyan-700 dark:text-cyan-300">Feed-Scoped</span>;
      case 'session':
        return <span className="px-2 py-0.5 rounded-full text-xs bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300">Session</span>;
      default:
        return <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">{authType || 'Unknown'}</span>;
    }
  };

  const getEventTypeBadge = (eventType: string | null, decision: string | null) => {
    // Use event_type if available, otherwise fall back to decision for legacy records
    const type = eventType || (decision === 'SERVED_AUDIO' ? 'AUDIO_DOWNLOAD' : decision === 'TRIGGERED' ? 'PROCESS_STARTED' : null);
    switch (type) {
      case 'RSS_READ':
        return <span className="px-2 py-0.5 rounded-full text-xs bg-orange-100 dark:bg-orange-900/50 text-orange-700 dark:text-orange-300">RSS Read</span>;
      case 'AUDIO_DOWNLOAD':
        return <span className="px-2 py-0.5 rounded-full text-xs bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300">Audio Download</span>;
      case 'TRIGGER_OPEN':
        return <span className="px-2 py-0.5 rounded-full text-xs bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300">Trigger Open</span>;
      case 'PROCESS_STARTED':
        return <span className="px-2 py-0.5 rounded-full text-xs bg-purple-100 dark:bg-purple-900/50 text-purple-700 dark:text-purple-300">Process Started</span>;
      case 'PROCESS_COMPLETE':
        return <span className="px-2 py-0.5 rounded-full text-xs bg-emerald-100 dark:bg-emerald-900/50 text-emerald-700 dark:text-emerald-300">Complete</span>;
      case 'FAILED':
        return <span className="px-2 py-0.5 rounded-full text-xs bg-red-100 dark:bg-red-900/50 text-red-700 dark:text-red-300">Failed</span>;
      default:
        return <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">{type || 'Legacy'}</span>;
    }
  };

  const downloadCSV = () => {
    if (!data?.attempts) return;
    
    const headers = ['Date', 'Episode', 'Feed', 'Auth Type', 'Decision', 'Source', 'Processed'];
    const rows = data.attempts.map(a => [
      a.downloaded_at || '',
      a.post_title,
      a.feed_title,
      a.auth_type || '',
      a.decision || '',
      a.download_source,
      a.is_processed ? 'Yes' : 'No',
    ]);
    
    const csvContent = [headers, ...rows]
      .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      .join('\n');
    
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `download-attempts-${username}-${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/80"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div 
        className="relative bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-3 sm:p-4 border-b border-purple-100 dark:border-purple-800 bg-purple-50 dark:bg-gray-800">
          <div className="min-w-0 flex-1">
            <h2 className="text-base sm:text-lg font-bold text-purple-900 dark:text-purple-100">Download Attempts</h2>
            <p className="text-xs sm:text-sm text-purple-600 dark:text-purple-400">User: {username} ({data?.total_count ?? 0} records)</p>
          </div>
          <div className="flex items-center gap-1 sm:gap-2 ml-2">
            <button
              type="button"
              className="px-2 sm:px-3 py-1 sm:py-1.5 text-xs sm:text-sm bg-purple-600 text-white rounded hover:bg-purple-700"
              onClick={downloadCSV}
              disabled={!data?.attempts?.length}
            >
              <span className="hidden sm:inline">Download </span>CSV
            </button>
            <button
              type="button"
              className="p-1.5 sm:p-2 rounded-lg hover:bg-purple-100 dark:hover:bg-purple-800 text-gray-500 dark:text-gray-400 transition-colors"
              onClick={onClose}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-2 sm:p-4 bg-white dark:bg-gray-900">
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div>
            </div>
          )}

          {error && (
            <div className="text-red-600 dark:text-red-400 text-center py-8">Failed to load download attempts</div>
          )}

          {data && data.attempts.length === 0 && (
            <div className="text-gray-500 dark:text-gray-400 text-center py-8">No download attempts found</div>
          )}

          {data && data.attempts.length > 0 && (
            <div>
              {data.attempts.map((attempt, idx) => (
                <div key={attempt.id} className={`px-3 sm:px-4 py-2.5 ${idx > 0 ? 'border-t border-purple-100/40 dark:border-purple-800/20' : ''}`}>
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <div className="text-purple-900 dark:text-purple-100 text-sm font-medium line-clamp-2">{attempt.post_title}</div>
                    {getEventTypeBadge(attempt.event_type, attempt.decision)}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="text-purple-600 dark:text-purple-300">{attempt.feed_title}</span>
                    {getAuthTypeBadge(attempt.auth_type)}
                    <span className="text-gray-500 dark:text-gray-400">{attempt.download_source}</span>
                    <span className="text-gray-400 dark:text-gray-500 ml-auto">{formatDate(attempt.downloaded_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}

function UserStatCard({ user, onRoleChange, onDeleteUser, onResetPassword, adminCount, isCurrentUser }: UserStatCardProps) {
  const { theme } = useTheme();
  const isOriginal = theme === 'original';
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showDownloadAttempts, setShowDownloadAttempts] = useState(false);
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  return (
    <div
      className={`rounded-xl border p-5 shadow-sm unicorn-card ${
        isOriginal
          ? 'bg-blue-900/45 border-blue-300/35'
          : 'bg-white/80 backdrop-blur-sm border-purple-200/50'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-pink-400 via-purple-400 to-cyan-400 flex items-center justify-center text-white font-bold text-lg">
            {user.username.charAt(0).toUpperCase()}
          </div>
          <div>
            <h3 className={`font-semibold ${isOriginal ? 'text-blue-100' : 'text-purple-900'}`}>{user.username}</h3>
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              user.role === 'admin'
                ? isOriginal
                  ? 'bg-blue-800/70 text-blue-100 border border-blue-300/40'
                  : 'bg-purple-100 text-purple-700'
                : isOriginal
                  ? 'bg-blue-900/65 text-blue-200 border border-blue-300/35'
                  : 'bg-gray-100 text-gray-600'
            }`}>
              {user.role}
            </span>
          </div>
        </div>
        <div className={`text-right text-xs ${isOriginal ? 'text-blue-200' : 'text-purple-400'}`}>
          Last active: {formatDate(user.last_activity)}
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-4 gap-2 mb-4">
        <div
          className="rounded-lg p-2 text-center"
          style={isOriginal ? { background: 'linear-gradient(135deg, rgba(25, 72, 128, 0.95), rgba(20, 58, 104, 0.95))', border: '1px solid rgba(96, 165, 250, 0.38)' } : undefined}
        >
          <div className={`text-xl font-bold ${isOriginal ? 'text-blue-100' : 'text-pink-600'}`}>{user.episodes_processed}</div>
          <div className={`text-xs ${isOriginal ? 'text-blue-200' : 'text-pink-500'}`}>Processed</div>
        </div>
        <div
          className="rounded-lg p-2 text-center"
          style={isOriginal ? { background: 'linear-gradient(135deg, rgba(23, 67, 119, 0.95), rgba(17, 52, 96, 0.95))', border: '1px solid rgba(96, 165, 250, 0.38)' } : undefined}
        >
          <div className={`text-xl font-bold ${isOriginal ? 'text-blue-100' : 'text-purple-600'}`}>{user.processed_downloads}</div>
          <div className={`text-xs ${isOriginal ? 'text-blue-200' : 'text-purple-500'}`}>Downloads</div>
          <div className={`text-[10px] ${isOriginal ? 'text-blue-300/90' : 'text-purple-400'}`}>RSS: {user.rss_processed_downloads ?? 0}</div>
        </div>
        <div
          className="rounded-lg p-2 text-center"
          style={isOriginal ? { background: 'linear-gradient(135deg, rgba(10, 110, 138, 0.94), rgba(14, 132, 167, 0.9))', border: '1px solid rgba(125, 211, 252, 0.45)' } : undefined}
        >
          <div className={`text-sm font-bold ${isOriginal ? 'text-cyan-50' : 'text-cyan-600'}`}>{user.ad_time_removed_formatted || '0s'}</div>
          <div className={`text-xs ${isOriginal ? 'text-cyan-100' : 'text-cyan-500'}`}>Ads Removed</div>
        </div>
        <div
          className="rounded-lg p-2 text-center"
          style={isOriginal ? { background: 'linear-gradient(135deg, rgba(55, 65, 132, 0.94), rgba(67, 56, 169, 0.9))', border: '1px solid rgba(165, 180, 252, 0.45)' } : undefined}
        >
          <div className={`text-xl font-bold ${isOriginal ? 'text-indigo-50' : 'text-indigo-600'}`}>{user.subscriptions_count ?? 0}</div>
          <div className={`text-xs ${isOriginal ? 'text-indigo-100' : 'text-indigo-500'}`}>Subscribed</div>
        </div>
      </div>

      {/* Recent Downloads */}
      {user.recent_downloads.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className={`text-xs font-medium ${isOriginal ? 'text-blue-200' : 'text-purple-500 dark:text-purple-300'}`}>Recent Downloads</div>
            <button
              type="button"
              className={`text-xs underline font-medium ${isOriginal ? 'text-blue-100 hover:text-white' : 'text-cyan-500 hover:text-cyan-400'}`}
              onClick={() => setShowDownloadAttempts(true)}
            >
              View all attempts
            </button>
          </div>
          <div className="space-y-1 max-h-24 overflow-y-auto">
            {user.recent_downloads.slice(0, 3).map((download, idx) => (
              <div key={idx} className={`flex items-center justify-between text-xs rounded px-2 py-1 ${isOriginal ? 'bg-blue-900/45' : 'bg-purple-50/50'}`}>
                <span className={`truncate flex-1 ${isOriginal ? 'text-blue-100' : 'text-purple-700'}`}>{download.post_title}</span>
                <span className={`${isOriginal ? 'text-blue-300/90' : 'text-purple-400'} ml-2 whitespace-nowrap`}>
                  {formatDate(download.downloaded_at)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {user.recent_downloads.length === 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className={`text-xs ${isOriginal ? 'text-blue-200' : 'text-purple-300'}`}>No downloads yet</div>
            <button
              type="button"
              className={`text-xs underline font-medium ${isOriginal ? 'text-blue-100 hover:text-white' : 'text-cyan-500 hover:text-cyan-400'}`}
              onClick={() => setShowDownloadAttempts(true)}
            >
              View all attempts
            </button>
          </div>
        </div>
      )}

      {/* Download Attempts Modal */}
      {showDownloadAttempts && (
        <DownloadAttemptsModal
          userId={user.id}
          username={user.username}
          onClose={() => setShowDownloadAttempts(false)}
        />
      )}

      {/* User Controls */}
      {(onRoleChange || onDeleteUser || onResetPassword) && (
        <div className={`border-t pt-3 mt-3 ${isOriginal ? 'border-blue-300/35' : 'border-purple-200/50'}`}>
          <div className="flex flex-wrap items-center gap-2">
            {onRoleChange && (
              <select
                className={`text-xs px-2 py-1 rounded border ${
                  isOriginal
                    ? 'border-blue-300/45 bg-blue-900/65 text-blue-100'
                    : 'border-purple-200 bg-white dark:bg-slate-800 dark:border-purple-600 dark:text-purple-200'
                }`}
                value={user.role}
                onChange={(e) => {
                  if (e.target.value !== user.role) {
                    void onRoleChange(user.username, e.target.value);
                  }
                }}
                disabled={(user.role === 'admin' && adminCount <= 1) || isCurrentUser}
                title={isCurrentUser ? "You cannot change your own role" : undefined}
              >
                <option value="user">user</option>
                <option value="admin">admin</option>
              </select>
            )}
            {onResetPassword && (
              <button
                type="button"
                className={`text-xs px-2 py-1 border rounded ${
                  isOriginal
                    ? 'border-blue-300/45 text-blue-100 hover:bg-blue-900/55'
                    : 'border-purple-200 dark:border-purple-600 hover:bg-purple-50 dark:hover:bg-purple-800 dark:text-purple-200'
                }`}
                onClick={() => setShowPasswordForm(!showPasswordForm)}
              >
                {showPasswordForm ? 'Cancel' : 'Set password'}
              </button>
            )}
            {onDeleteUser && (
              <button
                type="button"
                className={`text-xs px-2 py-1 border rounded disabled:opacity-50 ${
                  isOriginal
                    ? 'border-red-300/50 text-red-200 hover:bg-red-900/28'
                    : 'border-red-200 text-red-600 hover:bg-red-50'
                }`}
                onClick={() => void onDeleteUser(user.username)}
                disabled={user.role === 'admin' && adminCount <= 1}
              >
                Delete
              </button>
            )}
          </div>

          {showPasswordForm && onResetPassword && (
            <form 
              className="mt-2 flex flex-wrap gap-2 items-end"
              onSubmit={(e) => {
                e.preventDefault();
                if (newPassword && newPassword === confirmPassword) {
                  void onResetPassword(user.username, newPassword);
                  setNewPassword('');
                  setConfirmPassword('');
                  setShowPasswordForm(false);
                }
              }}
            >
              <input
                type="password"
                placeholder="New password"
                className={`text-xs px-2 py-1 rounded border w-24 ${
                  isOriginal
                    ? 'border-blue-300/45 bg-blue-900/65 text-blue-100'
                    : 'border-purple-200 dark:bg-slate-800 dark:border-purple-600'
                }`}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
              <input
                type="password"
                placeholder="Confirm"
                className={`text-xs px-2 py-1 rounded border w-24 ${
                  isOriginal
                    ? 'border-blue-300/45 bg-blue-900/65 text-blue-100'
                    : 'border-purple-200 dark:bg-slate-800 dark:border-purple-600'
                }`}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
              <button
                type="submit"
                className={`text-xs px-2 py-1 rounded text-white ${
                  isOriginal
                    ? 'bg-blue-500 hover:bg-blue-400 border border-blue-300/55'
                    : 'bg-purple-600 hover:bg-purple-700'
                }`}
              >
                Update
              </button>
            </form>
          )}
        </div>
      )}
    </div>
  );
}
