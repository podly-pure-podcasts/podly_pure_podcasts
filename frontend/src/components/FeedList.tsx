import { useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { MusicIcon, RssIcon } from './icons';
import type { Feed } from '../types';
import { WHISPER_LANGUAGE_NAMES } from '../constants/whisperLanguages';
import type { FeedSortOption } from '../utils/feedListSort';
import { useCascade } from '../hooks/useCascade';
import { prefersFullMotion } from '../utils/gsap';
import { EASE } from '../utils/nativeMotion';

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
  onFeedSelected,
  selectedFeedId,
  sortBy,
}: FeedListProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const { requireAuth, user } = useAuth();
  const showMembership = Boolean(requireAuth && user?.role === 'admin');

  const feedsArray = useMemo(() => (Array.isArray(feeds) ? feeds : []), [feeds]);

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

  const listRef = useRef<HTMLDivElement>(null);
  useCascade(listRef, { ready: displayedFeeds.length > 0, pop: true, limit: 10 });

  // The picked card gives a small bounce, so the choice registers before the
  // detail panel catches up.
  const lastSelectedId = useRef(selectedFeedId);
  useEffect(() => {
    const previous = lastSelectedId.current;
    lastSelectedId.current = selectedFeedId;
    if (selectedFeedId == null || previous === selectedFeedId || !prefersFullMotion()) return;
    const card = listRef.current?.querySelector(`[data-feed-id="${selectedFeedId}"]`);
    // Native, because the click that triggers it also starts the route change.
    card?.animate([{ transform: 'scale(0.96)' }, { transform: 'scale(1)' }], { duration: 450, easing: EASE.pop });
  }, [selectedFeedId]);

  if (feedsArray.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-sky-50 to-sky-100 text-sky-700" aria-hidden="true">
          <RssIcon className="h-5 w-5" />
        </span>
        <h2 className="text-lg font-semibold text-gray-900">No podcasts yet</h2>
        <p className="text-sm text-gray-600">Add a feed to start removing ads from your shows.</p>
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
          className="input"
        />
      </div>
      <div ref={listRef} className="space-y-2 overflow-y-auto h-full pb-20">
        {displayedFeeds.length === 0 ? (
          <div className="flex h-full items-center justify-center rounded-lg border border-gray-200 px-4 py-8 text-center">
            <p className="text-sm text-gray-600">
              No podcasts match &quot;{searchTerm}&quot;
            </p>
          </div>
        ) : (
          displayedFeeds.map((feed) => (
            <button
              type="button"
              key={feed.id}
              data-feed-id={feed.id}
              aria-current={selectedFeedId === feed.id ? 'true' : undefined}
              onClick={() => onFeedSelected(feed)}
              className={`block w-full rounded-lg border p-4 text-left shadow-sm transition-[background-color,border-color,box-shadow] hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                selectedFeedId === feed.id
                  ? 'bg-surface border-blue-500 ring-1 ring-inset ring-blue-500'
                  : 'bg-surface border-gray-200 hover:bg-gray-50 hover:border-gray-300'
              }`}
            >
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0">
                  {feed.image_url ? (
                    <img
                      src={feed.image_url}
                      alt=""
                      loading="lazy"
                      className="w-12 h-12 rounded-md object-cover"
                    />
                  ) : (
                    <div className="w-12 h-12 rounded-md bg-gray-200 flex items-center justify-center">
                      <MusicIcon className="w-6 h-6 text-gray-400" />
                    </div>
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <h3 className="font-medium text-gray-900 line-clamp-2">{feed.title}</h3>
                  {feed.author && (
                    <p className="text-sm text-gray-600 mt-1">by {feed.author}</p>
                  )}
                  <div className="flex items-center gap-2 mt-2">
                    <span className="text-xs text-gray-600 tabular-nums">{feed.posts_count} episodes</span>
                    {feed.language && (
                      <span
                        lang={feed.language}
                        title={`Transcription language: ${WHISPER_LANGUAGE_NAMES[feed.language] ?? feed.language}`}
                        className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-gray-700"
                      >
                        {feed.language}
                      </span>
                    )}
                    <span className="flex-1" />
                    {showMembership && (!feed.is_member || feed.is_active_subscription === false) && (
                      <span
                        className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${
                          feed.is_member
                            ? 'bg-amber-100 text-amber-800'
                            : 'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {feed.is_member ? 'Paused' : 'Not joined'}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
} 
