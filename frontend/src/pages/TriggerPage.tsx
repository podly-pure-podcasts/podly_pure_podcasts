/**
 * Trigger Page - Public page for processing episodes via feed token auth.
 * 
 * This page is accessed via RSS feed links and uses feed token authentication
 * (not session auth). It displays the canonical processing progress UI.
 * 
 * URL: /trigger?guid=X&token_id=Y&secret=Z
 * 
 * Polling rules:
 * - Single interval owner (intervalRef)
 * - Stops permanently on terminal states (ready, failed, error)
 * - HTTP-driven: 200=valid, 4xx=permanent error, 5xx=temporary
 * - "Temporary error" only for 5xx/network failures
 */

import { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import ProcessingProgressUI from '../components/ProcessingProgressUI';

const TERMINAL_STATES = ['ready', 'completed', 'failed', 'error'];
const POLL_INTERVAL_MS = 2000;

interface ErrorDetails {
  friendly: string;
  technical: string | null;
  retry_suggested: boolean;
}

interface TriggerStatus {
  state: 'ready' | 'processing' | 'queued' | 'failed' | 'not_found' | 'error' | 'not_started';
  processed: boolean;
  download_url: string | null;
  message: string;
  error_details?: ErrorDetails;
  job: {
    id: string;
    status: string;
    current_step: number;
    total_steps: number;
    step_name: string;
    progress_percentage: number;
    error_message?: string;
  } | null;
}

export default function TriggerPage() {
  const [searchParams] = useSearchParams();
  const guid = searchParams.get('guid');
  const tokenId = searchParams.get('token_id') || searchParams.get('feed_token');
  const secret = searchParams.get('secret') || searchParams.get('feed_secret');

  const [status, setStatus] = useState<TriggerStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<ErrorDetails | null>(null);
  const [isTemporarilyUnavailable, setIsTemporarilyUnavailable] = useState(false);
  const [copiedFeedUrl, setCopiedFeedUrl] = useState(false);
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);

  // Single polling owner - only one interval ever exists
  const intervalRef = useRef<number | null>(null);
  const stoppedRef = useRef(false);

  // Stop polling permanently
  const stopPolling = () => {
    stoppedRef.current = true;
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  // Build status URL
  const buildStatusUrl = () => {
    if (!guid || !tokenId || !secret) return null;
    return `/api/trigger/status?guid=${encodeURIComponent(guid)}&feed_token=${encodeURIComponent(tokenId)}&feed_secret=${encodeURIComponent(secret)}&t=${Date.now()}`;
  };

  // Fetch status - HTTP-driven logic
  const fetchStatus = async () => {
    if (stoppedRef.current) return;

    const url = buildStatusUrl();
    if (!url) return;

    try {
      const response = await fetch(url, {
        method: 'GET',
        cache: 'no-store',
        credentials: 'omit',
        headers: {
          Accept: 'application/json',
          'Cache-Control': 'no-store',
        },
      });

      const data = await response.json().catch(() => null);

      // 2xx: valid response
      if (response.ok) {
        // Handle failed state with error details
        if (data?.state === 'failed') {
          setStatus(data);
          setError(data?.message || 'Processing failed');
          setErrorDetails(data?.error_details || null);
          setIsTemporarilyUnavailable(false);
          stopPolling();
          return;
        }

        // Handle error state
        if (!data || data.state === 'error') {
          setError(data?.message || 'Unexpected status response');
          setErrorDetails(null);
          setIsTemporarilyUnavailable(false);
          stopPolling();
          return;
        }

        // Valid status - update UI
        setStatus(data);
        setError(null);
        setErrorDetails(null);
        setIsTemporarilyUnavailable(false);

        // Terminal state - stop polling permanently
        if (TERMINAL_STATES.includes(data.state)) {
          stopPolling();
        }
        return;
      }

      // 5xx: temporary server error - show banner, keep polling
      if (response.status >= 500) {
        setIsTemporarilyUnavailable(true);
        console.warn('[TriggerPage] 5xx response, retrying...', response.status, data?.message);
        return;
      }

      // 4xx: permanent error - stop polling
      setError(data?.message || `Error: ${response.status}`);
      setIsTemporarilyUnavailable(false);
      stopPolling();
    } catch (err) {
      // Network error - temporary, keep polling
      console.error('[TriggerPage] Network error:', err);
      setIsTemporarilyUnavailable(true);
    }
  };

  // Single effect for polling lifecycle
  useEffect(() => {
    if (!guid || !tokenId || !secret) {
      setError('Missing required parameters: guid, token_id, secret');
      return;
    }

    // Reset state for fresh mount
    stoppedRef.current = false;

    // Initial fetch
    fetchStatus();

    // Start single polling interval
    intervalRef.current = window.setInterval(fetchStatus, POLL_INTERVAL_MS);

    // Cleanup on unmount
    return () => {
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guid, tokenId, secret]);

  // Adapt trigger status to ProcessingProgressUI props
  const getProgressProps = () => {
    if (!status?.job) {
      if (status?.state === 'ready') {
        return {
          status: 'completed' as const,
          step: 4,
          stepName: 'Complete',
          totalSteps: 4,
        };
      }
      if (status?.state === 'queued') {
        return {
          status: 'pending' as const,
          step: 0,
          stepName: 'Waiting in queue...',
          totalSteps: 4,
        };
      }
      return null;
    }

    return {
      status: (status.job.status === 'running' ? 'running' : 
               status.job.status === 'pending' ? 'pending' :
               status.job.status === 'completed' ? 'completed' :
               status.job.status === 'failed' ? 'failed' : 'pending') as 'running' | 'pending' | 'completed' | 'failed',
      step: status.job.current_step,
      stepName: status.job.step_name || `Step ${status.job.current_step}/${status.job.total_steps}`,
      totalSteps: status.job.total_steps,
      jobId: status.job.id,
      error: status.job.error_message,
    };
  };

  const progressProps = getProgressProps();

  // Missing params error
  if (!guid || !tokenId || !secret) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-700 via-blue-800 to-blue-950 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full overflow-hidden">
          <div className="bg-gradient-to-r from-blue-600 via-blue-700 to-blue-800 p-6 text-center">
            <h1 className="text-2xl font-bold text-white">Podly</h1>
            <p className="text-blue-200 text-sm mt-1">Ad-free podcast processing</p>
          </div>
          <div className="p-6 text-center">
            <div className="text-4xl mb-4">&#9888;</div>
            <h2 className="text-xl font-semibold text-gray-800 mb-2">Invalid Link</h2>
            <p className="text-gray-600">This link is missing required parameters. Please use the link from your podcast app.</p>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-700 via-blue-800 to-blue-950 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full overflow-hidden">
          <div className="bg-gradient-to-r from-blue-600 via-blue-700 to-blue-800 p-6 text-center">
            <h1 className="text-2xl font-bold text-white">Podly</h1>
            <p className="text-blue-200 text-sm mt-1">Ad-free podcast processing</p>
          </div>
          <div className="p-6 text-center">
            <div className="text-4xl mb-4 text-red-500">&#10060;</div>
            <h2 className="text-xl font-semibold text-gray-800 mb-2">Processing Failed</h2>
            <p className="text-gray-600 mb-4">{errorDetails?.friendly || error}</p>

            {/* Retry suggestion */}
            {errorDetails?.retry_suggested && (
              <p className="text-sm text-blue-600 mb-4">
                This may be a temporary issue. Please try again in a few minutes.
              </p>
            )}

            {/* Technical details toggle */}
            {errorDetails?.technical && (
              <div className="mt-4 text-left">
                <button
                  onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
                  className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1 mx-auto"
                >
                  <span>{showTechnicalDetails ? '▼' : '▶'}</span>
                  <span>Technical details</span>
                </button>
                {showTechnicalDetails && (
                  <div className="mt-2 p-3 bg-gray-100 rounded-lg text-left">
                    <code className="text-xs text-gray-600 break-all whitespace-pre-wrap">
                      {errorDetails.technical}
                    </code>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Copy RSS feed URL to clipboard
  const handleCopyFeedUrl = async () => {
    if (!tokenId || !secret) return;
    
    // Build the RSS feed URL (not the download URL)
    const feedUrl = `${window.location.origin}/feed/combined?feed_token=${tokenId}&feed_secret=${secret}`;
    
    try {
      await navigator.clipboard.writeText(feedUrl);
      setCopiedFeedUrl(true);
      setTimeout(() => setCopiedFeedUrl(false), 2000);
    } catch {
      // Fallback: show in prompt
      window.prompt('Copy this RSS feed URL:', feedUrl);
    }
  };

  // Ready state - show return instructions
  if (status?.state === 'ready') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-700 via-blue-800 to-blue-950 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full overflow-hidden">
          <div className="bg-gradient-to-r from-blue-600 via-blue-700 to-blue-800 p-6 text-center">
            <h1 className="text-2xl font-bold text-white">Podly</h1>
            <p className="text-blue-200 text-sm mt-1">Ad-free podcast processing</p>
          </div>
          <div className="p-6">
            <div className="text-center mb-6">
              <div className="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-emerald-600" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
              </div>
              <h2 className="text-2xl font-bold text-emerald-600 mb-3">Episode Ready</h2>
              <p className="text-gray-700 text-base leading-relaxed">
                Return to your podcast app and refresh the feed.
                <br />
                The processed episode will download there.
              </p>
            </div>

            {/* Primary instruction - not a button, just prominent text */}
            <div className="bg-blue-50 rounded-xl p-4 mb-4 text-center">
              <p className="text-blue-800 font-semibold text-lg mb-1">
                Close this tab now
              </p>
              <p className="text-blue-600 text-sm">
                and return to your podcast app
              </p>
            </div>

            {/* Secondary actions */}
            <div className="border-t border-gray-100 pt-4">
              <button
                onClick={handleCopyFeedUrl}
                className="w-full py-2 px-4 text-blue-600 text-sm font-medium hover:bg-blue-50 rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                {copiedFeedUrl ? (
                  <>
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                    Copied!
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    Copy processed feed link
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Processing state
  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-700 via-blue-800 to-blue-950 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full overflow-hidden">
        <div className="bg-gradient-to-r from-blue-600 via-blue-700 to-blue-800 p-6 text-center">
          <h1 className="text-2xl font-bold text-white">Podly</h1>
          <p className="text-blue-200 text-sm mt-1">Ad-free podcast processing</p>
        </div>
        <div className="p-6">
          {/* Temporary unavailable warning - shown when polling fails but we have previous status */}
          {isTemporarilyUnavailable && (
            <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-700 text-sm text-center">
              Temporarily unavailable, retrying...
            </div>
          )}
          
          <div className="text-center mb-6">
            <h2 className="text-xl font-semibold text-gray-800 mb-2">
              {status?.state === 'queued' ? 'Queued for Processing' : 'Processing Episode'}
            </h2>
            <p className="text-gray-600 text-sm">
              {status?.message || 'Removing ads from your episode...'}
            </p>
          </div>

          {/* Canonical progress UI */}
          {progressProps && (
            <ProcessingProgressUI {...progressProps} />
          )}

          <div className="mt-6 text-center text-sm text-gray-500">
            <p>This page updates automatically.</p>
            <p className="mt-1">You can close this page and return later.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
