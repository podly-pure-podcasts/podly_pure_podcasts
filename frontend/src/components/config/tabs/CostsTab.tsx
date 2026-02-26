import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import { costsApi } from '../../../services/api';
import type { CostSummary, CallLog } from '../../../types';

function MonthSelector({
  year,
  month,
  onChange,
}: {
  year: number;
  month: number;
  onChange: (year: number, month: number) => void;
}) {
  const months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => {
          const d = new Date(year, month - 2);
          onChange(d.getFullYear(), d.getMonth() + 1);
        }}
        className="px-2 py-1 text-sm border border-gray-300 rounded hover:bg-gray-100"
      >
        ‹
      </button>
      <span className="text-sm font-medium w-24 text-center">
        {months[month - 1]} {year}
      </span>
      <button
        onClick={() => {
          const d = new Date(year, month);
          onChange(d.getFullYear(), d.getMonth() + 1);
        }}
        className="px-2 py-1 text-sm border border-gray-300 rounded hover:bg-gray-100"
      >
        ›
      </button>
    </div>
  );
}

export default function CostsTab() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [callPage, setCallPage] = useState(1);
  const queryClient = useQueryClient();

  const { data: costs, isLoading: costsLoading } = useQuery<CostSummary>({
    queryKey: ['admin-costs', year, month],
    queryFn: () => costsApi.getCosts(year, month),
  });

  const { data: calls, isLoading: callsLoading } = useQuery<CallLog>({
    queryKey: ['admin-calls', callPage],
    queryFn: () => costsApi.getCalls(callPage, 50),
  });

  const cleanupCancelledMutation = useMutation({
    mutationFn: () => costsApi.cleanupCancelledFeeds(),
    onSuccess: (data) => {
      toast.success(`Removed ${data.removed} cancelled-subscriber feed(s)`);
      queryClient.invalidateQueries({ queryKey: ['admin-costs'] });
    },
    onError: () => toast.error('Cleanup failed'),
  });

  const cleanupOrphanMutation = useMutation({
    mutationFn: () => costsApi.cleanupOrphanFeeds(),
    onSuccess: (data) => {
      toast.success(`Removed ${data.removed} orphan feed(s)`);
      queryClient.invalidateQueries({ queryKey: ['admin-costs'] });
    },
    onError: () => toast.error('Cleanup failed'),
  });

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-gray-900">Platform Costs</h3>
          <p className="text-sm text-gray-500 mt-1">
            <b>Platform logic:</b> ${costs?.cost_rate_per_hour ?? 0.04}/hr of processing | <b>User attribution:</b> Divided by subscribers
          </p>
        </div>
        <MonthSelector
          year={year}
          month={month}
          onChange={(y, m) => {
            setYear(y);
            setMonth(m);
          }}
        />
      </div>

      {/* Summary */}
      {costsLoading ? (
        <div className="text-sm text-gray-500">Loading cost data…</div>
      ) : costs ? (
        <>
          <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-4">
            <div className="text-2xl font-bold text-indigo-700">
              ${costs.total_cost.toFixed(2)}
            </div>
            <div className="text-sm text-gray-600 mt-1">Total processing cost this month</div>
          </div>

          {/* Per-feed breakdown */}
          <section>
            <h4 className="text-sm font-semibold text-gray-700 mb-3">Cost by Feed</h4>
            {costs.feeds.length === 0 ? (
              <p className="text-sm text-gray-500">No processed episodes this month.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 pr-4 font-medium text-gray-600">Feed</th>
                      <th className="text-right py-2 pr-4 font-medium text-gray-600">Subs</th>
                      <th className="text-right py-2 pr-4 font-medium text-gray-600">Episodes</th>
                      <th className="text-right py-2 font-medium text-gray-600">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {costs.feeds.map((feed) => (
                      <tr key={feed.id} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="py-2 pr-4 text-gray-800 max-w-xs truncate">{feed.title}</td>
                        <td className="py-2 pr-4 text-right text-gray-600">{feed.subscriber_count}</td>
                        <td className="py-2 pr-4 text-right text-gray-600">{feed.episodes_this_month}</td>
                        <td className="py-2 text-right font-mono text-gray-800">
                          ${feed.monthly_cost.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Per-user breakdown */}
          <section>
            <h4 className="text-sm font-semibold text-gray-700 mb-3">Cost per User</h4>
            {costs.users.length === 0 ? (
              <p className="text-sm text-gray-500">No users found.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 pr-4 font-medium text-gray-600">User</th>
                      <th className="text-left py-2 pr-4 font-medium text-gray-600">Status</th>
                      <th className="text-right py-2 pr-4 font-medium text-gray-600">Feeds</th>
                      <th className="text-right py-2 pr-4 font-medium text-gray-600">Sub $/mo</th>
                      <th className="text-right py-2 font-medium text-gray-600">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {costs.users.map((user) => (
                      <tr key={user.id} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="py-2 pr-4 text-gray-800">{user.username}</td>
                        <td className="py-2 pr-4">
                          <span
                            className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${user.subscription_status === 'active'
                              ? 'bg-green-100 text-green-700'
                              : 'bg-gray-100 text-gray-500'
                              }`}
                          >
                            {user.subscription_status}
                          </span>
                        </td>
                        <td className="py-2 pr-4 text-right text-gray-600">{user.feed_count}</td>
                        <td className="py-2 pr-4 text-right font-mono text-gray-600">
                          {user.subscription_amount_cents != null
                            ? `$${(user.subscription_amount_cents / 100).toFixed(2)}`
                            : '—'}
                        </td>
                        <td className="py-2 text-right font-mono text-gray-800">
                          ${user.monthly_cost.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : null}

      {/* API Call Log */}
      <section>
        <h4 className="text-sm font-semibold text-gray-700 mb-3">API Call Log</h4>
        {callsLoading ? (
          <div className="text-sm text-gray-500">Loading call log…</div>
        ) : calls ? (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-2 pr-4 font-medium text-gray-600">Model</th>
                    <th className="text-left py-2 pr-4 font-medium text-gray-600">Status</th>
                    <th className="text-right py-2 pr-4 font-medium text-gray-600">Retries</th>
                    <th className="text-right py-2 font-medium text-gray-600">Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {calls.calls.map((c) => (
                    <tr key={c.id} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-2 pr-4 text-gray-800 font-mono text-xs">{c.model_name}</td>
                      <td className="py-2 pr-4">
                        <span
                          className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${c.status === 'completed'
                            ? 'bg-green-100 text-green-700'
                            : c.status === 'failed'
                              ? 'bg-red-100 text-red-700'
                              : 'bg-gray-100 text-gray-500'
                            }`}
                        >
                          {c.status}
                        </span>
                      </td>
                      <td className="py-2 pr-4 text-right text-gray-600">{c.retry_attempts}</td>
                      <td className="py-2 text-right text-gray-500 text-xs">
                        {c.timestamp ? new Date(c.timestamp).toLocaleString() : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* Pagination */}
            {calls.pages > 1 && (
              <div className="flex items-center justify-between mt-3">
                <span className="text-xs text-gray-500">
                  Page {calls.page} of {calls.pages} ({calls.total} calls)
                </span>
                <div className="flex gap-2">
                  <button
                    disabled={calls.page <= 1}
                    onClick={() => setCallPage((p) => p - 1)}
                    className="px-3 py-1 text-xs border border-gray-300 rounded disabled:opacity-40 hover:bg-gray-100"
                  >
                    Prev
                  </button>
                  <button
                    disabled={calls.page >= calls.pages}
                    onClick={() => setCallPage((p) => p + 1)}
                    className="px-3 py-1 text-xs border border-gray-300 rounded disabled:opacity-40 hover:bg-gray-100"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        ) : null}
      </section>

      {/* Cleanup utilities */}
      <section>
        <h4 className="text-sm font-semibold text-gray-700 mb-3">Cleanup Utilities</h4>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => cleanupCancelledMutation.mutate()}
            disabled={cleanupCancelledMutation.isPending}
            className="px-4 py-2 text-sm bg-yellow-50 border border-yellow-300 text-yellow-800 rounded hover:bg-yellow-100 disabled:opacity-50"
          >
            {cleanupCancelledMutation.isPending ? 'Removing…' : 'Remove cancelled-subscriber feeds'}
          </button>
          <button
            onClick={() => cleanupOrphanMutation.mutate()}
            disabled={cleanupOrphanMutation.isPending}
            className="px-4 py-2 text-sm bg-red-50 border border-red-300 text-red-800 rounded hover:bg-red-100 disabled:opacity-50"
          >
            {cleanupOrphanMutation.isPending ? 'Removing…' : 'Remove orphan feeds (no subscribers)'}
          </button>
        </div>
      </section>
    </div>
  );
}
