import { useEpisodeStatus } from '../hooks/useEpisodeStatus';
import { buildProcessingProgressModel } from '../utils/processingProgress';

interface EpisodeProcessingStatusProps {
  episodeGuid: string;
  isWhitelisted: boolean;
  hasProcessedAudio: boolean;
  feedId?: number;
  className?: string;
}

export default function EpisodeProcessingStatus({
  episodeGuid,
  isWhitelisted,
  hasProcessedAudio,
  feedId,
  className = ''
}: EpisodeProcessingStatusProps) {
  const { data: status } = useEpisodeStatus(episodeGuid, isWhitelisted, hasProcessedAudio, feedId);

  if (!status) return null;

  // Don't show anything if completed (DownloadButton handles this) or not started
  if (status.status === 'completed' || status.status === 'not_started') {
    return null;
  }

  const model = buildProcessingProgressModel({
    status: status.status,
    step: status.step,
    totalSteps: status.total_steps,
    stepName: status.step_name,
    progressPercentage: status.progress_percentage,
  });

  const isFailure = status.status === 'error' || status.status === 'failed' || status.status === 'cancelled';
  const progressColor = isFailure ? 'bg-red-500' : status.status === 'completed' ? 'bg-green-500' : 'bg-blue-500';

  return (
    <div className={`space-y-2 min-w-[200px] ${className}`}>
      {/* Progress indicator */}
      <div className="space-y-1">
        {/* Progress bar */}
        <div className="w-full bg-gray-200 rounded-full h-1.5">
          <div
            className={`h-1.5 rounded-full transition-all duration-300 ${progressColor}`}
            style={{ width: `${model.progress}%` }}
          />
        </div>

        {/* Stage indicators */}
        <div className="grid grid-cols-5 gap-1 text-[10px] text-gray-600">
          {model.stages.map((stage) => (
            <div
              key={stage.index}
              title={stage.label}
              className={`flex flex-col items-center leading-tight ${
                stage.state === 'active'
                  ? 'text-blue-600 font-medium'
                  : stage.state === 'completed'
                    ? 'text-green-600'
                    : stage.state === 'failed'
                      ? 'text-red-600 font-medium'
                      : 'text-gray-400'
              }`}
            >
              <span className="text-xs">
                {stage.state === 'completed'
                  ? '✓'
                  : stage.state === 'active'
                    ? '●'
                    : stage.state === 'failed'
                      ? '!'
                      : '○'}
              </span>
              <span>{stage.shortLabel}</span>
            </div>
          ))}
        </div>

        {/* Current step name */}
        <div className="flex items-center justify-center gap-1.5 text-xs text-center text-gray-600">
          <span>
            {model.currentStageLabel} ({Math.round(model.progress)}%)
          </span>
          {status.service_tier ? <ServiceTierChip tier={status.service_tier} /> : null}
        </div>
      </div>

      {/* Error message */}
      {(status.error || status.status === 'failed' || status.status === 'error') && (
        <div className="text-xs text-red-600 text-center">
          {status.error || 'Processing failed'}
        </div>
      )}
    </div>
  );
}

export function ServiceTierChip({
  tier,
}: {
  tier: { label: string; latest: string; mixed: boolean };
}) {
  const color =
    tier.label === 'flex'
      ? 'bg-purple-100 text-purple-800'
      : tier.label === 'priority'
        ? 'bg-blue-100 text-blue-800'
        : 'bg-gray-100 text-gray-700';
  const title = tier.mixed
    ? `LLM calls so far used mixed tiers; latest=${tier.latest}`
    : `LLM calls used the "${tier.label}" service tier`;
  return (
    <span
      title={title}
      className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded ${color}`}
    >
      {tier.label}
      {tier.mixed ? '*' : ''}
    </span>
  );
}
