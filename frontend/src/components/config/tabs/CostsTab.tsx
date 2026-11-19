import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import ModalShell from '../../ModalShell';
import { ChevronDownIcon } from '../../icons';
import { costsApi } from '../../../services/api';
import type { CostSummary, CallLog, EstimatedCostBackfillResult, TokenBackfillResult } from '../../../types';
import { formatBackendDateTime } from '../../../utils/datetime';
import { Section } from '../shared';

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
        className="btn btn-secondary btn-icon btn-sm"
        aria-label="Previous month"
      >
        <ChevronDownIcon className="h-4 w-4 rotate-90" />
      </button>
      <span className="text-sm font-medium w-24 text-center">
        {months[month - 1]} {year}
      </span>
      <button
        onClick={() => {
          const d = new Date(year, month);
          onChange(d.getFullYear(), d.getMonth() + 1);
        }}
        className="btn btn-secondary btn-icon btn-sm"
        aria-label="Next month"
      >
        <ChevronDownIcon className="h-4 w-4 -rotate-90" />
      </button>
    </div>
  );
}

function formatUsd(value: number) {
  return `$${value.toFixed(value > 0 && value < 0.01 ? 4 : 2)}`;
}

// Cached tokens are already part of prompt_tokens, so they are not added again.
function costTokenTotal(call: CallLog['calls'][number]) {
  if (call.total_tokens != null) return call.total_tokens;
  if (call.prompt_tokens == null && call.completion_tokens == null) return null;
  return (call.prompt_tokens ?? 0) + (call.completion_tokens ?? 0);
}

function EstimatedCostBackfillSummary({ result }: { result: EstimatedCostBackfillResult }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-sm">
      <div className="rounded bg-gray-50 p-2">
        <div className="text-xs text-gray-600">Scanned</div>
        <div className="font-mono tabular-nums text-gray-900">{result.scanned.toLocaleString()}</div>
      </div>
      <div className="rounded bg-gray-50 p-2">
        <div className="text-xs text-gray-600">Eligible (billable LLM calls)</div>
        <div className="font-mono tabular-nums text-gray-900">{result.eligible.toLocaleString()}</div>
      </div>
      <div className="rounded bg-gray-50 p-2">
        <div className="text-xs text-gray-600">Non-billable</div>
        <div className="font-mono tabular-nums text-gray-900">{result.skipped_non_billable.toLocaleString()}</div>
      </div>
      <div className="rounded bg-gray-50 p-2" title="Run the token backfill first to price these.">
        <div className="text-xs text-gray-600">No token data</div>
        <div className="font-mono tabular-nums text-gray-900">{result.skipped_no_tokens.toLocaleString()}</div>
      </div>
      <div className="rounded bg-gray-50 p-2">
        <div className="text-xs text-gray-600">Updated</div>
        <div className="font-mono tabular-nums text-gray-900">{result.updated.toLocaleString()}</div>
      </div>
    </div>
  );
}

function BackfillSummary({ result }: { result: TokenBackfillResult }) {
  const modelEntries = Object.entries(result.models).slice(0, 5);
  return (
    <div className="space-y-3 text-sm">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <div className="rounded bg-gray-50 p-2">
          <div className="text-xs text-gray-600">Scanned</div>
          <div className="font-mono tabular-nums text-gray-900">{result.scanned.toLocaleString()}</div>
        </div>
        <div className="rounded bg-gray-50 p-2">
          <div className="text-xs text-gray-600">Eligible</div>
          <div className="font-mono tabular-nums text-gray-900">{result.eligible.toLocaleString()}</div>
        </div>
        <div className="rounded bg-gray-50 p-2">
          <div className="text-xs text-gray-600">Would update</div>
          <div className="font-mono tabular-nums text-gray-900">{result.would_update.toLocaleString()}</div>
        </div>
        <div className="rounded bg-gray-50 p-2">
          <div className="text-xs text-gray-600">Updated</div>
          <div className="font-mono tabular-nums text-gray-900">{result.updated.toLocaleString()}</div>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs text-gray-600">
        <div>Existing token data: <span className="font-mono tabular-nums">{result.skipped_existing.toLocaleString()}</span></div>
        <div>Non-LLM calls: <span className="font-mono tabular-nums">{result.skipped_non_llm.toLocaleString()}</span></div>
        <div>Missing text: <span className="font-mono tabular-nums">{result.skipped_missing_text.toLocaleString()}</span></div>
      </div>
      {modelEntries.length > 0 && (
        <div className="overflow-x-auto rounded border border-gray-200">
          <table className="min-w-full text-xs">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left py-2 px-2 font-medium text-gray-600">Model</th>
                <th className="text-right py-2 px-2 font-medium text-gray-600">Would update</th>
                <th className="text-right py-2 px-2 font-medium text-gray-600">Updated</th>
              </tr>
            </thead>
            <tbody>
              {modelEntries.map(([modelName, stats]) => (
                <tr key={modelName} className="border-b border-gray-100 last:border-b-0">
                  <td className="py-2 px-2 font-mono text-gray-700 truncate max-w-56">{modelName}</td>
                  <td className="py-2 px-2 text-right font-mono tabular-nums">{stats.would_update}</td>
                  <td className="py-2 px-2 text-right font-mono tabular-nums">{stats.updated}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {result.errors.length > 0 && (
        <div className="text-xs text-red-700 bg-red-50 rounded p-2">
          {result.errors.length} tokenizer/update error(s); first: {result.errors[0].error}
        </div>
      )}
    </div>
  );
}

export default function CostsTab() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [callPage, setCallPage] = useState(1);
  const [showBackfillWizard, setShowBackfillWizard] = useState(false);
  const [backfillLimit, setBackfillLimit] = useState('');
  const [backfillResult, setBackfillResult] = useState<TokenBackfillResult | null>(null);
  const [backfillNotice, setBackfillNotice] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);
  const [showCostBackfillWizard, setShowCostBackfillWizard] = useState(false);
  const [costBackfillLimit, setCostBackfillLimit] = useState('');
  const [costBackfillResult, setCostBackfillResult] =
    useState<EstimatedCostBackfillResult | null>(null);
  const [costBackfillNotice, setCostBackfillNotice] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);
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

  const costBackfillMutation = useMutation({
    mutationFn: (apply: boolean) => costsApi.backfillEstimatedCost({
      apply,
      limit: costBackfillLimit.trim() ? Number(costBackfillLimit) : null,
    }),
    onMutate: () => {
      setCostBackfillNotice(null);
    },
    onSuccess: (data) => {
      setCostBackfillResult(data);
      if (data.applied) {
        setCostBackfillNotice({
          type: data.failed_updates > 0 ? 'error' : 'success',
          message: data.failed_updates > 0
            ? `Backfill finished with ${data.updated} update(s) and ${data.failed_updates} failure(s).`
            : `Backfill complete. Updated ${data.updated} model call(s).`,
        });
        toast.success(`Backfilled ${data.updated} model call(s)`);
        queryClient.invalidateQueries({ queryKey: ['admin-costs'] });
        queryClient.invalidateQueries({ queryKey: ['admin-calls'] });
      } else {
        setCostBackfillNotice({
          type: 'success',
          message: `Dry run complete. ${data.eligible} model call(s) would be updated.`,
        });
        toast.success(`Dry run found ${data.eligible} model call(s) to price`);
      }
    },
    onError: () => {
      setCostBackfillNotice({
        type: 'error',
        message: 'Estimated-cost backfill failed. No model calls were updated.',
      });
      toast.error('Estimated-cost backfill failed');
    },
  });

  const backfillMutation = useMutation({
    mutationFn: (apply: boolean) => costsApi.backfillTokenUsage({
      apply,
      limit: backfillLimit.trim() ? Number(backfillLimit) : null,
    }),
    onMutate: () => {
      setBackfillNotice(null);
    },
    onSuccess: (data) => {
      setBackfillResult(data);
      if (data.apply) {
        setBackfillNotice({
          type: data.failed_updates > 0 ? 'error' : 'success',
          message: data.failed_updates > 0
            ? `Backfill finished with ${data.updated} update(s) and ${data.failed_updates} failure(s).`
            : `Backfill complete. Updated ${data.updated} model call(s).`,
        });
        toast.success(`Backfilled ${data.updated} model call(s)`);
        queryClient.invalidateQueries({ queryKey: ['admin-costs'] });
        queryClient.invalidateQueries({ queryKey: ['admin-calls'] });
      } else {
        setBackfillNotice({
          type: 'success',
          message: `Dry run complete. ${data.would_update} model call(s) would be updated.`,
        });
        toast.success(`Dry run found ${data.would_update} model call(s) to update`);
      }
    },
    onError: () => {
      setBackfillNotice({
        type: 'error',
        message: 'Token backfill failed. No token usage was updated.',
      });
      toast.error('Token backfill failed');
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <MonthSelector
          year={year}
          month={month}
          onChange={(y, m) => {
            setYear(y);
            setMonth(m);
          }}
        />
        <p className="min-w-0 text-sm text-gray-600">
          Priced from LiteLLM token rates, Whisper at ${costs?.whisper_cost_rate_per_hour ?? 0.04}/hr. User costs split each feed&apos;s cost across its subscribers.
        </p>
      </div>

      {costsLoading ? (
        <div className="text-sm text-gray-600">Loading cost data…</div>
      ) : costs ? (
        <>
          <Section title="Total for the month" stacked>
            <div>
              <div className="text-2xl font-semibold tabular-nums text-gray-900">
                {formatUsd(costs.total_cost)}
              </div>
              <div className="mt-1 text-sm tabular-nums text-gray-600">
                {(costs.total_audio_hours ?? 0).toFixed(2)} hours of audio
              </div>
            </div>
            <dl className="grid grid-cols-2 gap-3 border-t border-gray-200 pt-3">
              {[
                ['LLM', costs.total_llm_cost],
                ['Whisper', costs.total_whisper_cost],
              ].map(([label, value]) => (
                <div key={label as string}>
                  <dt className="text-xs text-gray-600">{label}</dt>
                  <dd className="font-semibold tabular-nums text-gray-900">
                    {formatUsd(value as number)}
                  </dd>
                </div>
              ))}
            </dl>
            <div className="border-t border-gray-200 pt-3 text-sm text-gray-600">
              <div>
                Service tier:{' '}
                <span className="font-medium text-gray-900">{costs.llm_service_tier}</span>
              </div>
              {Object.keys(costs.llm_cost_by_tier ?? {}).length > 0 && (
                <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1">
                  {Object.entries(costs.llm_cost_by_tier).map(([tier, cost]) => (
                    <div key={tier} className="flex gap-1.5">
                      <dt>LLM at {tier}:</dt>
                      <dd className="font-medium tabular-nums text-gray-900">{formatUsd(cost)}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
          </Section>

          <Section title="Cost by feed" stacked>
            {costs.feeds.length === 0 ? (
              <p className="text-sm text-gray-600">No processed episodes this month.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm tabular-nums">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 pr-4 font-medium text-gray-600">Feed</th>
                      <th className="text-right py-2 pr-4 font-medium text-gray-600">Subscribers</th>
                      <th className="text-right py-2 pr-4 font-medium text-gray-600">Episodes</th>
                      <th className="text-right py-2 pr-4 font-medium text-gray-600">LLM</th>
                      <th className="text-right py-2 pr-4 font-medium text-gray-600">Whisper</th>
                      <th className="text-right py-2 font-medium text-gray-600">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {costs.feeds.map((feed) => (
                      <tr key={feed.id} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="py-2 pr-4 text-gray-800 max-w-xs truncate">{feed.title}</td>
                        <td className="py-2 pr-4 text-right text-gray-600">{feed.subscriber_count}</td>
                        <td className="py-2 pr-4 text-right text-gray-600">{feed.episodes_this_month}</td>
                        <td className="py-2 pr-4 text-right font-mono text-gray-600">{formatUsd(feed.llm_cost)}</td>
                        <td className="py-2 pr-4 text-right font-mono text-gray-600">{formatUsd(feed.whisper_cost)}</td>
                        <td className="py-2 text-right font-mono text-gray-800">
                          {formatUsd(feed.monthly_cost)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          <Section title="Cost by user" stacked>
            {costs.users.length === 0 ? (
              <p className="text-sm text-gray-600">No users found.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm tabular-nums">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 pr-4 font-medium text-gray-600">User</th>
                      <th className="text-left py-2 pr-4 font-medium text-gray-600">Status</th>
                      <th className="text-right py-2 pr-4 font-medium text-gray-600">Feeds</th>
                      <th className="text-right py-2 pr-4 font-medium text-gray-600">Subscription $/month</th>
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
                              ? 'bg-green-50 text-green-700'
                              : 'bg-gray-100 text-gray-600'
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
                          {formatUsd(user.monthly_cost)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        </>
      ) : null}

      <Section title="API call log" stacked>
        {callsLoading ? (
          <div className="text-sm text-gray-600">Loading call log…</div>
        ) : calls ? (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm tabular-nums">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-2 pr-4 font-medium text-gray-600">Model</th>
                    <th className="text-left py-2 pr-4 font-medium text-gray-600">Status</th>
                    <th className="text-left py-2 pr-4 font-medium text-gray-600">Tier</th>
                    <th className="text-right py-2 pr-4 font-medium text-gray-600">Tokens</th>
                    <th className="text-right py-2 pr-4 font-medium text-gray-600">Cost</th>
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
                            ? 'bg-green-50 text-green-700'
                            : c.status === 'failed'
                              ? 'bg-red-50 text-red-700'
                              : 'bg-gray-100 text-gray-600'
                            }`}
                        >
                          {c.status}
                        </span>
                      </td>
                      <td className="py-2 pr-4 text-gray-600 text-xs">{c.service_tier ?? '—'}</td>
                      <td
                        className="py-2 pr-4 text-right text-gray-600 font-mono text-xs"
                        title={`prompt ${c.prompt_tokens ?? '—'} + cached ${c.cached_prompt_tokens ?? '—'} + completion ${c.completion_tokens ?? '—'}`}
                      >
                        {costTokenTotal(c) != null ? costTokenTotal(c)?.toLocaleString() : '—'}
                      </td>
                      <td className="py-2 pr-4 text-right text-gray-600 font-mono">
                        {c.estimated_cost != null ? `$${c.estimated_cost.toFixed(4)}` : '—'}
                      </td>
                      <td className="py-2 pr-4 text-right text-gray-600">{c.retry_attempts}</td>
                      <td className="py-2 text-right text-gray-600 text-xs whitespace-nowrap">
                        {formatBackendDateTime(c.timestamp)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {calls.pages > 1 && (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs tabular-nums text-gray-600">
                  Page {calls.page} of {calls.pages} ({calls.total} calls)
                </span>
                <div className="flex gap-2">
                  <button
                    disabled={calls.page <= 1}
                    onClick={() => setCallPage((p) => p - 1)}
                    className="btn btn-secondary btn-sm"
                  >
                    Prev
                  </button>
                  <button
                    disabled={calls.page >= calls.pages}
                    onClick={() => setCallPage((p) => p + 1)}
                    className="btn btn-secondary btn-sm"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        ) : null}
      </Section>

      <Section title="Maintenance" collapsible stacked>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => cleanupCancelledMutation.mutate()}
            disabled={cleanupCancelledMutation.isPending}
            className="btn btn-secondary"
          >
            {cleanupCancelledMutation.isPending ? 'Removing…' : 'Remove cancelled-subscriber feeds'}
          </button>
          <button
            onClick={() => cleanupOrphanMutation.mutate()}
            disabled={cleanupOrphanMutation.isPending}
            className="btn btn-secondary"
          >
            {cleanupOrphanMutation.isPending ? 'Removing…' : 'Remove orphan feeds (no subscribers)'}
          </button>
          <button
            onClick={() => {
              setShowBackfillWizard(true);
              setBackfillResult(null);
              setBackfillNotice(null);
            }}
            className="btn btn-secondary"
          >
            Backfill token usage
          </button>
          <button
            onClick={() => {
              setShowCostBackfillWizard(true);
              setCostBackfillResult(null);
              setCostBackfillNotice(null);
            }}
            className="btn btn-secondary"
            title="Prices legacy model calls so cost can be shown without loading LiteLLM into the web process."
          >
            Backfill estimated cost
          </button>
        </div>
      </Section>

      <ModalShell
        isOpen={showBackfillWizard}
        onClose={() => setShowBackfillWizard(false)}
        panelClassName="w-full max-w-2xl rounded-lg border border-gray-200 bg-surface p-5"
      >
        <div className="space-y-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h4 className="text-base font-semibold text-gray-900">Backfill token usage</h4>
              <p className="text-sm text-gray-600 mt-1">
                Estimate missing prompt and completion tokens for legacy successful LLM calls. Cached prompt tokens stay blank.
              </p>
            </div>
            <button
              onClick={() => setShowBackfillWizard(false)}
              className="btn btn-ghost btn-icon btn-sm"
              aria-label="Close"
            >
              ×
            </button>
          </div>

          <label className="block">
            <span className="text-sm font-medium text-gray-700">Scan limit</span>
            <input
              type="number"
              min="1"
              value={backfillLimit}
              onChange={(event) => {
                setBackfillLimit(event.target.value);
                setBackfillResult(null);
                setBackfillNotice(null);
              }}
              placeholder="All model calls"
              className="input mt-1.5"
            />
          </label>

          {backfillResult && <BackfillSummary result={backfillResult} />}

          {backfillNotice && (
            <div
              className={`text-sm rounded border px-3 py-2 ${backfillNotice.type === 'success'
                ? 'bg-green-50 border-green-200 text-green-800'
                : 'bg-red-50 border-red-200 text-red-800'
                }`}
              role="status"
              aria-live="polite"
            >
              {backfillNotice.message}
            </div>
          )}

          <div className="flex flex-wrap justify-end gap-3">
            <button
              onClick={() => backfillMutation.mutate(false)}
              disabled={backfillMutation.isPending}
              className="btn btn-secondary"
            >
              {backfillMutation.isPending ? 'Running…' : 'Run dry run'}
            </button>
            <button
              onClick={() => backfillMutation.mutate(true)}
              disabled={
                backfillMutation.isPending ||
                !backfillResult ||
                backfillResult.apply ||
                backfillResult.would_update <= 0
              }
              className="btn btn-primary"
            >
              Apply backfill
            </button>
          </div>
        </div>
      </ModalShell>

      <ModalShell
        isOpen={showCostBackfillWizard}
        onClose={() => setShowCostBackfillWizard(false)}
        panelClassName="w-full max-w-2xl rounded-lg border border-gray-200 bg-surface p-5"
      >
        <div className="space-y-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h4 className="text-base font-semibold text-gray-900">Backfill estimated cost</h4>
              <p className="text-sm text-gray-600 mt-1">
                Prices legacy model calls so the stats page can show per-call cost. This loads LiteLLM into the web process (about 160 MiB), so restart the web service afterwards to release the memory. New calls are priced automatically.
              </p>
            </div>
            <button
              onClick={() => setShowCostBackfillWizard(false)}
              className="btn btn-ghost btn-icon btn-sm"
              aria-label="Close"
            >
              ×
            </button>
          </div>

          <label className="block">
            <span className="text-sm font-medium text-gray-700">Scan limit</span>
            <input
              type="number"
              min="1"
              value={costBackfillLimit}
              onChange={(event) => {
                setCostBackfillLimit(event.target.value);
                setCostBackfillResult(null);
                setCostBackfillNotice(null);
              }}
              placeholder="All unpriced successful calls"
              className="input mt-1.5"
            />
          </label>

          {costBackfillResult && <EstimatedCostBackfillSummary result={costBackfillResult} />}

          {costBackfillNotice && (
            <div
              className={`text-sm rounded border px-3 py-2 ${costBackfillNotice.type === 'success'
                ? 'bg-green-50 border-green-200 text-green-800'
                : 'bg-red-50 border-red-200 text-red-800'
                }`}
              role="status"
              aria-live="polite"
            >
              {costBackfillNotice.message}
            </div>
          )}

          <div className="flex flex-wrap justify-end gap-3">
            <button
              onClick={() => costBackfillMutation.mutate(false)}
              disabled={costBackfillMutation.isPending}
              className="btn btn-secondary"
            >
              {costBackfillMutation.isPending ? 'Running…' : 'Run dry run'}
            </button>
            <button
              onClick={() => costBackfillMutation.mutate(true)}
              disabled={
                costBackfillMutation.isPending ||
                !costBackfillResult ||
                costBackfillResult.applied ||
                costBackfillResult.eligible <= 0
              }
              className="btn btn-primary"
            >
              Apply backfill
            </button>
          </div>
        </div>
      </ModalShell>
    </div>
  );
}
