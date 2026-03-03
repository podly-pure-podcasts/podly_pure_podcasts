import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { feedsApi } from '../services/api';
import { useEscapeKey } from '../hooks/useEscapeKey';
import { useTheme } from '../contexts/ThemeContext';

interface SubscriptionModalProps {
  onClose: () => void;
  onUpdate: () => void;
}

export default function SubscriptionModal({ onClose, onUpdate }: SubscriptionModalProps) {
  const queryClient = useQueryClient();
  const { theme } = useTheme();
  const isOriginal = theme === 'original';
  useEscapeKey(true, onClose);
  
  const { data: allFeeds, isLoading } = useQuery({
    queryKey: ['all-feeds'],
    queryFn: feedsApi.getAllFeeds,
  });

  const subscribeMutation = useMutation({
    mutationFn: ({ feedId, isPrivate }: { feedId: number; isPrivate: boolean }) => 
      feedsApi.subscribeFeed(feedId, isPrivate),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['all-feeds'] });
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
      queryClient.invalidateQueries({ queryKey: ['episodes', variables.feedId] });
      onUpdate();
    },
  });

  const unsubscribeMutation = useMutation({
    mutationFn: (feedId: number) => feedsApi.unsubscribeFeed(feedId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['all-feeds'] });
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
      onUpdate();
    },
  });

  const handleSubscribe = (feedId: number, isPrivate: boolean = false) => {
    subscribeMutation.mutate({ feedId, isPrivate });
  };

  const handleUnsubscribe = (feedId: number) => {
    unsubscribeMutation.mutate(feedId);
  };

  const handleTogglePrivacy = (feedId: number, currentPrivacy: boolean) => {
    subscribeMutation.mutate({ feedId, isPrivate: !currentPrivacy });
  };

  return (
    <div 
      className="fixed inset-0 flex items-center justify-center p-4"
      style={{ zIndex: 9999, backgroundColor: isOriginal ? 'rgba(2, 8, 23, 0.82)' : 'rgba(0, 0, 0, 0.8)' }}
      onClick={onClose}
    >
      <div 
        className="modal-content w-full max-w-2xl bg-white dark:bg-gray-800 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 flex flex-col max-h-[85vh]"
        style={isOriginal ? { backgroundColor: '#0a2249', borderColor: 'rgba(96, 165, 250, 0.46)' } : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="flex items-center justify-between border-b border-gray-200 dark:border-gray-700 px-4 sm:px-6 py-3 sm:py-4"
          style={isOriginal ? { borderColor: 'rgba(96, 165, 250, 0.35)', background: 'linear-gradient(to right, #14467e, #1d5995, #14467e)' } : undefined}
        >
          <div className="min-w-0">
            <h2 className={`text-lg sm:text-xl font-semibold ${isOriginal ? 'text-blue-100' : 'text-gray-900 dark:text-gray-100'}`}>Manage Subscriptions</h2>
            <p className={`text-xs sm:text-sm mt-0.5 sm:mt-1 ${isOriginal ? 'text-blue-200' : 'text-gray-500 dark:text-gray-400'}`}>Choose which podcasts appear in your feed list</p>
          </div>
          <button
            onClick={onClose}
            className={`p-2 rounded-lg ${isOriginal ? 'text-blue-200 hover:text-blue-50 hover:bg-blue-800/40' : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'}`}
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        
        <div className="overflow-y-auto px-3 sm:px-6 py-3 sm:py-4 flex-1">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className={`animate-spin rounded-full h-8 w-8 border-b-2 ${isOriginal ? 'border-blue-300' : 'border-purple-600'}`} />
            </div>
          ) : allFeeds && allFeeds.length > 0 ? (
            <div className="space-y-3">
              {allFeeds.map((feed) => (
                <div 
                  key={feed.id}
                  className={`p-3 sm:p-4 rounded-xl border transition-all ${
                    feed.is_subscribed 
                      ? isOriginal
                        ? 'bg-blue-900/55 border-blue-300/45'
                        : 'bg-purple-50 dark:bg-purple-900/30 border-purple-200 dark:border-purple-700'
                      : isOriginal
                        ? 'bg-blue-950/40 border-blue-300/30'
                        : 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700'
                  }`}
                >
                  <div className="flex items-center gap-2.5 sm:gap-3">
                    {feed.image_url ? (
                      <img
                        src={feed.image_url}
                        alt={feed.title}
                        className="w-10 h-10 sm:w-12 sm:h-12 rounded-lg object-cover flex-shrink-0"
                      />
                    ) : (
                      <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-lg bg-gray-200 dark:bg-gray-700 flex items-center justify-center flex-shrink-0">
                        <svg className="w-5 h-5 sm:w-6 sm:h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                        </svg>
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <h3 className={`font-medium truncate text-sm sm:text-base ${isOriginal ? 'text-blue-50' : 'text-gray-900 dark:text-gray-100'}`}>{feed.title}</h3>
                      <p className={`text-xs ${isOriginal ? 'text-blue-200' : 'text-gray-500 dark:text-gray-400'}`}>{feed.posts_count} episodes</p>
                    </div>
                    {/* Actions: visible on sm+ screens inline */}
                    <div className="hidden sm:flex items-center gap-2 flex-shrink-0">
                      {feed.is_subscribed ? (
                        <>
                          <button
                            onClick={() => handleTogglePrivacy(feed.id, (feed as any).is_private || false)}
                            disabled={subscribeMutation.isPending}
                            className={`p-2 rounded-lg transition-colors ${
                              (feed as any).is_private
                                ? 'bg-gray-700 text-white'
                                : 'bg-gray-100 dark:bg-gray-700 text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
                            }`}
                            title={(feed as any).is_private 
                              ? 'Private subscription - Click to make public' 
                              : 'Public subscription - Click to make private'}
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              {(feed as any).is_private ? (
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                              ) : (
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                              )}
                            </svg>
                          </button>
                          <button
                            onClick={() => handleUnsubscribe(feed.id)}
                            disabled={unsubscribeMutation.isPending}
                            className={`px-4 py-2 text-sm font-medium rounded-lg disabled:opacity-50 ${
                              isOriginal
                                ? 'bg-blue-500 text-white hover:bg-blue-400 border border-blue-300/55'
                                : 'bg-purple-600 text-white hover:bg-purple-700'
                            }`}
                            title="Click to unsubscribe"
                          >
                            Subscribed
                          </button>
                        </>
                      ) : (
                        <div className="flex items-center gap-0.5">
                          <button
                            onClick={() => handleSubscribe(feed.id, false)}
                            disabled={subscribeMutation.isPending}
                            className={`px-3 py-2 text-sm font-medium rounded-l-lg disabled:opacity-50 ${
                              isOriginal
                                ? 'bg-blue-900/65 text-blue-100 border border-blue-300/45 hover:bg-blue-800/75'
                                : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                            }`}
                            title="Subscribe publicly"
                          >
                            Subscribe
                          </button>
                          <button
                            onClick={() => handleSubscribe(feed.id, true)}
                            disabled={subscribeMutation.isPending}
                            className={`px-2 py-2 text-sm font-medium rounded-r-lg disabled:opacity-50 ${
                              isOriginal
                                ? 'bg-blue-800/65 text-blue-100 border border-blue-300/45 hover:bg-blue-700/75'
                                : 'bg-gray-300 dark:bg-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-400 dark:hover:bg-gray-500'
                            }`}
                            title="Subscribe privately"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                            </svg>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                  {/* Actions: mobile row below title */}
                  <div className="flex sm:hidden items-center gap-1.5 mt-2 pl-[50px]">
                    {feed.is_subscribed ? (
                      <>
                        <button
                          onClick={() => handleTogglePrivacy(feed.id, (feed as any).is_private || false)}
                          disabled={subscribeMutation.isPending}
                          className={`p-1.5 rounded-lg transition-colors ${
                            (feed as any).is_private
                              ? 'bg-gray-700 text-white'
                              : isOriginal
                                ? 'bg-blue-800/50 text-blue-200 hover:bg-blue-700/60'
                                : 'bg-gray-100 dark:bg-gray-700 text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
                          }`}
                          title={(feed as any).is_private 
                            ? 'Private - tap to make public' 
                            : 'Public - tap to make private'}
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            {(feed as any).is_private ? (
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                            ) : (
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                            )}
                          </svg>
                        </button>
                        <button
                          onClick={() => handleUnsubscribe(feed.id)}
                          disabled={unsubscribeMutation.isPending}
                          className={`px-2.5 py-1 text-xs font-medium rounded-lg disabled:opacity-50 ${
                            isOriginal
                              ? 'bg-blue-500 text-white hover:bg-blue-400 border border-blue-300/55'
                              : 'bg-purple-600 text-white hover:bg-purple-700'
                          }`}
                          title="Tap to unsubscribe"
                        >
                          Subscribed
                        </button>
                      </>
                    ) : (
                      <div className="flex items-center gap-0.5">
                        <button
                          onClick={() => handleSubscribe(feed.id, false)}
                          disabled={subscribeMutation.isPending}
                          className={`px-2.5 py-1 text-xs font-medium rounded-l-lg disabled:opacity-50 ${
                            isOriginal
                              ? 'bg-blue-900/65 text-blue-100 border border-blue-300/45 hover:bg-blue-800/75'
                              : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                          }`}
                          title="Subscribe publicly"
                        >
                          Subscribe
                        </button>
                        <button
                          onClick={() => handleSubscribe(feed.id, true)}
                          disabled={subscribeMutation.isPending}
                          className={`px-1.5 py-1 text-xs font-medium rounded-r-lg disabled:opacity-50 ${
                            isOriginal
                              ? 'bg-blue-800/65 text-blue-100 border border-blue-300/45 hover:bg-blue-700/75'
                              : 'bg-gray-300 dark:bg-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-400 dark:hover:bg-gray-500'
                          }`}
                          title="Subscribe privately"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                          </svg>
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <p className="text-gray-500 dark:text-gray-400">No podcasts available</p>
              <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">Ask an admin to add some podcasts first</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
