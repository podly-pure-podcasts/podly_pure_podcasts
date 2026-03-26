import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { feedsApi } from '../services/api';
import { toast } from 'react-hot-toast';
import type { Episode } from '../types';
import DownloadButton from '../components/DownloadButton';
import PlayButton from '../components/PlayButton';
import ProcessingStatsButton from '../components/ProcessingStatsButton';
import ReprocessButton from '../components/ReprocessButton';
import ProcessButton from '../components/ProcessButton';
import EpisodeProcessingStatus from '../components/EpisodeProcessingStatus';
import EpisodeDetailModal from '../components/episodes/EpisodeDetailModal';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { usePodcastsContext } from '../layouts/PodcastsLayout';
import { copyTextToClipboard } from '../services/clipboard';
import { isDarkSurfaceTheme } from '../theme';

export default function FeedDetailView() {
  const navigate = useNavigate();
  const { feeds, selectedFeedId, queryClient } = usePodcastsContext();
  const [showSettingsMenu, setShowSettingsMenu] = useState(false);
  const [processingPollTriggers, setProcessingPollTriggers] = useState<Record<string, number>>({});
  const [selectedEpisode, setSelectedEpisode] = useState<Episode | null>(null);
  const { requireAuth, isAuthenticated } = useAuth();
  const { theme } = useTheme();
  const isOriginal = theme === 'original';
  const isDark = isDarkSurfaceTheme(theme);

  const selectedFeed = feeds.find((f) => f.id === selectedFeedId);

  const { data: episodes, isLoading: episodesLoading } = useQuery({
    queryKey: ['episodes', selectedFeedId],
    queryFn: () => feedsApi.getFeedPosts(selectedFeedId!),
    enabled: !!selectedFeedId,
  });

  const unsubscribeMutation = useMutation({
    mutationFn: (feedId: number) => feedsApi.unsubscribeFeed(feedId),
    onSuccess: () => {
      toast.success('Unsubscribed');
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
      navigate('/podcasts');
    },
  });

  const whitelistMutation = useMutation({
    mutationFn: ({ guid, whitelisted }: { guid: string; whitelisted: boolean }) =>
      feedsApi.togglePostWhitelist(guid, whitelisted),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['episodes', selectedFeedId] });
    },
  });

  const bulkWhitelistMutation = useMutation({
    mutationFn: () => feedsApi.toggleAllPostsWhitelist(selectedFeedId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['episodes', selectedFeedId] });
    },
  });

  const refreshFeedMutation = useMutation({
    mutationFn: () => feedsApi.refreshFeed(selectedFeedId!),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
      queryClient.invalidateQueries({ queryKey: ['episodes', selectedFeedId] });
      toast.success(data?.message ?? 'Feed refreshed');
    },
    onError: () => {
      toast.error('Failed to refresh feed');
    },
  });

  const autoDownloadMutation = useMutation({
    mutationFn: (enabled: boolean) => feedsApi.setFeedAutoDownload(selectedFeedId!, enabled),
    onSuccess: (data: { auto_download_enabled: boolean }) => {
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
      toast.success(data.auto_download_enabled ? 'Auto-process enabled' : 'Auto-process disabled');
    },
    onError: () => {
      toast.error('Failed to update auto-process setting');
    },
  });

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (showSettingsMenu && !(event.target as Element).closest('.settings-menu-container')) {
        setShowSettingsMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showSettingsMenu]);

  const handleCopyOriginalRss = async () => {
    const rssUrl = selectedFeed?.rss_url || '';
    if (!rssUrl) {
      toast.error('No RSS URL available');
      return;
    }
    try {
      await copyTextToClipboard(rssUrl);
      toast.success('Original RSS URL copied');
    } catch {
      window.prompt('Copy this RSS feed URL:', rssUrl);
    }
  };

  // Calculate whitelist status for bulk button (same as FeedDetail.tsx)
  const whitelistedCount = episodes ? episodes.filter((ep: Episode) => ep.whitelisted).length : 0;
  const totalCount = episodes ? episodes.length : 0;
  const allWhitelisted = totalCount > 0 && whitelistedCount === totalCount;

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Unknown date';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return '';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  };

  const handleCloseFeed = () => {
    navigate('/podcasts');
  };

  // No feed selected - show placeholder
  if (!selectedFeed) {
    return (
      <div className="flex-1 hidden lg:flex items-center justify-center bg-gray-50 dark:bg-gray-900/50 rounded-xl border-2 border-dashed border-gray-300 dark:border-gray-700">
        <div className="text-center">
          <svg className="w-12 h-12 text-gray-400 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
          </svg>
          <p className="text-gray-500 dark:text-gray-400">Select a podcast to view episodes</p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className={`flex-1 w-full flex flex-col rounded-xl border shadow-sm overflow-hidden ${
        isOriginal
          ? 'bg-blue-900/40 border-blue-300/35'
          : 'bg-white/80 dark:bg-gray-900/50 backdrop-blur-sm border-purple-200/50 dark:border-purple-700/30'
      }`}>
        {/* Feed Header */}
        <div
          className={`p-6 border-b ${isOriginal ? 'border-blue-300/35' : 'border-purple-100/50 dark:border-purple-800/30 bg-gradient-to-r from-pink-50/50 via-purple-50/50 to-cyan-50/50 dark:from-pink-950/20 dark:via-purple-950/20 dark:to-cyan-950/20'}`}
          style={isOriginal ? { background: 'linear-gradient(to right, #1b4f89, #255f9c, #1b4f89)' } : undefined}
        >
          {/* Back button - mobile only */}
          <button
            onClick={handleCloseFeed}
            className={`lg:hidden flex items-center gap-1 mb-3 -mt-1 ${isOriginal ? 'text-blue-200 hover:text-white' : 'text-purple-500 hover:text-purple-700'}`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            <span className="text-sm">Back</span>
          </button>
          <div className="flex items-start gap-3">
            {selectedFeed.image_url && (
              <img
                src={selectedFeed.image_url}
                alt={selectedFeed.title}
                className={`w-16 h-16 sm:w-20 sm:h-20 rounded-xl object-cover shadow-sm flex-shrink-0 ${isOriginal ? 'border border-blue-300/40' : 'border border-purple-200/50'}`}
              />
            )}
            <div className="min-w-0 flex-1">
              <h2 className={`text-xl sm:text-2xl font-bold leading-tight truncate ${isOriginal ? 'text-blue-50' : 'text-purple-900 dark:text-purple-100'}`}>{selectedFeed.title}</h2>
              {selectedFeed.author && (
                <p className={isOriginal ? 'text-blue-100 mt-1 truncate' : 'text-purple-700 dark:text-purple-300 mt-1 truncate'}>{selectedFeed.author}</p>
              )}
              <div className="flex items-center gap-2 mt-1">
                <p className={`text-xs sm:text-sm ${isOriginal ? 'text-blue-200' : 'text-purple-500 dark:text-purple-400'}`}>{selectedFeed.posts_count} episodes</p>
                {(selectedFeed.auto_download_enabled || selectedFeed.auto_download_enabled_by_user) && (
                  <span 
                    className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400"
                    title="Auto-process enabled for new episodes"
                  >
                    Auto
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between gap-2 mt-4">
            <div className="flex items-center gap-2">
              <button
                onClick={async () => {
                  if (requireAuth && !isAuthenticated) {
                    toast.error('Please sign in to copy a protected RSS URL.');
                    return;
                  }
                  try {
                    let rssUrl: string;
                    try {
                      const shareData = await feedsApi.getFeedShareLink(selectedFeed.id);
                      rssUrl = shareData.url;
                    } catch {
                      rssUrl = `${window.location.origin}/feed/${selectedFeed.id}`;
                    }
                    try {
                      await copyTextToClipboard(rssUrl);
                      toast.success('RSS URL copied to clipboard!');
                    } catch {
                      window.prompt('Copy this RSS feed URL:', rssUrl);
                    }
                  } catch (err) {
                    console.error('Failed to get RSS URL', err);
                    toast.error('Failed to get RSS URL');
                  }
                }}
                className="px-3 py-2 text-sm font-medium text-white rounded-xl hover:shadow-lg hover:shadow-purple-500/30 transition-all flex items-center gap-2"
                style={isOriginal ? { background: 'linear-gradient(to right, #2563eb, #0ea5e9, #06b6d4)', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.25)' } : { background: 'linear-gradient(to right, #ec4899, #8b5cf6, #06b6d4)' }}
              >
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M6.18 15.64a2.18 2.18 0 0 1 2.18 2.18C8.36 19 7.38 20 6.18 20C5 20 4 19 4 17.82a2.18 2.18 0 0 1 2.18-2.18M4 4.44A15.56 15.56 0 0 1 19.56 20h-2.83A12.73 12.73 0 0 0 4 7.27V4.44m0 5.66a9.9 9.9 0 0 1 9.9 9.9h-2.83A7.07 7.07 0 0 0 4 12.93V10.1Z"/>
                </svg>
                Podly RSS
              </button>
              {/* Settings Menu */}
              <div className="relative settings-menu-container">
                <button
                  onClick={(e) => { e.stopPropagation(); setShowSettingsMenu(!showSettingsMenu); }}
                  className="px-3 py-2 text-sm font-medium rounded-xl transition-colors"
                  style={{
                    backgroundColor: isOriginal
                      ? 'rgba(15, 35, 73, 0.82)'
                      : isDark
                        ? 'rgba(30, 20, 50, 0.8)'
                        : 'rgba(255, 255, 255, 0.8)',
                    borderWidth: 1,
                    borderColor: isOriginal
                      ? 'rgba(96, 165, 250, 0.45)'
                      : isDark
                        ? 'rgba(139, 92, 246, 0.4)'
                        : 'rgba(196, 181, 253, 0.5)',
                    color: isOriginal ? '#bfdbfe' : isDark ? '#c4b5fd' : '#7c3aed',
                  }}
                >
                  Settings
                </button>

                {/* Dropdown Menu */}
                {showSettingsMenu && (
                  <div 
                    className="absolute top-full left-0 mt-1 w-56 rounded-lg shadow-lg border py-1 z-20"
                    style={{
                      backgroundColor: isOriginal ? '#0b1f45' : isDark ? '#1f2937' : '#ffffff',
                      borderColor: isOriginal ? '#1d4ed8' : isDark ? '#374151' : '#e5e7eb',
                    }}
                  >
                    {/* Auto-process toggle - only when auth is enabled */}
                    {requireAuth && (
                      <button
                        onClick={() => {
                          const isEnabled = selectedFeed.auto_download_enabled || selectedFeed.auto_download_enabled_by_user;
                          const isEnabledByOther = selectedFeed.auto_download_enabled_by_other && !selectedFeed.auto_download_enabled_by_user;
                          if (!isEnabledByOther) {
                            autoDownloadMutation.mutate(!isEnabled);
                          }
                          setShowSettingsMenu(false);
                        }}
                        disabled={autoDownloadMutation.isPending || (selectedFeed.auto_download_enabled_by_other && !selectedFeed.auto_download_enabled_by_user)}
                        className="w-full px-4 py-2 text-left text-sm flex items-center justify-between disabled:opacity-50 disabled:cursor-not-allowed"
                        style={{ color: isOriginal ? '#dbeafe' : isDark ? '#e5e7eb' : '#374151' }}
                      >
                        <span className="flex items-center gap-3">
                          <svg className="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                          </svg>
                          Auto-process
                        </span>
                        <span className={`inline-block w-8 h-4 rounded-full transition-colors ${
                          (selectedFeed.auto_download_enabled || selectedFeed.auto_download_enabled_by_user) ? 'bg-emerald-500' : 'bg-gray-300 dark:bg-gray-600'
                        }`}>
                          <span className={`inline-block w-3 h-3 mt-0.5 rounded-full bg-white transition-transform ${
                            (selectedFeed.auto_download_enabled || selectedFeed.auto_download_enabled_by_user) ? 'translate-x-4' : 'translate-x-0.5'
                          }`} />
                        </span>
                      </button>
                    )}

                    <button
                      onClick={() => {
                        if (!allWhitelisted) {
                          bulkWhitelistMutation.mutate();
                        }
                        setShowSettingsMenu(false);
                      }}
                      disabled={bulkWhitelistMutation.isPending || totalCount === 0 || allWhitelisted}
                      className="w-full px-4 py-2 text-left text-sm flex items-center gap-3 disabled:opacity-50 disabled:cursor-not-allowed hover:opacity-80"
                      style={{ color: isOriginal ? '#dbeafe' : isDark ? '#e5e7eb' : '#374151' }}
                    >
                      <span className="text-green-600">✓</span>
                      Enable all episodes
                    </button>

                    <button
                      onClick={() => {
                        if (allWhitelisted) {
                          bulkWhitelistMutation.mutate();
                        }
                        setShowSettingsMenu(false);
                      }}
                      disabled={bulkWhitelistMutation.isPending || totalCount === 0 || !allWhitelisted}
                      className="w-full px-4 py-2 text-left text-sm flex items-center gap-3 disabled:opacity-50 disabled:cursor-not-allowed hover:opacity-80"
                      style={{ color: isOriginal ? '#dbeafe' : isDark ? '#e5e7eb' : '#374151' }}
                    >
                      <span className="text-red-600">⛔</span>
                      Disable all episodes
                    </button>

                    <button
                      onClick={() => {
                        refreshFeedMutation.mutate();
                        setShowSettingsMenu(false);
                      }}
                      disabled={refreshFeedMutation.isPending}
                      className="w-full px-4 py-2 text-left text-sm flex items-center gap-3 disabled:opacity-50 disabled:cursor-not-allowed hover:opacity-80"
                      style={{ color: isOriginal ? '#dbeafe' : isDark ? '#e5e7eb' : '#374151' }}
                    >
                      <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      Refresh feed
                    </button>

                    <button
                      onClick={() => {
                        handleCopyOriginalRss();
                        setShowSettingsMenu(false);
                      }}
                      className="w-full px-4 py-2 text-left text-sm flex items-center gap-3 hover:opacity-80"
                      style={{ color: isOriginal ? '#dbeafe' : isDark ? '#e5e7eb' : '#374151' }}
                    >
                      <svg className="w-4 h-4 text-orange-500" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M6.18 15.64a2.18 2.18 0 0 1 2.18 2.18C8.36 19 7.38 20 6.18 20C5 20 4 19 4 17.82a2.18 2.18 0 0 1 2.18-2.18M4 4.44A15.56 15.56 0 0 1 19.56 20h-2.83A12.73 12.73 0 0 0 4 7.27V4.44m0 5.66a9.9 9.9 0 0 1 9.9 9.9h-2.83A7.07 7.07 0 0 0 4 12.93V10.1Z"/>
                      </svg>
                      Original RSS feed
                    </button>
                  </div>
                )}
              </div>
            </div>
            {requireAuth && (
              <button
                onClick={() => {
                  if (!isAuthenticated) {
                    toast.error('Please sign in to unsubscribe.');
                    return;
                  }
                  if (confirm(`Unsubscribe from "${selectedFeed.title}"?`)) {
                    unsubscribeMutation.mutate(selectedFeed.id);
                  }
                }}
                disabled={unsubscribeMutation.isPending}
                className="px-3 py-2 text-sm font-medium rounded-xl transition-colors"
                style={{
                  backgroundColor: 'transparent',
                  borderWidth: 1,
                  borderColor: isOriginal ? 'rgba(96, 165, 250, 0.52)' : isDark ? 'rgba(244, 114, 182, 0.4)' : 'rgba(251, 207, 232, 1)',
                  color: isOriginal ? '#bfdbfe' : isDark ? '#f9a8d4' : '#be185d'
                }}
                title="Unsubscribe"
              >
                Unsubscribe
              </button>
            )}
          </div>
        </div>

        {/* Description */}
        {selectedFeed.description && (
          <div className="px-6 pt-4 pb-2">
            <p className={`text-sm line-clamp-3 ${isOriginal ? 'text-blue-100' : 'text-purple-700 dark:text-purple-300'}`}>{selectedFeed.description}</p>
          </div>
        )}

        {/* Episodes List */}
        <div className="flex-1 overflow-y-auto">
          {episodesLoading ? (
            <div className="flex items-center justify-center h-32">
              <div className={`animate-spin rounded-full h-6 w-6 border-b-2 ${isOriginal ? 'border-blue-300' : 'border-purple-600'}`} />
            </div>
          ) : episodes && episodes.length > 0 ? (
            <div>
              {episodes.map((episode: Episode, idx: number) => (
                <div
                  key={episode.id}
                  className={`px-4 sm:px-6 py-3 sm:py-4 transition-colors ${
                    idx > 0
                      ? isOriginal
                        ? 'border-t border-blue-300/15'
                        : 'border-t border-purple-100/40 dark:border-purple-800/20'
                      : ''
                  } ${
                    !(episode.whitelisted || episode.has_processed_audio)
                      ? isOriginal ? 'opacity-60' : 'opacity-50'
                      : ''
                  }`}
                >
                  {/* Top row: Title + Status badge */}
                  <div className="flex items-start justify-between gap-3 mb-1.5">
                    <div className="flex-1 min-w-0">
                      <button
                        onClick={() => setSelectedEpisode(episode)}
                        className={`text-left font-medium line-clamp-2 leading-snug hover:underline cursor-pointer transition-colors ${
                          isOriginal
                            ? 'text-blue-100 hover:text-white'
                            : 'text-purple-900 dark:text-purple-100 hover:text-purple-700 dark:hover:text-purple-300'
                        }`}
                      >
                        {episode.title}
                      </button>
                    </div>
                    {/* Status indicator */}
                    <div className="flex-shrink-0">
                      {episode.has_processed_audio ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400 rounded-full">
                          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                          </svg>
                          Ready
                        </span>
                      ) : episode.whitelisted ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400 rounded-full">
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" />
                          </svg>
                          Enabled
                        </span>
                      ) : (
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full ${
                          isOriginal
                            ? 'text-blue-300/70'
                            : 'text-purple-400 dark:text-purple-500'
                        }`}>
                          Disabled
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Middle row: Metadata */}
                  <div className={`flex items-center gap-2 text-xs mb-2.5 ${isOriginal ? 'text-blue-300/70' : 'text-purple-400 dark:text-purple-500'}`}>
                    <span>{formatDate(episode.release_date)}</span>
                    {episode.duration && (
                      <>
                        <span>·</span>
                        <span>{formatDuration(episode.duration)}</span>
                      </>
                    )}
                  </div>

                  {/* Bottom row: Actions */}
                  <div className="flex flex-wrap items-center gap-1.5">
                    {/* Toggle Enable/Skip */}
                    <button
                      onClick={() => whitelistMutation.mutate({ guid: episode.guid, whitelisted: !episode.whitelisted })}
                      className={`px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-1 border ${
                        isOriginal
                          ? episode.whitelisted
                            ? 'bg-blue-950/55 border-red-300/45 text-red-200 hover:bg-red-900/28'
                            : 'bg-blue-950/55 border-emerald-300/45 text-emerald-100 hover:bg-emerald-900/24'
                          : episode.whitelisted
                            ? 'bg-white dark:bg-gray-800 border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30'
                            : 'bg-white dark:bg-gray-800 border-emerald-200 dark:border-emerald-800 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-900/30'
                      }`}
                    >
                      {episode.whitelisted ? (
                        <>
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                          Disable
                        </>
                      ) : (
                        <>
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                          </svg>
                          Enable
                        </>
                      )}
                    </button>

                    {/* Processed episode actions */}
                    {episode.has_processed_audio && (
                      <>
                        <PlayButton episode={episode} />
                        <DownloadButton 
                          episodeGuid={episode.guid}
                          isWhitelisted={episode.whitelisted}
                          hasProcessedAudio={episode.has_processed_audio}
                          feedId={selectedFeed?.id}
                        />
                        <ProcessingStatsButton 
                          episodeGuid={episode.guid}
                          hasProcessedAudio={episode.has_processed_audio}
                        />
                        <ReprocessButton 
                          episodeGuid={episode.guid}
                          isWhitelisted={episode.whitelisted}
                          feedId={selectedFeed?.id}
                          onReprocessStart={() => {
                            setProcessingPollTriggers(prev => ({
                              ...prev,
                              [episode.guid]: Date.now(),
                            }));
                          }}
                        />
                      </>
                    )}

                    {/* Process button for enabled but not yet processed */}
                    {episode.whitelisted && !episode.has_processed_audio && (
                      <ProcessButton 
                        episodeGuid={episode.guid}
                        feedId={selectedFeed?.id}
                        onProcessStart={() => {
                          setProcessingPollTriggers(prev => ({
                            ...prev,
                            [episode.guid]: Date.now(),
                          }));
                        }}
                      />
                    )}
                  </div>

                  {/* Processing status indicator */}
                  <EpisodeProcessingStatus
                    episodeGuid={episode.guid}
                    isWhitelisted={episode.whitelisted}
                    hasProcessedAudio={episode.has_processed_audio}
                    pollTrigger={processingPollTriggers[episode.guid]}
                    onProcessingComplete={() => {
                      queryClient.invalidateQueries({ queryKey: ['episodes', selectedFeed?.id] });
                    }}
                  />
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <p className="text-gray-500 dark:text-gray-400">No episodes found</p>
            </div>
          )}
        </div>
      </div>

      {/* Episode Details Modal */}
      {selectedEpisode && (
        <EpisodeDetailModal
          episode={selectedEpisode}
          feedTitle={selectedFeed?.title}
          feedImageUrl={selectedFeed?.image_url}
          feedId={selectedFeed?.id}
          onClose={() => setSelectedEpisode(null)}
          onWhitelistToggle={(guid, whitelisted) => {
            whitelistMutation.mutate({ guid, whitelisted });
          }}
          onProcessStart={(guid) => {
            setProcessingPollTriggers(prev => ({
              ...prev,
              [guid]: Date.now()
            }));
          }}
        />
      )}
    </>
  );
}
