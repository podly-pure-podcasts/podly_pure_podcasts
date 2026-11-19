import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { feedsApi } from '../services/api';
import ModalShell from './ModalShell';
import { CloseIcon, RefreshIcon } from './icons';

type ReprocessMode = 'full' | 'keep-transcript';

interface ReprocessButtonProps {
  episodeGuid: string;
  isWhitelisted: boolean;
  feedId?: number;
  canModifyEpisodes?: boolean;
  className?: string;
  onReprocessStart?: () => void;
}

export default function ReprocessButton({
  episodeGuid,
  isWhitelisted,
  feedId,
  canModifyEpisodes = true,
  className = '',
  onReprocessStart
}: ReprocessButtonProps) {
  const [isReprocessing, setIsReprocessing] = useState(false);
  const [activeMode, setActiveMode] = useState<ReprocessMode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [keepTranscript, setKeepTranscript] = useState(true);
  const queryClient = useQueryClient();

  const handleReprocessClick = () => {
    if (!isWhitelisted) {
      setError('Post must be whitelisted before reprocessing');
      return;
    }

    setKeepTranscript(true);
    setShowModal(true);
  };

  const handleConfirmReprocess = async () => {
    const mode: ReprocessMode = keepTranscript ? 'keep-transcript' : 'full';

    setShowModal(false);
    setIsReprocessing(true);
    setActiveMode(mode);
    setError(null);

    try {
      const response = mode === 'keep-transcript'
        ? await feedsApi.reprocessPostKeepTranscript(episodeGuid)
        : await feedsApi.reprocessPost(episodeGuid);

      if (response.status === 'started') {
        // Notify parent component that reprocessing started
        onReprocessStart?.();

        // Invalidate queries to refresh the UI
        if (feedId) {
          queryClient.invalidateQueries({ queryKey: ['episodes', feedId] });
        }
        queryClient.invalidateQueries({ queryKey: ['episode-stats', episodeGuid] });
      } else {
        setError(response.message || 'Failed to start reprocessing');
      }
    } catch (err: unknown) {
      console.error('Error starting reprocessing:', err);
      const errorMessage = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { message?: string } } }).response?.data?.message
          || 'Failed to start reprocessing'
        : 'Failed to start reprocessing';
      setError(errorMessage);
    } finally {
      setIsReprocessing(false);
      setActiveMode(null);
    }
  };

  if (!isWhitelisted || !canModifyEpisodes) {
    return null;
  }

  const buttonTitle = isReprocessing && activeMode === 'keep-transcript'
    ? 'Reprocessing from transcript stage...'
    : isReprocessing
      ? 'Clearing data and reprocessing...'
      : 'Clear processed data and choose whether to reuse the existing transcript in the confirmation modal';

  return (
    <div className={`${className}`}>
      <button
        onClick={handleReprocessClick}
        disabled={isReprocessing}
        className={`btn btn-secondary btn-sm ${isReprocessing ? 'cursor-wait' : ''}`}
        title={buttonTitle}
      >
        {isReprocessing && activeMode === 'keep-transcript' ? (
          <>
            <RefreshIcon className="h-3.5 w-3.5 animate-spin" />
            <span className="sm:hidden">Reusing...</span>
            <span className="hidden sm:inline">Reprocessing (Transcript)...</span>
          </>
        ) : isReprocessing ? (
          <>
            <RefreshIcon className="h-3.5 w-3.5 animate-spin" />
            Reprocessing...
          </>
        ) : (
          'Reprocess'
        )}
      </button>

      {error && (
        <div className="text-xs text-red-600 mt-1">
          {error}
        </div>
      )}

      {/* Confirmation Modal */}
      <ModalShell
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        panelClassName="bg-surface rounded-lg max-w-md w-full overflow-hidden"
      >
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b">
              <h2 className="text-xl font-semibold text-gray-900">Confirm Reprocess</h2>
              <button
                onClick={() => setShowModal(false)}
                aria-label="Close"
                className="btn btn-ghost btn-icon"
              >
                <CloseIcon className="h-5 w-5" />
              </button>
            </div>

            {/* Content */}
            <div className="p-6">
              <p className="text-gray-700 mb-6">
                Are you sure you want to reprocess this episode? This will
                delete the existing processed data and start processing again.
              </p>

              <label className="flex items-start gap-3 rounded-lg border border-gray-200 bg-gray-50 p-4 mb-6">
                <input
                  type="checkbox"
                  checked={keepTranscript}
                  onChange={(event) => setKeepTranscript(event.target.checked)}
                  className="mt-1 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-gray-900">
                    Keep existing transcript
                  </span>
                  <span className="block text-sm text-gray-600">
                    Reuse the current transcript and restart after
                    transcription, if that transcript is still reusable.
                  </span>
                </span>
              </label>

              {/* Action Buttons */}
              <div className="flex gap-3 justify-end">
                <button
                  onClick={() => setShowModal(false)}
                  className="btn btn-secondary"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirmReprocess}
                  className={`btn ${keepTranscript ? 'btn-primary' : 'btn-danger'}`}
                >
                  {keepTranscript
                    ? 'Reprocess episode (keep transcript)'
                    : 'Reprocess episode'}
                </button>
              </div>
            </div>
      </ModalShell>
    </div>
  );
}
