import { useEffect, useMemo, useState } from 'react';
import { useDiagnostics } from '../contexts/DiagnosticsContext';
import { DIAGNOSTIC_UPDATED_EVENT, diagnostics, type DiagnosticsEntry } from '../utils/diagnostics';
import ModalShell from './ModalShell';
import { CloseIcon } from './icons';

const GITHUB_NEW_ISSUE_URL = 'https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/new';

const buildIssueUrl = (title: string, body: string) => {
  const url = new URL(GITHUB_NEW_ISSUE_URL);
  url.searchParams.set('title', title);
  url.searchParams.set('body', body);
  return url.toString();
};

const formatTs = (ts: number) => {
  try {
    return new Date(ts).toISOString();
  } catch {
    return String(ts);
  }
};

export default function DiagnosticsModal() {
  const { isOpen, close, clear, getEntries, currentError } = useDiagnostics();
  const [entries, setEntries] = useState<DiagnosticsEntry[]>(() => getEntries());

  useEffect(() => {
    if (!isOpen) return;

    // Refresh immediately when opened
    setEntries(getEntries());

    const handler = () => {
      setEntries(getEntries());
    };

    window.addEventListener(DIAGNOSTIC_UPDATED_EVENT, handler);
    return () => window.removeEventListener(DIAGNOSTIC_UPDATED_EVENT, handler);
  }, [getEntries, isOpen]);

  const recentEntries = useMemo(() => entries.slice(-80), [entries]);

  const issueTitle = currentError?.title
    ? `[FE] ${currentError.title}`
    : '[FE] Troubleshooting info';

  const issueBody = useMemo(() => {
    const env = {
      userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : null,
      url: typeof window !== 'undefined' ? window.location.href : null,
      time: new Date().toISOString(),
    };

    const payload = {
      error: currentError,
      env,
      logs: recentEntries,
    };

    const json = JSON.stringify(diagnostics.sanitize(payload), null, 2);

    return [
      '## What happened',
      '(Describe what you clicked / expected / saw)',
      '',
      '## Diagnostics (auto-collected)',
      '```json',
      json,
      '```',
    ].join('\n');
  }, [currentError, recentEntries]);

  const issueUrl = useMemo(() => buildIssueUrl(issueTitle, issueBody), [issueTitle, issueBody]);

  return (
    <ModalShell
      isOpen={isOpen}
      onClose={close}
      panelClassName="w-full max-w-3xl bg-surface border border-gray-200 rounded-lg overflow-hidden"
    >
      <div>
        <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-gray-200">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Troubleshooting</h2>
            <p className="text-sm text-gray-600">
              {currentError
                ? 'An error occurred. You can report it with logs.'
                : 'Use this to collect logs for a bug report.'}
            </p>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label="Close"
            title="Close"
            className="btn btn-ghost btn-icon btn-sm"
          >
            <CloseIcon />
          </button>
        </div>

        {currentError && (
          <div className="px-5 py-4 border-b border-gray-200 bg-red-50">
            <div className="text-sm font-medium text-red-900">{currentError.title}</div>
            <div className="text-sm text-red-800 mt-1">{currentError.message}</div>
          </div>
        )}

        <div className="px-5 py-4">
          <div className="flex flex-col sm:flex-row gap-2 sm:items-center sm:justify-between mb-3">
            <div className="text-sm text-gray-700">
              Showing last {recentEntries.length} log entries (session only).
            </div>
            <div className="flex gap-2">
              <a
                href={issueUrl}
                target="_blank"
                rel="noreferrer"
                className="btn btn-primary"
              >
                Report on GitHub
              </a>
              <button
                type="button"
                onClick={() => {
                  try {
                    navigator.clipboard.writeText(issueBody);
                  } catch {
                    // ignore
                  }
                }}
                className="btn btn-secondary"
              >
                Copy logs
              </button>
              <button
                type="button"
                onClick={() => {
                  clear();
                }}
                className="btn btn-secondary"
              >
                Clear
              </button>
            </div>
          </div>

          <div className="border border-gray-200 rounded-md bg-gray-50 overflow-hidden">
            <div className="max-h-[45vh] overflow-auto">
              <pre className="text-xs text-gray-800 p-3 whitespace-pre-wrap break-words">
{recentEntries
  .map((e) => {
    const base = `[${formatTs(e.ts)}] ${e.level.toUpperCase()}: ${e.message}`;
    if (e.data === undefined) return base;
    try {
      return base + `\n  ${JSON.stringify(e.data)}`;
    } catch {
      return base;
    }
  })
  .join('\n')}
              </pre>
            </div>
          </div>

          <div className="text-xs text-gray-500 mt-2">
            Sensitive fields like tokens/cookies are redacted.
          </div>
        </div>
      </div>
    </ModalShell>
  );
}
