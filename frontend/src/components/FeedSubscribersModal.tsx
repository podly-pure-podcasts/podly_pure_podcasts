import { useQuery } from '@tanstack/react-query';
import { feedsApi } from '../services/api';
import ModalShell from './ModalShell';
import type { FeedSubscriber } from '../types';
import { CloseIcon } from './icons';

interface FeedSubscribersModalProps {
  feedId: number;
  feedTitle: string;
  isOpen: boolean;
  onClose: () => void;
}

function StatusBadge({ status }: { status: string }) {
  const isActive = status === 'active';
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
        isActive
          ? 'bg-green-100 text-green-800'
          : 'bg-gray-100 text-gray-700'
      }`}
    >
      {status}
    </span>
  );
}

export default function FeedSubscribersModal({
  feedId,
  feedTitle,
  isOpen,
  onClose,
}: FeedSubscribersModalProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['feed-subscribers', feedId],
    queryFn: () => feedsApi.getSubscribers(feedId),
    enabled: isOpen,
  });

  const subscribers: FeedSubscriber[] = data?.subscribers ?? [];

  return (
    <ModalShell
      isOpen={isOpen}
      onClose={onClose}
      panelClassName="w-full max-w-md bg-surface rounded-lg border border-gray-200 shadow-lg overflow-hidden"
    >
        {/* Header */}
        <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-gray-200">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Subscribers</h2>
            <p className="text-sm text-gray-500 mt-0.5 truncate max-w-xs">{feedTitle}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="btn btn-ghost btn-icon btn-sm shrink-0"
          >
            <CloseIcon className="h-5 w-5" />
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
                        <span className="ml-1.5 text-xs text-gray-600 font-medium">admin</span>
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
    </ModalShell>
  );
}
