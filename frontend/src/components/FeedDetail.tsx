import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { toast } from 'react-hot-toast';
import type { Feed, Episode, PagedResult, ConfigResponse } from '../types';
import { feedsApi, configApi } from '../services/api';
import EpisodeRow, { EpisodeRowSkeleton, type EpisodeDescriptionView } from './EpisodeRow';
import FadeImage from './FadeImage';
import FeedSettingsModal from './FeedSettingsModal';
import FeedSubscribersModal from './FeedSubscribersModal';
import ModalShell from './ModalShell';
import { useAuth } from '../contexts/AuthContext';
import { copyToClipboard } from '../utils/clipboard';
import { emitDiagnosticError } from '../utils/diagnostics';
import { getHttpErrorInfo } from '../utils/httpError';
import { useDelayedFlag } from '../hooks/useDelayedFlag';
import { gsap, prefersFullMotion, SETTLE_EASE, useGSAP } from '../utils/gsap';
import { EASE } from '../utils/nativeMotion';
import {
  BlockedIcon,
  CheckIcon,
  CloseIcon,
  DotsVerticalIcon,
  GearIcon,
  InfoIcon,
  LogoutIcon,
  MusicIcon,
  PlusIcon,
  RefreshIcon,
  TrashIcon,
  WarningIcon,
} from './icons';

interface FeedDetailProps {
  feed: Feed;
  onClose?: () => void;
  onFeedDeleted?: () => void;
  /** The phone panel is sliding in, which already serves as the first entrance. */
  slidesIn?: boolean;
  /** Hold the episode rows back while the phone panel slides, so their render doesn't land mid-animation. */
  holdContent?: boolean;
}

type SortOption = 'newest' | 'oldest' | 'title';

const EPISODE_DESCRIPTION_VIEW_STORAGE_KEY_PREFIX = 'podly:episode-description-view:feed:';

function getEpisodeDescriptionViewStorageKey(feedId: number): string {
  return `${EPISODE_DESCRIPTION_VIEW_STORAGE_KEY_PREFIX}${feedId}`;
}

function loadEpisodeDescriptionView(feedId: number): EpisodeDescriptionView {
  if (typeof window === 'undefined') {
    return 'source';
  }
  const rawValue = window.localStorage.getItem(
    getEpisodeDescriptionViewStorageKey(feedId)
  );
  return rawValue === 'podly' ? 'podly' : 'source';
}

function persistEpisodeDescriptionView(
  feedId: number,
  view: EpisodeDescriptionView
): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(
    getEpisodeDescriptionViewStorageKey(feedId),
    view
  );
}

interface ProcessingEstimate {
  post_guid: string;
  estimated_minutes: number;
  can_process: boolean;
  reason: string | null;
}

const EPISODES_PAGE_SIZE = 25;

const htmlToPlainText = (html: string) => new DOMParser().parseFromString(html, 'text/html').body.textContent?.trim() ?? '';

export default function FeedDetail({ feed, onClose, onFeedDeleted, slidesIn = false, holdContent = false }: FeedDetailProps) {
  const { requireAuth, isAuthenticated, user } = useAuth();
  const [sortBy, setSortBy] = useState<SortOption>('newest');
  const [showStickyHeader, setShowStickyHeader] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const queryClient = useQueryClient();
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const feedHeaderRef = useRef<HTMLDivElement>(null);
  const [currentFeed, setCurrentFeed] = useState(feed);
  const [expandedDescriptions, setExpandedDescriptions] = useState<Set<string>>(new Set());
  const [pendingEpisode, setPendingEpisode] = useState<Episode | null>(null);
  const [showProcessingModal, setShowProcessingModal] = useState(false);
  const [processingEstimate, setProcessingEstimate] = useState<ProcessingEstimate | null>(null);
  const [isEstimating, setIsEstimating] = useState(false);
  const [estimateError, setEstimateError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [isFeedTransitionActive, setIsFeedTransitionActive] = useState(false);
  // The old feed fades out at once, but the skeleton only appears for a slow
  // load, so a fast switch goes straight to the new feed's entrance.
  const showFeedSkeleton = useDelayedFlag(isFeedTransitionActive, 250);
  const [episodeDescriptionView, setEpisodeDescriptionView] =
    useState<EpisodeDescriptionView>(() => loadEpisodeDescriptionView(feed.id));
  const handleEpisodeDescriptionViewChange = (view: EpisodeDescriptionView) => {
    setEpisodeDescriptionView(view);
    persistEpisodeDescriptionView(currentFeed.id, view);
  };
  const [showSubscribersModal, setShowSubscribersModal] = useState(false);

  const isAdmin = !requireAuth || user?.role === 'admin';
  const whitelistedOnly = requireAuth && !isAdmin;


  const { data: configResponse } = useQuery<ConfigResponse>({
    queryKey: ['config'],
    queryFn: configApi.getConfig,
    enabled: isAdmin,
  });

  const {
    data: episodesPage,
    isLoading,
    isFetching,
    error,
  } = useQuery<PagedResult<Episode>, Error, PagedResult<Episode>, [string, number, number, boolean]>({
    queryKey: ['episodes', currentFeed.id, page, whitelistedOnly],
    queryFn: () =>
      feedsApi.getFeedPosts(currentFeed.id, {
        page,
        pageSize: EPISODES_PAGE_SIZE,
        whitelistedOnly,
      }),
    placeholderData: (previousData, previousQuery) => {
      const previousFeedId =
        Array.isArray(previousQuery?.queryKey) &&
        typeof previousQuery.queryKey[1] === 'number'
          ? previousQuery.queryKey[1]
          : null;
      return previousFeedId === currentFeed.id ? previousData : undefined;
    },
  });
  const showSkeleton = useDelayedFlag(isLoading);
  const skeletonVisible = holdContent || (isLoading && showSkeleton);
  // When rows replace a visible skeleton, the skeleton stays mounted over them
  // just long enough to fade out; the rows rise in only once it is gone, so the
  // two never show at the same time.
  const [dissolveFor, setDissolveFor] = useState<number | null>(null);
  useEffect(() => {
    if (skeletonVisible) setDissolveFor(currentFeed.id);
  }, [skeletonVisible, currentFeed.id]);
  const showDissolveOverlay = !skeletonVisible && dissolveFor === currentFeed.id;
  useEffect(() => {
    if (!showDissolveOverlay) return;
    // Fallback so the overlay can never outlive a dissolve that didn't run.
    const timeout = window.setTimeout(() => setDissolveFor(null), 1500);
    return () => window.clearTimeout(timeout);
  }, [showDissolveOverlay]);

  const whitelistMutation = useMutation({
    mutationFn: ({ guid, whitelisted, triggerProcessing }: { guid: string; whitelisted: boolean; triggerProcessing?: boolean }) =>
      feedsApi.togglePostWhitelist(guid, whitelisted, triggerProcessing),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['episodes', currentFeed.id] });
    },
    onError: (err) => {
      const { status, data, message } = getHttpErrorInfo(err);
      emitDiagnosticError({
        title: 'Failed to update whitelist status',
        message,
        kind: status ? 'http' : 'network',
        details: {
          status,
          response: data,
        },
      });
    },
  });

  const bulkWhitelistMutation = useMutation({
    mutationFn: () => feedsApi.toggleAllPostsWhitelist(currentFeed.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['episodes', currentFeed.id] });
    },
  });

  const refreshFeedMutation = useMutation({
    mutationFn: () => feedsApi.refreshFeed(currentFeed.id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
      queryClient.invalidateQueries({ queryKey: ['episodes', currentFeed.id] });
      toast.success(data?.message ?? 'Feed refreshed');
    },
    onError: (err) => {
      console.error('Failed to refresh feed', err);
      const { status, data, message } = getHttpErrorInfo(err);
      emitDiagnosticError({
        title: 'Failed to refresh feed',
        message,
        kind: status ? 'http' : 'network',
        details: {
          status,
          response: data,
          feedId: currentFeed.id,
        },
      });
    },
  });

  const deleteFeedMutation = useMutation({
    mutationFn: () => feedsApi.deleteFeed(currentFeed.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
      if (onFeedDeleted) {
        onFeedDeleted();
      }
    },
    onError: (err) => {
      console.error('Failed to delete feed', err);
      const { status, data, message } = getHttpErrorInfo(err);
      emitDiagnosticError({
        title: 'Failed to delete feed',
        message,
        kind: status ? 'http' : 'network',
        details: {
          status,
          response: data,
          feedId: currentFeed.id,
        },
      });
    },
  });

  const joinFeedMutation = useMutation({
    mutationFn: () => feedsApi.joinFeed(currentFeed.id),
    onSuccess: (data) => {
      toast.success('Joined feed');
      setCurrentFeed(data);
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
    },
    onError: (err) => {
      console.error('Failed to join feed', err);
      const { status, data, message } = getHttpErrorInfo(err);
      emitDiagnosticError({
        title: 'Failed to join feed',
        message,
        kind: status ? 'http' : 'network',
        details: {
          status,
          response: data,
          feedId: currentFeed.id,
        },
      });
    },
  });

  const leaveFeedMutation = useMutation({
    mutationFn: () => feedsApi.leaveFeed(currentFeed.id),
    onSuccess: () => {
      toast.success('Removed from your feeds');
      setCurrentFeed((prev) => (prev ? { ...prev, is_member: false, is_active_subscription: false } : prev));
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
      if (onFeedDeleted && !isAdmin) {
        onFeedDeleted();
      }
    },
    onError: (err) => {
      console.error('Failed to leave feed', err);
      const { status, data, message } = getHttpErrorInfo(err);
      emitDiagnosticError({
        title: 'Failed to remove feed',
        message,
        kind: status ? 'http' : 'network',
        details: {
          status,
          response: data,
          feedId: currentFeed.id,
        },
      });
    },
  });

  // Switching feeds: the old feed exits first, and only then does the panel
  // swap to the new one, so new content is never seen before its entrance.
  // Episodes are prefetched at the click so the exit overlaps the request.
  const contentRef = useRef<HTMLDivElement>(null);
  const latestFeedRef = useRef(feed);
  latestFeedRef.current = feed;
  const exitingRef = useRef(false);
  // Holds the content hidden from the exit until the entrance reveals it.
  const exitAnimRef = useRef<Animation | null>(null);
  const { contextSafe } = useGSAP();
  const swapToLatestFeed = contextSafe(() => {
    exitingRef.current = false;
    setCurrentFeed(latestFeedRef.current);
  });

  useEffect(() => {
    if (feed.id === currentFeed.id) {
      setCurrentFeed(feed);
      return;
    }
    void queryClient.prefetchQuery({
      queryKey: ['episodes', feed.id, 1, whitelistedOnly],
      queryFn: () =>
        feedsApi.getFeedPosts(feed.id, { page: 1, pageSize: EPISODES_PAGE_SIZE, whitelistedOnly }),
    });
    setIsFeedTransitionActive(true);
    if (exitingRef.current) return;
    const content = contentRef.current;
    const alreadyHidden = exitAnimRef.current !== null;
    if (!content || alreadyHidden || !prefersFullMotion()) {
      if (content && !alreadyHidden) {
        exitAnimRef.current = content.animate([{ opacity: 0 }, { opacity: 0 }], { duration: 0, fill: 'forwards' });
      }
      swapToLatestFeed();
      return;
    }
    exitingRef.current = true;
    // Native, because it runs while the click's route change renders.
    const exit = content.animate(
      [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(10px)' }],
      { duration: 140, easing: EASE.in, fill: 'forwards' }
    );
    exitAnimRef.current = exit;
    exit.finished.then(swapToLatestFeed, () => {});
  }, [feed, currentFeed.id, queryClient, whitelistedOnly, swapToLatestFeed]);

  useEffect(() => {
    if (!isFeedTransitionActive || feed.id !== currentFeed.id) {
      return;
    }

    if (isLoading) {
      return;
    }

    setIsFeedTransitionActive(false);
  }, [isFeedTransitionActive, isLoading, feed.id, currentFeed.id]);

  useEffect(() => {
    setEpisodeDescriptionView(loadEpisodeDescriptionView(currentFeed.id));
  }, [currentFeed.id]);

  useEffect(() => {
    setExpandedDescriptions(new Set());
  }, [currentFeed.id, episodeDescriptionView]);

  useEffect(() => {
    setPage(1);
  }, [currentFeed.id, whitelistedOnly]);

  useEffect(() => {
    scrollContainerRef.current?.scrollTo({ top: 0 });
  }, [currentFeed.id]);

  // Show/hide sticky header
  useEffect(() => {
    const scrollContainer = scrollContainerRef.current;
    const feedHeader = feedHeaderRef.current;

    if (!scrollContainer || !feedHeader) return;

    // Show the sticky header once the feed header is within 100px of leaving the container.
    const observer = new IntersectionObserver(
      ([entry]) => setShowStickyHeader(!entry.isIntersecting),
      { root: scrollContainer, rootMargin: '-100px 0px 0px 0px' }
    );
    observer.observe(feedHeader);
    return () => observer.disconnect();
  }, []);

  // Handle click outside to close menu
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (showMenu && !(event.target as Element).closest('.menu-container')) {
        setShowMenu(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showMenu]);

  const handleToggleExpanded = useCallback((guid: string) => {
    setExpandedDescriptions((prev) => {
      const next = new Set(prev);
      if (next.has(guid)) {
        next.delete(guid);
      } else {
        next.add(guid);
      }
      return next;
    });
  }, []);

  const { mutate: mutateWhitelist } = whitelistMutation;
  const handleWhitelistToggle = useCallback((episode: Episode) => {
    if (!episode.whitelisted) {
      setPendingEpisode(episode);
      setShowProcessingModal(true);
      setProcessingEstimate(null);
      setEstimateError(null);
      setIsEstimating(true);
      feedsApi
        .getProcessingEstimate(episode.guid)
        .then((estimate) => {
          setProcessingEstimate(estimate);
        })
        .catch((err) => {
          console.error('Failed to load processing estimate', err);
          const { status, data, message } = getHttpErrorInfo(err);
          emitDiagnosticError({
            title: 'Failed to load processing estimate',
            message,
            kind: status ? 'http' : 'network',
            details: {
              status,
              response: data,
              postGuid: episode.guid,
            },
          });
          setEstimateError(message ?? 'Unable to estimate processing time');
        })
        .finally(() => setIsEstimating(false));
      return;
    }

    mutateWhitelist({
      guid: episode.guid,
      whitelisted: false,
    });
  }, [mutateWhitelist]);

  const handleConfirmProcessing = () => {
    if (!pendingEpisode) return;
    whitelistMutation.mutate(
      {
        guid: pendingEpisode.guid,
        whitelisted: true,
        triggerProcessing: true,
      },
      {
        onSuccess: () => {
          setShowProcessingModal(false);
          setPendingEpisode(null);
          setProcessingEstimate(null);
        },
      }
    );
  };

  const handleCancelProcessing = () => {
    setShowProcessingModal(false);
    setPendingEpisode(null);
    setProcessingEstimate(null);
    setEstimateError(null);
  };

  const isMember = Boolean(currentFeed.is_member);
  const isActiveSubscription = currentFeed.is_active_subscription !== false;

  // Admins can manage everything; regular users are read-only.
  const canDeleteFeed = isAdmin; // only admins can delete feeds
  const canModifyEpisodes = !requireAuth ? true : Boolean(isAdmin);
  const canBulkModifyEpisodes = !requireAuth ? true : Boolean(isAdmin);
  const canSubscribe = !requireAuth || isMember;
  const showPodlyRssButton = !(requireAuth && isAdmin && !isMember);
  const showWhitelistUi = canModifyEpisodes && isAdmin;
  const appAutoWhitelistDefault =
    configResponse?.config?.app?.automatically_whitelist_new_episodes;

  const episodes = useMemo(() => episodesPage?.items ?? [], [episodesPage?.items]);
  // Before the first page lands, the list's count stands in so the header
  // doesn't jump from 0. Non-admins see only enabled episodes, so they wait.
  const totalCount = episodesPage?.total ?? (whitelistedOnly ? 0 : currentFeed.posts_count ?? 0);
  const whitelistedCount =
    episodesPage?.whitelisted_total ?? episodes.filter((ep: Episode) => ep.whitelisted).length;
  const totalPages = Math.max(
    1,
    episodesPage?.total_pages ?? Math.ceil(totalCount / EPISODES_PAGE_SIZE)
  );
  const hasEpisodes = totalCount > 0;
  const visibleStart = hasEpisodes ? (page - 1) * EPISODES_PAGE_SIZE + 1 : 0;
  const visibleEnd = hasEpisodes ? Math.min(totalCount, page * EPISODES_PAGE_SIZE) : 0;

  useEffect(() => {
    if (page > totalPages && totalPages > 0) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  const handleBulkWhitelistToggle = () => {
    if (requireAuth && !isAdmin) {
      toast.error('Only admins can bulk toggle whitelist status.');
      return;
    }
    bulkWhitelistMutation.mutate();
  };

  const handleDeleteFeed = () => {
    if (confirm(`Are you sure you want to delete "${currentFeed.title}"? This action cannot be undone.`)) {
      deleteFeedMutation.mutate();
    }
  };

  const sortedEpisodes = useMemo(() => {
    const list = [...episodes];
    return list.sort((a, b) => {
      switch (sortBy) {
        case 'newest':
          return new Date(b.release_date || 0).getTime() - new Date(a.release_date || 0).getTime();
        case 'oldest':
          return new Date(a.release_date || 0).getTime() - new Date(b.release_date || 0).getTime();
        case 'title':
          return a.title.localeCompare(b.title);
        default:
          return 0;
      }
    });
  }, [episodes, sortBy]);

  // Calculate whitelist status for bulk button
  const allWhitelisted = totalCount > 0 && whitelistedCount === totalCount;

  const handleCopyRssToClipboard = async () => {
    if (requireAuth && !isAuthenticated) {
      toast.error('Please sign in to copy a protected RSS URL.');
      return;
    }

    try {
      let rssUrl: string;
      if (requireAuth) {
        const response = await feedsApi.createProtectedFeedShareLink(currentFeed.id);
        rssUrl = response.url;
      } else {
        rssUrl = new URL(`/feed/${currentFeed.id}`, window.location.origin).toString();
      }

      await copyToClipboard(rssUrl, 'Copy the Feed RSS URL:', 'Feed URL copied to clipboard!');
    } catch (err) {
      console.error('Failed to copy feed URL', err);
      toast.error('Failed to copy feed URL');
    }
  };

  const handleCopyOriginalRssToClipboard = async () => {
    try {
      const rssUrl = currentFeed.rss_url || '';
      if (!rssUrl) throw new Error('No RSS URL');

      await copyToClipboard(rssUrl, 'Copy the Original RSS URL:', 'Original RSS URL copied to clipboard');
    } catch (err) {
      console.error('Failed to copy original RSS URL', err);
      toast.error('Failed to copy original RSS URL');
    }
  };

  // Entrance once a feed's content is actually on screen: the header when the
  // switch skeleton lifts (or on first open, unless the phone panel is sliding
  // in), and the first rows when its episodes arrive.
  const openedBySlide = useRef(slidesIn).current;
  const revealRootRef = useRef<HTMLDivElement>(null);
  const headerRevealedFor = useRef<number | null>(null);
  const rowsRevealedFor = useRef<number | null>(null);
  const isFirstReveal = headerRevealedFor.current === null;
  const headerReady = !isFeedTransitionActive;
  const rowsReady = headerReady && !holdContent && !isLoading && sortedEpisodes.length > 0;
  const { contextSafe: revealSafe } = useGSAP({ scope: revealRootRef });
  const endDissolve = revealSafe(() => setDissolveFor(null));
  useGSAP(
    () => {
      // The switch exit leaves the wrapper hidden; show it before any entrance.
      if (headerReady) {
        exitAnimRef.current?.cancel();
        exitAnimRef.current = null;
      }
      if (!prefersFullMotion()) {
        if (rowsReady) endDissolve();
        return;
      }
      let headerAnimating = false;
      if (headerReady && headerRevealedFor.current !== currentFeed.id) {
        headerRevealedFor.current = currentFeed.id;
        if (!isFirstReveal || !openedBySlide) {
          headerAnimating = true;
          gsap
            .timeline()
            .from('[data-reveal="art"]', {
              autoAlpha: 0, scale: 0.9, rotate: -3, duration: 0.5, ease: 'back.out(1.6)', clearProps: 'transform',
            })
            .from('[data-reveal="text"]', {
              autoAlpha: 0, y: 14, filter: 'blur(6px)', duration: 0.4, ease: SETTLE_EASE, stagger: 0.06,
              clearProps: 'transform,filter',
            }, 0.08);
        }
      }
      if (rowsReady && rowsRevealedFor.current !== currentFeed.id) {
        rowsRevealedFor.current = currentFeed.id;
        const rows = gsap.utils.toArray<HTMLElement>('[data-reveal-row]').slice(0, 8);
        const placeholders = gsap.utils.toArray<HTMLElement>('[data-dissolve-overlay] > *');
        if (placeholders.length) {
          gsap.set(rows, { autoAlpha: 0 });
          gsap
            .timeline()
            .to(placeholders, { autoAlpha: 0, duration: 0.15, ease: 'power1.in' })
            .call(endDissolve)
            .fromTo(rows, { autoAlpha: 0, y: 18 }, {
              autoAlpha: 1, y: 0, duration: 0.45, ease: SETTLE_EASE, stagger: 0.045, clearProps: 'transform',
            });
          return;
        }
        gsap.from(rows, {
          // Rows follow a header that is animating in this same pass; otherwise
          // (after the phone slide, or a late data arrival) they start at once.
          autoAlpha: 0, y: 18, duration: 0.45, ease: SETTLE_EASE, stagger: 0.045,
          delay: headerAnimating ? 0.3 : 0.05,
          clearProps: 'transform',
        });
      }
    },
    { scope: revealRootRef, dependencies: [currentFeed.id, headerReady, rowsReady] }
  );

  const transitionSkeletonClass =
    'rounded-full bg-gray-200';
  const transitionSkeletonSoftClass =
    'rounded-full bg-gray-100';

  return (
    <div
      ref={revealRootRef}
      className="h-full flex flex-col bg-surface relative"
      aria-busy={isFeedTransitionActive}
    >
      <div
        ref={contentRef}
        className={`flex h-full flex-col ${isFeedTransitionActive ? 'pointer-events-none' : ''}`}
      >
        {/* Mobile Header */}
        <div className="flex items-center justify-between p-4 border-b lg:hidden">
          <h2 className="text-lg font-semibold text-gray-900">Podcast details</h2>
          {onClose && (
            <button
              onClick={onClose}
              aria-label="Close"
              className="btn btn-ghost btn-icon"
            >
              <CloseIcon className="h-5 w-5" />
            </button>
          )}
        </div>

        {/* Sticky Header - appears when scrolling */}
        <div inert={!showStickyHeader} className={`absolute top-16 lg:top-0 left-0 right-0 z-10 bg-surface border-b transition-[opacity,transform] duration-300 ease-out ${
          showStickyHeader ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-full pointer-events-none'
        }`}>
          <div className="p-4">
            <div className="flex items-center gap-3">
              {currentFeed.image_url && (
                <img
                  src={currentFeed.image_url}
                  alt=""
                  className="w-10 h-10 rounded-lg object-cover"
                />
              )}
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-gray-900 truncate">{currentFeed.title}</p>
                {currentFeed.author && (
                  <p className="text-sm text-gray-600 truncate">by {currentFeed.author}</p>
                )}
              </div>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as SortOption)}
                aria-label="Sort episodes"
                className="input w-auto py-1.5 pl-3 pr-8"
              >
                <option value="newest">Newest first</option>
                <option value="oldest">Oldest first</option>
                <option value="title">Title A–Z</option>
              </select>

              {/* do not add addtional controls to sticky headers */}
            </div>
          </div>
        </div>

        {/* Scrollable Content */}
        <div ref={scrollContainerRef} className="flex-1 overflow-y-auto overscroll-contain">
        {/* Feed Info Header */}
        <div ref={feedHeaderRef} className="p-6 border-b">
          <div className="flex flex-col gap-6">
            {/* Top Section: Image and Title */}
            <div className="flex items-end gap-6">
              {/* Podcast Image */}
              <div className="flex-shrink-0" data-reveal="art">
                {currentFeed.image_url ? (
                  <FadeImage
                    src={currentFeed.image_url}
                    alt=""
                    className="w-32 h-32 sm:w-40 sm:h-40 rounded-lg object-cover"
                  />
                ) : (
                  <div className="w-32 h-32 sm:w-40 sm:h-40 rounded-lg bg-gray-200 flex items-center justify-center">
                    <MusicIcon className="h-16 w-16 text-gray-400" />
                  </div>
                )}
              </div>

              {/* Title aligned to bottom-left of image */}
              <div className="flex-1 min-w-0 pb-2">
                <h2 data-reveal="text" className="text-2xl font-bold text-gray-900 mb-1">{currentFeed.title}</h2>
                {currentFeed.author && (
                  <p data-reveal="text" className="text-lg text-gray-600">by {currentFeed.author}</p>
                )}
                <div data-reveal="text" className="mt-2 text-sm text-gray-500">
                  <span>{totalCount} episodes visible</span>
                </div>
                {requireAuth && isAdmin && (
                  <div data-reveal="text" className="mt-2 flex items-center gap-2 flex-wrap text-sm">
                    <button
                      onClick={() => setShowSubscribersModal(true)}
                      className="px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors"
                      title="View subscribers"
                    >
                      {currentFeed.member_count ?? 0} subscriber{(currentFeed.member_count ?? 0) !== 1 ? 's' : ''}
                    </button>
                    <span
                      className={`px-2 py-1 rounded-full text-xs font-medium border ${
                        isMember
                          ? 'bg-green-50 text-green-700 border-green-200'
                          : 'bg-gray-100 text-gray-600 border-gray-200'
                      }`}
                    >
                      {isMember ? 'Joined' : 'Not joined'}
                    </span>
                    {isMember && !isActiveSubscription && (
                      <span className="px-2 py-1 rounded-full text-xs font-medium border bg-amber-50 text-amber-700 border-amber-200">
                        Paused
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* RSS Button and Menu */}
            <div data-reveal="text" className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
              {/* Podly RSS Subscribe Button */}
              {showPodlyRssButton && (
                <button
                  onClick={handleCopyRssToClipboard}
                  title="Copy Podly RSS feed URL"
                  className="btn btn-dark w-full sm:w-auto h-auto min-h-9 whitespace-normal py-2 text-center"
                  disabled={!canSubscribe}
                >
                  <img
                    src="/rss-round-color-icon.svg"
                    alt="Podly RSS"
                    className="h-5 w-5 shrink-0"
                    aria-hidden="true"
                  />
                  <span>
                    {canSubscribe ? 'Subscribe to Podly RSS' : 'Join feed to subscribe'}
                  </span>
                </button>
              )}

              <div className="flex w-full items-center gap-3 sm:w-auto sm:flex-1 flex-wrap">
                {requireAuth && isAdmin && !isMember && (
                  <button
                    onClick={() => joinFeedMutation.mutate()}
                    disabled={joinFeedMutation.isPending}
                    className="btn btn-secondary flex-1 sm:flex-none"
                  >
                    <PlusIcon className="h-4 w-4 shrink-0" />
                    <span>Join feed</span>
                  </button>
                )}

                {canModifyEpisodes && (
                  <button
                    onClick={() => refreshFeedMutation.mutate()}
                    disabled={refreshFeedMutation.isPending}
                    title="Refresh feed from source"
                    className="btn btn-secondary flex-1 sm:flex-none"
                  >
                    <RefreshIcon className={`h-4 w-4 shrink-0 ${refreshFeedMutation.isPending ? 'animate-spin' : ''}`} />
                    <span>Refresh feed</span>
                  </button>
                )}

                {/* Settings Button (cog) */}
                {isAdmin && (
                  <button
                    onClick={() => setShowSettingsModal(true)}
                    title="Feed settings"
                    aria-label="Feed settings"
                    className="btn btn-secondary btn-icon shrink-0"
                  >
                    <GearIcon className="h-5 w-5" />
                  </button>
                )}

                {/* Ellipsis Menu */}
                <div className="relative menu-container shrink-0">
                  <button
                    onClick={() => setShowMenu(!showMenu)}
                    aria-label="More actions"
                    aria-expanded={showMenu}
                    className="btn btn-secondary btn-icon"
                  >
                    <DotsVerticalIcon className="h-5 w-5" />
                  </button>

                  {/* Dropdown Menu */}
                  {showMenu && (
                    <div className="absolute top-full right-0 mt-1 w-56 animate-pop-in origin-top-right bg-surface rounded-lg shadow-lg border border-gray-200 py-1 z-20 max-w-[calc(100vw-2rem)]">
                      {canBulkModifyEpisodes && (
                        <>
                          <button
                            onClick={() => {
                              if (!allWhitelisted) {
                                handleBulkWhitelistToggle();
                            }
                            setShowMenu(false);
                          }}
                          disabled={bulkWhitelistMutation.isPending || totalCount === 0 || allWhitelisted}
                          className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-3 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <CheckIcon className="h-4 w-4 text-green-600" />
                          Enable all episodes
                        </button>

                        <button
                          onClick={() => {
                            if (allWhitelisted) {
                              handleBulkWhitelistToggle();
                            }
                            setShowMenu(false);
                          }}
                          disabled={bulkWhitelistMutation.isPending || totalCount === 0 || !allWhitelisted}
                          className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-3 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <BlockedIcon className="h-4 w-4 text-red-600" />
                          Disable all episodes
                        </button>
                      </>
                      )}

                      {isAdmin && (
                        <button
                          onClick={() => {
                            setShowHelp(!showHelp);
                            setShowMenu(false);
                          }}
                          className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-3"
                        >
                          <InfoIcon className="h-4 w-4 text-blue-600" />
                          Explain whitelist
                        </button>
                      )}

                    <button
                      onClick={() => {
                        handleCopyOriginalRssToClipboard();
                        setShowMenu(false);
                      }}
                      className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-3"
                    >
                      <img src="/rss-round-color-icon.svg" alt="Original RSS" className="w-4 h-4" />
                      Original RSS feed
                    </button>

                    {requireAuth && isAdmin && isMember && (
                      <>
                        <div className="border-t border-gray-100 my-1"></div>
                        <button
                          onClick={() => {
                            leaveFeedMutation.mutate();
                            setShowMenu(false);
                          }}
                          disabled={leaveFeedMutation.isPending}
                          className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-3 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <LogoutIcon className="h-4 w-4" />
                          Leave feed
                        </button>
                      </>
                    )}

                    {canDeleteFeed && (
                      <>
                        <div className="border-t border-gray-100 my-1"></div>

                        <button
                          onClick={() => {
                            handleDeleteFeed();
                            setShowMenu(false);
                          }}
                          disabled={deleteFeedMutation.isPending}
                          className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-3 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <TrashIcon className="h-4 w-4" />
                          Delete feed
                        </button>
                      </>
                    )}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Feed Description */}
            {currentFeed.description && (
              <div data-reveal="text" className="text-gray-700 leading-relaxed">
                <p>{htmlToPlainText(currentFeed.description)}</p>
              </div>
            )}
          </div>
        </div>

        {/* Inactive Subscription Warning */}
        {currentFeed.is_member && currentFeed.is_active_subscription === false && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-start gap-3">
            <WarningIcon className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
            <div>
              <h3 className="text-sm font-medium text-amber-800">Processing Paused</h3>
              <p className="text-sm text-amber-700 mt-1">
                This feed exceeds your plan's allowance. New episodes will not be processed automatically until you upgrade your plan or leave other feeds.
              </p>
            </div>
          </div>
        )}

        {/* Episodes Header with Sort Only */}
        <div className="p-4 border-b bg-gray-50">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-gray-900">Episodes</h3>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              aria-label="Sort episodes"
              className="input w-auto py-1.5 pl-3 pr-8"
            >
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="title">Title A–Z</option>
            </select>
          </div>
        </div>

            {/* Help Explainer (admins only) */}
            {showHelp && isAdmin && (
          <div className="bg-blue-50 border-b border-blue-200 p-4">
            <div className="max-w-2xl">
              <h4 className="font-semibold text-blue-900 mb-2">About Enabling & Disabling Ad Removal</h4>
              <div className="text-sm text-blue-800 space-y-2 text-left">
                <p>
                  <strong>Enabled episodes</strong> are processed by Podly to automatically detect and remove advertisements,
                  giving you a clean, ad-free listening experience.
                </p>
                <p>
                  <strong>Disabled episodes</strong> are not processed and won't be available for download through Podly.
                  This is useful for episodes you don't want to listen to.
                </p>
                <p>
                  <strong>Why whitelist episodes?</strong> Processing takes time and computational resources.
                  Enable only the episodes you want to hear to keep your feed focused. This is useful when adding a new feed with a large back catalog.
                </p>
              </div>
              <button
                onClick={() => setShowHelp(false)}
                className="mt-3 text-xs text-blue-600 hover:text-blue-800 font-medium"
              >
                Got it, hide this explanation
              </button>
            </div>
          </div>
        )}

        {/* Episodes List */}
        <div className="relative min-h-[32rem]">
          {showDissolveOverlay && (
            <div data-dissolve-overlay className="pointer-events-none absolute inset-x-0 top-0 z-10 divide-y divide-gray-200" aria-hidden="true">
              {[0, 1, 2, 3].map((i) => (
                <EpisodeRowSkeleton key={i} />
              ))}
            </div>
          )}
          {skeletonVisible ? (
            <div className="animate-pulse divide-y divide-gray-200">
              {[0, 1, 2, 3].map((i) => (
                <EpisodeRowSkeleton key={i} />
              ))}
            </div>
          ) : isLoading ? null : error ? (
            <div className="p-6">
              <p className="text-red-600">Failed to load episodes</p>
            </div>
          ) : sortedEpisodes.length === 0 ? (
            <div className="flex animate-pop-in flex-col items-center gap-3 px-6 py-12 text-center">
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-sky-50 to-sky-100 text-sky-700" aria-hidden="true">
                <MusicIcon className="h-5 w-5" />
              </span>
              <h2 className="text-lg font-semibold text-gray-900">
                {whitelistedOnly ? 'No episodes enabled yet' : 'No episodes yet'}
              </h2>
              <p className="max-w-sm text-sm text-gray-600">
                {whitelistedOnly
                  ? 'Episodes show up here once an admin enables them for ad removal.'
                  : 'Refresh the feed to pull in its latest episodes.'}
              </p>
            </div>
          ) : (
            <div className="divide-y divide-gray-200">
              {sortedEpisodes.map((episode) => (
                <EpisodeRow
                  key={episode.id}
                  episode={episode}
                  feedId={currentFeed.id}
                  feedTitle={currentFeed.title}
                  feedImageUrl={currentFeed.image_url}
                  adDetectionStrategy={currentFeed.ad_detection_strategy}
                  descriptionView={episodeDescriptionView}
                  isExpanded={expandedDescriptions.has(episode.guid)}
                  showWhitelistUi={showWhitelistUi}
                  canModifyEpisodes={canModifyEpisodes}
                  isWhitelistPending={whitelistMutation.isPending}
                  onToggleExpanded={handleToggleExpanded}
                  onWhitelistToggle={handleWhitelistToggle}
                />
              ))}
            </div>
          )}
        </div>

        {totalCount > 0 && (
          <div className="flex items-center justify-between px-4 py-3 border-t bg-surface">
            <div className="text-sm text-gray-600">
              Showing {visibleStart}-{visibleEnd} of {totalCount} episodes
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((prev) => Math.max(1, prev - 1))}
                disabled={page === 1 || isLoading || isFetching}
                className="btn btn-secondary btn-sm"
              >
                Previous
              </button>
              <span className="text-sm text-gray-700">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
                disabled={page >= totalPages || isLoading || isFetching}
                className="btn btn-secondary btn-sm"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
      </div>

      <div
        className={`absolute inset-0 z-20 transition-opacity duration-200 ${
          showFeedSkeleton
            ? 'opacity-100'
            : 'pointer-events-none opacity-0'
        }`}
        aria-hidden={!showFeedSkeleton}
      >
        <div className="absolute inset-0 bg-surface/95 backdrop-blur-[3px]" />
        <div className="absolute inset-0 overflow-hidden">
          <div className="flex h-full flex-col animate-pulse">
            <div className="flex items-center justify-between border-b p-4 lg:hidden">
              <div className={`h-7 w-40 ${transitionSkeletonClass}`} />
              <div className="h-10 w-10 rounded-lg bg-gray-200" />
            </div>

            <div className="flex-1 overflow-y-auto">
              <div className="border-b p-6">
                <div className="flex flex-col gap-6">
                  <div className="flex items-end gap-6">
                    <div className="h-32 w-32 rounded-lg bg-gray-200 sm:h-40 sm:w-40" />
                    <div className="min-w-0 flex-1 pb-2">
                      <div className={`mb-2 h-8 w-2/3 max-w-xl ${transitionSkeletonClass}`} />
                      <div className={`mb-3 h-6 w-1/4 min-w-[8rem] ${transitionSkeletonClass}`} />
                      <div className={`h-5 w-32 ${transitionSkeletonSoftClass}`} />
                      {requireAuth && isAdmin && (
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <div className="h-7 w-24 rounded-full bg-gray-200" />
                          <div className="h-7 w-16 rounded-full bg-gray-200" />
                          {isMember && !isActiveSubscription && (
                            <div className="h-7 w-16 rounded-full bg-gray-200" />
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
                    {showPodlyRssButton && (
                      <div className="h-11 w-full rounded-lg bg-gray-200 sm:w-72" />
                    )}

                    <div className="flex w-full items-center gap-3 sm:w-auto sm:flex-1 sm:flex-wrap">
                      {requireAuth && isAdmin && !isMember && (
                        <div className="h-11 flex-1 rounded-lg bg-gray-200 sm:w-32 sm:flex-none" />
                      )}
                      {canModifyEpisodes && (
                        <div className="h-11 flex-1 rounded-lg bg-gray-200 sm:w-40 sm:flex-none" />
                      )}
                      {isAdmin && (
                        <div className="h-11 w-11 rounded-lg bg-gray-200" />
                      )}
                      <div className="h-11 w-11 rounded-lg bg-gray-200" />
                    </div>
                  </div>

                  {currentFeed.description && (
                    <div className="space-y-3">
                      <div className={`h-4 w-full ${transitionSkeletonSoftClass}`} />
                      <div className={`h-4 w-11/12 ${transitionSkeletonSoftClass}`} />
                      <div className={`h-4 w-3/4 ${transitionSkeletonSoftClass}`} />
                    </div>
                  )}
                </div>
              </div>

              {currentFeed.is_member && currentFeed.is_active_subscription === false && (
                <div className="border-b px-6 py-4">
                  <div className="flex items-start gap-3 rounded-lg border border-gray-200 bg-gray-50 p-4">
                    <div className="mt-0.5 h-5 w-5 rounded-full bg-gray-200" />
                    <div className="flex-1 space-y-2">
                      <div className={`h-4 w-40 ${transitionSkeletonClass}`} />
                      <div className={`h-4 w-full ${transitionSkeletonSoftClass}`} />
                      <div className={`h-4 w-10/12 ${transitionSkeletonSoftClass}`} />
                    </div>
                  </div>
                </div>
              )}

              <div className="border-b bg-gray-50 p-4">
                <div className="flex items-center justify-between">
                  <div className={`h-7 w-24 ${transitionSkeletonClass}`} />
                  <div className="h-9 w-32 rounded-md bg-gray-200" />
                </div>
              </div>

              {showHelp && isAdmin && (
                <div className="border-b px-4 py-4">
                  <div className="space-y-3">
                    <div className={`h-4 w-64 ${transitionSkeletonClass}`} />
                    <div className={`h-4 w-full ${transitionSkeletonSoftClass}`} />
                    <div className={`h-4 w-11/12 ${transitionSkeletonSoftClass}`} />
                    <div className={`h-4 w-10/12 ${transitionSkeletonSoftClass}`} />
                  </div>
                </div>
              )}

              <div className="min-h-[32rem] divide-y divide-gray-200">
                {[0, 1, 2].map((item) => (
                  <div key={item} className="p-4">
                    <div className="flex flex-col gap-3">
                      <div className="flex items-start gap-3">
                        <div className="h-16 w-16 rounded-lg bg-gray-200" />
                        <div className="min-w-0 flex-1">
                          <div className={`mb-2 h-5 w-3/5 ${transitionSkeletonClass}`} />
                          <div className={`h-4 w-1/4 min-w-[8rem] ${transitionSkeletonClass}`} />
                        </div>
                      </div>
                      <div className="space-y-3">
                        <div className={`h-4 w-full ${transitionSkeletonSoftClass}`} />
                        <div className={`h-4 w-5/6 ${transitionSkeletonSoftClass}`} />
                        <div className={`h-4 w-16 ${transitionSkeletonSoftClass}`} />
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="h-8 w-24 rounded-full bg-gray-200" />
                        <div className={`h-4 w-32 ${transitionSkeletonSoftClass}`} />
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="h-8 w-24 rounded-md bg-gray-200" />
                        <div className="h-8 w-24 rounded-md bg-gray-200" />
                        <div className="h-8 w-16 rounded-md bg-gray-200" />
                        <div className="ml-auto h-10 w-10 rounded-full bg-gray-200" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between border-t bg-surface px-4 py-3">
                <div className={`h-4 w-40 ${transitionSkeletonSoftClass}`} />
                <div className="flex items-center gap-2">
                  <div className="h-8 w-20 rounded-md bg-gray-200" />
                  <div className={`h-4 w-20 ${transitionSkeletonSoftClass}`} />
                  <div className="h-8 w-16 rounded-md bg-gray-200" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <ModalShell
        isOpen={showProcessingModal && pendingEpisode !== null}
        onClose={handleCancelProcessing}
        panelClassName="bg-surface rounded-lg shadow-2xl max-w-lg w-full p-6 space-y-4"
      >
        {pendingEpisode && (
          <>
            <h3 className="text-lg font-semibold text-gray-900">Enable episode</h3>
            <p className="text-sm text-gray-600">{pendingEpisode.title}</p>
            {isEstimating && (
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <div className="w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                Estimating processing time…
              </div>
            )}
            {!isEstimating && estimateError && (
              <p className="text-sm text-red-600">{estimateError}</p>
            )}
            {!isEstimating && processingEstimate && (
              <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-700 space-y-1">
                <p><strong>Estimated minutes:</strong> {processingEstimate.estimated_minutes.toFixed(2)}</p>
                {!processingEstimate.can_process && (
                  <p className="text-red-600 font-medium">Processing not available for this episode.</p>
                )}
              </div>
            )}
            <div className="flex justify-end gap-3">
              <button
                onClick={handleCancelProcessing}
                className="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmProcessing}
                disabled={
                  whitelistMutation.isPending ||
                  isEstimating ||
                  !processingEstimate?.can_process
                }
                className="btn btn-primary"
              >
                {whitelistMutation.isPending ? 'Starting…' : 'Confirm & process'}
              </button>
            </div>
          </>
        )}
      </ModalShell>

      <FeedSettingsModal
        feed={currentFeed}
        isOpen={showSettingsModal}
        onClose={() => setShowSettingsModal(false)}
        autoWhitelistGlobalDefault={appAutoWhitelistDefault}
        llmChapterFallbackGlobalDefault={
          configResponse?.config?.llm?.enable_llm_chapter_fallback_tagging
        }
        episodeDescriptionView={episodeDescriptionView}
        onEpisodeDescriptionViewChange={handleEpisodeDescriptionViewChange}
      />

      <FeedSubscribersModal
        feedId={currentFeed.id}
        feedTitle={currentFeed.title}
        isOpen={showSubscribersModal}
        onClose={() => setShowSubscribersModal(false)}
      />
    </div>
  );
}
