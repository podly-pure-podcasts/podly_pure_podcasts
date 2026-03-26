import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { feedsApi } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { Navigate, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import toast from 'react-hot-toast';
import { useTheme } from '../contexts/ThemeContext';
import { useEscapeKey } from '../hooks/useEscapeKey';

export default function SubscriptionsPage() {
  const { user, requireAuth } = useAuth();
  const { theme } = useTheme();
  const isOriginal = theme === 'original';
  const originalModalStyles = {
    panel: { backgroundColor: 'var(--original-modal-base)', borderColor: 'var(--original-modal-border)' },
    header: { borderColor: 'rgba(96, 165, 250, 0.38)', background: 'linear-gradient(to right, #14467e, #1d5995, #14467e)' },
    section: { backgroundColor: 'var(--original-modal-surface-alt)', border: '1px solid rgba(96, 165, 250, 0.28)' },
    divider: { borderColor: 'rgba(96, 165, 250, 0.28)' },
    footer: { borderColor: 'rgba(96, 165, 250, 0.28)', backgroundColor: 'var(--original-modal-footer)' },
    closeButton: { color: '#dbeafe', borderColor: 'rgba(96, 165, 250, 0.45)', backgroundColor: 'var(--original-modal-base)' },
    confirmHeader: { borderColor: 'rgba(96, 165, 250, 0.35)', backgroundColor: 'var(--original-modal-danger)' },
    confirmFooter: { borderColor: 'rgba(96, 165, 250, 0.35)', backgroundColor: 'var(--original-modal-footer)' },
  };
  const [expandedSubscribers, setExpandedSubscribers] = useState<Record<number, boolean>>({});
  const [settingsModalFeedId, setSettingsModalFeedId] = useState<number | null>(null);
  const [confirmAction, setConfirmAction] = useState<{ type: 'unsubscribe-all' | 'delete'; feedId: number; feedTitle: string } | null>(null);
  useEscapeKey(!!confirmAction, () => setConfirmAction(null));
  useEscapeKey(!!settingsModalFeedId, () => setSettingsModalFeedId(null));
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-feed-subscriptions'],
    queryFn: feedsApi.getAdminFeedSubscriptions,
    enabled: user?.role === 'admin',
  });

  // useMemo must be called before any early returns (React rules of hooks)
  const feeds = data?.feeds ?? [];
  const selectedFeed = feeds.find(f => f.id === settingsModalFeedId);

  const visibilityMutation = useMutation({
    mutationFn: ({ feedId, isHidden }: { feedId: number; isHidden: boolean }) =>
      feedsApi.setFeedVisibility(feedId, isHidden),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['admin-feed-subscriptions'] });
      toast.success(data.is_hidden ? 'Feed hidden from browse' : 'Feed visible in browse');
    },
    onError: () => {
      toast.error('Failed to update feed visibility');
    },
  });

  const disableAutoProcessMutation = useMutation({
    mutationFn: (feedId: number) => feedsApi.disableAutoProcessAll(feedId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['admin-feed-subscriptions'] });
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
      toast.success(`Auto-process disabled for ${data.subscriptions_updated} subscription(s)`);
      setSettingsModalFeedId(null);
    },
    onError: () => {
      toast.error('Failed to disable auto-process');
    },
  });

  const unsubscribeAllMutation = useMutation({
    mutationFn: (feedId: number) => feedsApi.adminUnsubscribeAll(feedId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['admin-feed-subscriptions'] });
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
      toast.success(data.message);
      setConfirmAction(null);
      setSettingsModalFeedId(null);
    },
    onError: () => {
      toast.error('Failed to unsubscribe users');
    },
  });

  const deleteFeedMutation = useMutation({
    mutationFn: (feedId: number) => feedsApi.adminDeleteFeed(feedId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['admin-feed-subscriptions'] });
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
      toast.success(data.message);
      setConfirmAction(null);
      setSettingsModalFeedId(null);
    },
    onError: () => {
      toast.error('Failed to delete feed');
    },
  });

  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    const remainingMins = minutes % 60;
    return `${hours}h ${remainingMins}m`;
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  // Redirect non-admins
  if (requireAuth && user && user.role !== 'admin') {
    return <Navigate to="/podcasts" replace />;
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className={`animate-spin rounded-full h-8 w-8 border-b-2 ${isOriginal ? 'border-blue-400' : 'border-purple-600'}`} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
          Failed to load subscription data
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className={`text-2xl font-bold ${isOriginal ? 'text-blue-100' : 'text-gray-900 dark:text-purple-100'}`}>Feed Subscriptions</h1>
          <p className={`text-sm mt-1 ${isOriginal ? 'text-blue-200' : 'text-gray-500'}`}>
            Overview of all podcast feeds and their subscribers
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:gap-4 text-sm">
          <div className={`px-2.5 py-1 rounded-lg font-medium ${isOriginal ? 'bg-blue-900/65 text-blue-100 border border-blue-300/45' : 'bg-purple-100 text-purple-700'}`}>
            {data?.total_feeds || 0} feeds
          </div>
          <div className={`px-2.5 py-1 rounded-lg font-medium ${isOriginal ? 'bg-cyan-900/35 text-cyan-100 border border-cyan-300/40' : 'bg-cyan-100 text-cyan-700'}`}>
            {data?.total_subscriptions || 0} subscriptions
          </div>
          <div className={`px-2.5 py-1 rounded-lg font-medium ${isOriginal ? 'bg-emerald-900/30 text-emerald-100 border border-emerald-300/35' : 'bg-emerald-100 text-emerald-700'}`}>
            {data?.total_processed_episodes || 0} processed
          </div>
          <div className={`px-2.5 py-1 rounded-lg font-medium ${isOriginal ? 'bg-amber-900/30 text-amber-100 border border-amber-300/45' : 'bg-amber-100 text-amber-700'}`}>
            {formatBytes(data?.total_storage_bytes || 0)} stored
          </div>
        </div>
      </div>

      {/* Feeds List */}
      <div className={`rounded-xl border overflow-hidden ${
        isOriginal
          ? 'bg-blue-900/40 border-blue-300/30'
          : 'bg-white/80 backdrop-blur-sm border-purple-200/50'
      }`}>
        {feeds.length === 0 ? (
          <div className="text-center py-12 px-4">
            <p className={isOriginal ? 'text-blue-200' : 'text-gray-500'}>No feeds have been added yet</p>
          </div>
        ) : (
          feeds.map((feed, idx) => (
            <div
              key={feed.id}
              className={`px-4 sm:px-5 py-3 sm:py-4 ${
                idx > 0
                  ? isOriginal
                    ? 'border-t border-blue-300/15'
                    : 'border-t border-purple-100/40 dark:border-purple-800/20'
                  : ''
              }`}
            >
              <div className="flex items-start gap-3">
                {/* Feed Image */}
                {feed.image_url ? (
                  <img
                    src={feed.image_url}
                    alt={feed.title}
                    className="w-10 h-10 sm:w-12 sm:h-12 rounded-lg object-cover flex-shrink-0"
                  />
                ) : (
                  <div className={`w-10 h-10 sm:w-12 sm:h-12 rounded-lg flex items-center justify-center flex-shrink-0 ${isOriginal ? 'bg-blue-800/40' : 'bg-purple-100'}`}>
                    <svg className="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                    </svg>
                  </div>
                )}

                {/* Feed Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <button
                      onClick={() => navigate(`/podcasts?feed=${feed.id}`)}
                      className={`font-semibold text-sm leading-snug truncate transition-colors text-left ${
                        isOriginal
                          ? 'text-blue-100 hover:text-white'
                          : 'text-gray-900 dark:text-purple-100 hover:text-purple-600 dark:hover:text-purple-300'
                      }`}
                    >
                      {feed.title}
                    </button>
                    {feed.auto_process_enabled && (
                      <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400" title="Auto-process enabled">
                        Auto
                      </span>
                    )}
                    {feed.is_hidden ? (
                      <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-300" title="Admin hidden from browse page">
                        Hidden
                      </span>
                    ) : !feed.has_public_subscriber ? (
                      <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400" title="All subscribers are private">
                        Private
                      </span>
                    ) : (
                      <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400" title="Visible in Browse Podcasts">
                        Public
                      </span>
                    )}
                  </div>
                  {/* Author + Stats on same line */}
                  <div className={`flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-0.5 text-xs ${isOriginal ? 'text-blue-300/70' : 'text-gray-500 dark:text-purple-400'}`}>
                    {feed.author && <span>{feed.author}</span>}
                    {feed.author && <span>·</span>}
                    <span>{feed.posts_count} eps</span>
                    <span>·</span>
                    <span className="text-green-600 dark:text-green-400">{feed.stats.processed_count} processed</span>
                    {feed.stats.total_ad_time_removed > 0 && (
                      <>
                        <span>·</span>
                        <span className="text-pink-600 dark:text-pink-400">{formatDuration(feed.stats.total_ad_time_removed)} removed</span>
                      </>
                    )}
                  </div>
                </div>

                {/* Settings Button + Subscriber Count */}
                <div className="flex-shrink-0 flex items-center gap-1.5">
                  <button
                    onClick={() => setSettingsModalFeedId(feed.id)}
                    className={`p-1.5 rounded-lg transition-colors ${isOriginal ? 'text-blue-200 hover:bg-blue-800/40' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'}`}
                    title="Feed settings"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                  </button>
                  <div className={`text-center min-w-[2.5rem] ${
                    feed.subscriber_count > 0 
                      ? (isOriginal ? 'text-blue-100' : 'text-purple-700')
                      : (isOriginal ? 'text-blue-300/50' : 'text-gray-400')
                  }`}>
                    <div className="text-base font-bold leading-tight">{feed.subscriber_count}</div>
                    <div className="text-[10px]">subs</div>
                  </div>
                </div>
              </div>

              {/* Subscribers List - inline */}
              {feed.subscribers.length > 0 && (
                <div className={`mt-2.5 pt-2.5 border-t flex items-center gap-1.5 flex-wrap ${isOriginal ? 'border-blue-300/10' : 'border-purple-100/30 dark:border-purple-800/15'}`}>
                  {(expandedSubscribers[feed.id] ? feed.subscribers : feed.subscribers.slice(0, 6)).map((sub) => (
                    <div
                      key={sub.user_id}
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs ${
                        sub.is_private 
                          ? isOriginal ? 'text-blue-300/60' : 'text-gray-500'
                          : isOriginal
                            ? 'text-blue-100'
                            : 'text-purple-700'
                      }`}
                      title={sub.is_private ? 'Private subscription' : ''}
                    >
                      <div className={`w-4 h-4 rounded-full flex items-center justify-center text-white text-[10px] font-bold ${
                        sub.is_private 
                          ? 'bg-gray-400' 
                          : 'bg-gradient-to-br from-pink-400 via-purple-400 to-cyan-400'
                      }`}>
                        {sub.username.charAt(0).toUpperCase()}
                      </div>
                      <span className="font-medium">{sub.username}</span>
                      {sub.is_private && (
                        <svg className="w-3 h-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                        </svg>
                      )}
                    </div>
                  ))}
                  {feed.subscribers.length > 6 && !expandedSubscribers[feed.id] && (
                    <button
                      type="button"
                      onClick={() => setExpandedSubscribers((prev) => ({ ...prev, [feed.id]: true }))}
                      className={`text-xs font-medium ${isOriginal ? 'text-blue-200 hover:text-blue-50' : 'text-purple-600 hover:text-purple-800'}`}
                    >
                      +{feed.subscribers.length - 6} more
                    </button>
                  )}
                  {expandedSubscribers[feed.id] && feed.subscribers.length > 6 && (
                    <button
                      type="button"
                      onClick={() => setExpandedSubscribers((prev) => ({ ...prev, [feed.id]: false }))}
                      className={`text-xs font-medium ${isOriginal ? 'text-blue-200 hover:text-blue-50' : 'text-purple-600 hover:text-purple-800'}`}
                    >
                      less
                    </button>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Settings Modal */}
      {settingsModalFeedId && selectedFeed && (
        <div 
          className="fixed inset-0 flex items-center justify-center z-50 p-4"
          style={{ backgroundColor: isOriginal ? 'rgba(2, 8, 23, 0.8)' : 'rgba(0, 0, 0, 0.5)' }}
          onClick={() => setSettingsModalFeedId(null)}
        >
          <div 
            className="modal-content bg-white rounded-xl shadow-xl max-w-md w-full overflow-hidden border"
            style={isOriginal ? originalModalStyles.panel : undefined}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="p-4 border-b border-gray-100 bg-gradient-to-r from-pink-50 via-purple-50 to-cyan-50"
              style={isOriginal ? originalModalStyles.header : undefined}
            >
              <div className="flex items-center justify-between">
                <h3 className={`font-semibold ${isOriginal ? 'text-blue-100' : 'text-gray-900'}`}>Feed Settings</h3>
                <button
                  onClick={() => setSettingsModalFeedId(null)}
                  className="p-1 rounded"
                  style={isOriginal ? { color: '#93c5fd' } : undefined}
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <p className={`text-sm mt-1 truncate ${isOriginal ? 'text-blue-200' : 'text-gray-500'}`}>{selectedFeed.title}</p>
            </div>

            <div className="p-4 space-y-4">
              {/* Visibility Toggle */}
              <div
                className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                style={isOriginal ? originalModalStyles.section : undefined}
              >
                <div>
                  <div className={`font-medium text-sm ${isOriginal ? 'text-blue-100' : 'text-gray-900'}`}>Hide from Browse</div>
                  <div className={`text-xs mt-0.5 ${isOriginal ? 'text-blue-200' : 'text-gray-500'}`}>
                    Hidden feeds won't appear in "Browse Podcasts on Server"
                  </div>
                </div>
                <button
                  onClick={() => visibilityMutation.mutate({ 
                    feedId: selectedFeed.id, 
                    isHidden: !selectedFeed.is_hidden 
                  })}
                  disabled={visibilityMutation.isPending}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    selectedFeed.is_hidden
                      ? (isOriginal ? 'bg-blue-500' : 'bg-purple-600')
                      : (isOriginal ? 'bg-blue-900/60' : 'bg-gray-300')
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      selectedFeed.is_hidden ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>

              {/* Auto-Process Toggle */}
              <div
                className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                style={isOriginal ? originalModalStyles.section : undefined}
              >
                <div>
                  <div className={`font-medium text-sm ${isOriginal ? 'text-blue-100' : 'text-gray-900'}`}>Auto-Process</div>
                  <div className={`text-xs mt-0.5 ${isOriginal ? 'text-blue-200' : 'text-gray-500'}`}>
                    {selectedFeed.auto_process_enabled 
                      ? 'Enabled by a user - new episodes auto-process'
                      : 'Disabled - no auto-processing'}
                  </div>
                </div>
                <button
                  onClick={() => {
                    if (selectedFeed.auto_process_enabled) {
                      disableAutoProcessMutation.mutate(selectedFeed.id);
                    }
                  }}
                  disabled={disableAutoProcessMutation.isPending || !selectedFeed.auto_process_enabled}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    selectedFeed.auto_process_enabled
                      ? 'bg-emerald-500'
                      : (isOriginal ? 'bg-blue-900/60' : 'bg-gray-300')
                  } ${!selectedFeed.auto_process_enabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                  title={selectedFeed.auto_process_enabled ? 'Click to disable for all users' : 'No users have enabled auto-process'}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      selectedFeed.auto_process_enabled ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
            </div>

            {/* Danger Zone */}
            <div className="p-4 border-t border-gray-100" style={isOriginal ? originalModalStyles.divider : undefined}>
              <div className="text-xs font-medium text-red-600 mb-3">Danger Zone</div>
              <div className="space-y-2">
                <button
                  onClick={() => setConfirmAction({ type: 'unsubscribe-all', feedId: selectedFeed.id, feedTitle: selectedFeed.title })}
                  disabled={unsubscribeAllMutation.isPending || selectedFeed.subscriber_count === 0}
                  className={`w-full px-4 py-2 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                    isOriginal
                      ? 'text-amber-100 bg-amber-900/35 border border-amber-300/45 hover:bg-amber-900/45'
                      : 'text-amber-700 bg-amber-50 border border-amber-200 hover:bg-amber-100'
                  }`}
                >
                  Unsubscribe All Users ({selectedFeed.subscriber_count})
                </button>
                <button
                  onClick={() => setConfirmAction({ type: 'delete', feedId: selectedFeed.id, feedTitle: selectedFeed.title })}
                  disabled={deleteFeedMutation.isPending}
                  className={`w-full px-4 py-2 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 ${
                    isOriginal
                      ? 'text-red-100 bg-red-900/35 border border-red-300/45 hover:bg-red-900/45'
                      : 'text-red-700 bg-red-50 border border-red-200 hover:bg-red-100'
                  }`}
                >
                  Delete Feed & All Episodes
                </button>
              </div>
            </div>

            <div className="p-4 border-t border-gray-100 bg-gray-50" style={isOriginal ? originalModalStyles.footer : undefined}>
              <button
                onClick={() => setSettingsModalFeedId(null)}
                className="w-full px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                style={isOriginal ? originalModalStyles.closeButton : undefined}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirmation Modal */}
      {confirmAction && (
        <div 
          className="fixed inset-0 flex items-center justify-center z-[60] p-4"
          style={{ backgroundColor: isOriginal ? 'rgba(2, 8, 23, 0.8)' : 'rgba(0, 0, 0, 0.5)' }}
          onClick={() => setConfirmAction(null)}
        >
          <div 
            className="modal-content bg-white rounded-xl shadow-xl max-w-sm w-full overflow-hidden border"
            style={isOriginal ? originalModalStyles.panel : undefined}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="p-4 border-b border-gray-100 bg-red-50"
              style={isOriginal ? originalModalStyles.confirmHeader : undefined}
            >
              <h3 className={`font-semibold ${isOriginal ? 'text-red-100' : 'text-red-900'}`}>
                {confirmAction.type === 'delete' ? 'Delete Feed?' : 'Unsubscribe All Users?'}
              </h3>
            </div>
            <div className="p-4">
              <p className={`text-sm ${isOriginal ? 'text-blue-100' : 'text-gray-600'}`}>
                {confirmAction.type === 'delete' 
                  ? `This will permanently delete "${confirmAction.feedTitle}" and all its episodes, transcripts, and processing data. This cannot be undone.`
                  : `This will unsubscribe all users from "${confirmAction.feedTitle}". The feed and episodes will remain on the server.`
                }
              </p>
            </div>
            <div
              className="p-4 border-t border-gray-100 bg-gray-50 flex gap-2"
              style={isOriginal ? originalModalStyles.confirmFooter : undefined}
            >
              <button
                onClick={() => setConfirmAction(null)}
                className={`flex-1 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                  isOriginal
                    ? 'text-blue-100 bg-blue-900/45 border border-blue-300/45 hover:bg-blue-800/55'
                    : 'text-gray-700 bg-white border border-gray-200 hover:bg-gray-50'
                }`}
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (confirmAction.type === 'delete') {
                    deleteFeedMutation.mutate(confirmAction.feedId);
                  } else {
                    unsubscribeAllMutation.mutate(confirmAction.feedId);
                  }
                }}
                disabled={deleteFeedMutation.isPending || unsubscribeAllMutation.isPending}
                className={`flex-1 px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors disabled:opacity-50 ${
                  confirmAction.type === 'delete' 
                    ? 'bg-red-600 hover:bg-red-700' 
                    : 'bg-amber-600 hover:bg-amber-700'
                }`}
              >
                {(deleteFeedMutation.isPending || unsubscribeAllMutation.isPending) 
                  ? 'Processing...' 
                  : confirmAction.type === 'delete' ? 'Delete' : 'Unsubscribe All'
                }
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
