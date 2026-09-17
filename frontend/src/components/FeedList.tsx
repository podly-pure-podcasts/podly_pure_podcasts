import { useMemo, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import type { Feed } from '../types';
import { WHISPER_LANGUAGE_NAMES } from '../constants/whisperLanguages';
import type { FeedSortOption } from '../utils/feedListSort';

function getLatestEpisodeTimestamp(feed: Feed): number | null {
  if (!feed.latest_episode_release_date) {
    return null;
  }

  const timestamp = new Date(feed.latest_episode_release_date).getTime();
  return Number.isNaN(timestamp) ? null : timestamp;
}

function compareFeedsByLatestEpisode(
  leftFeed: Feed,
  rightFeed: Feed,
  direction: 'asc' | 'desc'
): number {
  const leftTimestamp = getLatestEpisodeTimestamp(leftFeed);
  const rightTimestamp = getLatestEpisodeTimestamp(rightFeed);

  if (leftTimestamp === null && rightTimestamp === null) {
    return 0;
  }
  if (leftTimestamp === null) {
    return 1;
  }
  if (rightTimestamp === null) {
    return -1;
  }

  return direction === 'asc'
    ? leftTimestamp - rightTimestamp
    : rightTimestamp - leftTimestamp;
}

function compareFeedsByTitle(
  leftFeed: Feed,
  rightFeed: Feed,
  direction: 'asc' | 'desc'
): number {
  const comparison = leftFeed.title.localeCompare(rightFeed.title, undefined, {
    sensitivity: 'base',
    numeric: true,
  });
  return direction === 'asc' ? comparison : -comparison;
}

function compareFeedsByAddedOrder(
  leftFeed: Feed,
  rightFeed: Feed,
  direction: 'asc' | 'desc'
): number {
  // Tech debt: Feed does not expose a true created_at yet, so we use the
  // autoincrementing id as a proxy for "feed added" ordering for now.
  return direction === 'asc'
    ? leftFeed.id - rightFeed.id
    : rightFeed.id - leftFeed.id;
}

interface FeedListProps {
  feeds: Feed[];
  onFeedDeleted: () => void;
  onFeedSelected: (feed: Feed) => void;
  selectedFeedId?: number;
  sortBy: FeedSortOption;
}

export default function FeedList({
  feeds,
  onFeedDeleted: _onFeedDeleted,
  onFeedSelected,
  selectedFeedId,
  sortBy,
}: FeedListProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const { requireAuth, user } = useAuth();
  const showMembership = Boolean(requireAuth && user?.role === 'admin');

  // Ensure feeds is an array
  const feedsArray = Array.isArray(feeds) ? feeds : [];

  const displayedFeeds = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    return feedsArray
      .map((feed, index) => ({ feed, index }))
      .filter(({ feed }) => {
        if (!term) {
          return true;
        }

        const title = feed.title?.toLowerCase() ?? '';
        const author = feed.author?.toLowerCase() ?? '';
        return title.includes(term) || author.includes(term);
      })
      .sort((left, right) => {
        let primarySort = 0;

        switch (sortBy) {
          case 'title-asc':
            primarySort = compareFeedsByTitle(left.feed, right.feed, 'asc');
            break;
          case 'title-desc':
            primarySort = compareFeedsByTitle(left.feed, right.feed, 'desc');
            break;
          case 'feed-added-oldest':
            primarySort = compareFeedsByAddedOrder(
              left.feed,
              right.feed,
              'asc'
            );
            break;
          case 'feed-added-newest':
            primarySort = compareFeedsByAddedOrder(
              left.feed,
              right.feed,
              'desc'
            );
            break;
          case 'oldest':
            primarySort = compareFeedsByLatestEpisode(
              left.feed,
              right.feed,
              'asc'
            );
            break;
          default:
            primarySort = compareFeedsByLatestEpisode(
              left.feed,
              right.feed,
              'desc'
            );
            break;
        }

        if (primarySort !== 0) {
          return primarySort;
        }

        const titleSort = compareFeedsByTitle(left.feed, right.feed, 'asc');
        if (titleSort !== 0) {
          return titleSort;
        }

        return left.index - right.index;
      })
      .map(({ feed }) => feed);
  }, [feedsArray, searchTerm, sortBy]);

  if (feedsArray.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500 text-lg">No podcast feeds added yet.</p>
        <p className="text-gray-400 mt-2">Click "Add Feed" to get started.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="mb-3">
        <label htmlFor="feed-search" className="sr-only">
          Search feeds
        </label>
        <input
          id="feed-search"
          type="search"
          placeholder="Search feeds"
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
        />
      </div>
      <div className="space-y-2 overflow-y-auto h-full pb-20">
        {displayedFeeds.length === 0 ? (
          <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-gray-300 bg-gray-50 px-4 py-8 text-center">
            <p className="text-sm text-gray-500">
              No podcasts match &quot;{searchTerm}&quot;
            </p>
          </div>
        ) : (
          displayedFeeds.map((feed) => (
            <div 
              key={feed.id} 
              className={`bg-white rounded-lg shadow border cursor-pointer transition-all hover:shadow-md group dark:bg-slate-900/45 dark:border-slate-700/80 dark:hover:border-slate-500/70 dark:hover:bg-slate-900/70 ${
                selectedFeedId === feed.id ? 'ring-2 ring-blue-500 border-blue-200 dark:ring-1 dark:ring-blue-400/80 dark:border-blue-400/35 dark:bg-slate-900/80' : ''
              }`}
              onClick={() => onFeedSelected(feed)}
            >
              <div className="p-4">
                <div className="flex items-start gap-3">
                  {/* Podcast Image */}
                  <div className="flex-shrink-0">
                    {feed.image_url ? (
                      <img
                        src={feed.image_url}
                        alt={feed.title}
                        className="w-12 h-12 rounded-lg object-cover"
                      />
                    ) : (
                      <div className="w-12 h-12 rounded-lg bg-gray-200 flex items-center justify-center">
                        <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                        </svg>
                      </div>
                    )}
                  </div>

                  {/* Feed Info */}
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-gray-900 line-clamp-2">{feed.title}</h3>
                    {feed.author && (
                      <p className="text-sm text-gray-600 mt-1">by {feed.author}</p>
                    )}
                    <div className="flex items-center gap-2 mt-2">
                      <span className="text-xs text-gray-500">{feed.posts_count} episodes</span>
                      {feed.language && (
                        <span
                          lang={feed.language}
                          title={`Transcription language: ${WHISPER_LANGUAGE_NAMES[feed.language] ?? feed.language}`}
                          className="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase bg-gray-100 text-gray-700 border border-gray-200"
                        >
                          {feed.language}
                        </span>
                      )}
                      <span className="flex-1" />
                      {showMembership && (
                        <div className="flex items-center gap-2">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${
                              feed.is_member
                                ? 'bg-green-100 text-green-700 border border-green-200'
                                : 'bg-gray-100 text-gray-600 border border-gray-200'
                            }`}
                          >
                            {feed.is_member ? 'Joined' : 'Not joined'}
                          </span>
                          {feed.is_member && feed.is_active_subscription === false && (
                            <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-100 text-amber-700 border border-amber-200">
                              Paused
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
} 
