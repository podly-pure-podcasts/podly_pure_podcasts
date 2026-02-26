import { useQuery } from '@tanstack/react-query';
import { feedsApi } from '../services/api';
import type { FeedSubscriber } from '../types';

interface FeedSubscribersModalProps {
  feedId: number;
  feedTitle: string;
  onClose: () => void;
}

function StatusBadge({ status }: { status: string }) {
  const isActive = status === 'active';
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
        isActive
          ? 'bg-green-100 text-green-700'
          : 'bg-gray-100 text-gray-500'
      }`}
    >
      {status}
    </span>
  );
}

export default function FeedSubscribersModal({
  feedId,
  feedTitle,
  onClose,
}: FeedSubscribersModalProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['feed-subscribers', feedId],
    queryFn: () => feedsApi.getSubscribers(feedId),
  });

  const subscribers: FeedSubscriber[] = data?.subscribers ?? [];

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      <div className="relative w-full max-w-md bg-white rounded-xl border border-gray-200 shadow-lg overflow-hidden">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-gray-200">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Subscribers</h2>
            <p className="text-sm text-gray-500 mt-0.5 truncate max-w-xs">{feedTitle}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 shrink-0"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 max-h-96 overflow-y-auto">
          {isLoading ? (
            <p className="text-sm text-gray-500">Loading…</p>
          ) : isError ? (
            <p className="text-sm text-red-600">Failed to load subscribers.</p>
          ) : subscribers.length === 0 ? (
            <p className="text-sm text-gray-500">No subscribers yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-2 pr-4 font-medium text-gray-600">User</th>
                  <th className="text-left py-2 font-medium text-gray-600">Status</th>
                </tr>
              </thead>
              <tbody>
                {subscribers.map((sub) => (
                  <tr key={sub.user_id} className="border-b border-gray-50 last:border-0">
                    <td className="py-2 pr-4 text-gray-800">
                      {sub.username}
                      {sub.role === 'admin' && (
                        <span className="ml-1.5 text-xs text-indigo-500 font-medium">admin</span>
                      )}
                    </td>
                    <td className="py-2">
                      <StatusBadge status={sub.subscription_status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-200 bg-gray-50 text-xs text-gray-500">
          {subscribers.length} subscriber{subscribers.length !== 1 ? 's' : ''}
        </div>
      </div>
    </div>
  );
}
