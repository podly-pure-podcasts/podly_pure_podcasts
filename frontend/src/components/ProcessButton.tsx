import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { feedsApi } from '../services/api';
import { useTheme } from '../contexts/ThemeContext';

interface ProcessButtonProps {
  episodeGuid: string;
  feedId?: number;
  className?: string;
  onProcessStart?: () => void;
}

export default function ProcessButton({
  episodeGuid,
  feedId,
  className = '',
  onProcessStart
}: ProcessButtonProps) {
  const { theme } = useTheme();
  const isOriginal = theme === 'original';
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const handleProcessClick = async () => {
    setIsProcessing(true);
    setError(null);

    try {
      const response = await feedsApi.processPost(episodeGuid);

      if (response.status === 'started' || response.status === 'processing') {
        // Notify parent component that processing started
        onProcessStart?.();

        // Invalidate queries to refresh the UI
        if (feedId) {
          queryClient.invalidateQueries({ queryKey: ['episodes', feedId] });
        }
        queryClient.invalidateQueries({ queryKey: ['jobs'] });
      } else if (response.status === 'skipped') {
        // Already processed
        if (feedId) {
          queryClient.invalidateQueries({ queryKey: ['episodes', feedId] });
        }
      } else {
        setError(response.message || 'Failed to start processing');
      }
    } catch (err: unknown) {
      console.error('Error starting processing:', err);
      const errorMessage = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { message?: string } } }).response?.data?.message || 'Failed to start processing'
        : 'Failed to start processing';
      setError(errorMessage);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <>
      <button
        onClick={handleProcessClick}
        disabled={isProcessing}
        className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all border flex items-center gap-1.5 ${className} ${
          isProcessing
            ? isOriginal
              ? 'bg-blue-500 text-white cursor-wait border-blue-400'
              : 'bg-purple-500 text-white cursor-wait border-purple-500'
            : isOriginal
              ? 'bg-blue-950/60 border-blue-300/50 text-blue-100 hover:bg-blue-900/70 hover:border-blue-200/60'
              : 'bg-white border-purple-200 text-purple-600 hover:bg-purple-50'
        }`}
        title="Start processing this episode to remove ads"
      >
        {isProcessing ? (
          <>
            <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
            Processing...
          </>
        ) : (
          <>
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Process
          </>
        )}
      </button>

      {error && (
        <div className="text-xs text-red-600 mt-1">
          {error}
        </div>
      )}
    </>
  );
}
