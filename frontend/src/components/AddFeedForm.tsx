import { useState, useEffect, useRef } from 'react';
import { feedsApi } from '../services/api';
import type { PodcastSearchResult } from '../types';
import { useAuth } from '../contexts/AuthContext';

// Debounce hook for live search
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
}

interface AddFeedFormProps {
  onSuccess: () => void;
  subscribedFeedUrls?: string[];
}

type AddMode = 'url' | 'search';

const PAGE_SIZE = 10;

export default function AddFeedForm({ onSuccess, subscribedFeedUrls = [] }: AddFeedFormProps) {
  const [url, setUrl] = useState('');
  const [activeMode, setActiveMode] = useState<AddMode>('search');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [addingFeedUrl, setAddingFeedUrl] = useState<string | null>(null);
  const [addingPrivately, setAddingPrivately] = useState(false);
  const { requireAuth } = useAuth();

  // Normalize URLs for comparison (remove trailing slashes, lowercase)
  const normalizeUrl = (url: string) => url.toLowerCase().replace(/\/+$/, '');
  const subscribedUrlsSet = new Set(subscribedFeedUrls.map(normalizeUrl));
  const isSubscribed = (feedUrl: string) => subscribedUrlsSet.has(normalizeUrl(feedUrl));

  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState<PodcastSearchResult[]>([]);
  const [searchError, setSearchError] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [searchPage, setSearchPage] = useState(1);
  const [totalResults, setTotalResults] = useState(0);
  const [previewPodcast, setPreviewPodcast] = useState<PodcastSearchResult | null>(null);
  
  const searchInputRef = useRef<HTMLInputElement>(null);
  const debouncedSearchTerm = useDebounce(searchTerm, 400);

  const resetSearchState = () => {
    setSearchResults([]);
    setSearchError('');
    setSearchPage(1);
    setTotalResults(0);
  };

  // Auto-focus search input when in search mode
  useEffect(() => {
    if (activeMode === 'search' && searchInputRef.current) {
      // Longer delay for iOS to ensure modal is fully rendered
      // iOS Safari needs the element to be visible before focus works
      setTimeout(() => {
        if (searchInputRef.current) {
          searchInputRef.current.focus();
          // iOS workaround: scroll into view to help trigger keyboard
          searchInputRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }, 300);
    }
  }, [activeMode]);

  // Live search as user types (debounced)
  useEffect(() => {
    if (debouncedSearchTerm.trim().length >= 2) {
      performSearch();
    } else if (debouncedSearchTerm.trim().length === 0) {
      resetSearchState();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearchTerm]);

  const handleSubmitManual = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    setError('');
    await addFeed(url.trim(), 'url');
  };

  const addFeed = async (feedUrl: string, source: AddMode, isPrivate: boolean = false) => {
    setIsSubmitting(true);
    setAddingFeedUrl(source === 'url' ? 'manual' : feedUrl);
    setAddingPrivately(isPrivate);
    setError('');

    try {
      // Add the feed first
      const result = await feedsApi.addFeed(feedUrl);
      
      // If auth is enabled and user wants private subscription, update it
      if (requireAuth && isPrivate && result.feed_id) {
        await feedsApi.subscribeFeed(result.feed_id, true);
      }
      
      if (source === 'url') {
        setUrl('');
      }
      onSuccess();
    } catch (err) {
      console.error('Failed to add feed:', err);
      setError('Failed to add feed. Please check the URL and try again.');
    } finally {
      setIsSubmitting(false);
      setAddingFeedUrl(null);
      setAddingPrivately(false);
    }
  };

  const performSearch = async () => {
    if (!searchTerm.trim()) {
      setSearchError('Enter a search term to find podcasts.');
      return;
    }

    setIsSearching(true);
    setSearchError('');

    try {
      const response = await feedsApi.searchFeeds(searchTerm.trim());
      setSearchResults(response.results);
      setTotalResults(response.total ?? response.results.length);
      setSearchPage(1);
    } catch (err) {
      console.error('Podcast search failed:', err);
      setSearchError('Failed to search podcasts. Please try again.');
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };


  const handleAddFromSearch = async (result: PodcastSearchResult, isPrivate: boolean = false) => {
    await addFeed(result.feedUrl, 'search', isPrivate);
  };

  const totalPages =
    totalResults === 0 ? 1 : Math.max(1, Math.ceil(totalResults / PAGE_SIZE));
  const startIndex =
    totalResults === 0 ? 0 : (searchPage - 1) * PAGE_SIZE + 1;
  const endIndex =
    totalResults === 0
      ? 0
      : Math.min(searchPage * PAGE_SIZE, totalResults);
  const displayedResults = searchResults.slice(
    (searchPage - 1) * PAGE_SIZE,
    (searchPage - 1) * PAGE_SIZE + PAGE_SIZE
  );

  return (
    <div className="flex flex-col h-full">
      <div className="flex gap-2 mb-3">
        <button
          type="button"
          onClick={() => {
            setActiveMode('search');
            setError('');
            resetSearchState();
          }}
          className={`flex-1 px-2 py-1.5 text-sm rounded-md border ${
            activeMode === 'search'
              ? 'bg-blue-50 border-blue-500 text-blue-700'
              : 'border-gray-200 text-gray-600 hover:bg-gray-100'
          }`}
        >
          Search
        </button>
        <button
          type="button"
          onClick={() => {
            setActiveMode('url');
          }}
          className={`flex-1 px-2 py-1.5 text-sm rounded-md border transition-colors ${
            activeMode === 'url'
              ? 'bg-blue-50 border-blue-500 text-blue-700'
              : 'border-gray-200 text-gray-600 hover:bg-gray-100'
          }`}
        >
          RSS URL
        </button>
      </div>

      {activeMode === 'url' && (
        <form onSubmit={handleSubmitManual} className="space-y-4">
          <div>
            <label htmlFor="feed-url" className="block text-sm font-medium text-gray-700 mb-1">
              RSS Feed URL
            </label>
            <input
              type="url"
              id="feed-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/podcast/feed.xml"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              required
            />
          </div>

          {error && (
            <div className="text-red-600 text-sm">{error}</div>
          )}

          <div className="flex flex-col sm:flex-row sm:justify-end gap-3">
            <button
              type="submit"
              disabled={isSubmitting || !url.trim()}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white px-4 py-2 rounded-md font-medium transition-colors sm:w-auto w-full"
            >
              {isSubmitting && addingFeedUrl === 'manual' ? 'Adding...' : 'Add Feed'}
            </button>
          </div>
        </form>
      )}

      {activeMode === 'search' && (
        <div className="flex flex-col flex-1 min-h-0 gap-3">
          <div className="flex gap-2">
            <input
              ref={searchInputRef}
              type="text"
              id="search-term"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search podcasts..."
              className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              autoComplete="off"
            />
            {isSearching && (
              <div className="flex items-center px-2">
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600" />
              </div>
            )}
          </div>

          {searchError && (
            <div className="text-red-600 text-sm">{searchError}</div>
          )}

          {isSearching && searchResults.length === 0 && (
            <div className="text-sm text-gray-600">Searching for podcasts...</div>
          )}

          {!isSearching && searchResults.length === 0 && totalResults === 0 && searchTerm && !searchError && (
            <div className="text-sm text-gray-600">No podcasts found. Try a different search term.</div>
          )}

          {searchResults.length > 0 && (
            <div className="flex flex-col flex-1 min-h-0">
              <div className="flex justify-between items-center text-sm text-gray-500">
                <span>
                  Showing {startIndex}-{endIndex} of {totalResults} results
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      setSearchPage((prev) => Math.max(prev - 1, 1))
                    }
                    disabled={isSearching || searchPage <= 1}
                    className="px-3 py-1 border border-gray-200 rounded-md disabled:text-gray-400 disabled:border-gray-200 hover:bg-gray-100 transition-colors"
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setSearchPage((prev) => Math.min(prev + 1, totalPages))
                    }
                    disabled={isSearching || searchPage >= totalPages}
                    className="px-3 py-1 border border-gray-200 rounded-md disabled:text-gray-400 disabled:border-gray-200 hover:bg-gray-100 transition-colors"
                  >
                    Next
                  </button>
                </div>
              </div>

              <ul className="space-y-3 flex-1 overflow-y-auto pr-2">
                {displayedResults.map((result) => (
                  <li
                    key={result.feedUrl}
                    className="p-3 border border-gray-200 rounded-md bg-gray-50"
                  >
                    <button
                      type="button"
                      onClick={() => setPreviewPodcast(result)}
                      className="flex gap-3 w-full text-left hover:opacity-80 transition-opacity"
                    >
                      {result.artworkUrl ? (
                        <img
                          src={result.artworkUrl}
                          alt={result.title}
                          className="w-14 h-14 sm:w-16 sm:h-16 rounded-md object-cover flex-shrink-0"
                        />
                      ) : (
                        <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-md bg-gray-200 flex items-center justify-center text-gray-500 text-xs flex-shrink-0">
                          No Image
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        <h4 className="font-medium text-gray-900 line-clamp-2">{result.title}</h4>
                        {result.author && (
                          <p className="text-sm text-gray-600 truncate">{result.author}</p>
                        )}
                        {result.genres.length > 0 && (
                          <p className="text-xs text-gray-500 truncate">
                            {result.genres.join(' · ')}
                          </p>
                        )}
                      </div>
                    </button>
                    <div className="flex items-center justify-between gap-2 mt-2 pt-2 border-t border-gray-200">
                      <p className="text-xs text-gray-400 truncate flex-1 min-w-0">{result.feedUrl}</p>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        {isSubscribed(result.feedUrl) ? (
                          <span className="inline-flex items-center gap-1 px-2 py-1.5 bg-green-100 text-green-700 rounded-md text-xs font-medium">
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                            Subscribed
                          </span>
                        ) : requireAuth ? (
                          <>
                            <button
                              type="button"
                              onClick={() => handleAddFromSearch(result, false)}
                              disabled={isSubmitting && addingFeedUrl === result.feedUrl}
                              className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white px-2.5 py-1.5 rounded-l-md text-xs font-medium transition-colors"
                              title="Subscribe publicly - other users will see this feed in Browse Podcasts"
                            >
                              {isSubmitting && addingFeedUrl === result.feedUrl && !addingPrivately ? '...' : 'Subscribe'}
                            </button>
                            <button
                              type="button"
                              onClick={() => handleAddFromSearch(result, true)}
                              disabled={isSubmitting && addingFeedUrl === result.feedUrl}
                              className="bg-gray-500 hover:bg-gray-600 disabled:bg-gray-400 text-white px-1.5 py-1.5 rounded-r-md text-xs transition-colors"
                              title="Subscribe privately - this feed won't appear in Browse Podcasts for other users"
                            >
                              {isSubmitting && addingFeedUrl === result.feedUrl && addingPrivately ? (
                                <span>...</span>
                              ) : (
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                                </svg>
                              )}
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            onClick={() => handleAddFromSearch(result)}
                            disabled={isSubmitting && addingFeedUrl === result.feedUrl}
                            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors"
                          >
                            {isSubmitting && addingFeedUrl === result.feedUrl ? '...' : 'Add'}
                          </button>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Podcast Preview Modal */}
      {previewPodcast && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50"
          onClick={() => setPreviewPodcast(null)}
        >
          <div
            className="bg-white dark:bg-slate-900 rounded-xl shadow-2xl max-w-lg w-full max-h-[80vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-start gap-4 p-4 border-b border-gray-200 dark:border-purple-700/50">
              {previewPodcast.artworkUrl ? (
                <img
                  src={previewPodcast.artworkUrl}
                  alt={previewPodcast.title}
                  className="w-20 h-20 rounded-lg object-cover flex-shrink-0"
                />
              ) : (
                <div className="w-20 h-20 rounded-lg bg-gray-200 dark:bg-purple-800 flex items-center justify-center text-gray-500 dark:text-purple-400 text-xs flex-shrink-0">
                  No Image
                </div>
              )}
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-gray-900 dark:text-purple-100 text-lg leading-tight">
                  {previewPodcast.title}
                </h3>
                {previewPodcast.author && (
                  <p className="text-sm text-gray-600 dark:text-purple-300 mt-1">{previewPodcast.author}</p>
                )}
                {previewPodcast.genres.length > 0 && (
                  <p className="text-xs text-gray-500 dark:text-purple-400 mt-1">
                    {previewPodcast.genres.join(' · ')}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => setPreviewPodcast(null)}
                className="p-1 text-gray-400 hover:text-gray-600 dark:text-purple-400 dark:hover:text-purple-200"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Description */}
            <div className="flex-1 overflow-y-auto p-4">
              {previewPodcast.description ? (
                <p className="text-sm text-gray-700 dark:text-purple-200 whitespace-pre-line">
                  {previewPodcast.description}
                </p>
              ) : (
                <p className="text-sm text-gray-500 dark:text-purple-400 italic">No description available.</p>
              )}
            </div>

            {/* Footer with actions */}
            <div className="p-4 border-t border-gray-200 dark:border-purple-700/50 flex items-center justify-between gap-3">
              <p className="text-xs text-gray-400 dark:text-purple-500 truncate flex-1 min-w-0">
                {previewPodcast.feedUrl}
              </p>
              {isSubscribed(previewPodcast.feedUrl) ? (
                <span className="inline-flex items-center gap-1 px-3 py-2 bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400 rounded-lg text-sm font-medium">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Subscribed
                </span>
              ) : requireAuth ? (
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => {
                      handleAddFromSearch(previewPodcast, false);
                      setPreviewPodcast(null);
                    }}
                    disabled={isSubmitting}
                    className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white px-4 py-2 rounded-l-lg text-sm font-medium transition-colors"
                  >
                    {isSubmitting ? 'Adding...' : 'Subscribe'}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      handleAddFromSearch(previewPodcast, true);
                      setPreviewPodcast(null);
                    }}
                    disabled={isSubmitting}
                    className="bg-gray-500 hover:bg-gray-600 disabled:bg-gray-400 text-white px-2 py-2 rounded-r-lg text-sm transition-colors"
                    title="Subscribe privately"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                    </svg>
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    handleAddFromSearch(previewPodcast);
                    setPreviewPodcast(null);
                  }}
                  disabled={isSubmitting}
                  className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                >
                  {isSubmitting ? 'Adding...' : 'Add Podcast'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
