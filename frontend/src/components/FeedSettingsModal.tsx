import { useState, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { feedsApi } from '../services/api';
import type { Feed, FeedSettingsUpdate } from '../types';

interface FeedSettingsModalProps {
  feed: Feed;
  isOpen: boolean;
  onClose: () => void;
  autoWhitelistGlobalDefault?: boolean;
  llmChapterFallbackGlobalDefault?: boolean;
  episodeDescriptionView?: 'source' | 'podly';
  onEpisodeDescriptionViewChange?: (view: 'source' | 'podly') => void;
}

const DEFAULT_FILTER_STRINGS = 'sponsor,advertisement,ad break,promo,brought to you by';

export default function FeedSettingsModal({
  feed,
  isOpen,
  onClose,
  autoWhitelistGlobalDefault,
  llmChapterFallbackGlobalDefault,
  episodeDescriptionView = 'source',
  onEpisodeDescriptionViewChange,
}: FeedSettingsModalProps) {
  const queryClient = useQueryClient();

  const [strategy, setStrategy] = useState<'llm' | 'chapter' | 'chapter_insert'>(
    feed.ad_detection_strategy || 'llm'
  );
  const [filterStrings, setFilterStrings] = useState(
    feed.chapter_filter_strings || DEFAULT_FILTER_STRINGS
  );
  const [chapterFallbackOverride, setChapterFallbackOverride] = useState<
    'inherit' | 'on' | 'off'
  >(
    feed.enable_llm_chapter_fallback_tagging === true
      ? 'on'
      : feed.enable_llm_chapter_fallback_tagging === false
        ? 'off'
        : 'inherit'
  );
  const [autoWhitelistOverride, setAutoWhitelistOverride] = useState<'inherit' | 'on' | 'off'>(
    feed.auto_whitelist_new_episodes_override === true
      ? 'on'
      : feed.auto_whitelist_new_episodes_override === false
        ? 'off'
        : 'inherit'
  );
  const [customLlmAdPrompt, setCustomLlmAdPrompt] = useState<string>(
    feed.custom_llm_ad_prompt || ''
  );

  useEffect(() => {
    setStrategy(feed.ad_detection_strategy || 'llm');
    setFilterStrings(feed.chapter_filter_strings || DEFAULT_FILTER_STRINGS);
    setChapterFallbackOverride(
      feed.enable_llm_chapter_fallback_tagging === true
        ? 'on'
        : feed.enable_llm_chapter_fallback_tagging === false
          ? 'off'
          : 'inherit'
    );
    setAutoWhitelistOverride(
      feed.auto_whitelist_new_episodes_override === true
        ? 'on'
        : feed.auto_whitelist_new_episodes_override === false
          ? 'off'
          : 'inherit'
    );
    setCustomLlmAdPrompt(feed.custom_llm_ad_prompt || '');
  }, [feed, llmChapterFallbackGlobalDefault]);

  const updateMutation = useMutation({
    mutationFn: (settings: FeedSettingsUpdate) =>
      feedsApi.updateFeedSettings(feed.id, settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
      onClose();
    },
  });

  const currentStrategy = feed.ad_detection_strategy || 'llm';
  const currentFilterStrings = feed.chapter_filter_strings || DEFAULT_FILTER_STRINGS;
  const currentChapterFallbackOverride =
    feed.enable_llm_chapter_fallback_tagging === true
      ? 'on'
      : feed.enable_llm_chapter_fallback_tagging === false
        ? 'off'
        : 'inherit';
  const currentAutoWhitelistOverride =
    feed.auto_whitelist_new_episodes_override === true
      ? 'on'
      : feed.auto_whitelist_new_episodes_override === false
        ? 'off'
        : 'inherit';

  const handleSave = () => {
    const settings: FeedSettingsUpdate = {};

    if (strategy !== currentStrategy) {
      settings.ad_detection_strategy = strategy;
    }

    if (strategy === 'chapter' && filterStrings !== currentFilterStrings) {
      settings.chapter_filter_strings = filterStrings || null;
    }

    if (
      strategy !== 'chapter_insert' &&
      chapterFallbackOverride !== currentChapterFallbackOverride
    ) {
      settings.enable_llm_chapter_fallback_tagging =
        chapterFallbackOverride === 'inherit'
          ? null
          : chapterFallbackOverride === 'on';
    }

    if (autoWhitelistOverride !== currentAutoWhitelistOverride) {
      settings.auto_whitelist_new_episodes_override =
        autoWhitelistOverride === 'inherit' ? null : autoWhitelistOverride === 'on';
    }

    const currentCustomPrompt = feed.custom_llm_ad_prompt || '';
    if (customLlmAdPrompt !== currentCustomPrompt) {
      settings.custom_llm_ad_prompt = customLlmAdPrompt || null;
    }

    if (Object.keys(settings).length === 0) {
      onClose();
      return;
    }

    updateMutation.mutate(settings);
  };

  const autoWhitelistDefaultLabel =
    autoWhitelistGlobalDefault === undefined
      ? 'Unknown'
      : autoWhitelistGlobalDefault
        ? 'On'
        : 'Off';
  const chapterFallbackGlobalDefaultLabel =
    llmChapterFallbackGlobalDefault === undefined
      ? 'Unknown'
      : llmChapterFallbackGlobalDefault
        ? 'On'
        : 'Off';
  const isChapterFallbackLocked = strategy === 'chapter_insert';

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      <div className="relative w-full max-w-md bg-white rounded-xl border border-gray-200 shadow-lg overflow-hidden">
        <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-gray-200">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Feed Settings</h2>
            <p className="text-sm text-gray-600 mt-1">
              Settings for "{feed.title}"
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Ad Detection Strategy
            </label>
            <select
              value={strategy}
              onChange={(e) =>
                setStrategy(e.target.value as 'llm' | 'chapter' | 'chapter_insert')
              }
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            >
              <option value="llm">LLM (AI-based)</option>
              <option value="chapter">Chapter-based</option>
              <option value="chapter_insert">
                Chapter insertion only (no ad removal)
              </option>
            </select>
            <p className="text-xs text-gray-500 mt-1">
              {strategy === 'llm'
                ? 'Uses AI transcription and classification to detect ads'
                : strategy === 'chapter'
                  ? 'Removes chapters matching filter strings (requires chapter metadata). Uses CBR encoding for accurate chapter seeking, instead of the default VBR.'
                  : 'Preserves audio and only inserts chapter metadata into the processed file/output description.'}
            </p>

            {strategy === 'chapter' && (
              <div className="mt-3 ml-3 pl-3 border-l-2 border-gray-200">
                <label className="block text-xs text-gray-600 mb-1">
                  Filter Strings
                </label>
                <textarea
                  value={filterStrings}
                  onChange={(e) => setFilterStrings(e.target.value)}
                  placeholder="sponsor,advertisement,ad break"
                  rows={3}
                  className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Comma-separated list. Chapters containing any of these will be removed (case-insensitive).
                </p>
              </div>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Auto-whitelist new episodes
            </label>
            <select
              value={autoWhitelistOverride}
              onChange={(e) =>
                setAutoWhitelistOverride(e.target.value as 'inherit' | 'on' | 'off')
              }
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-500"
            >
              <option value="inherit">
                Use global setting ({autoWhitelistDefaultLabel})
              </option>
              <option value="on">On</option>
              <option value="off">Off</option>
            </select>
            <p className="text-xs text-gray-500 mt-1">
              Overrides the global setting for this feed.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              LLM-Based chapter tagging
            </label>
            <select
              value={isChapterFallbackLocked ? 'on' : chapterFallbackOverride}
              disabled={isChapterFallbackLocked}
              onChange={(e) =>
                setChapterFallbackOverride(
                  e.target.value as 'inherit' | 'on' | 'off'
                )
              }
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-500"
            >
              <option value="inherit">
                Use global setting ({chapterFallbackGlobalDefaultLabel})
              </option>
              <option value="on">On</option>
              <option value="off">Off</option>
            </select>
            <p className="text-xs text-gray-500 mt-1">
              Preserves embedded chapters when available, otherwise falls back
              to description or transcript-derived chapters during LLM
              processing.
            </p>
            {isChapterFallbackLocked && (
              <p className="text-xs text-blue-700 mt-2">
                Chapter insertion mode requires chapter fallback tagging, so
                this setting is locked on.
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Custom Ad Detection Instructions
            </label>
            <textarea
              value={customLlmAdPrompt}
              onChange={(e) => setCustomLlmAdPrompt(e.target.value)}
              placeholder="e.g. Ads appear only in first 30 seconds of the podcast. If they are not detected in this initial segment, do not look any further and assume rest is ads free."
              rows={4}
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            />
            <p className="text-xs text-gray-500 mt-1">
              Optional custom instructions appended to the LLM system prompt
              for ad detection. Use this to guide the LLM based on your
              podcast's specific ad patterns.
            </p>
          </div>

          <div className="border-t border-gray-200" />

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Episode description preview
            </label>
            <select
              value={episodeDescriptionView}
              onChange={(e) =>
                onEpisodeDescriptionViewChange?.(
                  e.target.value as 'source' | 'podly'
                )
              }
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            >
              <option value="source">Source description</option>
              <option value="podly">Podly description preview</option>
            </select>
            <p className="text-xs text-gray-500 mt-1">
              Uses the same composed description as the Podly RSS feed (source
              description + Podly chapters). This affects only the UI preview
              and does not change source RSS content.
            </p>
          </div>

          {updateMutation.isError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-700">
                Failed to save settings. Please try again.
              </p>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 px-5 py-4 border-t border-gray-200 bg-gray-50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={updateMutation.isPending}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {updateMutation.isPending ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
