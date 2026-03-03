import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { jobsApi } from '../services/api';
import type { Job, JobManagerRun, JobManagerStatus } from '../types';
import { copyTextToClipboard } from '../services/clipboard';
import { useEscapeKey } from '../hooks/useEscapeKey';

function getStatusColor(status: string) {
  switch (status) {
    case 'running':
      return 'bg-gradient-to-r from-cyan-100 to-cyan-200 text-cyan-800';
    case 'pending':
      return 'bg-gradient-to-r from-pink-100 to-pink-200 text-pink-800';
    case 'failed':
      return 'bg-gradient-to-r from-red-100 to-red-200 text-red-800';
    case 'completed':
      return 'bg-gradient-to-r from-purple-100 to-purple-200 text-purple-800';
    case 'skipped':
      return 'bg-gradient-to-r from-lavender-100 to-lavender-200 text-purple-700';
    case 'cancelled':
      return 'bg-gradient-to-r from-gray-100 to-gray-200 text-gray-700';
    case 'idle':
      return 'bg-gradient-to-r from-gray-100 to-gray-200 text-gray-600';
    default:
      return 'bg-gradient-to-r from-gray-100 to-gray-200 text-gray-700';
  }
}

function StatusBadge({ status }: { status: string }) {
  const color = getStatusColor(status);
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}

function ProgressBar({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="w-full bg-purple-100 rounded-full h-2">
      <div
        className="bg-gradient-to-r from-pink-500 via-purple-500 to-cyan-500 h-2 rounded-full transition-all"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

function RunStat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-1 text-lg font-semibold text-gray-900">{value}</div>
    </div>
  );
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return '—';
  }
  try {
    return new Date(value).toLocaleString();
  } catch (err) {
    console.error('Failed to format date', err);
    return value;
  }
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [managerStatus, setManagerStatus] = useState<JobManagerStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<'active' | 'all'>('all');  // Default to 'all' to show history
  const [clearing, setClearing] = useState(false);
  const [cancellingJobs, setCancellingJobs] = useState<Set<string>>(new Set());
  const previousHasActiveWork = useRef<boolean>(false);
  const [selectedJobError, setSelectedJobError] = useState<{ title: string; error: string; jobId: string } | null>(null);
  useEscapeKey(!!selectedJobError, () => setSelectedJobError(null));

  const loadStatus = useCallback(async () => {
    try {
      const data = await jobsApi.getJobManagerStatus();
      setManagerStatus(data);
      setStatusError(null);
    } catch (e) {
      console.error('Failed to load job manager status:', e);
      setStatusError('Failed to load manager status');
    }
  }, []);

  const loadActive = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await jobsApi.getActiveJobs(100);
      setJobs(data);
    } catch (e) {
      console.error('Failed to load active jobs:', e);
      setError('Failed to load jobs');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await jobsApi.getAllJobs(200);
      setJobs(data);
    } catch (e) {
      console.error('Failed to load all jobs:', e);
      setError('Failed to load jobs');
    } finally {
      setLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    await loadStatus();
    if (mode === 'active') {
      await loadActive();
    } else {
      await loadAll();
    }
  }, [mode, loadActive, loadAll, loadStatus]);

  const cancelJob = useCallback(
    async (jobId: string) => {
      setCancellingJobs(prev => new Set(prev).add(jobId));
      try {
        await jobsApi.cancelJob(jobId);
        await refresh();
      } catch (e) {
        setError(`Failed to cancel job: ${e instanceof Error ? e.message : 'Unknown error'}`);
      } finally {
        setCancellingJobs(prev => {
          const newSet = new Set(prev);
          newSet.delete(jobId);
          return newSet;
        });
      }
    },
    [refresh]
  );

  const clearHistory = useCallback(async () => {
    if (!window.confirm('Clear all completed, failed, and cancelled jobs from history?')) {
      return;
    }
    setClearing(true);
    try {
      await jobsApi.clearHistory();
      await refresh();
    } catch (e) {
      console.error('Failed to clear history:', e);
      setError('Failed to clear history');
    } finally {
      setClearing(false);
    }
  }, [refresh]);

  // Load all jobs by default to show history
  useEffect(() => {
    void loadStatus();
    void loadAll();  // Load all jobs on fresh load to show history
  }, [loadAll, loadStatus]);

  useEffect(() => {
    const queued = managerStatus?.run?.queued_jobs ?? 0;
    const running = managerStatus?.run?.running_jobs ?? 0;
    const hasActiveWork = queued + running > 0;
    if (!hasActiveWork) {
      return undefined;
    }

    // Poll both status and job list while there's active work
    const interval = setInterval(() => {
      void loadStatus();
      if (mode === 'active') {
        void loadActive();
      } else {
        void loadAll();
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [managerStatus?.run?.queued_jobs, managerStatus?.run?.running_jobs, loadStatus, loadActive, loadAll, mode]);

  useEffect(() => {
    const queued = managerStatus?.run?.queued_jobs ?? 0;
    const running = managerStatus?.run?.running_jobs ?? 0;
    const hasActiveWork = queued + running > 0;
    if (!hasActiveWork && previousHasActiveWork.current) {
      void refresh();
    }
    previousHasActiveWork.current = hasActiveWork;
  }, [managerStatus?.run?.queued_jobs, managerStatus?.run?.running_jobs, refresh]);

  const run: JobManagerRun | null = managerStatus?.run ?? null;
  const hasActiveWork = run ? run.queued_jobs + run.running_jobs > 0 : false;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-purple-200/50 bg-white/80 backdrop-blur-sm p-4 shadow-sm unicorn-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-purple-900">Jobs Manager 💫</h2>
            <p className="text-xs text-purple-600">
              {run
                ? hasActiveWork
                  ? `Processing · Last update ${formatDateTime(run.updated_at)}`
                  : `Idle · Last activity ${formatDateTime(run.updated_at)}`
                : 'Jobs Manager has not started yet.'}
            </p>
          </div>
          {run ? (
            <StatusBadge status={run.status} />
          ) : (
            <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-800">
              idle
            </span>
          )}
        </div>

        {statusError && (
          <div className="mt-2 text-xs text-red-600">{statusError}</div>
        )}

        {run ? (
          <>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
              <RunStat label="Queued" value={run.queued_jobs} />
              <RunStat label="Running" value={run.running_jobs} />
              <RunStat label="Completed" value={run.completed_jobs} />
              <RunStat label="Skipped" value={run.skipped_jobs} />
              <RunStat label="Failed" value={run.failed_jobs} />
            </div>
            <div className="mt-4 space-y-1">
              <ProgressBar value={run.progress_percentage} />
              <div className="text-xs text-gray-500">
                {run.completed_jobs} completed · {run.skipped_jobs} skipped · {run.failed_jobs} failed of {run.total_jobs} jobs
              </div>
            </div>
            <div className="mt-3 text-xs text-gray-500">
              Trigger: <span className="font-medium text-gray-700">{run.trigger}</span>
            </div>
            {run.counters_reset_at ? (
              <div className="mt-1 text-xs text-gray-500">
                Stats since {formatDateTime(run.counters_reset_at)}
              </div>
            ) : null}
          </>
        ) : null}
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h3 className="text-xl font-semibold text-gray-900">{mode === 'active' ? 'Active Jobs' : 'All Jobs'}</h3>
          <p className="text-sm text-gray-600">
            {mode === 'active'
              ? 'Queued and running jobs, ordered by priority.'
              : 'All jobs ordered by priority (running/pending first).'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto sm:justify-end">
          <button
            onClick={() => { void refresh(); }}
            className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-pink-500 via-purple-500 to-cyan-500 px-3 py-1.5 text-sm font-medium text-white hover:shadow-lg hover:shadow-purple-500/30 transition-all flex-1 sm:flex-none"
            disabled={loading}
          >
            <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
          <div className="flex w-full sm:w-auto rounded-xl border border-purple-200 overflow-hidden">
            <button
              onClick={async () => { setMode('active'); await loadStatus(); await loadActive(); }}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                mode === 'active' 
                  ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white' 
                  : 'bg-white/80 text-purple-700 hover:bg-purple-50'
              }`}
              disabled={loading}
            >
              Active
            </button>
            <button
              onClick={async () => { setMode('all'); await loadStatus(); await loadAll(); }}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                mode === 'all' 
                  ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white' 
                  : 'bg-white/80 text-purple-700 hover:bg-purple-50'
              }`}
              disabled={loading}
            >
              All History
            </button>
          </div>
          {mode === 'all' && jobs.some(j => ['completed', 'failed', 'cancelled', 'skipped'].includes(j.status)) && (
            <button
              onClick={() => { void clearHistory(); }}
              className="px-3 py-1.5 text-sm font-medium text-pink-600 border border-pink-200 rounded-xl hover:bg-pink-50 transition-colors disabled:opacity-50 w-full sm:w-auto"
              disabled={clearing}
            >
              {clearing ? 'Clearing...' : 'Clear History'}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>
      )}

      {jobs.length === 0 && !loading ? (
        <div className="text-sm text-gray-600">No jobs to display.</div>
      ) : null}

      <div className="bg-white/80 backdrop-blur-sm border border-purple-200/50 rounded-xl overflow-hidden unicorn-card">
        {jobs.map((job, idx) => (
          <div key={job.job_id} className={`px-4 py-3.5 ${idx > 0 ? 'border-t border-purple-100/40' : ''}`}>
            <div className="flex items-center justify-between gap-2 mb-1">
              {job.feed_id ? (
                <Link 
                  to={`/podcasts?feed=${job.feed_id}`}
                  className="text-sm font-medium text-purple-900 truncate hover:text-pink-600 transition-colors"
                >
                  {job.post_title || 'Untitled episode'}
                </Link>
              ) : (
                <div className="text-sm font-medium text-purple-900 truncate">
                  {job.post_title || 'Untitled episode'}
                </div>
              )}
              <StatusBadge status={job.status} />
            </div>
            <div className="text-xs text-purple-500 truncate mb-2">{job.feed_title || 'Unknown feed'}</div>

            <div className="flex items-center gap-3 mb-2">
              <div className="flex-1">
                <ProgressBar value={job.progress_percentage} />
              </div>
              <span className="text-xs font-medium text-purple-700 w-8 text-right">{Math.round(job.progress_percentage)}%</span>
            </div>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
              <span>Step {job.step}/{job.total_steps}{job.step_name ? ` · ${job.step_name}` : ''}</span>
              <span>Priority {job.priority}</span>
              {job.triggered_by_username && <span>by {job.triggered_by_username}</span>}
              {!job.triggered_by_username && job.trigger_source === 'auto_feed_refresh' && <span>by System</span>}
              <span>
                {job.trigger_source === 'manual_ui' && 'Manual (UI)'}
                {job.trigger_source === 'manual_reprocess' && 'Reprocess'}
                {job.trigger_source === 'auto_feed_refresh' && 'Auto-download'}
                {job.trigger_source === 'on_demand_rss' && 'RSS Request'}
              </span>
              {job.error_message && (
                <button
                  onClick={() => setSelectedJobError({ 
                    title: job.post_title || 'Job Error', 
                    error: job.error_message!, 
                    jobId: job.job_id 
                  })}
                  className="text-red-600 truncate text-left hover:text-red-800 hover:underline max-w-[200px]"
                  title="Click to view full error"
                >
                  {job.error_message}
                </button>
              )}
            </div>

            {(job.status === 'pending' || job.status === 'running') && (
              <div className="mt-2.5 pt-2.5 border-t border-gray-100">
                <button
                  onClick={() => { void cancelJob(job.job_id); }}
                  disabled={cancellingJobs.has(job.job_id)}
                  className="px-3 py-1.5 text-xs font-medium text-red-600 border border-red-200 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {cancellingJobs.has(job.job_id) ? 'Cancelling...' : 'Cancel Job'}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Error Details Modal */}
      {selectedJobError && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80">
          <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[80vh] overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-red-50 to-pink-50">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-red-900">Error Details</h3>
                <button
                  onClick={() => setSelectedJobError(null)}
                  className="text-gray-500 hover:text-gray-700"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <p className="text-sm text-red-700 mt-1">{selectedJobError.title}</p>
            </div>
            <div className="p-6 overflow-y-auto max-h-[60vh]">
              <div className="mb-4">
                <div className="text-xs text-gray-500 mb-1">Job ID</div>
                <code className="text-xs bg-gray-100 px-2 py-1 rounded font-mono">{selectedJobError.jobId}</code>
              </div>
              <div>
                <div className="text-xs text-gray-500 mb-2">Error Message</div>
                <pre className="text-sm text-red-800 bg-red-50 p-4 rounded-lg overflow-x-auto whitespace-pre-wrap font-mono">
                  {selectedJobError.error}
                </pre>
              </div>
            </div>
            <div className="px-6 py-4 border-t border-gray-200 bg-gray-50 flex justify-end gap-3">
              <button
                onClick={() => { void copyTextToClipboard(selectedJobError.error); }}
                className="px-4 py-2 text-sm font-medium text-purple-700 bg-purple-100 rounded-lg hover:bg-purple-200"
              >
                Copy Error
              </button>
              <button
                onClick={() => setSelectedJobError(null)}
                className="px-4 py-2 text-sm font-medium text-white bg-gradient-to-r from-purple-600 to-pink-500 rounded-lg hover:from-purple-700 hover:to-pink-600"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
