export const formatTimelineLabel = (seconds: number) => {
  const totalSeconds = Math.max(0, Math.round(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }

  return `${minutes}:${secs.toString().padStart(2, '0')}`;
};

export const formatTimelineRange = (startSeconds: number, endSeconds: number) => (
  `${formatTimelineLabel(startSeconds)}-${formatTimelineLabel(endSeconds)}`
);

const TIMELINE_TICK_STEPS_SECONDS = [60, 120, 300, 600, 900, 1800, 3600];
const MAX_TIMELINE_TICKS = 6;

export interface TimelineTick {
  seconds: number;
  percent: number;
}

/** Round-step ticks from 0 up to the duration, at most six, with no forced tick at the end. */
export const getTimelineTicks = (durationSeconds: number): TimelineTick[] => {
  if (!Number.isFinite(durationSeconds) || durationSeconds <= 0) {
    return [{ seconds: 0, percent: 0 }];
  }

  const step = TIMELINE_TICK_STEPS_SECONDS.find(
    (candidate) => Math.floor(durationSeconds / candidate) + 1 <= MAX_TIMELINE_TICKS
  ) ?? TIMELINE_TICK_STEPS_SECONDS[TIMELINE_TICK_STEPS_SECONDS.length - 1];

  const ticks: TimelineTick[] = [];
  for (let seconds = 0; seconds <= durationSeconds; seconds += step) {
    ticks.push({ seconds, percent: (seconds / durationSeconds) * 100 });
  }
  return ticks;
};
