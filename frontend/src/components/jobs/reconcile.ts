import type { Job } from '../../types';

// Returns `prev` itself when a poll brings no change, so React skips the
// state update. Unchanged jobs keep their previous object identity so memoized
// cards don't re-render.
export function reconcileJobs(prev: Job[], next: Job[]): Job[] {
  const prevById = new Map(prev.map((job) => [job.job_id, job] as const));
  const merged = next.map((job) => {
    const previous = prevById.get(job.job_id);
    return previous !== undefined && JSON.stringify(previous) === JSON.stringify(job)
      ? previous
      : job;
  });
  const unchanged =
    merged.length === prev.length && merged.every((job, index) => job === prev[index]);
  return unchanged ? prev : merged;
}

export function reconcileValue<T>(prev: T | null, next: T): T {
  return prev !== null && JSON.stringify(prev) === JSON.stringify(next) ? (prev as T) : next;
}
