import { useCallback, useEffect, useRef, useState } from 'react';
import { jobsApi } from '../services/api';
import type {
  CleanupPreview,
  Job,
  JobManagerRun,
  JobManagerStatus,
} from '../types';
import { JobProgressBar } from '../components/JobProgress';
import { formatBackendDateTime } from '../utils/datetime';
import { useCascade } from '../hooks/useCascade';
import { JobCard } from '../components/jobs/JobCard';
import {
  reconcileJobs,
  reconcileValue,
} from '../components/jobs/reconcile';

function RunStat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-xs text-gray-600">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums text-gray-900">{value}</div>
    </div>
  );
}

const formatDateTime = formatBackendDateTime;

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [managerStatus, setManagerStatus] = useState<JobManagerStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<'active' | 'all'>('active');
  const [cancellingJobs, setCancellingJobs] = useState<Set<string>>(new Set());
  const [cancellingQueued, setCancellingQueued] = useState(false);
  const previousHasActiveWork = useRef<boolean>(false);
  const [cleanupPreview, setCleanupPreview] = useState<CleanupPreview | null>(null);
  const [cleanupLoading, setCleanupLoading] = useState(false);
  const [cleanupError, setCleanupError] = useState<string | null>(null);
  const [cleanupRunning, setCleanupRunning] = useState(false);
  const [cleanupMessage, setCleanupMessage] = useState<string | null>(null);
  const jobGridRef = useRef<HTMLDivElement>(null);
  useCascade(jobGridRef, { playKey: mode, ready: jobs.length > 0, pop: true });

  const loadStatus = useCallback(async () => {
    try {
      const data = await jobsApi.getJobManagerStatus();
      setManagerStatus(prev => reconcileValue(prev, data));
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
      setJobs(prev => reconcileJobs(prev, data));
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
      setJobs(prev => reconcileJobs(prev, data));
    } catch (e) {
      console.error('Failed to load all jobs:', e);
      setError('Failed to load jobs');
    } finally {
      setLoading(false);
    }
  }, []);

  // Background refetch of the visible jobs list (no spinner, no error
  // surfaces) so the polling effect can keep job rows fresh without making
  // the manual "Refresh" button look like it's in flight.
  const silentLoadJobs = useCallback(async () => {
    try {
      const data =
        mode === 'active'
          ? await jobsApi.getActiveJobs(100)
          : await jobsApi.getAllJobs(200);
      setJobs(prev => reconcileJobs(prev, data));
    } catch (e) {
      console.error('Background jobs refresh failed:', e);
    }
  }, [mode]);

  const loadCleanupPreview = useCallback(async () => {
    setCleanupLoading(true);
    try {
      const data = await jobsApi.getCleanupPreview();
      setCleanupPreview(data);
      setCleanupError(null);
    } catch (e) {
      console.error('Failed to load cleanup preview:', e);
      setCleanupError('Failed to load cleanup preview');
    } finally {
      setCleanupLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    await loadStatus();
    if (mode === 'active') {
      await loadActive();
    } else {
      await loadAll();
    }
    await loadCleanupPreview();
  }, [mode, loadActive, loadAll, loadStatus, loadCleanupPreview]);

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

  const cancelAllQueuedJobs = useCallback(async () => {
    const queuedCount =
      managerStatus?.run?.queued_jobs ??
      jobs.filter(job => job.status === 'pending').length;
    if (queuedCount <= 0) {
      return;
    }

    const confirmMessage = `Cancel all ${queuedCount} queued job${queuedCount === 1 ? '' : 's'}?`;
    if (!window.confirm(confirmMessage)) {
      return;
    }

    const queuedVisibleJobIds = jobs
      .filter(job => job.status === 'pending')
      .map(job => job.job_id);

    setCancellingQueued(true);
    setCancellingJobs(prev => {
      const next = new Set(prev);
      queuedVisibleJobIds.forEach(id => next.add(id));
      return next;
    });

    try {
      await jobsApi.cancelQueuedJobs();
      setError(null);
      await refresh();
    } catch (e) {
      setError(
        `Failed to cancel queued jobs: ${
          e instanceof Error ? e.message : 'Unknown error'
        }`
      );
    } finally {
      setCancellingQueued(false);
      setCancellingJobs(prev => {
        const next = new Set(prev);
        queuedVisibleJobIds.forEach(id => next.delete(id));
        return next;
      });
    }
  }, [jobs, managerStatus?.run?.queued_jobs, refresh]);

  const runCleanupNow = useCallback(async () => {
    setCleanupRunning(true);
    setCleanupError(null);
    setCleanupMessage(null);
    try {
      const result = await jobsApi.runCleanupJob();
      if (result.status === 'disabled') {
        setCleanupMessage(result.message ?? 'Cleanup is disabled.');
        return;
      }
      if (result.status !== 'ok') {
        setCleanupError(result.message ?? 'Cleanup job failed');
        return;
      }
      const removed = result.removed_posts ?? 0;
      const remaining = result.remaining_candidates ?? 0;
      const removedText = `Cleanup removed ${removed} episode${removed === 1 ? '' : 's'}.`;
      const remainingText =
        remaining > 0
          ? ` ${remaining} episode${remaining === 1 ? '' : 's'} still eligible.`
          : '';
      setCleanupMessage(`${removedText}${remainingText}`);
      await refresh();
    } catch (e) {
      console.error('Failed to run cleanup job:', e);
      setCleanupError('Failed to run cleanup job');
    } finally {
      setCleanupRunning(false);
    }
  }, [refresh]);

  useEffect(() => {
    void loadStatus();
    void loadActive();
    void loadCleanupPreview();
  }, [loadActive, loadStatus, loadCleanupPreview]);

  useEffect(() => {
    const queued = managerStatus?.run?.queued_jobs ?? 0;
    const running = managerStatus?.run?.running_jobs ?? 0;
    const hasActiveWork = queued + running > 0;
    if (!hasActiveWork) {
      return undefined;
    }

    // Poll every 15 seconds when jobs are active to reduce database contention.
    // Jobs and manager counters share one cadence so they stay in sync.
    const interval = setInterval(() => {
      void silentLoadJobs();
      void loadStatus();
    }, 15000);

    return () => clearInterval(interval);
  }, [
    managerStatus?.run?.queued_jobs,
    managerStatus?.run?.running_jobs,
    loadStatus,
    silentLoadJobs,
  ]);

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
  const queuedJobsCount =
    run?.queued_jobs ?? jobs.filter(job => job.status === 'pending').length;
  const retentionDays = cleanupPreview?.retention_days ?? null;
  const cleanupDisabled = retentionDays === null || retentionDays <= 0;
  const cleanupEligibleCount = cleanupPreview?.count ?? 0;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold text-gray-900">Jobs</h1>
      <div className="rounded-lg border border-gray-200 bg-surface p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Jobs Manager</h2>
            <p className="text-xs text-gray-600">
              {run
                ? hasActiveWork
                  ? `Processing · Last update ${formatDateTime(run.updated_at)}`
                  : `Idle · Last activity ${formatDateTime(run.updated_at)}`
                : 'Jobs Manager has not started yet.'}
            </p>
          </div>
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
            {run.total_jobs > 0 ? (
              <div className="mt-4 space-y-1">
                <JobProgressBar value={run.progress_percentage} />
                <div className="text-xs text-gray-600">
                  {run.completed_jobs} completed · {run.skipped_jobs} skipped · {run.failed_jobs} failed of {run.total_jobs} jobs
                </div>
              </div>
            ) : (
              <p className="mt-4 text-sm text-gray-600">
                {run.counters_reset_at
                  ? `No jobs have run since ${formatDateTime(run.counters_reset_at)}.`
                  : 'No jobs have run yet.'}
              </p>
            )}
            <div className="mt-3 text-xs text-gray-600">
              Trigger: <span className="font-medium text-gray-700">{run.trigger}</span>
            </div>
            {run.counters_reset_at && run.total_jobs > 0 ? (
              <div className="mt-1 text-xs text-gray-600">
                Stats since {formatDateTime(run.counters_reset_at)}
              </div>
            ) : null}
          </>
        ) : null}
      </div>

      <div className="rounded-lg border border-gray-200 bg-surface p-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Post Cleanup</h2>
            <p className="text-xs text-gray-600">
              {cleanupDisabled
                ? 'Cleanup is disabled while retention days are unset or zero.'
                : `Episodes older than ${retentionDays} day${retentionDays === 1 ? '' : 's'} will be removed.`}
            </p>
          </div>
        </div>

        {cleanupError && (
          <div className="mt-2 text-xs text-red-600">{cleanupError}</div>
        )}
        {cleanupMessage && (
          <div className="mt-2 text-xs text-green-700">{cleanupMessage}</div>
        )}

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div>
            <div className="text-xs text-gray-600">Retention</div>
            <div className="text-sm font-medium text-gray-900">
              {cleanupDisabled ? 'Disabled' : `${retentionDays} day${retentionDays === 1 ? '' : 's'}`}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-600">Eligible episodes</div>
            <div className="text-sm font-medium tabular-nums text-gray-900">
              {cleanupLoading ? 'Loading…' : cleanupEligibleCount}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-600">Cutoff date</div>
            {cleanupPreview?.cutoff_utc ? (
              <div className="text-sm font-medium text-gray-900">{formatDateTime(cleanupPreview.cutoff_utc)}</div>
            ) : (
              <div className="text-sm text-gray-600">—</div>
            )}
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="text-xs text-gray-600">
            Includes completed jobs and non-whitelisted episodes with release dates older than the retention window.
          </div>
          <button
            onClick={() => { void runCleanupNow(); }}
            disabled={cleanupRunning || cleanupDisabled || cleanupLoading}
            className="btn btn-secondary"
          >
            {cleanupRunning ? 'Running cleanup…' : 'Run cleanup now'}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">{mode === 'active' ? 'Active Jobs' : 'All Jobs'}</h2>
          <p className="text-sm text-gray-600">
            {mode === 'active'
              ? 'Queued and running jobs, ordered by priority.'
              : 'All jobs ordered by priority (running/pending first).'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => { void cancelAllQueuedJobs(); }}
            className="btn btn-secondary text-red-700 disabled:text-gray-600"
            disabled={loading || cancellingQueued || queuedJobsCount <= 0}
          >
            {cancellingQueued
              ? 'Cancelling queued…'
              : `Cancel queued${queuedJobsCount > 0 ? ` (${queuedJobsCount})` : ''}`}
          </button>
          <button
            onClick={() => { void refresh(); }}
            className="btn btn-secondary"
            disabled={loading}
          >
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
          {mode === 'active' ? (
            <button
              onClick={async () => { setMode('all'); await loadStatus(); await loadAll(); await loadCleanupPreview(); }}
              className="btn btn-secondary"
              disabled={loading}
            >
              Load all jobs
            </button>
          ) : (
            <button
              onClick={async () => { setMode('active'); await loadStatus(); await loadActive(); await loadCleanupPreview(); }}
              className="btn btn-secondary"
              disabled={loading}
            >
              Show active only
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

      <div ref={jobGridRef} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {jobs.map((job) => (
          <JobCard
            key={job.job_id}
            job={job}
            isCancelling={cancellingJobs.has(job.job_id)}
            onCancel={cancelJob}
          />
        ))}
      </div>
    </div>
  );
}
