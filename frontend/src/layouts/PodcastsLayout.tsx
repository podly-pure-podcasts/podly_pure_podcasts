import { useState, createContext, useContext } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { createPortal } from 'react-dom';
import { feedsApi, presetsApi } from '../services/api';
import { toast } from 'react-hot-toast';
import type { Feed } from '../types';
import AddFeedForm from '../components/AddFeedForm';
import SubscriptionModal from '../components/SubscriptionModal';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { getThemeLogoPath } from '../theme';
import { useEscapeKey } from '../hooks/useEscapeKey';

// Regression guard: Track feed list fetches to detect duplicate requests
const feedFetchTracker = {
  lastFetchTime: 0,
  fetchCount: 0,
  warnThreshold: 2, // Warn if more than 2 fetches within window
  windowMs: 5000, // 5 second window
};

function trackFeedFetch() {
  const now = Date.now();
  if (now - feedFetchTracker.lastFetchTime > feedFetchTracker.windowMs) {
    // Reset counter if outside window
    feedFetchTracker.fetchCount = 1;
  } else {
    feedFetchTracker.fetchCount++;
    if (feedFetchTracker.fetchCount > feedFetchTracker.warnThreshold && import.meta.env.DEV) {
      console.warn(
        `[PodcastsLayout] Duplicate feed list fetch detected! ` +
        `${feedFetchTracker.fetchCount} fetches in ${feedFetchTracker.windowMs}ms. ` +
        `This may indicate a routing/remount issue.`
      );
    }
  }
  feedFetchTracker.lastFetchTime = now;
}

// Context for sharing podcasts data with child routes
interface PodcastsContextType {
  feeds: Feed[];
  feedsLoading: boolean;
  refetchFeeds: () => void;
  selectedFeedId: number | null;
  setSelectedFeedId: (id: number | null) => void;
  searchTerm: string;
  setSearchTerm: (term: string) => void;
  presets: any[] | undefined;
  queryClient: ReturnType<typeof useQueryClient>;
}

const PodcastsContext = createContext<PodcastsContextType | null>(null);

export function usePodcastsContext() {
  const context = useContext(PodcastsContext);
  if (!context) {
    throw new Error('usePodcastsContext must be used within PodcastsLayout');
  }
  return context;
}

export default function PodcastsLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [showAddForm, setShowAddForm] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [showSubscriptions, setShowSubscriptions] = useState(false);
  const [copyUrlModal, setCopyUrlModal] = useState<string | null>(null);
  const { requireAuth, user } = useAuth();
  const { theme } = useTheme();
  const isOriginal = theme === 'original';
  const themeLogoPath = getThemeLogoPath(theme);
  useEscapeKey(showAddForm, () => setShowAddForm(false));
  useEscapeKey(!!copyUrlModal, () => setCopyUrlModal(null));

  // Determine if we're on the combined page
  const isCombinedView = location.pathname === '/podcasts/combined';
  
  // Get selected feed from URL (only for non-combined view)
  const urlParams = new URLSearchParams(location.search);
  const selectedFeedId = !isCombinedView && urlParams.get('feed') ? parseInt(urlParams.get('feed')!) : null;

  // Single source of truth for feeds - fetched once here
  const { data: feeds, isLoading: feedsLoading, refetch: refetchFeeds } = useQuery({
    queryKey: ['feeds'],
    queryFn: () => {
      trackFeedFetch(); // Regression guard
      return feedsApi.getFeeds();
    },
    staleTime: 30000, // Consider data fresh for 30 seconds
  });

  const { data: presets } = useQuery({
    queryKey: ['presets'],
    queryFn: presetsApi.getPresets,
    enabled: requireAuth && user?.role === 'admin',
  });

  const feedsArray = Array.isArray(feeds) ? feeds : [];

  const filteredFeeds = feedsArray.filter((feed: Feed) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return feed.title?.toLowerCase().includes(term) || feed.author?.toLowerCase().includes(term);
  });

  const togglePrivacyMutation = useMutation({
    mutationFn: ({ feedId, isPrivate }: { feedId: number; isPrivate: boolean }) => 
      feedsApi.subscribeFeed(feedId, isPrivate),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
    },
  });

  const handleSelectFeed = (feedId: number) => {
    navigate(`/podcasts?feed=${feedId}`);
  };

  const handleSelectCombined = () => {
    navigate('/podcasts/combined');
  };

  const setSelectedFeedId = (id: number | null) => {
    if (id) {
      navigate(`/podcasts?feed=${id}`);
    } else {
      navigate('/podcasts');
    }
  };

  if (feedsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600" />
      </div>
    );
  }

  const contextValue: PodcastsContextType = {
    feeds: feedsArray,
    feedsLoading,
    refetchFeeds,
    selectedFeedId,
    setSelectedFeedId,
    searchTerm,
    setSearchTerm,
    presets,
    queryClient,
  };

  return (
    <PodcastsContext.Provider value={contextValue}>
      <div className="min-h-full lg:h-full flex flex-col lg:flex-row gap-4 lg:gap-6">
        {/* Left Panel - Feed List - hidden on mobile when content selected */}
        <div className={`lg:w-80 flex-shrink-0 flex-col ${(selectedFeedId || isCombinedView) ? 'hidden lg:flex' : 'flex w-full'}`}>
          <div className="flex items-center justify-between mb-4">
            <h1 className={`text-xl font-bold ${isOriginal ? 'text-blue-100' : 'text-gray-900 dark:text-gray-100'}`}>Podcasts</h1>
            <button
              onClick={() => setShowAddForm(true)}
              className={`px-3 py-1.5 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-1 ${
                isOriginal ? 'bg-blue-500 hover:bg-blue-400 border border-blue-300/55' : 'bg-blue-600 hover:bg-blue-700'
              }`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Add Podcast
            </button>
          </div>
          
          {requireAuth && (
            <div className="space-y-2 mb-4">
              <button
                onClick={() => setShowSubscriptions(true)}
                className={`w-full px-3 py-2 text-sm font-medium rounded-lg transition-colors border flex items-center justify-center gap-2 ${
                  isOriginal
                    ? 'bg-blue-900/55 text-blue-100 hover:bg-blue-800/65 border-blue-300/45'
                    : 'bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 hover:bg-purple-100 dark:hover:bg-purple-900/50 border-purple-200 dark:border-purple-700/50'
                }`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                Browse Podcasts on Server
              </button>
              <button
                onClick={() => {
                  feedsApi.getCombinedFeedShareLink()
                    .then((result) => {
                      if (navigator.clipboard && window.isSecureContext) {
                        return navigator.clipboard.writeText(result.url).then(() => {
                          toast.success('Combined feed URL copied! Add this to your podcast app to get all your shows in one feed.');
                        }).catch(() => {
                          setCopyUrlModal(result.url);
                        });
                      } else {
                        setCopyUrlModal(result.url);
                      }
                    })
                    .catch((err: unknown) => {
                      console.error('Failed to get combined feed link:', err);
                      const axiosErr = err as { response?: { status?: number; data?: { error?: string } } };
                      if (axiosErr.response?.status === 401) {
                        toast.error('Please log in again to generate feed link');
                      } else if (axiosErr.response?.data?.error) {
                        toast.error(axiosErr.response.data.error);
                      } else {
                        toast.error('Failed to generate combined feed link');
                      }
                    });
                }}
                className="w-full px-3 py-2 bg-gradient-to-r from-pink-500 via-purple-500 to-cyan-500 text-white text-sm font-medium rounded-lg hover:from-pink-600 hover:via-purple-600 hover:to-cyan-600 transition-colors flex items-center justify-center gap-2"
                style={isOriginal ? { background: 'linear-gradient(to right, #1d4ed8, #0ea5e9, #06b6d4)' } : undefined}
                title="Get one RSS feed with all episodes from all your subscribed podcasts"
              >
                <img src={themeLogoPath} alt="" className="w-5 h-5" />
                All-in-One Podly RSS
              </button>
              <p className={`text-xs text-center ${isOriginal ? 'text-blue-200' : 'text-gray-500 dark:text-gray-400'}`}>
                One feed with all your podcasts combined
              </p>
            </div>
          )}

          <input
            type="search"
            placeholder="Search podcasts..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className={`w-full px-3 py-2 mb-4 border rounded-lg focus:ring-2 focus:border-purple-500 ${
              isOriginal
                ? 'border-blue-300/45 focus:ring-blue-400 bg-blue-900/45 text-blue-100'
                : 'border-gray-300 dark:border-gray-600 focus:ring-purple-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100'
            }`}
          />

          <div className="flex-1 overflow-y-auto pb-16">
            {/* Pinned Combined RSS entry - uses same card styling */}
            {requireAuth && feedsArray.length > 0 && (
              <FeedSidebarItem
                isSelected={isCombinedView}
                onClick={handleSelectCombined}
                imageUrl={themeLogoPath}
                title="Combined Episodes"
                subtitle="All episodes from your subscriptions"
                badge={`${feedsArray.length} shows`}
                isCombined
              />
            )}

            {filteredFeeds.length === 0 ? (
              <div className="text-center py-8">
                <p className={isOriginal ? 'text-blue-200' : 'text-gray-500 dark:text-gray-400'}>No podcasts found</p>
                {requireAuth && (
                  <button
                    onClick={() => setShowSubscriptions(true)}
                    className={`mt-3 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                      isOriginal
                        ? 'bg-blue-900/55 text-blue-100 border border-blue-300/45 hover:bg-blue-800/65'
                        : 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 hover:bg-purple-200 dark:hover:bg-purple-900/50'
                    }`}
                  >
                    Browse Podcasts on Server
                  </button>
                )}
              </div>
            ) : (
              filteredFeeds.map((feed: Feed) => (
                <FeedSidebarItem
                  key={feed.id}
                  isSelected={selectedFeedId === feed.id}
                  onClick={() => handleSelectFeed(feed.id)}
                  imageUrl={feed.image_url}
                  title={feed.title}
                  subtitle={`${feed.posts_count} episodes`}
                  presetName={feed.effective_prompt_preset?.name}
                  showAutoTag={feed.auto_download_enabled || feed.auto_download_enabled_by_user}
                  showPrivacyToggle={requireAuth}
                  isPrivate={(feed as any).is_private}
                  onPrivacyToggle={() => {
                    togglePrivacyMutation.mutate({ feedId: feed.id, isPrivate: !(feed as any).is_private });
                  }}
                  privacyToggleDisabled={togglePrivacyMutation.isPending}
                />
              ))
            )}
          </div>
        </div>

        {/* Right Panel - Content from child route */}
        <Outlet />

        {/* Add Feed Modal */}
        {showAddForm && createPortal(
          <div 
            className="fixed inset-0 flex items-center justify-center p-4"
            style={{ zIndex: 9999, backgroundColor: isOriginal ? 'rgba(2, 8, 23, 0.82)' : 'rgba(0, 0, 0, 0.8)' }}
            onClick={() => setShowAddForm(false)}
          >
            <div 
              className="modal-content w-full max-w-2xl bg-white dark:bg-gray-800 rounded-2xl shadow-2xl border border-purple-200 dark:border-purple-700 flex flex-col max-h-[85vh]"
              style={isOriginal ? { backgroundColor: '#0a2249', borderColor: 'rgba(96, 165, 250, 0.45)' } : undefined}
              onClick={(e) => e.stopPropagation()}
            >
              <div
                className="flex items-center justify-between border-b border-purple-100 dark:border-purple-800 px-4 py-3 bg-gradient-to-r from-pink-50 via-purple-50 to-cyan-50 dark:from-pink-950/30 dark:via-purple-950/30 dark:to-cyan-950/30 rounded-t-2xl"
                style={isOriginal ? { borderColor: 'rgba(96, 165, 250, 0.35)', background: 'linear-gradient(to right, #14467e, #1d5995, #14467e)' } : undefined}
              >
                <h2 className={`text-lg font-semibold ${isOriginal ? 'text-blue-100' : 'text-purple-900 dark:text-purple-100'}`}>Add Podcast</h2>
                <button
                  onClick={() => setShowAddForm(false)}
                  className={`p-2 rounded-lg ${
                    isOriginal
                      ? 'text-blue-200 hover:text-blue-50 hover:bg-blue-800/40'
                      : 'text-purple-600 dark:text-purple-400 hover:text-purple-800 dark:hover:text-purple-200 hover:bg-purple-100 dark:hover:bg-purple-900/50'
                  }`}
                  aria-label="Close"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div className="overflow-y-auto px-3 py-2 sm:px-4 sm:py-3 flex-1">
                <AddFeedForm
                  onSuccess={() => {
                    setShowAddForm(false);
                    refetchFeeds();
                  }}
                  subscribedFeedUrls={feedsArray.map((f: Feed) => f.rss_url)}
                />
              </div>
            </div>
          </div>,
          document.body
        )}

        {/* Subscription Management Modal */}
        {showSubscriptions && createPortal(
          <SubscriptionModal 
            onClose={() => setShowSubscriptions(false)} 
            onUpdate={() => refetchFeeds()}
          />,
          document.body
        )}

        {/* Copy URL Modal for iOS fallback */}
        {copyUrlModal && createPortal(
          <div 
            className="fixed inset-0 flex items-center justify-center p-4"
            style={{ zIndex: 10000, backgroundColor: isOriginal ? 'rgba(2, 8, 23, 0.82)' : 'rgba(0, 0, 0, 0.8)' }}
            onClick={() => setCopyUrlModal(null)}
          >
            <div 
              className="modal-content bg-white dark:bg-gray-800 rounded-2xl max-w-lg w-full overflow-hidden shadow-2xl border border-purple-200 dark:border-purple-700"
              style={isOriginal ? { backgroundColor: '#0a2249', borderColor: 'rgba(96, 165, 250, 0.45)' } : undefined}
              onClick={(e) => e.stopPropagation()}
            >
              <div
                className="p-6 border-b border-purple-100 dark:border-purple-800 bg-gradient-to-r from-pink-50 via-purple-50 to-cyan-50 dark:from-pink-950/30 dark:via-purple-950/30 dark:to-cyan-950/30"
                style={isOriginal ? { borderColor: 'rgba(96, 165, 250, 0.35)', background: 'linear-gradient(to right, #14467e, #1d5995, #14467e)' } : undefined}
              >
                <h2 className={`text-xl font-bold flex items-center gap-2 ${isOriginal ? 'text-blue-100' : 'text-purple-900 dark:text-purple-100'}`}>
                  <img src={themeLogoPath} alt="" className="w-6 h-6" />
                  Combined Feed URL
                </h2>
              </div>
              <div className="p-6">
                <p className={`text-sm mb-4 ${isOriginal ? 'text-blue-200' : 'text-gray-600 dark:text-gray-300'}`}>Copy this URL and add it to your podcast app:</p>
                <textarea
                  readOnly
                  value={copyUrlModal}
                  className={`w-full p-3 border rounded-lg text-sm font-mono ${
                    isOriginal
                      ? 'border-blue-300/45 bg-blue-950/55 text-blue-100'
                      : 'border-purple-200 dark:border-purple-700 bg-purple-50 dark:bg-purple-950/50 text-purple-900 dark:text-purple-100'
                  }`}
                  rows={3}
                  onClick={(e) => (e.target as HTMLTextAreaElement).select()}
                />
                <div className="flex gap-2 mt-4">
                  <button
                    onClick={() => {
                      navigator.clipboard?.writeText(copyUrlModal);
                      toast.success('Copied!');
                    }}
                    className={`flex-1 px-4 py-2 text-white rounded-lg transition-colors ${
                      isOriginal
                        ? 'bg-blue-500 hover:bg-blue-400 border border-blue-300/55'
                        : 'bg-purple-600 hover:bg-purple-700'
                    }`}
                  >
                    Copy
                  </button>
                  <button
                    onClick={() => setCopyUrlModal(null)}
                    className={`px-4 py-2 border rounded-lg transition-colors ${
                      isOriginal
                        ? 'border-blue-300/45 text-blue-100 hover:bg-blue-900/45'
                        : 'border-purple-200 dark:border-purple-700 text-purple-700 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-900/50'
                    }`}
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          </div>,
          document.body
        )}
      </div>
    </PodcastsContext.Provider>
  );
}

// Shared sidebar item component for both regular feeds and combined entry
interface FeedSidebarItemProps {
  isSelected: boolean;
  onClick: () => void;
  imageUrl?: string | null;
  title: string;
  subtitle: string;
  badge?: string;
  presetName?: string;
  showAutoTag?: boolean;
  isCombined?: boolean;
  showPrivacyToggle?: boolean;
  isPrivate?: boolean;
  onPrivacyToggle?: () => void;
  privacyToggleDisabled?: boolean;
}

function FeedSidebarItem({
  isSelected,
  onClick,
  imageUrl,
  title,
  subtitle,
  badge,
  presetName,
  showAutoTag,
  isCombined,
  showPrivacyToggle,
  isPrivate,
  onPrivacyToggle,
  privacyToggleDisabled,
}: FeedSidebarItemProps) {
  const { theme } = useTheme();
  const isOriginal = theme === 'original';
  const baseClasses = isOriginal
    ? isSelected
      ? 'bg-blue-700/25'
      : 'hover:bg-blue-800/20'
    : isSelected
      ? 'bg-purple-100 dark:bg-purple-900/30'
      : 'hover:bg-purple-50 dark:hover:bg-purple-900/20';

  const borderClass = isOriginal
    ? 'border-t border-blue-300/15'
    : 'border-t border-purple-100/40 dark:border-purple-800/20';

  return (
    <div className={`px-2 py-2.5 rounded-lg transition-colors ${baseClasses} ${isCombined ? '' : borderClass}`}>
      <div 
        className="flex items-center gap-3 cursor-pointer"
        onClick={onClick}
      >
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={title}
            className={`w-12 h-12 rounded-lg object-cover ${isCombined ? '' : ''}`}
          />
        ) : (
          <div className="w-12 h-12 rounded-lg bg-gray-200 dark:bg-gray-700 flex items-center justify-center">
            <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
            </svg>
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <h3 className={`font-medium truncate ${isCombined ? 'text-purple-900 dark:text-purple-100' : 'text-gray-900 dark:text-gray-100'}`}>
              <span className={isOriginal ? 'text-blue-100' : ''}>{title}</span>
            </h3>
            {badge && (
              <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded ${
                isOriginal
                  ? 'bg-blue-800/40 text-blue-200/80'
                  : 'bg-purple-200 dark:bg-purple-800 text-purple-700 dark:text-purple-300'
              }`}>
                {badge}
              </span>
            )}
            {showAutoTag && (
              <span 
                className="flex-shrink-0 px-1.5 py-0.5 text-[10px] font-medium rounded bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400"
                title="Auto-process enabled for new episodes"
              >
                Auto
              </span>
            )}
          </div>
          <p className={`text-xs truncate ${isOriginal ? 'text-blue-200' : isCombined ? 'text-purple-600 dark:text-purple-400' : 'text-gray-500 dark:text-gray-400'}`}>
            {subtitle}
          </p>
          {presetName && (
            <p className={`text-[11px] truncate ${isOriginal ? 'text-blue-200' : 'text-purple-600 dark:text-purple-400'}`}>
              Preset: {presetName}
            </p>
          )}
        </div>
        {isCombined && (
          <svg className={`w-5 h-5 ${isOriginal ? 'text-blue-200' : 'text-purple-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        )}
      </div>
      {showPrivacyToggle && onPrivacyToggle && (
        <div className={`flex items-center justify-end gap-2 mt-2 pt-2 border-t ${isOriginal ? 'border-blue-300/30' : 'border-purple-100/50 dark:border-purple-800/50'}`}>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onPrivacyToggle();
            }}
            disabled={privacyToggleDisabled}
            className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs transition-colors ${
              isPrivate
                ? isOriginal
                  ? 'bg-blue-800/55 text-blue-100 border border-blue-300/40'
                  : 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                : isOriginal
                  ? 'bg-emerald-900/30 text-emerald-100 border border-emerald-300/35'
                  : 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400'
            }`}
            title={isPrivate 
              ? 'Private - This feed is hidden from other users. Click to make public.' 
              : 'Public - Other users can discover this feed. Click to make private.'}
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {isPrivate ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              )}
            </svg>
            {isPrivate ? 'Private' : 'Public'}
          </button>
        </div>
      )}
    </div>
  );
}
