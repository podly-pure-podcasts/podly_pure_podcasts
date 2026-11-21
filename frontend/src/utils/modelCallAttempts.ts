// `ModelCall.retry_attempts` counts Podly's own attempts at a call, including the
// first one: ad classification stores 1 for a first-try success and 2 after one
// retry, and the boundary refiners store 1 for their single request. Transcription
// rows never record a count and keep 0, so 0 means "not tracked", not "no requests".

export const ATTEMPTS_COLUMN_LABEL = 'Attempts';

export const ATTEMPTS_COLUMN_TITLE =
  "Podly's attempts at this call, including the first one (1 = succeeded first time). " +
  'Retries inside the provider client are not counted.';

const NOT_TRACKED_TITLE = 'No attempt count is recorded for this call';

export function formatModelCallAttempts(value: number | null | undefined): {
  text: string;
  title: string;
} {
  if (value == null || !Number.isFinite(value) || value <= 0) {
    return { text: '—', title: NOT_TRACKED_TITLE };
  }
  return {
    text: String(value),
    title: value === 1 ? '1 attempt' : `${value} attempts (${value - 1} retried)`,
  };
}
