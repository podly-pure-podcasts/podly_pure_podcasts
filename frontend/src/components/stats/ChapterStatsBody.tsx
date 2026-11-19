import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { feedsApi } from '../../services/api';
import { useDelayedFlag } from '../../hooks/useDelayedFlag';
import { useStatsReveal } from '../../hooks/useStatsReveal';
import { formatTimelineLabel } from '../../utils/processingTimeline';
import {
  StatsHeader,
  StatsTabBarPlaceholder,
  StatsTabBarShell,
} from './StatsLoadingFrame';
import ShowMoreRows, { ROW_PAGE_SIZE } from './ShowMoreRows';

interface ChapterStatsBodyProps {
  episodeGuid: string;
  onClose: () => void;
}

type TabId = 'overview' | 'chapters' | 'transcript';

function getFallbackDurationSeconds(transcriptSegments: Array<{ end_time: number }> | undefined) {
  const candidates = (transcriptSegments || []).map((segment) => segment.end_time);
  return candidates.length ? Math.max(...candidates) : 0;
}

export default function ChapterStatsBody({ episodeGuid, onClose }: ChapterStatsBodyProps) {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
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
  const isChapterInsert = stats?.ad_detection_strategy === 'chapter_insert';
  const showTranscriptTab = isChapterInsert;
  const transcriptSegments = stats?.transcript_segments;
  const modelEntries = useMemo(
    () => Object.entries(stats?.processing_stats?.model_types || {}),
    [stats?.processing_stats?.model_types]
  );

  useEffect(() => {
    if (!showTranscriptTab && activeTab === 'transcript') {
      selectTab('overview');
    }
  }, [activeTab, showTranscriptTab]);

  const formatDuration = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.round(seconds % 60);

    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`;
    }
    return `${minutes}m ${secs}s`;
  };

  const formatBytes = (bytes: number | null) => {
    if (bytes === null || Number.isNaN(bytes)) return 'unknown';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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

  const contentViewKey = isLoading
    ? 'loading'
    : error
      ? 'error'
      : stats
        ? activeTab
        : 'empty';
  const originalDurationSeconds = stats?.processing_stats?.original_duration_seconds
    || (stats?.post?.duration != null ? stats.post.duration : getFallbackDurationSeconds(transcriptSegments));
  const reportedOriginalSeconds = stats?.processing_stats?.original_duration_seconds;
  const hasOriginalDuration =
    reportedOriginalSeconds != null &&
    stats?.post?.duration != null &&
    Math.abs(reportedOriginalSeconds - stats.post.duration) > 1;

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
                    { id: 'chapters', label: 'Chapters' },
                    ...(showTranscriptTab ? [{ id: 'transcript', label: 'Transcript' }] : []),
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
                      {stats && tab.id === 'chapters' && stats.chapters && ` (${stats.chapters.chapters?.length || 0})`}
                      {stats && tab.id === 'transcript' && ` (${stats.transcript_segments?.length || 0})`}
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
                              {isChapterInsert ? 'Chapter insertion only' : 'Chapter-based removal'}
                            </span>
                          </div>
                        </div>
                      </div>

                      <div>
                        <h3 className="font-semibold text-gray-900 mb-4 text-left">Key metrics</h3>
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                          <div data-stats-tile className="rounded-lg border border-transparent bg-gradient-to-br from-purple-50 to-purple-100 p-4 text-center dark:border-purple-800/70 dark:from-purple-950 dark:to-slate-900">
                            <div className="text-2xl font-bold tabular-nums tracking-tight text-purple-600 dark:text-purple-200">
                              {(stats.chapters?.total_chapters || 0).toLocaleString()}
                            </div>
                            <div className="text-sm text-purple-800 dark:text-purple-100">Total chapters</div>
                          </div>

                          <div data-stats-tile className="rounded-lg border border-transparent bg-gradient-to-br from-green-50 to-green-100 p-4 text-center dark:border-[rgb(22_101_52/0.7)] dark:from-green-950 dark:to-slate-900">
                            <div className="text-2xl font-bold tabular-nums tracking-tight text-green-600">
                              {(stats.chapters?.chapters_kept || 0).toLocaleString()}
                            </div>
                            <div className="text-sm text-green-800">
                              {isChapterInsert ? 'Chapters inserted' : 'Chapters kept'}
                            </div>
                          </div>

                          <div data-stats-tile className="rounded-lg border border-transparent bg-gradient-to-br from-red-50 to-red-100 p-4 text-center dark:border-[rgb(153_27_27/0.7)] dark:from-red-950 dark:to-slate-900">
                            <div className="text-2xl font-bold tabular-nums tracking-tight text-red-600">
                              {(stats.chapters?.chapters_removed || 0).toLocaleString()}
                            </div>
                            <div className="text-sm text-red-800">
                              {isChapterInsert ? 'Chapters removed (N/A)' : 'Chapters removed'}
                            </div>
                          </div>
                        </div>
                      </div>

                      {isChapterInsert && (
                        <div className="rounded-lg border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900">
                          Chapter insertion mode keeps audio unchanged and only writes chapter metadata.
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
                                    status === 'failed' || status === 'failed_permanent' || status === 'failed_retries' ? 'bg-red-100 text-red-800' :
                                    status === 'cancelled' ? 'bg-gray-200 text-gray-700' :
                                    status === 'retrying' ? 'bg-amber-100 text-amber-800' :
                                    'bg-gray-100 text-gray-800'
                                  }`}>
                                    {count}
                                  </span>
                                </div>
                              ))}
                              {Object.keys(stats.processing_stats?.model_call_statuses || {}).length === 0 && (
                                <p className="text-sm text-gray-500 text-left">No model calls were recorded for this run.</p>
                              )}
                            </div>
                          </div>

                          <div className="bg-surface border rounded-lg p-4">
                            <h4 className="font-medium text-gray-900 mb-3 text-left">
                              Models used ({stats.processing_stats?.total_model_calls || 0} {stats.processing_stats?.total_model_calls === 1 ? 'call' : 'calls'})
                            </h4>
                            <div className="space-y-2">
                              {modelEntries.map(([model, count]) => (
                                <div key={model} className="flex justify-between items-center gap-4">
                                  <span className="text-sm text-gray-600 break-all text-left">{model}</span>
                                  <span className="px-2 py-1 bg-sky-100 text-sky-800 rounded-full text-xs font-medium shrink-0">
                                    {count} {count === 1 ? 'call' : 'calls'}
                                  </span>
                                </div>
                              ))}
                              {modelEntries.length === 0 && (
                                <p className="text-sm text-gray-500 text-left">No model calls were recorded for this run.</p>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>

                      {!isChapterInsert && (stats.chapters?.filter_strings ?? []).length > 0 && (
                        <div>
                          <h3 className="font-semibold text-gray-900 mb-4 text-left">Filter strings</h3>
                          <div className="bg-surface border rounded-lg p-4">
                            <div className="flex flex-wrap gap-2">
                              {(stats.chapters?.filter_strings ?? []).map((filter: string, idx: number) => (
                                <span key={idx} className="px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-sm">
                                  {filter}
                                </span>
                              ))}
                            </div>
                          </div>
                        </div>
                      )}

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
                    </div>
                  )}

                  {activeTab === 'chapters' && (
                    <div>
                      <h3 className="font-semibold text-gray-900 mb-4 text-left">Chapters ({stats.chapters?.chapters?.length || 0})</h3>
                      <div className="bg-surface border rounded-lg overflow-hidden">
                        <div className="overflow-x-auto">
                          <table className="min-w-full divide-y divide-gray-200">
                            <thead>
                              <tr>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">#</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Title</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Time range</th>
                                <th className="px-4 py-3 text-right text-xs font-medium text-gray-600">Duration</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Status</th>
                              </tr>
                            </thead>
                            <tbody className="bg-surface divide-y divide-gray-200">
                              {(stats.chapters?.chapters || []).map((chapter: { title: string; start_time: number; end_time: number; label: string }, idx: number) => (
                                <tr key={idx} className={`hover:bg-gray-50 ${
                                  chapter.label === 'ad' && !isChapterInsert ? 'bg-red-50' : ''
                                }`}>
                                  <td className="px-4 py-3 text-sm text-gray-900">{idx + 1}</td>
                                  <td className="px-4 py-3 text-sm text-gray-900 font-medium">{chapter.title}</td>
                                  <td className="px-4 py-3 text-sm text-gray-600">
                                    {chapter.start_time}s - {chapter.end_time}s
                                  </td>
                                  <td className="px-4 py-3 text-sm text-gray-600">
                                    {Math.round(chapter.end_time - chapter.start_time)}s
                                  </td>
                                  <td className="px-4 py-3">
                                    <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                                      chapter.label === 'ad'
                                        ? 'bg-red-100 text-red-800'
                                        : 'bg-green-100 text-green-800'
                                    }`}>
                                      {chapter.label === 'ad'
                                        ? (isChapterInsert ? 'Excluded' : 'Removed')
                                        : (isChapterInsert ? 'Included' : 'Kept')}
                                    </span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                      {stats.chapters?.note && (
                        <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
                          Note: {stats.chapters.note}
                        </div>
                      )}
                      {(!stats.chapters?.chapters || stats.chapters.chapters.length === 0) && (
                        <div className="text-center py-8 text-gray-500">
                          No chapter data available.
                        </div>
                      )}
                    </div>
                  )}

                  {activeTab === 'transcript' && (
                    <div>
                      <h3 className="font-semibold text-gray-900 mb-4 text-left">
                        Transcript segments ({stats.transcript_segments?.length || 0})
                      </h3>
                      {(!stats.transcript_segments || stats.transcript_segments.length === 0) ? (
                        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700">
                          No transcript segments were generated for this episode.
                        </div>
                      ) : (
                        <div className="bg-surface border rounded-lg overflow-hidden">
                          <div className="overflow-x-auto">
                            <table className="min-w-full divide-y divide-gray-200">
                              <thead>
                                <tr>
                                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">#</th>
                                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Start</th>
                                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">End</th>
                                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-600">Ad confidence</th>
                                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-600">Text</th>
                                </tr>
                              </thead>
                              <tbody className="bg-surface divide-y divide-gray-200">
                                {(stats.transcript_segments || []).slice(0, visibleRows).map((segment, idx) => {
                                  const adConfidence = getAdConfidence(segment);

                                  return (
                                    <tr key={segment.id ?? idx} className="hover:bg-gray-50">
                                      <td className="px-4 py-3 text-sm text-gray-900">{segment.sequence_num}</td>
                                      <td className="px-4 py-3 text-sm text-gray-600">{segment.start_time}s</td>
                                      <td className="px-4 py-3 text-sm text-gray-600">{segment.end_time}s</td>
                                      <td className="px-4 py-3 text-right text-sm tabular-nums text-gray-600">
                                        {adConfidence !== null ? adConfidence.toFixed(2) : '-'}
                                      </td>
                                      <td className="px-4 py-3 text-sm text-gray-700 min-w-[28rem] max-w-4xl">
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
                      )}
                      {(stats.transcript_segments?.length || 0) > 0 && (
                        <ShowMoreRows shown={visibleRows} total={stats.transcript_segments?.length || 0} onShowMore={showMoreRows} />
                      )}
                    </div>
                  )}
                </>
              ) : null}
              </div>
            </div>
    </>
  );
}
