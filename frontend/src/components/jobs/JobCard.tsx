import { memo, useCallback } from 'react';
import type { Job } from '../../types';
import {
  JobProgressBar,
  JobProgressCaption,
  JobStageRail,
} from '../JobProgress';
import {
  backendDateMs,
  formatBackendDateTime,
  formatDuration,
} from '../../utils/datetime';
import { ServiceTierChip } from '../EpisodeProcessingStatus';
import { buildProcessingProgressModel } from '../../utils/processingProgress';
import { useNow } from './useNow';

function getStatusColor(status: string) {
  switch (status) {
    case 'running':
      return 'bg-green-100 text-green-800';
    case 'pending':
      return 'bg-yellow-100 text-yellow-800';
    case 'failed':
      return 'bg-red-100 text-red-800';
    case 'completed':
      return 'bg-blue-100 text-blue-800';
    case 'skipped':
      return 'bg-sky-100 text-sky-800';
    case 'cancelled':
      return 'bg-gray-100 text-gray-800';
    default:
      return 'bg-gray-100 text-gray-800';
  }
}

function StatusBadge({ status }: { status: string }) {
  const color = getStatusColor(status);
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}

const formatDateTime = formatBackendDateTime;

interface JobCardProps {
  job: Job;
  isCancelling: boolean;
  onCancel: (jobId: string) => void;
}

function JobCardBase({ job, isCancelling, onCancel }: JobCardProps) {
  const now = useNow(job.status === 'running');
  const progressModel = buildProcessingProgressModel({
    status: job.status,
    step: job.step,
    totalSteps: job.total_steps,
    stepName: job.step_name,
    progressPercentage: job.progress_percentage,
  });
  const progressColorClass =
    job.status === 'failed' || job.status === 'cancelled'
      ? 'bg-red-600'
      : job.status === 'completed' || job.status === 'skipped'
        ? 'bg-green-600'
        : 'bg-blue-600';

  const handleCancel = useCallback(() => {
    onCancel(job.job_id);
  }, [onCancel, job.job_id]);

  return (
    <div className="bg-surface border border-gray-200 rounded-lg p-4 space-y-3 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-gray-900 truncate">
          {job.post_title || 'Untitled episode'}
        </div>
        <div className="flex items-center gap-1.5">
          {job.service_tier ? <ServiceTierChip tier={job.service_tier} /> : null}
          <StatusBadge status={job.status} />
        </div>
      </div>
      <div className="text-xs text-gray-600 truncate">{job.feed_title || 'Unknown feed'}</div>

      <div className="space-y-2">
        <JobProgressBar
          value={progressModel.progress}
          colorClass={progressColorClass}
        />
        <JobStageRail stages={progressModel.stages} />
        <JobProgressCaption
          stageLabel={progressModel.currentStageLabel}
          percent={progressModel.progress}
        />
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs text-gray-600">
        <div>
          <div className="text-gray-600">Job ID</div>
          <div className="truncate" title={job.job_id}>{job.job_id}</div>
        </div>
        <div>
          <div className="text-gray-600">Post GUID</div>
          <div className="truncate" title={job.post_guid}>{job.post_guid}</div>
        </div>
        <div>
          <div className="text-gray-600">Created</div>
          <div>{job.created_at ? formatDateTime(job.created_at) : '—'}</div>
        </div>
        <div>
          <div className="text-gray-600">Started</div>
          <div>{job.started_at ? formatDateTime(job.started_at) : '—'}</div>
        </div>
        {(() => {
          const isTerminal =
            job.status === 'completed' ||
            job.status === 'skipped' ||
            job.status === 'failed' ||
            job.status === 'cancelled';
          const startedMs = backendDateMs(job.started_at);
          const endMs = isTerminal
            ? backendDateMs(job.completed_at) || now
            : now;
          if (!Number.isFinite(startedMs)) {
            return null;
          }
          return (
            <div className="col-span-2">
              <div className="text-gray-600">Total time</div>
              <div className="font-mono tabular-nums">
                {formatDuration(endMs - startedMs)}
              </div>
            </div>
          );
        })()}
        {job.error_message ? (
          <div className="col-span-2">
            <div className="text-gray-600">Message</div>
            <div className="text-red-700 truncate" title={job.error_message}>{job.error_message}</div>
          </div>
        ) : null}
      </div>

      {(job.status === 'pending' || job.status === 'running') && (
        <div className="mt-3 pt-3 border-t border-gray-200">
          <button
            onClick={handleCancel}
            disabled={isCancelling}
            className="btn btn-danger w-full"
          >
            {isCancelling ? 'Cancelling...' : 'Cancel Job'}
          </button>
        </div>
      )}
    </div>
  );
}

export const JobCard = memo(JobCardBase);
