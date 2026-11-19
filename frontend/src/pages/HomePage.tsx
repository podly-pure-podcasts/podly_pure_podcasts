import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { feedsApi, billingApi } from '../services/api';
import FeedList from '../components/FeedList';
import FeedDetail from '../components/FeedDetail';
import AddFeedForm from '../components/AddFeedForm';
import ModalShell from '../components/ModalShell';
import {
  loadFeedListSortPreference,
  persistFeedListSortPreference,
} from '../utils/feedListSort';
import type { FeedSortOption } from '../utils/feedListSort';
import { toast } from 'react-hot-toast';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate, useParams } from 'react-router-dom';
import { copyToClipboard } from '../utils/clipboard';
import { emitDiagnosticError } from '../utils/diagnostics';
import { getHttpErrorInfo } from '../utils/httpError';
import { useDelayedFlag } from '../hooks/useDelayedFlag';
import { gsap, prefersFullMotion } from '../utils/gsap';
import { EASE } from '../utils/nativeMotion';
import { LinkIcon, PlusIcon, RefreshIcon, RssIcon, SlidersIcon, CheckIcon, CloseIcon } from '../components/icons';

const HOME_ROUTE_QUERY_GC_TIME_MS = 5 * 60 * 1000;

const MOBILE_FEED_QUERY = '(max-width: 1023px)';
const SHEET_OPEN_MS = 420;
const SHEET_CLOSE_MS = 300;

function isMobileFeedViewport(): boolean {
  return typeof window !== 'undefined' && window.matchMedia(MOBILE_FEED_QUERY).matches;
}

function subscribeMobileFeedViewport(onChange: () => void): () => void {
  const query = window.matchMedia(MOBILE_FEED_QUERY);
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
}

export default function HomePage() {
  const navigate = useNavigate();
  const { feedId } = useParams();
  const [showAddForm, setShowAddForm] = useState(false);
  const [showSortMenu, setShowSortMenu] = useState(false);
  const sortMenuRef = useRef<HTMLDivElement>(null);
  const [feedSortBy, setFeedSortBy] = useState<FeedSortOption>(() =>
    loadFeedListSortPreference()
  );
  const isMobileViewport = useSyncExternalStore(subscribeMobileFeedViewport, isMobileFeedViewport, () => false);
  // Phone detail panel: a tap in the list slides it in over the list (which keeps
  // its scroll), and the episode rows wait until the slide settles so no heavy
  // render lands mid-animation. A feed opened from its URL appears in place.
  const listPaneRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [panelSlides, setPanelSlides] = useState(false);
  const [panelSettled, setPanelSettled] = useState(true);
  const closingRef = useRef(false);
  const settleCallRef = useRef<gsap.core.Tween | null>(null);
  const slideStartedRef = useRef(false);
  const panelAnimRef = useRef<Animation | null>(null);
  const listAnimRef = useRef<Animation | null>(null);
  const { requireAuth, user } = useAuth();

  const { data: feeds, isLoading, error, refetch } = useQuery({
    queryKey: ['feeds'],
    queryFn: feedsApi.getFeeds,
    gcTime: HOME_ROUTE_QUERY_GC_TIME_MS,
  });
  const showSkeleton = useDelayedFlag(isLoading);

  const { data: billingSummary, refetch: refetchBilling } = useQuery({
    queryKey: ['billing', 'summary'],
    queryFn: billingApi.getSummary,
    enabled: requireAuth && !!user,
    gcTime: HOME_ROUTE_QUERY_GC_TIME_MS,
  });
  const canRefreshAll = !requireAuth || user?.role === 'admin';
  const refreshAllMutation = useMutation({
    mutationFn: () => feedsApi.refreshAllFeeds(),
    onSuccess: (data) => {
      toast.success(
        `Refreshed ${data.feeds_refreshed} feeds and enqueued ${data.jobs_enqueued} jobs`
      );
      refetch();
    },
    onError: (err) => {
      console.error('Failed to refresh all feeds', err);
      const { status, data, message } = getHttpErrorInfo(err);
      emitDiagnosticError({
        title: 'Failed to refresh all feeds',
        message,
        kind: status ? 'http' : 'network',
        details: {
          status,
          response: data,
        },
      });
    },
  });




  useEffect(() => {
    if (!showSortMenu) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (!sortMenuRef.current?.contains(event.target as Node)) {
        setShowSortMenu(false);
      }
    };
    document.addEventListener('pointerdown', handlePointerDown);
    return () => document.removeEventListener('pointerdown', handlePointerDown);
  }, [showSortMenu]);

  const planLimitReached =
    !!billingSummary &&
    billingSummary.feeds_in_use >= billingSummary.feed_allowance &&
    user?.role !== 'admin';

  const handleChangePlan = () => {
    navigate('/billing');
  };

  const parsedFeedId = feedId ? Number(feedId) : null;
  const feedIdIsValid = parsedFeedId !== null && Number.isFinite(parsedFeedId);
  // The URL is the only source of the open feed: a second copy in state lags
  // the router by a render and fights it, remounting the panel mid-animation.
  const selectedFeed = useMemo(
    () => (feedIdIsValid && feeds ? feeds.find((feed) => feed.id === parsedFeedId) ?? null : null),
    [feeds, feedIdIsValid, parsedFeedId]
  );
  const feedNotFound = feedIdIsValid && !!feeds && !selectedFeed;
  const detailFeed = selectedFeed;
  const panelWasOpenRef = useRef(false);

  useLayoutEffect(() => {
    const panel = panelRef.current;
    const list = listPaneRef.current;
    if (!selectedFeed) {
      // A tap sets the slide flags a render before the URL opens the panel,
      // so they only reset once a panel that was open has closed.
      slideStartedRef.current = false;
      if (panelWasOpenRef.current) {
        listAnimRef.current?.cancel();
        listAnimRef.current = null;
        setPanelSlides(false);
        setPanelSettled(true);
      }
      panelWasOpenRef.current = false;
      return;
    }
    panelWasOpenRef.current = true;
    // A feeds refetch gives the selected feed a new identity and re-runs this
    // effect; the slide for an opening starts only once.
    if (!panel || !panelSlides || panelSettled || slideStartedRef.current) return;
    slideStartedRef.current = true;
    // The sheet slide runs as a Web Animation on the compositor, so a busy main
    // thread can't freeze or skip it. Created before paint with fill 'both', its
    // first frame is already off screen; its clock starts once that frame is
    // committed, so a slow first paint doesn't make it jump.
    panelAnimRef.current?.cancel();
    panelAnimRef.current = panel.animate(
      [{ transform: 'translateX(100%)' }, { transform: 'translateX(0)' }],
      { duration: SHEET_OPEN_MS, easing: EASE.settle, fill: 'both' }
    );
    if (list) {
      listAnimRef.current?.cancel();
      listAnimRef.current = list.animate(
        [{ transform: 'none', opacity: 1 }, { transform: 'translateX(-18%)', opacity: 0.45 }],
        { duration: SHEET_OPEN_MS, easing: EASE.settle, fill: 'forwards' }
      );
    }
    // The ease has covered ~98.5% of the distance by 80% of the duration; the
    // rows' render lands there, where the remaining movement is a few px.
    settleCallRef.current?.kill();
    settleCallRef.current = gsap.delayedCall((SHEET_OPEN_MS * 0.8) / 1000, () => setPanelSettled(true));
  }, [selectedFeed, panelSlides, panelSettled]);

  useEffect(() => {
    if (!isMobileViewport) {
      panelAnimRef.current?.cancel();
      listAnimRef.current?.cancel();
    }
  }, [isMobileViewport]);

  // The slide-out runs first and the route changes after it, so nothing heavy
  // renders while the panel moves.
  const closePanel = () => {
    const panel = panelRef.current;
    const list = listPaneRef.current;
    const finish = () => {
      closingRef.current = false;
      navigate('/');
    };
    if (!panel || closingRef.current || !isMobileFeedViewport() || !prefersFullMotion()) {
      finish();
      return;
    }
    closingRef.current = true;
    settleCallRef.current?.kill();
    // Start from wherever the sheet and list are, so closing mid-open doesn't jump.
    const panelFrom = getComputedStyle(panel).transform;
    panelAnimRef.current?.cancel();
    panelAnimRef.current = panel.animate(
      [{ transform: panelFrom }, { transform: 'translateX(100%)' }],
      { duration: SHEET_CLOSE_MS, easing: EASE.in, fill: 'forwards' }
    );
    panelAnimRef.current.finished.then(finish, () => {});
    if (list) {
      const listStyle = getComputedStyle(list);
      const listFrom = { transform: listStyle.transform, opacity: listStyle.opacity };
      listAnimRef.current?.cancel();
      listAnimRef.current = list.animate(
        [listFrom, { transform: 'none', opacity: 1 }],
        { duration: SHEET_CLOSE_MS, easing: EASE.out, fill: 'forwards' }
      );
    }
  };

  const handleCopyAggregateLink = async () => {
    try {
      const { url } = await feedsApi.getAggregateFeedLink();
      await copyToClipboard(url, 'Copy the Aggregate RSS URL:', 'Aggregate feed URL copied to clipboard!');
    } catch (err) {
      console.error('Failed to get aggregate link', err);
      toast.error('Failed to get aggregate feed link');
    }
  };

  const handleAddFeedClick = () => {
    if (planLimitReached) {
      navigate('/billing');
    } else {
      setShowAddForm((prev) => !prev);
    }
  };

  const handleFeedSortChange = (nextSort: FeedSortOption) => {
    setFeedSortBy(nextSort);
    persistFeedListSortPreference(nextSort);
    setShowSortMenu(false);
  };

  const feedSortOptions: { value: FeedSortOption; label: string }[] = [
    { value: 'newest', label: 'Newest episode' },
    { value: 'oldest', label: 'Oldest episode' },
    { value: 'title-asc', label: 'Title A–Z' },
    { value: 'title-desc', label: 'Title Z–A' },
    { value: 'feed-added-oldest', label: 'Feed Added (Oldest)' },
    { value: 'feed-added-newest', label: 'Feed Added (Newest)' },
  ];

  return (
    <div className="relative h-full flex flex-col lg:flex-row gap-6">
      {/* Left Panel - Feed List (behind the detail panel on phones) */}
      <div
        ref={listPaneRef}
        inert={isMobileViewport && !!selectedFeed}
        className={`flex-1 lg:max-w-md xl:max-w-lg flex flex-col ${
          feedIdIsValid && isLoading ? 'hidden lg:flex' : 'flex'
        }`}
      >
        <div className="mb-6 flex flex-wrap items-center gap-x-3 gap-y-3">
          <h1 className="w-full text-2xl font-semibold text-gray-900 sm:w-auto sm:flex-1">
            Podcast feeds
          </h1>
          <div className="flex items-center gap-2">
            <div ref={sortMenuRef} className="relative">
              <button
                type="button"
                onClick={() => setShowSortMenu((prev) => !prev)}
                title="Sort podcast feeds"
                aria-label="Sort feeds"
                aria-haspopup="menu"
                aria-expanded={showSortMenu}
                className="btn btn-secondary btn-icon"
              >
                <SlidersIcon className="w-4 h-4" />
              </button>
              {showSortMenu && (
                <div
                  role="menu"
                  className="absolute right-0 top-full mt-1 w-48 origin-top-right animate-pop-in rounded-md border border-gray-200 bg-surface py-1 shadow-lg z-20 max-w-[calc(100vw-2rem)]"
                >
                  {feedSortOptions.map((option) => {
                    const isActive = option.value === feedSortBy;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        role="menuitemradio"
                        aria-checked={isActive}
                        onClick={() => handleFeedSortChange(option.value)}
                        className={`flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm leading-5 transition-colors ${
                          isActive
                            ? 'font-medium text-blue-700'
                            : 'text-gray-700 hover:bg-gray-50'
                        }`}
                      >
                        <span>{option.label}</span>
                        {isActive && <CheckIcon className="h-3.5 w-3.5 shrink-0 text-blue-700" />}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
            {canRefreshAll && (
              <button
                type="button"
                onClick={() => refreshAllMutation.mutate()}
                disabled={refreshAllMutation.isPending}
                title="Refresh all feeds"
                aria-label="Refresh all feeds"
                className="btn btn-secondary btn-icon"
              >
                <RefreshIcon
                  className={`w-4 h-4 ${refreshAllMutation.isPending ? 'animate-spin' : ''}`}
                />
              </button>
            )}
            <button
              type="button"
              onClick={handleCopyAggregateLink}
              className="btn btn-secondary btn-icon"
              aria-label="Copy aggregate feed link"
              title="Copy your aggregate feed URL (last 3 episodes from each feed)"
            >
              <LinkIcon className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={handleAddFeedClick}
              className="btn btn-primary"
              title={planLimitReached ? 'Your plan is full. Click to upgrade.' : undefined}
            >
              <PlusIcon className="w-4 h-4" />
              {planLimitReached ? 'Plan full' : showAddForm ? 'Close' : 'Add feed'}
            </button>
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-hidden">
          {isLoading ? (
            showSkeleton && (
            <div className="space-y-2" aria-hidden="true">
              {Array.from({ length: 6 }, (_, index) => (
                <div
                  key={index}
                  className="flex items-start gap-3 rounded-lg border border-gray-200 bg-surface p-4"
                >
                  <div className="h-12 w-12 shrink-0 rounded-md bg-gray-200" />
                  <div className="flex-1 space-y-2 pt-1">
                    <div className="h-4 w-3/4 rounded bg-gray-200" />
                    <div className="h-3 w-1/2 rounded bg-gray-200" />
                  </div>
                </div>
              ))}
            </div>
            )
          ) : error ? (
            <div
              role="alert"
              className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 p-4"
            >
              <p className="text-sm text-red-800">Error loading feeds.</p>
              <button
                type="button"
                onClick={() => refetch()}
                className="btn btn-ghost btn-sm"
              >
                Retry
              </button>
            </div>
          ) : (
            <FeedList 
            feeds={feeds || []} 
            onFeedDeleted={refetch}
            onFeedSelected={(feed) => {
              if (isMobileFeedViewport() && prefersFullMotion()) {
                setPanelSlides(true);
                setPanelSettled(false);
              }
              navigate(`/feeds/${feed.id}`);
            }}
            selectedFeedId={selectedFeed?.id}
            sortBy={feedSortBy}
          />
          )}
        </div>
      </div>

      {/* Right Panel - Feed Detail */}
      {detailFeed && (
        <div
          ref={panelRef}
          className="fixed inset-x-0 top-[49px] bottom-0 z-30 flex flex-col overflow-hidden bg-surface shadow-[-12px_0_32px_rgba(0,0,0,0.28)] lg:static lg:inset-auto lg:z-auto lg:flex-1 lg:flex-[2] lg:rounded-lg lg:border lg:border-gray-200 lg:shadow-sm"
        >
          <FeedDetail 
            feed={detailFeed}
            slidesIn={panelSlides}
            holdContent={!panelSettled}
            onClose={closePanel}
            onFeedDeleted={() => {
              navigate('/');
              refetch();
            }}
          />
        </div>
      )}

      {/* Empty State for Desktop */}
      {!selectedFeed && !feedNotFound && feeds && (
        <div className="hidden lg:flex flex-[2] flex-col items-start gap-4 self-start rounded-lg border border-gray-200 bg-surface p-6 shadow-sm">
          {feeds.length === 0 ? (
            <>
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-sky-50 to-sky-100 text-sky-700" aria-hidden="true">
                <RssIcon className="h-5 w-5" />
              </span>
              <h2 className="text-lg font-semibold text-gray-900">No podcasts yet</h2>
              <p className="text-sm text-gray-600">Add a feed to start removing ads from your shows.</p>
              <button type="button" onClick={handleAddFeedClick} className="btn btn-primary">
                <PlusIcon className="w-4 h-4" />
                Add feed
              </button>
            </>
          ) : (
            <>
              <h2 className="text-lg font-semibold text-gray-900">Select a podcast to see its episodes</h2>
              <p className="text-sm text-gray-600">
                <span className="tabular-nums">{feeds.length}</span>{' '}
                {feeds.length === 1 ? 'podcast' : 'podcasts'},{' '}
                <span className="tabular-nums">
                  {feeds.reduce((sum, feed) => sum + (feed.posts_count ?? 0), 0).toLocaleString()}
                </span>{' '}
                episodes in total
              </p>
              <button type="button" onClick={handleCopyAggregateLink} className="btn btn-secondary">
                <LinkIcon className="w-4 h-4" />
                Copy combined RSS link
              </button>
            </>
          )}
        </div>
      )}

      {feedNotFound && (
        <div className="hidden lg:flex flex-[2] flex-col items-start gap-1 self-start rounded-lg border border-gray-200 bg-surface p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">Feed not found</h2>
          <p className="text-sm text-gray-600">Pick a feed from the list to continue.</p>
        </div>
      )}

      <ModalShell
        isOpen={showAddForm}
        onClose={() => setShowAddForm(false)}
        containerClassName="items-start p-4 sm:items-center sm:p-6"
        panelClassName="w-full max-w-3xl bg-surface rounded-lg shadow-2xl border border-gray-200 flex flex-col max-h-[90vh]"
      >
            <div className="flex items-center justify-between border-b border-gray-200 px-4 sm:px-6 py-4">
              <div>
                <h2 className="text-xl sm:text-2xl font-semibold text-gray-900">Add a podcast feed</h2>
                <p className="text-sm text-gray-500 mt-1">
                  Paste an RSS URL or search the catalog to find shows to follow.
                </p>
              </div>
              <button
                onClick={() => setShowAddForm(false)}
                className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100 transition-colors"
                aria-label="Close add feed modal"
              >
                <CloseIcon className="w-6 h-6" />
              </button>
            </div>

            <div className="overflow-y-auto px-4 sm:px-6 py-4">
              <AddFeedForm
                onSuccess={() => {
                  setShowAddForm(false);
                  refetch();
                  refetchBilling();
                }}
                onUpgradePlan={handleChangePlan}
                planLimitReached={planLimitReached}
              />
            </div>
      </ModalShell>
    </div>
  );
}
