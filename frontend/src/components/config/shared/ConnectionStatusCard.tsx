interface ConnectionStatusCardProps {
  title: string;
  status: 'loading' | 'ok' | 'error';
  message: string;
  error?: string;
  onRetry: () => void;
}

const DOT = {
  loading: 'bg-gray-400 animate-pulse',
  ok: 'bg-green-500',
  error: 'bg-red-500',
} as const;

const TEXT = {
  loading: 'text-gray-600',
  ok: 'text-green-700',
  error: 'text-red-700',
} as const;

/** One service's connection state as a flat row; the text carries the state, the dot only reinforces it. */
export default function ConnectionStatusCard({
  title,
  status,
  message,
  error,
  onRetry,
}: ConnectionStatusCardProps) {
  const displayMessage =
    status === 'loading'
      ? 'Testing…'
      : status === 'ok'
      ? message || 'Connected'
      : error || 'Could not connect. Check the API key and URL, then test again.';

  return (
    <div className="flex items-start justify-between gap-3" role="status" aria-live="polite">
      <div className="flex min-w-0 items-start gap-2.5">
        <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${DOT[status]}`} aria-hidden="true" />
        <div className="min-w-0">
          <div className="text-sm font-medium text-gray-900">{title}</div>
          <div className={`break-words text-xs ${TEXT[status]}`}>{displayMessage}</div>
        </div>
      </div>
      <button
        type="button"
        className="btn btn-ghost btn-sm shrink-0"
        onClick={onRetry}
        disabled={status === 'loading'}
      >
        Test again
      </button>
    </div>
  );
}
