import { memo, useCallback } from 'react';
import type { Episode, Feed } from '../types';
import DownloadButton from './DownloadButton';
import PlayButton from './PlayButton';
import ProcessingStatsButton from './ProcessingStatsButton';
import EpisodeProcessingStatus from './EpisodeProcessingStatus';
import ExpandingBlock from './ExpandingBlock';
import FadeImage from './FadeImage';
import { BlockedIcon, CheckIcon, MusicIcon, RefreshIcon } from './icons';

export type EpisodeDescriptionView = 'source' | 'podly';


type DescriptionToken =
  | { type: 'text'; value: string }
  | { type: 'link'; href: string; text: string }
  | { type: 'newline' };

const parseDescription = (rawDescription: string): DescriptionToken[] => {
  if (typeof document === 'undefined') {
    return [{ type: 'text', value: rawDescription }];
  }

  const parser = new DOMParser();
  const doc = parser.parseFromString(rawDescription, 'text/html');
  const tokens: DescriptionToken[] = [];
  const blockTags = new Set(['p', 'div', 'li', 'ul', 'ol']);

  const pushText = (text: string) => {
    if (!text) {
      return;
    }
    const parts = text.split(/\r?\n/);
    parts.forEach((part, index) => {
      if (part) {
        tokens.push({ type: 'text', value: part });
      }
      if (index < parts.length - 1) {
        tokens.push({ type: 'newline' });
      }
    });
  };

  const visitNode = (node: Node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      pushText(node.textContent ?? '');
      return;
    }

    if (node.nodeType !== Node.ELEMENT_NODE) {
      return;
    }

    const element = node as HTMLElement;
    const tag = element.tagName.toLowerCase();

    if (tag === 'br') {
      tokens.push({ type: 'newline' });
      return;
    }

    if (tag === 'a') {
      const href = element.getAttribute('href');
      const text = element.textContent ?? '';
      if (href) {
        tokens.push({ type: 'link', href, text: text || href });
      } else {
        pushText(text);
      }
      return;
    }

    if (blockTags.has(tag)) {
      tokens.push({ type: 'newline' });
      element.childNodes.forEach(visitNode);
      tokens.push({ type: 'newline' });
      return;
    }

    element.childNodes.forEach(visitNode);
  };

  doc.body.childNodes.forEach(visitNode);

  const normalized: DescriptionToken[] = [];
  for (const token of tokens) {
    const last = normalized[normalized.length - 1];
    if (token.type === 'text') {
      const cleaned = token.value.replace(/[ \t]+/g, ' ');
      if (!cleaned) {
        continue;
      }
      if (last?.type === 'text') {
        last.value += cleaned;
      } else {
        normalized.push({ type: 'text', value: cleaned });
      }
      continue;
    }

    if (token.type === 'newline') {
      if (last?.type !== 'newline') {
        normalized.push(token);
      }
      continue;
    }

    normalized.push(token);
  }

  while (normalized[0]?.type === 'newline') {
    normalized.shift();
  }
  while (normalized[normalized.length - 1]?.type === 'newline') {
    normalized.pop();
  }

  return normalized;
};

// Parsing runs a DOMParser pass per description, and the episode list
// re-renders several times while a feed loads; parse each description once.
const descriptionTokenCache = new Map<string, DescriptionToken[]>();
const DESCRIPTION_CACHE_LIMIT = 500;

const tokenizeDescription = (rawDescription: string): DescriptionToken[] => {
  const cached = descriptionTokenCache.get(rawDescription);
  if (cached) return cached;
  const tokens = parseDescription(rawDescription);
  if (descriptionTokenCache.size >= DESCRIPTION_CACHE_LIMIT) {
    const oldest = descriptionTokenCache.keys().next().value;
    if (oldest !== undefined) descriptionTokenCache.delete(oldest);
  }
  descriptionTokenCache.set(rawDescription, tokens);
  return tokens;
};

const renderDescriptionTokens = (tokens: DescriptionToken[]) =>
  tokens.map((token, index) => {
    if (token.type === 'newline') {
      return (
        <span key={`newline-${index}`}>
          {'\n'}
        </span>
      );
    }

    if (token.type === 'link') {
      return (
        <a
          key={`link-${index}`}
          href={token.href}
          target="_blank"
          rel="noreferrer"
          className="text-blue-600 hover:underline"
        >
          {token.text}
        </a>
      );
    }

    return (
      <span key={`text-${index}`}>
        {token.value}
      </span>
    );
  });

const tokensToPlainText = (tokens: DescriptionToken[]) =>
  tokens
    .map((token) => {
      if (token.type === 'text') {
        return token.value;
      }
      if (token.type === 'link') {
        return token.text;
      }
      return ' • ';
    })
    .join('')
    .replace(/\s+/g, ' ')
    .trim();

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
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
};


interface EpisodeRowProps {
  episode: Episode;
  feedId: number;
  feedTitle: string;
  feedImageUrl: Feed['image_url'];
  adDetectionStrategy: Feed['ad_detection_strategy'];
  descriptionView: EpisodeDescriptionView;
  isExpanded: boolean;
  showWhitelistUi: boolean;
  canModifyEpisodes: boolean;
  isWhitelistPending: boolean;
  onToggleExpanded: (guid: string) => void;
  onWhitelistToggle: (episode: Episode) => void;
}

function EpisodeRow({
  episode,
  feedId,
  feedTitle,
  feedImageUrl,
  adDetectionStrategy,
  descriptionView,
  isExpanded,
  showWhitelistUi,
  canModifyEpisodes,
  isWhitelistPending,
  onToggleExpanded,
  onWhitelistToggle,
}: EpisodeRowProps) {
  const handleToggleExpanded = useCallback(
    () => onToggleExpanded(episode.guid),
    [onToggleExpanded, episode.guid]
  );

  return (
      <div key={episode.id} data-reveal-row className="p-4 hover:bg-gray-50 [content-visibility:auto] [contain-intrinsic-size:auto_200px]">
        <div className={`flex flex-col ${episode.whitelisted ? 'gap-3' : 'gap-2'}`}>
          {/* Top Section: Thumbnail and Title */}
          <div className="flex items-start gap-3">
            {/* Episode/Podcast Thumbnail */}
            <div className="flex-shrink-0">
              {(episode.image_url || feedImageUrl) ? (
                <FadeImage
                  src={episode.image_url || feedImageUrl}
                  alt=""
                  loading="lazy"
                  className="w-16 h-16 rounded-lg object-cover"
                />
              ) : (
                <div className="w-16 h-16 rounded-lg bg-gray-200 flex items-center justify-center">
                  <MusicIcon className="h-8 w-8 text-gray-400" />
                </div>
              )}
            </div>

            {/* Title and Feed Name */}
            <div className="flex-1 min-w-0 text-left">
              <h4 className="font-medium text-gray-900 mb-1 line-clamp-2 text-left">
                {episode.title}
              </h4>
              <p className="text-sm text-gray-600 text-left">
                {feedTitle}
              </p>
            </div>
          </div>

          {/* Episode Description */}
          {(
            descriptionView === 'podly'
              ? (episode.podly_description_html || episode.description)
              : episode.description
          ) && (
            <div className="text-left">
              {(() => {
                const descriptionHtml =
                  descriptionView === 'podly'
                    ? (episode.podly_description_html || episode.description)
                    : episode.description;
                const descriptionTokens = tokenizeDescription(descriptionHtml);
                const descriptionLength = descriptionTokens.reduce((total, token) => {
                  if (token.type === 'text') {
                    return total + token.value.length;
                  }
                  if (token.type === 'link') {
                    return total + token.text.length;
                  }
                  return total + 1;
                }, 0);
                const shouldTruncate = descriptionLength > 300;
                const isTruncated = !isExpanded && shouldTruncate;
                const plainText = tokensToPlainText(descriptionTokens);
                const truncatedText = isTruncated
                  ? `${plainText.slice(0, 300)}…`
                  : plainText;
                return (
                  <>
                    <ExpandingBlock expanded={isExpanded}>
                      {isExpanded ? (
                        <p className="text-sm text-gray-500 whitespace-pre-line">
                          {renderDescriptionTokens(descriptionTokens)}
                        </p>
                      ) : (
                        <p className="text-sm text-gray-500 line-clamp-3">
                          {truncatedText}
                        </p>
                      )}
                    </ExpandingBlock>
                    {shouldTruncate && (
                      <button
                        type="button"
                        aria-expanded={isExpanded}
                        onClick={handleToggleExpanded}
                        className="touch-target mt-2 inline-flex items-center text-xs font-medium text-gray-500 underline-offset-2 transition hover:text-gray-700 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-300/60"
                      >
                        {isExpanded ? 'Show less' : 'Show more'}
                      </button>
                    )}
                  </>
                );
              })()}
            </div>
          )}

          {/* Metadata: Status, Date and Duration */}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-gray-500">
            {showWhitelistUi && (
              <>
                <button
                  onClick={() => onWhitelistToggle(episode)}
                  disabled={isWhitelistPending}
                  role="switch"
                  aria-checked={episode.whitelisted}
                  className={`touch-target px-2 py-1 text-xs font-medium rounded-full transition-colors flex items-center justify-center gap-1 ${
                    episode.whitelisted
                      ? 'bg-green-100 text-green-800 hover:bg-green-200'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  } ${isWhitelistPending ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  <span className="sr-only">Process episode: </span>
                  {isWhitelistPending ? (
                    <>
                      <RefreshIcon className="h-3 w-3 animate-spin" />
                      <span>...</span>
                    </>
                  ) : episode.whitelisted ? (
                    <>
                      <CheckIcon className="h-3 w-3" />
                      <span>Enabled</span>
                    </>
                  ) : (
                    <>
                      <BlockedIcon className="h-3 w-3" />
                      <span>Disabled</span>
                    </>
                  )}
                </button>
              </>
            )}
            {/* Each separator leads its item so a wrapped line never ends on a bullet. */}
            <span className="whitespace-nowrap">
              {showWhitelistUi && <span aria-hidden="true" className="mr-2">•</span>}
              {formatDate(episode.release_date)}
            </span>
            {episode.duration && (
              <span className="whitespace-nowrap">
                <span aria-hidden="true" className="mr-2">•</span>
                {formatDuration(episode.duration)}
              </span>
            )}
            <span className="whitespace-nowrap">
              <span aria-hidden="true" className="mr-2">•</span>
              {episode.download_count ? episode.download_count : 0} {episode.download_count === 1 ? 'download' : 'downloads'}
            </span>
          </div>

          {/* Bottom Controls - only show if episode is whitelisted */}
          {episode.whitelisted && (
            <div className="flex items-center gap-2">
              <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
                <DownloadButton
                  episodeGuid={episode.guid}
                  isWhitelisted={episode.whitelisted}
                  hasProcessedAudio={episode.has_processed_audio}
                  feedId={feedId}
                  canModifyEpisodes={canModifyEpisodes}
                  className="min-w-[100px] shrink-0"
                />

                <EpisodeProcessingStatus
                  episodeGuid={episode.guid}
                  isWhitelisted={episode.whitelisted}
                  hasProcessedAudio={episode.has_processed_audio}
                  feedId={feedId}
                />

                {episode.has_processed_audio && episode.processing_failed && (
                  <span
                    className="shrink-0 rounded-full bg-red-50 px-2 py-1 text-xs font-medium text-red-700"
                    title="Ad detection did not finish. The episode was published without ad removal; reprocess it to try again."
                  >
                    Processing failed
                  </span>
                )}

                <ProcessingStatsButton
                  episodeGuid={episode.guid}
                  hasProcessedAudio={episode.has_processed_audio}
                  adDetectionStrategy={adDetectionStrategy}
                />
              </div>

              {episode.has_processed_audio && (
                <PlayButton
                  episode={episode}
                  className="ml-auto shrink-0"
                />
              )}
            </div>
          )}
        </div>
      </div>
  );
}

export default memo(EpisodeRow);

// Placeholder shaped like an EpisodeRow, so the list reads as arriving rather
// than missing while the phone panel slides in or the first page loads.
export function EpisodeRowSkeleton() {
  return (
    <div className="p-4" aria-hidden="true">
      <div className="flex items-start gap-3">
        <div className="h-16 w-16 shrink-0 rounded-lg bg-gray-100" />
        <div className="flex-1 space-y-2 pt-1">
          <div className="h-4 w-3/4 rounded bg-gray-100" />
          <div className="h-3 w-1/3 rounded bg-gray-100" />
        </div>
      </div>
      <div className="mt-3 space-y-2">
        <div className="h-3 w-full rounded bg-gray-100" />
        <div className="h-3 w-5/6 rounded bg-gray-100" />
      </div>
      <div className="mt-3 flex gap-2">
        <div className="h-5 w-16 rounded-full bg-gray-100" />
        <div className="h-5 w-24 rounded-full bg-gray-100" />
      </div>
      <div className="mt-3 flex items-center gap-2">
        <div className="h-[30px] w-20 rounded-md bg-gray-100" />
        <div className="h-[30px] w-20 rounded-md bg-gray-100" />
        <div className="h-[30px] w-14 rounded-md bg-gray-100" />
        <div className="ml-auto h-8 w-8 rounded-full bg-gray-100" />
      </div>
    </div>
  );
}
