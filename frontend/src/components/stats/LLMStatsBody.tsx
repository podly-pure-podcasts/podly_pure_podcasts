import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { feedsApi } from '../../services/api';
import { useDelayedFlag } from '../../hooks/useDelayedFlag';
import { useStatsReveal } from '../../hooks/useStatsReveal';
import ProcessingTimelineSummaryCard from '../ProcessingTimelineSummaryCard';
import { formatBackendDateTime } from '../../utils/datetime';
import {
  formatTimelineLabel,
  formatTimelineRange,
} from '../../utils/processingTimeline';
import {
  StatsHeader,
  StatsTabBarPlaceholder,
  StatsTabBarShell,
} from './StatsLoadingFrame';
import ShowMoreRows, { ROW_PAGE_SIZE } from './ShowMoreRows';

interface LLMStatsBodyProps {
  episodeGuid: string;
  onClose: () => void;
}

type TabId = 'overview' | 'model-calls' | 'transcript' | 'identifications';

function getFallbackDurationSeconds(transcriptSegments: Array<{ end_time: number }> | undefined) {
  const candidates = (transcriptSegments || []).map((segment) => segment.end_time);
  return candidates.length ? Math.max(...candidates) : 0;
}

export default function LLMStatsBody({ episodeGuid, onClose }: LLMStatsBodyProps) {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [expandedModelCalls, setExpandedModelCalls] = useState<Set<number>>(new Set());
  const [visibleRows, setVisibleRows] = useState(ROW_PAGE_SIZE);
  const selectTab = (tab: TabId) => {
    setActiveTab(tab);
    setVisibleRows(ROW_PAGE_SIZE);
  };
  const showMoreRows = () => setVisibleRows((count) => count + ROW_PAGE_SIZE);

  const { data: stats, isLoading, error } = useQuery({
    queryKey: ['episode-stats', episodeGuid],
    queryFn: () => feedsApi.getPostStats(episodeGuid),
  });
  // Fast responses skip the spinner rather than flashing it.
  const showSpinner = useDelayedFlag(isLoading, 250);
  const overviewRef = useStatsReveal(true, Boolean(stats) && activeTab === 'overview');

  const formatDuration = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.round(seconds % 60);

    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`;
    }
    return `${minutes}m ${secs}s`;
  };

  const formatTimestamp = (timestamp: string | null) => {
    if (!timestamp) return 'N/A';
    return formatBackendDateTime(timestamp);
  };

  const formatBytes = (bytes: number | null) => {
    if (bytes === null || Number.isNaN(bytes)) return 'unknown';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const toggleModelCallDetails = (callId: number) => {
    const newExpanded = new Set(expandedModelCalls);
    if (newExpanded.has(callId)) {
      newExpanded.delete(callId);
    } else {
      newExpanded.add(callId);
    }
    setExpandedModelCalls(newExpanded);
  };

  const getAdConfidence = (segment: {
    identifications?: Array<{ label: string; confidence: number | null }>;
  }) => {
    const adConfidences = (segment.identifications || [])
      .filter((identification) => identification.label === 'ad' && identification.confidence !== null)
      .map((identification) => identification.confidence as number);

    if (!adConfidences.length) {
      return null;
    }

    return Math.max(...adConfidences);
  };

  const transcriptSegments = stats?.transcript_segments;
  // Published without ad removal: ads were detected, not cut.
  const notRemoved = Boolean(stats?.post?.processing_failed);
  const contentViewKey = isLoading
    ? 'loading'
    : error
      ? 'error'
      : stats
        ? activeTab
        : 'empty';
  const apiAdBlocks = useMemo(
    () => (stats?.processing_stats?.ad_blocks || []).map((block) => ({
      startTime: block.start_time,
      endTime: block.end_time,
    })),
    [stats?.processing_stats?.ad_blocks]
  );
  const mergedFallbackAdBlocks = useMemo(() => {
    if (apiAdBlocks.length) return [];
    const blocks = (transcriptSegments || [])
      .filter((segment) => segment.primary_label === 'ad')
      .map((segment) => ({ startTime: segment.start_time, endTime: segment.end_time }))
      .sort((a, b) => a.startTime - b.startTime);
    return blocks.reduce<Array<{ startTime: number; endTime: number }>>((merged, segment) => {
      if (!merged.length) {
        return [{ ...segment }];
      }

      const current = merged[merged.length - 1];
      if (segment.startTime <= current.endTime + 1) {
        current.endTime = Math.max(current.endTime, segment.endTime);
        return merged;
      }

      merged.push({ ...segment });
      return merged;
    }, []);
  }, [apiAdBlocks, transcriptSegments]);
  const adBlocks = apiAdBlocks.length ? apiAdBlocks : mergedFallbackAdBlocks;
  const adTimeSeconds = stats?.processing_stats?.estimated_ad_time_seconds
    ?? adBlocks.reduce((sum, block) => sum + Math.max(0, block.endTime - block.startTime), 0);
  const originalDurationSeconds = stats?.processing_stats?.original_duration_seconds
    || (
      stats?.post?.duration != null
        ? stats.post.duration + (notRemoved ? 0 : adTimeSeconds)
        : getFallbackDurationSeconds(transcriptSegments)
    );
  const reportedOriginalSeconds = stats?.processing_stats?.original_duration_seconds;
  const hasOriginalDuration =
    !notRemoved &&
    reportedOriginalSeconds != null &&
    stats?.post?.duration != null &&
    Math.abs(reportedOriginalSeconds - stats.post.duration) > 1;
  const estimatedCost = stats?.processing_stats?.estimated_cost;
  const hasCost = estimatedCost != null;
  const adPercent = stats?.processing_stats?.ad_percentage
    ?? (originalDurationSeconds > 0 ? (adTimeSeconds / originalDurationSeconds) * 100 : 0);
  const adTimelineSegments = useMemo(() => adBlocks.map((block) => ({
    startTime: block.startTime,
    endTime: block.endTime,
    kind: 'range' as const,
    tooltipTitle: notRemoved ? 'Detected ad break' : 'Removed ad break',
    tooltipRows: [
      {
        label: 'Original',
        value: formatTimelineRange(block.startTime, block.endTime),
      },
      {
        label: 'Length',
        value: formatTimelineLabel(Math.max(0, block.endTime - block.startTime)),
      },
    ],
    ariaLabel: [
      notRemoved ? 'Detected ad break.' : 'Removed ad break.',
      `Original range ${formatTimelineRange(block.startTime, block.endTime)}.`,
    ].join(' '),
  })), [adBlocks, notRemoved]);

  return (
    <>
            <StatsHeader onClose={onClose} />

            <StatsTabBarShell>
              {/* Tabs and their counts depend on the stats, so placeholders hold the
                  bar's height until they land instead of tabs shifting in. */}
              {stats ? (
                <nav role="tablist" className="podly-tab-panel-enter flex min-w-max space-x-8 px-6">
                  {[
                    { id: 'overview', label: 'Overview' },
                    { id: 'model-calls', label: 'Model calls' },
                    { id: 'transcript', label: 'Transcript segments' },
                    { id: 'identifications', label: 'Identifications' },
                  ].map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      role="tab"
                      aria-selected={activeTab === tab.id}
                      onClick={() => selectTab(tab.id as TabId)}
                      className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                        activeTab === tab.id
                          ? 'border-blue-600 text-blue-700'
                          : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                      } shrink-0 whitespace-nowrap`}
                    >
                      {tab.label}
                      {stats && tab.id === 'model-calls' && stats.model_calls && ` (${stats.model_calls.length})`}
                      {stats && tab.id === 'transcript' && stats.transcript_segments && ` (${stats.transcript_segments.length})`}
                      {stats && tab.id === 'identifications' && stats.identifications && ` (${stats.identifications.length})`}
                    </button>
                  ))}
                </nav>
              ) : (
                <StatsTabBarPlaceholder />
              )}
            </StatsTabBarShell>

            <div className="flex-1 min-h-0 overflow-y-auto p-6">
              <div
                key={contentViewKey}
                className="podly-tab-panel-enter min-h-full"
              >
              {isLoading ? (
                showSpinner && <div className="flex min-h-full items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                  <span className="ml-3 text-gray-600">Loading stats...</span>
                </div>
              ) : error ? (
                <div className="flex min-h-full items-center justify-center text-center py-12">
                  <p className="text-red-600">Failed to load processing statistics</p>
                </div>
              ) : stats ? (
                <>
                  {activeTab === 'overview' && (
                    <div ref={overviewRef} className="space-y-6">
                      <div className="bg-gray-50 rounded-lg p-4">
                        <h3 className="font-semibold text-gray-900 mb-2 text-left">Episode information</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                          <div className="text-left">
                            <span className="font-medium text-gray-700">Title:</span>
                            <span className="ml-2 text-gray-600">{stats.post?.title || 'Unknown'}</span>
                          </div>
                          <div className="text-left">
                            <span className="font-medium text-gray-700">{hasOriginalDuration ? 'Length:' : 'Duration:'}</span>
                            <span className="ml-2 text-gray-600">
                              {stats.post?.duration
                                ? hasOriginalDuration
                                  ? `${formatDuration(stats.post.duration)} after cuts (original ${formatTimelineLabel(originalDurationSeconds)})`
                                  : formatDuration(stats.post.duration)
                                : 'Unknown'}
                            </span>
                          </div>
                          <div className="text-left">
                            <span className="font-medium text-gray-700">Detection method:</span>
                            <span className="ml-2 px-2 py-0.5 rounded text-xs font-medium bg-sky-100 text-sky-800">
                              LLM transcription
                            </span>
                          </div>
                          {hasCost && (
                            <div className="text-left">
                              <span className="font-medium text-gray-700">Estimated cost:</span>
                              <span className="ml-2 text-gray-600 tabular-nums">${estimatedCost.toFixed(4)}</span>
                            </div>
                          )}
                        </div>
                      </div>

                      {notRemoved && (
                        <p className="text-sm text-red-700 text-left">
                          Ad detection did not finish, so this episode was published without ad removal. Reprocess it to try again.
                        </p>
                      )}

                      <ProcessingTimelineSummaryCard
                        title={notRemoved ? 'Ad detection summary' : 'Ad removal summary'}
                        itemCount={adBlocks.length}
                        itemLabel="Ad breaks"
                        totalTimeSeconds={adTimeSeconds}
                        totalTimeLabel={notRemoved ? 'Ad time detected' : 'Time removed'}
                        percentage={adPercent}
                        percentageLabel={notRemoved ? 'Of episode' : 'Of original audio'}
                        durationSeconds={originalDurationSeconds}
                        timelineDurationSeconds={originalDurationSeconds}
                        minimumSegmentWidthPx={10}
                        segments={adTimelineSegments}
                        segmentClassName="bg-red-500"
                        legendBaseLabel="Content"
                        legendSegmentLabel={notRemoved ? 'Ads detected' : 'Ad cuts'}
                      />

                      <div>
                        <h3 className="font-semibold text-gray-900 mb-4 text-left">Key metrics</h3>
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                          <div data-stats-tile className="rounded-lg border border-transparent bg-gradient-to-br from-blue-50 to-blue-100 p-4 text-center dark:border-[rgb(30_64_175/0.7)] dark:from-blue-950 dark:to-slate-900">
                            <div className="text-2xl font-bold tabular-nums tracking-tight text-blue-600">
                              {(stats.processing_stats?.total_segments || 0).toLocaleString()}
                            </div>
                            <div className="text-sm text-blue-800">Transcript lines</div>
                          </div>

                          <div data-stats-tile className="rounded-lg border border-transparent bg-gradient-to-br from-green-50 to-green-100 p-4 text-center dark:border-[rgb(22_101_52/0.7)] dark:from-green-950 dark:to-slate-900">
                            <div className="text-2xl font-bold tabular-nums tracking-tight text-green-600">
                              {(stats.processing_stats?.content_segments || 0).toLocaleString()}
                            </div>
                            <div className="text-sm text-green-800">Content lines</div>
                          </div>

                          <div data-stats-tile className="rounded-lg border border-transparent bg-gradient-to-br from-red-50 to-red-100 p-4 text-center dark:border-[rgb(153_27_27/0.7)] dark:from-red-950 dark:to-slate-900">
                            <div className="text-2xl font-bold tabular-nums tracking-tight text-red-600">
                              {(stats.processing_stats?.ad_segments_count || 0).toLocaleString()}
                            </div>
                            <div className="text-sm text-red-800">{notRemoved ? 'Ad lines detected' : 'Ad lines removed'}</div>
                          </div>
                        </div>
                      </div>

                      {stats.debug_info && (
                        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                          <h3 className="font-semibold text-gray-900 mb-2 text-left">Debug details</h3>
                          <p className="text-xs text-gray-600 mb-4 text-left">
                            Visible because <code>PODLY_STATS_DEBUG</code> is enabled.
                          </p>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                            <div className="text-left">
                              <span className="font-medium text-gray-700">GUID:</span>
                              <span className="ml-2 text-gray-600 font-mono break-all">{stats.debug_info.guid}</span>
                            </div>
                            <div className="text-left">
                              <span className="font-medium text-gray-700">Post ID / Feed ID:</span>
                              <span className="ml-2 text-gray-600">{stats.debug_info.post_id} / {stats.debug_info.feed_id}</span>
                            </div>
                            <div className="text-left md:col-span-2">
                              <span className="font-medium text-gray-700">Download URL:</span>
                              <span className="ml-2 text-gray-600 font-mono break-all">{stats.debug_info.download_url}</span>
                            </div>
                            <div className="text-left md:col-span-2">
                              <span className="font-medium text-gray-700">Processed audio path:</span>
                              <span className="ml-2 text-gray-600 font-mono break-all">
                                {stats.debug_info.processed_audio.path || 'missing'}
                              </span>
                              <div className="text-xs text-gray-500 mt-1">
                                {stats.debug_info.processed_audio.exists
                                  ? `exists (${formatBytes(stats.debug_info.processed_audio.size_bytes)})`
                                  : 'missing'}
                              </div>
                            </div>
                            <div className="text-left md:col-span-2">
                              <span className="font-medium text-gray-700">Unprocessed audio path:</span>
                              <span className="ml-2 text-gray-600 font-mono break-all">
                                {stats.debug_info.unprocessed_audio.path || 'missing'}
                              </span>
                              <div className="text-xs text-gray-500 mt-1">
                                {stats.debug_info.unprocessed_audio.exists
                                  ? `exists (${formatBytes(stats.debug_info.unprocessed_audio.size_bytes)})`
                                  : 'missing'}
                              </div>
                            </div>
                            <div className="text-left md:col-span-2">
                              <span className="font-medium text-gray-700">Data roots:</span>
                              <span className="ml-2 text-gray-600 font-mono break-all">
                                in: {stats.debug_info.processing_roots.in_root} | srv: {stats.debug_info.processing_roots.srv_root}
                              </span>
                            </div>
                            <div className="text-left">
                              <span className="font-medium text-gray-700">Record counts:</span>
                              <span className="ml-2 text-gray-600">
                                segments {stats.debug_info.record_counts.transcript_segments}, calls {stats.debug_info.record_counts.model_calls}, ids {stats.debug_info.record_counts.identifications}
                              </span>
                            </div>
                          </div>

                          <div className="mt-4">
                            <h4 className="font-medium text-gray-900 mb-2 text-left">Processed audio path candidates</h4>
                            {(stats.debug_info.processed_audio_path_candidates || []).length === 0 ? (
                              <p className="text-xs text-gray-500 text-left">No candidates derived.</p>
                            ) : (
                              <div className="space-y-2">
                                {(stats.debug_info.processed_audio_path_candidates || []).map((candidate, idx) => (
                                  <div key={`${candidate.path}-${idx}`} className="bg-surface rounded p-2">
                                    <div className="font-mono text-xs text-gray-700 break-all text-left">{candidate.path}</div>
                                    <div className="text-xs text-gray-500 mt-1 text-left">
                                      {candidate.exists ? `exists (${formatBytes(candidate.size_bytes)})` : 'missing'}
                                      {candidate.error ? ` - ${candidate.error}` : ''}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      <div>
                        <h3 className="font-semibold text-gray-900 mb-4 text-left">LLM performance</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                          <div className="bg-surface border rounded-lg p-4">
                            <h4 className="font-medium text-gray-900 mb-3 text-left">Processing status</h4>
                            <div className="space-y-2">
                              {Object.entries(stats.processing_stats?.model_call_statuses || {}).map(([status, count]) => (
                                <div key={status} className="flex justify-between items-center">
                                  <span className="text-sm text-gray-600 capitalize">{status}</span>
                                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                                    status === 'success' ? 'bg-green-100 text-green-800' :
                                    status === 'failed' ? 'bg-red-100 text-red-800' :
                                    'bg-gray-100 text-gray-800'
                                  }`}>
                                    {count}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>

                          <div className="bg-surface border rounded-lg p-4">
                            <h4 className="font-medium text-gray-900 mb-3 text-left">Models used</h4>
                            <div className="space-y-2">
                              {Object.entries(stats.processing_stats?.model_types || {}).map(([model, count]) => (
                                <div key={model} className="flex justify-between items-center">
                                  <span className="text-sm text-gray-600">{model}</span>
                                  <span className="px-2 py-1 bg-sky-100 text-sky-800 rounded-full text-xs font-medium">
                                    {count} {count === 1 ? 'call' : 'calls'}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {activeTab === 'model-calls' && (
                    <div>
                      <h3 className="font-semibold text-gray-900 mb-4 text-left">Model calls ({stats.model_calls?.length || 0})</h3>
                      <div className="bg-surface border rounded-lg overflow-hidden">
                        <div className="overflow-x-auto">
                          <table className="min-w-full divide-y divide-gray-200">
                            <thead>
                              <tr>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">ID</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Model</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Segment range</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Status</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Tier</th>
                                <th className="px-4 py-3 text-right text-xs font-medium text-gray-600">Tokens</th>
                                {hasCost && (
                                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-600">Cost</th>
                                )}
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Timestamp</th>
                                <th className="px-4 py-3 text-right text-xs font-medium text-gray-600">Retries</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Actions</th>
                              </tr>
                            </thead>
                            <tbody className="bg-surface divide-y divide-gray-200">
                              {(stats.model_calls || []).map((call) => (
                                <>
                                  <tr key={call.id} className="hover:bg-gray-50">
                                    <td className="px-4 py-3 text-sm text-gray-900">{call.id}</td>
                                    <td className="px-4 py-3 text-sm text-gray-900">{call.model_name}</td>
                                    <td className="px-4 py-3 text-sm text-gray-600">{call.segment_range}</td>
                                    <td className="px-4 py-3">
                                      <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                                        call.status === 'success' ? 'bg-green-100 text-green-800' :
                                        call.status === 'failed' || call.status === 'failed_permanent' || call.status === 'failed_retries' ? 'bg-red-100 text-red-800' :
                                        call.status === 'cancelled' ? 'bg-gray-200 text-gray-700' :
                                        call.status === 'retrying' ? 'bg-amber-100 text-amber-800' :
                                        'bg-amber-100 text-amber-800'
                                      }`}>
                                        {call.status}
                                      </span>
                                    </td>
                                    <td className="px-4 py-3 text-sm text-gray-600">{call.service_tier ?? '—'}</td>
                                    <td
                                      className="px-4 py-3 text-right text-sm tabular-nums text-gray-600"
                                      title={
                                        call.prompt_tokens != null
                                          ? `${call.prompt_tokens.toLocaleString()} prompt (${(call.cached_prompt_tokens ?? 0).toLocaleString()} cached), ${(call.completion_tokens ?? 0).toLocaleString()} completion`
                                          : undefined
                                      }
                                    >
                                      {call.total_tokens != null ? call.total_tokens.toLocaleString() : '—'}
                                    </td>
                                    {hasCost && (
                                      <td className="px-4 py-3 text-right text-sm tabular-nums text-gray-600">
                                        {call.estimated_cost_usd != null ? `$${call.estimated_cost_usd.toFixed(4)}` : '—'}
                                      </td>
                                    )}
                                    <td className="px-4 py-3 text-sm text-gray-600">{formatTimestamp(call.timestamp)}</td>
                                    <td className="px-4 py-3 text-right text-sm tabular-nums text-gray-600">{call.retry_attempts}</td>
                                    <td className="px-4 py-3">
                                      <button
                                        onClick={() => toggleModelCallDetails(call.id)}
                                        className="btn btn-secondary btn-sm"
                                      >
                                        {expandedModelCalls.has(call.id) ? 'Hide' : 'Details'}
                                      </button>
                                    </td>
                                  </tr>
                                  {expandedModelCalls.has(call.id) && (
                                    <tr className="bg-gray-50">
                                      <td colSpan={hasCost ? 10 : 9} className="px-4 py-4">
                                        <div className="space-y-4">
                                          {call.prompt && (
                                            <div>
                                              <h5 className="font-medium text-gray-900 mb-2 text-left">Prompt:</h5>
                                              <div className="bg-gray-100 p-3 rounded text-sm whitespace-pre-wrap max-h-40 overflow-y-auto text-left">
                                                {call.prompt}
                                              </div>
                                            </div>
                                          )}
                                          {call.error_message && (
                                            <div>
                                              <h5 className="font-medium text-red-900 mb-2 text-left">Error message:</h5>
                                              <div className="bg-red-50 p-3 rounded text-sm font-mono whitespace-pre-wrap text-left">
                                                {call.error_message}
                                              </div>
                                            </div>
                                          )}
                                          {call.response && (
                                            <div>
                                              <h5 className="font-medium text-gray-900 mb-2 text-left">Response:</h5>
                                              <div className="bg-gray-100 p-3 rounded text-sm whitespace-pre-wrap max-h-40 overflow-y-auto text-left">
                                                {call.response}
                                              </div>
                                            </div>
                                          )}
                                        </div>
                                      </td>
                                    </tr>
                                  )}
                                </>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  )}

                  {activeTab === 'transcript' && (
                    <div>
                      <h3 className="font-semibold text-gray-900 mb-4 text-left">Transcript segments ({stats.transcript_segments?.length || 0})</h3>
                      <div className="bg-surface border rounded-lg overflow-hidden">
                        <div className="overflow-x-auto">
                          <table className="min-w-full divide-y divide-gray-200">
                            <thead>
                              <tr>
                                <th className="px-4 py-3 text-right text-xs font-medium text-gray-600">Seq #</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Time range</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Label</th>
                                <th className="px-4 py-3 text-right text-xs font-medium text-gray-600">Ad confidence</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Text</th>
                              </tr>
                            </thead>
                            <tbody className="bg-surface divide-y divide-gray-200">
                              {(transcriptSegments || []).slice(0, visibleRows).map((segment) => {
                                const adConfidence = getAdConfidence(segment);

                                return (
                                  <tr key={segment.id} className={`hover:bg-gray-50 ${
                                    segment.primary_label === 'ad' ? 'bg-red-50' : ''
                                  }`}>
                                    <td className="px-4 py-3 text-sm text-gray-900">{segment.sequence_num}</td>
                                    <td className="px-4 py-3 text-sm text-gray-600">
                                      {segment.start_time}s - {segment.end_time}s
                                    </td>
                                    <td className="px-4 py-3">
                                      <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                                        segment.primary_label === 'ad'
                                          ? 'bg-red-100 text-red-800'
                                          : 'bg-green-100 text-green-800'
                                      }`}>
                                        {segment.primary_label === 'ad'
                                          ? (segment.mixed ? 'Ad (mixed)' : 'Ad')
                                          : 'Content'}
                                      </span>
                                    </td>
                                    <td className="px-4 py-3 text-right text-sm tabular-nums text-gray-600">
                                      {adConfidence !== null ? adConfidence.toFixed(2) : '-'}
                                    </td>
                                    <td className="px-4 py-3 text-sm text-gray-900 min-w-[28rem] max-w-4xl">
                                      <div className="whitespace-pre-wrap break-words text-left leading-6">
                                        {segment.text}
                                      </div>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                      <ShowMoreRows shown={visibleRows} total={(transcriptSegments || []).length} onShowMore={showMoreRows} />
                    </div>
                  )}

                  {activeTab === 'identifications' && (
                    <div>
                      <h3 className="font-semibold text-gray-900 mb-4 text-left">Identifications ({stats.identifications?.length || 0})</h3>
                      <div className="bg-surface border rounded-lg overflow-hidden">
                        <div className="overflow-x-auto">
                          <table className="min-w-full divide-y divide-gray-200">
                            <thead>
                              <tr>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">ID</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Segment ID</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Time range</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Label</th>
                                <th className="px-4 py-3 text-right text-xs font-medium text-gray-600">Confidence</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Model call</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Text</th>
                              </tr>
                            </thead>
                            <tbody className="bg-surface divide-y divide-gray-200">
                              {(stats.identifications || []).slice(0, visibleRows).map((identification) => (
                                <tr key={identification.id} className={`hover:bg-gray-50 ${
                                  identification.label === 'ad' ? 'bg-red-50' : ''
                                }`}>
                                  <td className="px-4 py-3 text-sm text-gray-900">{identification.id}</td>
                                  <td className="px-4 py-3 text-sm text-gray-600">{identification.transcript_segment_id}</td>
                                  <td className="px-4 py-3 text-sm text-gray-600">
                                    {identification.segment_start_time}s - {identification.segment_end_time}s
                                  </td>
                                  <td className="px-4 py-3">
                                    <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                                      identification.label === 'ad'
                                        ? 'bg-red-100 text-red-800'
                                        : 'bg-green-100 text-green-800'
                                    }`}>
                                      {identification.label === 'ad'
                                        ? (identification.mixed ? 'ad (mixed)' : 'ad')
                                        : identification.label}
                                    </span>
                                  </td>
                                  <td className="px-4 py-3 text-right text-sm tabular-nums text-gray-600">
                                    {identification.confidence ? identification.confidence.toFixed(2) : 'N/A'}
                                  </td>
                                  <td className="px-4 py-3 text-sm text-gray-600">{identification.model_call_id}</td>
                                  <td className="px-4 py-3 text-sm text-gray-900 max-w-md">
                                    <div className="truncate text-left" title={identification.segment_text}>
                                      {identification.segment_text}
                                    </div>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                      <ShowMoreRows shown={visibleRows} total={(stats.identifications || []).length} onShowMore={showMoreRows} />
                    </div>
                  )}
                </>
              ) : null}
              </div>
            </div>
    </>
  );
}
