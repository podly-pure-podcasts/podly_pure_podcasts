import { useCallback, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import type { Episode } from '../../types';
import { feedsApi } from '../../services/api';
import PlayButton from '../PlayButton';
import DownloadButton from '../DownloadButton';
import ProcessingStatsButton from '../ProcessingStatsButton';
import ProcessButton from '../ProcessButton';
import { copyTextToClipboard } from '../../services/clipboard';
import { useEscapeKey } from '../../hooks/useEscapeKey';

// Extended episode type that includes optional combined-feed fields
export interface EpisodeWithTrigger extends Episode {
  feed_id?: number;
  feed_title?: string;
  trigger_url?: string | null;
}

interface EpisodeDetailModalProps {
  episode: EpisodeWithTrigger;
  feedTitle?: string;
  feedImageUrl?: string;
  feedId?: number;
  onClose: () => void;
  onWhitelistToggle: (guid: string, whitelisted: boolean) => void;
  onProcessStart?: (guid: string) => void;
  // For combined view, allow navigating to feed
  showFeedLink?: boolean;
}

// Helper functions
const formatDate = (dateString: string | null) => {
  if (!dateString) return 'Unknown date';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

const formatDuration = (seconds: number | null) => {
  if (!seconds) return '';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
};

export default function EpisodeDetailModal({
  episode,
  feedTitle,
  feedImageUrl,
  feedId,
  onClose,
  onWhitelistToggle,
  onProcessStart,
  showFeedLink = false,
}: EpisodeDetailModalProps) {
  const [copyModalUrl, setCopyModalUrl] = useState<string | null>(null);
  const [isLoadingTrigger, setIsLoadingTrigger] = useState(false);
  const closeCopyModal = useCallback(() => setCopyModalUrl(null), []);
  const closeModal = useCallback(() => {
    if (copyModalUrl) {
      closeCopyModal();
      return;
    }
    onClose();
  }, [copyModalUrl, closeCopyModal, onClose]);

  useEscapeKey(true, closeModal);

  // Determine the effective feed ID and title
  const effectiveFeedId = feedId ?? episode.feed_id;
  const effectiveFeedTitle = feedTitle ?? episode.feed_title;

  // Get trigger URL - prefer inline, otherwise fetch
  const getTriggerUrl = async (): Promise<string | null> => {
    // If we have an inline trigger_url, use it directly
    if (episode.trigger_url) {
      return episode.trigger_url;
    }

    // Otherwise, fetch it from the API
    try {
      setIsLoadingTrigger(true);
      const data = await feedsApi.getTriggerLink(episode.guid);
      return data.trigger_url;
    } catch (err) {
      console.error('Failed to get trigger URL:', err);
      return null;
    } finally {
      setIsLoadingTrigger(false);
    }
  };

  const handleOpenTriggerPage = async () => {
    const url = await getTriggerUrl();
    if (url) {
      window.open(url, '_blank');
    } else {
      toast.error('Failed to get processing link');
    }
  };

  const handleCopyTriggerLink = async () => {
    const url = await getTriggerUrl();
    if (!url) {
      toast.error('Failed to get processing link');
      return;
    }

    try {
      await copyTextToClipboard(url);
      toast.success('Processing link copied!');
    } catch {
      // Clipboard failed - show fallback modal
      setCopyModalUrl(url);
    }
  };

  // Determine if trigger buttons should be disabled
  const triggerUnavailable = !episode.whitelisted || episode.has_processed_audio;
  const triggerButtonsDisabled = triggerUnavailable || isLoadingTrigger;

  return createPortal(
    <>
      {/* Main Modal */}
      <div 
        className="fixed inset-0 bg-black/80 flex items-start sm:items-center justify-center p-2 sm:p-4 pt-4 sm:pt-8 overflow-y-auto"
        style={{ zIndex: 10000 }}
        onClick={onClose}
      >
        {/* 
          Modal container: flex-col with max-h-[90vh] for viewport constraint.
          IMPORTANT: min-h-0 is required on flex containers to allow children to shrink 
          and enable overflow scrolling. Without it, flex items default to min-height: min-content.
        */}
        <div 
          className="bg-white dark:bg-gray-800 rounded-2xl max-w-2xl w-full overflow-hidden shadow-2xl border border-purple-200 dark:border-purple-700 max-h-[90vh] flex flex-col min-h-0"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header - flex-shrink-0 to prevent shrinking */}
          <div className="p-4 sm:p-6 border-b border-purple-100 dark:border-purple-800 bg-gradient-to-r from-pink-50 via-purple-50 to-cyan-50 dark:from-pink-950/30 dark:via-purple-950/30 dark:to-cyan-950/30 flex-shrink-0">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <h2 className="text-lg sm:text-xl font-bold text-purple-900 dark:text-purple-100 leading-tight">{episode.title}</h2>
                {effectiveFeedTitle && (
                  showFeedLink && effectiveFeedId ? (
                    <Link
                      to={`/podcasts?feed=${effectiveFeedId}`}
                      className="text-sm text-purple-600 dark:text-purple-400 hover:underline mt-1 inline-block"
                      onClick={onClose}
                    >
                      {effectiveFeedTitle}
                    </Link>
                  ) : (
                    <p className="text-sm text-purple-600 dark:text-purple-400 mt-1">{effectiveFeedTitle}</p>
                  )
                )}
              </div>
              <button
                onClick={onClose}
                className="p-2 text-purple-600 dark:text-purple-400 hover:text-purple-800 dark:hover:text-purple-200 rounded-lg hover:bg-purple-100 dark:hover:bg-purple-900/50 bg-purple-100 dark:bg-purple-900/30 flex-shrink-0"
                aria-label="Close"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Content - scrollable area. min-h-0 required for flex child to enable overflow scroll */}
          <div className="p-4 sm:p-6 overflow-y-auto flex-1 min-h-0 bg-white dark:bg-gray-800">
            {/* Episode Image & Metadata */}
            <div className="flex gap-4 mb-4">
              {episode.image_url ? (
                <img 
                  src={episode.image_url} 
                  alt={episode.title}
                  className="w-20 h-20 sm:w-24 sm:h-24 rounded-xl object-cover flex-shrink-0 shadow-md"
                />
              ) : feedImageUrl ? (
                <img 
                  src={feedImageUrl} 
                  alt={effectiveFeedTitle || 'Feed'}
                  className="w-20 h-20 sm:w-24 sm:h-24 rounded-xl object-cover flex-shrink-0 shadow-md opacity-60"
                />
              ) : null}
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap gap-2 text-sm text-purple-600 dark:text-purple-400 mb-2">
                  {episode.release_date && (
                    <span className="flex items-center gap-1">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                      {formatDate(episode.release_date)}
                    </span>
                  )}
                  {episode.duration && (
                    <span className="flex items-center gap-1">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      {formatDuration(episode.duration)}
                    </span>
                  )}
                </div>
                
                {/* Status Badge */}
                <div className="mb-2">
                  {episode.has_processed_audio ? (
                    <span className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400 rounded-lg">
                      <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                      Processed & Ready
                    </span>
                  ) : episode.whitelisted ? (
                    <span className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400 rounded-lg">
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" />
                      </svg>
                      Enabled for Processing
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium bg-purple-100/50 dark:bg-purple-900/30 text-purple-500 rounded-lg border border-dashed border-purple-300/50 dark:border-purple-700/50">
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                      </svg>
                      Disabled
                    </span>
                  )}
                </div>

                {/* Download count */}
                {episode.download_count > 0 && (
                  <p className="text-xs text-purple-400 dark:text-purple-500">
                    Downloaded {episode.download_count} time{episode.download_count !== 1 ? 's' : ''}
                  </p>
                )}
              </div>
            </div>

            {/* Description */}
            {episode.description && (
              <div className="mt-4">
                <h3 className="text-sm font-semibold text-purple-900 dark:text-purple-100 mb-2">Description</h3>
                <div 
                  className="text-sm text-purple-700 dark:text-purple-300 leading-relaxed"
                  style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                  dangerouslySetInnerHTML={{ 
                    __html: episode.description.replace(/\n/g, '<br />')
                  }}
                />
              </div>
            )}
          </div>

          {/* Footer Actions */}
          <div className="p-4 sm:p-6 border-t border-purple-100 dark:border-purple-800 bg-purple-50 dark:bg-purple-950/30 flex-shrink-0">
            <div className="flex flex-wrap gap-2">
              {episode.has_processed_audio && (
                <>
                  <PlayButton episode={episode} />
                  <DownloadButton 
                    episodeGuid={episode.guid}
                    isWhitelisted={episode.whitelisted}
                    hasProcessedAudio={episode.has_processed_audio}
                    feedId={effectiveFeedId}
                  />
                  <ProcessingStatsButton 
                    episodeGuid={episode.guid}
                    hasProcessedAudio={episode.has_processed_audio}
                  />
                </>
              )}
              {!episode.has_processed_audio && episode.whitelisted && (
                <>
                  <ProcessButton 
                    episodeGuid={episode.guid}
                    feedId={effectiveFeedId}
                    onProcessStart={() => onProcessStart?.(episode.guid)}
                  />
                  <button
                    onClick={handleOpenTriggerPage}
                    disabled={triggerButtonsDisabled}
                    className="px-3 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-1.5 border bg-white dark:bg-gray-800 border-purple-200 dark:border-purple-700 text-purple-600 dark:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-900/50 disabled:opacity-50 disabled:cursor-not-allowed"
                    title={isLoadingTrigger ? 'Loading...' : 'Opens a page that queues processing and shows progress'}
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                    {isLoadingTrigger ? 'Loading...' : 'Open processing page'}
                  </button>
                  <button
                    onClick={handleCopyTriggerLink}
                    disabled={triggerButtonsDisabled}
                    className="px-3 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-1.5 border bg-white dark:bg-gray-800 border-purple-200 dark:border-purple-700 text-purple-600 dark:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-900/50 disabled:opacity-50 disabled:cursor-not-allowed"
                    title={isLoadingTrigger ? 'Loading...' : 'Copy link to share'}
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                    </svg>
                    {isLoadingTrigger ? 'Loading...' : 'Copy link'}
                  </button>
                </>
              )}
              <button
                onClick={() => {
                  onWhitelistToggle(episode.guid, !episode.whitelisted);
                  onClose();
                }}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-1.5 border ${
                  episode.whitelisted
                    ? 'bg-white dark:bg-gray-800 border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30'
                    : 'bg-white dark:bg-gray-800 border-emerald-200 dark:border-emerald-800 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-900/30'
                }`}
              >
                {episode.whitelisted ? 'Disable' : 'Enable'}
              </button>
            </div>
            {/* Workflow explanation for unprocessed episodes */}
            {!episode.has_processed_audio && episode.whitelisted && (
              <div className="mt-4 p-3 rounded-lg bg-purple-100/50 dark:bg-purple-900/30 border border-purple-200 dark:border-purple-700">
                <p className="text-sm text-purple-700 dark:text-purple-300">
                  <strong>How it works:</strong> Click "Open processing page" to queue ad removal. 
                  Once complete (usually 1-2 minutes), return to your podcast app and download the episode as normal.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Copy URL Fallback Modal */}
      {copyModalUrl && (
        <div 
          className="fixed inset-0 bg-black/80 flex items-center justify-center p-4"
          style={{ zIndex: 10001 }}
          onClick={closeCopyModal}
        >
          <div 
            className="bg-white dark:bg-gray-800 rounded-xl max-w-md w-full p-6 shadow-2xl border border-purple-200 dark:border-purple-700"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-purple-900 dark:text-purple-100 mb-2">Copy Processing Link</h3>
            <p className="text-sm text-purple-600 dark:text-purple-400 mb-4">
              Select and copy the URL below:
            </p>
            <input
              type="text"
              readOnly
              value={copyModalUrl}
              className="w-full px-3 py-2 rounded-lg border border-purple-200 dark:border-purple-700 bg-purple-50 dark:bg-purple-950/50 text-purple-900 dark:text-purple-100 text-sm font-mono"
              onClick={(e) => (e.target as HTMLInputElement).select()}
            />
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={closeCopyModal}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-purple-100 dark:bg-purple-900/50 text-purple-700 dark:text-purple-300 hover:bg-purple-200 dark:hover:bg-purple-900"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>,
    document.body
  );
}
