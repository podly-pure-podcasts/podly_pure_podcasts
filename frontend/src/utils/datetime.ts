// The Flask backend serializes naive UTC datetimes via `.isoformat()`, which
// produces strings like "2026-05-15T00:57:44.123456" with no timezone marker.
// `new Date()` treats those as local time, which is wrong. This helper appends
// a `Z` when the string lacks an offset so the Date is anchored to UTC and
// then rendered in the user's local timezone by `toLocaleString` and friends.

const TZ_SUFFIX = /(Z|[+-]\d{2}:?\d{2})$/i;

export function parseBackendDate(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const normalized = TZ_SUFFIX.test(value) ? value : `${value}Z`;
  const date = new Date(normalized);
  return Number.isFinite(date.getTime()) ? date : null;
}

export function formatBackendDateTime(value: string | null | undefined): string {
  const date = parseBackendDate(value);
  return date ? date.toLocaleString() : '—';
}

export function formatBackendDate(
  value: string | null | undefined,
  options: Intl.DateTimeFormatOptions = { year: 'numeric', month: 'short', day: 'numeric' },
): string {
  const date = parseBackendDate(value);
  return date ? date.toLocaleDateString(undefined, options) : '—';
}

export function formatBackendTime(
  value: string | null | undefined,
  options: Intl.DateTimeFormatOptions = { hour: 'numeric', minute: '2-digit' },
): string {
  const date = parseBackendDate(value);
  return date ? date.toLocaleTimeString(undefined, options) : '';
}

export function backendDateMs(value: string | null | undefined): number {
  const date = parseBackendDate(value);
  return date ? date.getTime() : NaN;
}

export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) {
    return '—';
  }
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m ${seconds.toString().padStart(2, '0')}s`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds.toString().padStart(2, '0')}s`;
  }
  return `${seconds}s`;
}
