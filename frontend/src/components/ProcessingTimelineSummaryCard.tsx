import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';
import { formatTimelineLabel, getTimelineTicks } from '../utils/processingTimeline';

interface TimelineSegment {
  startTime: number;
  endTime: number;
  kind?: 'range' | 'point';
  visualDurationSeconds?: number;
  tooltipTitle: string;
  tooltipRows: Array<{
    label: string;
    value: string;
  }>;
  ariaLabel?: string;
}

interface ProcessingTimelineSummaryCardProps {
  title: string;
  itemCount: number;
  itemLabel: string;
  totalTimeSeconds: number;
  totalTimeLabel: string;
  percentage: number;
  percentageLabel: string;
  durationSeconds: number;
  timelineDurationSeconds?: number;
  minimumSegmentWidthPercent?: number;
  minimumSegmentWidthPx?: number;
  minimumPointWidthPx?: number;
  segments: TimelineSegment[];
  segmentClassName: string;
  legendBaseLabel?: string;
  legendSegmentLabel: string;
  variant?: 'markers' | 'density';
  itemNoun?: { one: string; other: string };
}

interface DensityBin {
  count: number;
  seconds: number;
  nearest: TimelineSegment | null;
}

const DENSITY_BIN_PX = 4;
const DENSITY_MIN_BINS = 40;
const DENSITY_MAX_BINS = 240;
const DENSITY_MAX_BAR_PX = 24;
const DENSITY_MIN_BAR_PX = 3;
const DEFAULT_ITEM_NOUN = { one: 'item', other: 'items' };

const timelineTrackClass = 'relative h-3 w-full overflow-hidden rounded-full bg-gray-200';
const timelineContentOverlayClass = 'absolute inset-0 bg-gray-400/20';
const timelineLegendSwatchClass = 'relative h-2.5 w-5 shrink-0 overflow-hidden rounded-full';
const SCRUB_SNAP_PX = 16;

const formatDuration = (seconds: number) => {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m ${secs}s`;
  }
  if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  }
  return `${secs}s`;
};

export default function ProcessingTimelineSummaryCard({
  title,
  itemCount,
  itemLabel,
  totalTimeSeconds,
  totalTimeLabel,
  percentage,
  percentageLabel,
  durationSeconds,
  timelineDurationSeconds,
  minimumSegmentWidthPercent = 0,
  minimumSegmentWidthPx = 2,
  minimumPointWidthPx = 6,
  segments,
  segmentClassName,
  legendBaseLabel,
  legendSegmentLabel,
  variant = 'markers',
  itemNoun = DEFAULT_ITEM_NOUN,
}: ProcessingTimelineSummaryCardProps) {
  const [activeSegmentIndex, setActiveSegmentIndex] = useState<number | null>(null);
  const effectiveTimelineDurationSeconds = Math.max(
    timelineDurationSeconds ?? durationSeconds,
    0
  );
  const cardRef = useRef<HTMLDivElement>(null);
  const surfaceRef = useRef<HTMLDivElement>(null);
  const capturedPointerId = useRef<number | null>(null);
  const isDensity = variant === 'density';
  const [trackWidth, setTrackWidth] = useState(0);
  useEffect(() => {
    const element = surfaceRef.current;
    if (!isDensity || !element) {
      return undefined;
    }
    setTrackWidth(element.getBoundingClientRect().width);
    if (typeof ResizeObserver === 'undefined') {
      return undefined;
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        setTrackWidth(entry.contentRect.width);
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [isDensity]);
  const binCount = Math.min(
    DENSITY_MAX_BINS,
    Math.max(DENSITY_MIN_BINS, Math.round(trackWidth / DENSITY_BIN_PX))
  );
  const bins = useMemo<DensityBin[]>(() => {
    const result: DensityBin[] = Array.from({ length: binCount }, () => ({
      count: 0,
      seconds: 0,
      nearest: null,
    }));
    if (!isDensity || effectiveTimelineDurationSeconds <= 0) {
      return result;
    }
    const nearestDistance = new Array<number>(binCount).fill(Infinity);
    segments.forEach((segment) => {
      const midpoint = (segment.startTime + segment.endTime) / 2;
      if (!Number.isFinite(midpoint)) {
        return;
      }
      const index = Math.min(
        binCount - 1,
        Math.max(0, Math.floor((midpoint / effectiveTimelineDurationSeconds) * binCount))
      );
      const center = ((index + 0.5) / binCount) * effectiveTimelineDurationSeconds;
      const bin = result[index];
      bin.count += 1;
      bin.seconds += Math.max(0, segment.endTime - segment.startTime);
      const distance = Math.abs(midpoint - center);
      if (distance < nearestDistance[index]) {
        nearestDistance[index] = distance;
        bin.nearest = segment;
      }
    });
    return result;
  }, [isDensity, segments, binCount, effectiveTimelineDurationSeconds]);
  const maxBinCount = bins.reduce((max, bin) => Math.max(max, bin.count), 0);
  const activeBin = isDensity && activeSegmentIndex !== null && activeSegmentIndex < binCount
    && bins[activeSegmentIndex].count > 0
    ? activeSegmentIndex
    : null;
  const activeSegment = isDensity
    ? null
    : activeSegmentIndex !== null ? segments[activeSegmentIndex] ?? null : null;
  const nonEmptyBins = bins.reduce<number[]>((acc, bin, index) => {
    if (bin.count > 0) {
      acc.push(index);
    }
    return acc;
  }, []);
  const densityTooltip = (() => {
    if (activeBin === null) {
      return null;
    }
    const bin = bins[activeBin];
    const binSeconds = effectiveTimelineDurationSeconds / binCount;
    const noun = bin.count === 1 ? itemNoun.one : itemNoun.other;
    const rows = [
      {
        label: 'Range',
        value: `${formatTimelineLabel(activeBin * binSeconds)}-${formatTimelineLabel((activeBin + 1) * binSeconds)}`,
      },
      { label: 'Covered', value: formatDuration(bin.seconds) },
      { label: 'Nearest', value: bin.nearest?.tooltipRows[0]?.value ?? '' },
    ];
    return { title: `${bin.count.toLocaleString()} ${noun}`, rows };
  })();
  const getIsPointSegment = (segment: TimelineSegment) => (
    segment.kind === 'point' || segment.endTime <= segment.startTime
  );
  const getRawWidthPercent = (segment: TimelineSegment) => {
    if (effectiveTimelineDurationSeconds <= 0) {
      return 0;
    }

    if (getIsPointSegment(segment)) {
      const visualDurationSeconds = Math.max(0, segment.visualDurationSeconds ?? 0);
      return (visualDurationSeconds / effectiveTimelineDurationSeconds) * 100;
    }

    return ((segment.endTime - segment.startTime) / effectiveTimelineDurationSeconds) * 100;
  };
  const getWidthPercent = (segment: TimelineSegment) => (
    Math.min(100, Math.max(minimumSegmentWidthPercent, getRawWidthPercent(segment)))
  );
  const getLeftPercent = (segment: TimelineSegment, widthPercent: number) => {
    if (effectiveTimelineDurationSeconds <= 0) {
      return 0;
    }

    const anchorPercent = (segment.startTime / effectiveTimelineDurationSeconds) * 100;
    if (getIsPointSegment(segment)) {
      return anchorPercent - (widthPercent / 2);
    }
    return anchorPercent;
  };

  const getSegmentGeometry = (segment: TimelineSegment) => {
    const width = getWidthPercent(segment);
    const left = getLeftPercent(segment, width);
    const boundedLeft = Math.min(Math.max(0, left), Math.max(0, 100 - width));
    const minPx = getIsPointSegment(segment) ? minimumPointWidthPx : minimumSegmentWidthPx;
    return { width, boundedLeft, minPx };
  };

  const findBinAt = (clientX: number): number | null => {
    const rect = surfaceRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || effectiveTimelineDurationSeconds <= 0 || !nonEmptyBins.length) {
      return null;
    }
    const x = clientX - rect.left;
    const binWidth = rect.width / binCount;
    const under = Math.min(binCount - 1, Math.max(0, Math.floor(x / binWidth)));
    if (bins[under].count > 0) {
      return under;
    }
    let best: number | null = null;
    let bestDistance = Infinity;
    nonEmptyBins.forEach((index) => {
      const start = index * binWidth;
      const end = start + binWidth;
      const distance = x < start ? start - x : x > end ? x - end : 0;
      if (distance < bestDistance) {
        best = index;
        bestDistance = distance;
      }
    });
    return bestDistance <= SCRUB_SNAP_PX ? best : null;
  };

  const findSegmentAt = (clientX: number): number | null => {
    if (isDensity) {
      return findBinAt(clientX);
    }
    const rect = surfaceRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || effectiveTimelineDurationSeconds <= 0) {
      return null;
    }
    const x = clientX - rect.left;
    let best: number | null = null;
    let bestDistance = Infinity;
    let bestCenterDistance = Infinity;
    segments.forEach((segment, index) => {
      const { width, boundedLeft, minPx } = getSegmentGeometry(segment);
      const startPx = (boundedLeft / 100) * rect.width;
      const widthPx = Math.max((width / 100) * rect.width, minPx);
      const endPx = startPx + widthPx;
      const distance = x < startPx ? startPx - x : x > endPx ? x - endPx : 0;
      const centerDistance = Math.abs(x - (startPx + endPx) / 2);
      if (
        distance < bestDistance
        || (distance === bestDistance && centerDistance <= bestCenterDistance)
      ) {
        best = index;
        bestDistance = distance;
        bestCenterDistance = centerDistance;
      }
    });
    return bestDistance <= SCRUB_SNAP_PX ? best : null;
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (capturedPointerId.current !== null) {
      return;
    }
    capturedPointerId.current = event.pointerId;
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Capture is best-effort; tracking still works while the pointer stays over the surface.
    }
    setActiveSegmentIndex(findSegmentAt(event.clientX));
  };
  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const captured = capturedPointerId.current;
    if (captured !== null) {
      if (captured !== event.pointerId) {
        return;
      }
    } else if (event.pointerType !== 'mouse') {
      return;
    }
    setActiveSegmentIndex(findSegmentAt(event.clientX));
  };
  const releasePointer = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (capturedPointerId.current !== event.pointerId) {
      return false;
    }
    capturedPointerId.current = null;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // Already released.
    }
    return true;
  };
  const handlePointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    releasePointer(event);
  };
  const handlePointerCancel = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (releasePointer(event)) {
      setActiveSegmentIndex(null);
    }
  };
  const handlePointerLeave = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.pointerType === 'mouse' && capturedPointerId.current === null) {
      setActiveSegmentIndex(null);
    }
  };

  const hasActiveSegment = activeSegmentIndex !== null;
  useEffect(() => {
    if (!hasActiveSegment) {
      return undefined;
    }
    const handleOutsidePointerDown = (event: PointerEvent) => {
      if (!cardRef.current?.contains(event.target as Node)) {
        setActiveSegmentIndex(null);
      }
    };
    document.addEventListener('pointerdown', handleOutsidePointerDown);
    return () => document.removeEventListener('pointerdown', handleOutsidePointerDown);
  }, [hasActiveSegment]);

  const activeSegmentLeft = (() => {
    if (activeBin !== null) {
      return (activeBin / binCount) * 100;
    }
    if (!activeSegment || effectiveTimelineDurationSeconds <= 0) {
      return 0;
    }

    const width = getWidthPercent(activeSegment);
    const left = getLeftPercent(activeSegment, width);
    return Math.min(Math.max(0, left), Math.max(0, 100 - width));
  })();
  const activeSegmentWidth = (() => {
    if (activeBin !== null) {
      return 100 / binCount;
    }
    if (!activeSegment || effectiveTimelineDurationSeconds <= 0) {
      return 0;
    }

    return getWidthPercent(activeSegment);
  })();
  const activeSegmentCenter = Math.max(
    0,
    Math.min(100, activeSegmentLeft + (activeSegmentWidth / 2))
  );
  const activeSegmentRight = Math.max(
    0,
    Math.min(100, activeSegmentLeft + activeSegmentWidth)
  );

  const tooltip = densityTooltip
    ? { title: densityTooltip.title, rows: densityTooltip.rows }
    : activeSegment
      ? { title: activeSegment.tooltipTitle, rows: activeSegment.tooltipRows }
      : null;
  const liveText = tooltip
    ? `${tooltip.title}. ${tooltip.rows.map((row) => `${row.label} ${row.value}`).join('. ')}`
    : '';

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!isDensity || !nonEmptyBins.length) {
      return;
    }
    const current = activeBin;
    let next: number | undefined;
    if (event.key === 'ArrowRight') {
      next = current === null ? nonEmptyBins[0] : nonEmptyBins.find((index) => index > current);
    } else if (event.key === 'ArrowLeft') {
      next = current === null
        ? nonEmptyBins[nonEmptyBins.length - 1]
        : [...nonEmptyBins].reverse().find((index) => index < current);
    } else if (event.key === 'Home') {
      next = nonEmptyBins[0];
    } else if (event.key === 'End') {
      next = nonEmptyBins[nonEmptyBins.length - 1];
    } else {
      return;
    }
    event.preventDefault();
    // Keep the player's document-level arrow shortcuts from also seeking.
    event.stopPropagation();
    if (next !== undefined) {
      setActiveSegmentIndex(next);
    }
  };
  const handleSurfaceBlur = () => {
    if (isDensity && capturedPointerId.current === null) {
      setActiveSegmentIndex(null);
    }
  };

  const tooltipStyle = activeSegmentRight <= 72
    ? { left: `calc(${activeSegmentRight}% + 12px)`, transform: 'translateX(0)' }
    : activeSegmentLeft >= 28
      ? { left: `calc(${activeSegmentLeft}% - 12px)`, transform: 'translateX(-100%)' }
      : activeSegmentCenter < 15
        ? { left: '0%', transform: 'translateX(0)' }
        : activeSegmentCenter > 85
          ? { left: '100%', transform: 'translateX(-100%)' }
          : { left: `${activeSegmentCenter}%`, transform: 'translateX(-50%)' };

  const tooltipOriginClass = activeSegmentRight <= 72
    ? 'origin-left'
    : activeSegmentLeft >= 28
      ? 'origin-right'
      : 'origin-bottom';

  return (
    <div ref={cardRef} className="rounded-lg border border-gray-200 bg-surface p-5 sm:p-6">
      <h3 className="mb-5 text-left font-semibold text-gray-900">{title}</h3>
      <div className="grid grid-cols-1 gap-5 text-center md:grid-cols-3 md:gap-6">
        <div>
          <div className="text-2xl font-semibold tabular-nums tracking-tight text-gray-900">{itemCount.toLocaleString()}</div>
          <div className="mt-1 text-sm text-gray-600">{itemLabel}</div>
        </div>
        <div>
          <div className="text-2xl font-semibold tabular-nums tracking-tight text-gray-900">
            {formatDuration(totalTimeSeconds)}
          </div>
          <div className="mt-1 text-sm text-gray-600">{totalTimeLabel}</div>
        </div>
        <div>
          <div className="text-2xl font-semibold tabular-nums tracking-tight text-gray-900">
            {percentage.toFixed(1)}%
          </div>
          <div className="mt-1 text-sm text-gray-600">{percentageLabel}</div>
        </div>
      </div>

      <div className="mt-6 space-y-3">
        <div className="relative">
          {tooltip && (
            <div
              className="pointer-events-none absolute bottom-full z-30 mb-3 w-full"
              aria-hidden="true"
            >
              <div className="absolute w-max min-w-[13rem] max-w-[calc(100vw-3rem)]" style={tooltipStyle}>
              <div className={`animate-pop-in rounded-lg border border-gray-200 bg-surface p-3.5 text-left shadow-2xl ${tooltipOriginClass}`}>
                <div className="text-sm font-semibold text-gray-900">
                  {tooltip.title}
                </div>
                <div className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5">
                  {tooltip.rows.map((row) => (
                    <div key={`${row.label}-${row.value}`} className="contents">
                      <div className="text-xs text-gray-600">
                        {row.label}
                      </div>
                      <div className="text-sm font-medium tabular-nums text-gray-900">
                        {row.value}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              </div>
            </div>
          )}

          <div
            ref={surfaceRef}
            className={`relative flex h-8 touch-pan-y select-none items-center ${
              isDensity ? 'rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/70' : ''
            }`}
            {...(isDensity
              ? {
                tabIndex: 0,
                role: 'group',
                'aria-label': `${segments.length.toLocaleString()} ${
                  segments.length === 1 ? itemNoun.one : itemNoun.other
                } across the episode`,
                onKeyDown: handleKeyDown,
                onBlur: handleSurfaceBlur,
              }
              : {})}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerCancel}
            onPointerLeave={handlePointerLeave}
          >
            {isDensity ? (
              <>
                <div className="absolute inset-x-0 bottom-0 h-1 rounded-full bg-gray-200" />
                <div className="pointer-events-none absolute inset-x-0 bottom-1 h-6">
                  {bins.map((bin, index) => {
                    if (bin.count === 0) {
                      return null;
                    }
                    const height = Math.max(
                      DENSITY_MIN_BAR_PX,
                      (bin.count / maxBinCount) * DENSITY_MAX_BAR_PX
                    );
                    return (
                      <div
                        key={index}
                        className={`absolute bottom-0 rounded-t-sm transition-opacity duration-150 ${segmentClassName}`}
                        style={{
                          left: `${(index / binCount) * 100}%`,
                          width: `calc(${100 / binCount}% - 1px)`,
                          height: `${height}px`,
                          opacity: activeBin === index ? 1 : 0.75,
                        }}
                      />
                    );
                  })}
                </div>
                <div className="sr-only" aria-live="polite">{liveText}</div>
              </>
            ) : (
              <div className={timelineTrackClass}>
                <div className={timelineContentOverlayClass} />
              </div>
            )}

            <div className="pointer-events-none absolute inset-x-0 top-1/2 h-3 -translate-y-1/2">
              {!isDensity && effectiveTimelineDurationSeconds > 0 && segments.map((segment, index) => {
                const isPointSegment = getIsPointSegment(segment);
                const { width, boundedLeft } = getSegmentGeometry(segment);
                const isActive = activeSegmentIndex === index;

                return (
                  <button
                    key={`${segment.startTime}-${segment.endTime}-${index}`}
                    type="button"
                    aria-label={segment.ariaLabel ?? `${segment.tooltipTitle}: ${segment.tooltipRows.map((row) => `${row.label} ${row.value}`).join('. ')}`}
                    className={[
                      'pointer-events-none absolute transition-transform duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/70',
                      isPointSegment
                        ? '-top-1 h-5 rounded-full ring-2 ring-surface'
                        : 'top-0 h-full rounded-full',
                      segmentClassName,
                      isActive ? 'scale-y-110' : '',
                    ].join(' ').trim()}
                    style={{
                      left: `${boundedLeft}%`,
                      width: isPointSegment
                        ? `max(${width}%, ${minimumPointWidthPx}px)`
                        : `max(${width}%, ${minimumSegmentWidthPx}px)`,
                      zIndex: isActive ? 20 : 10,
                    }}
                    onFocus={() => setActiveSegmentIndex(index)}
                    onBlur={() => setActiveSegmentIndex((currentIndex) => (
                      currentIndex === index ? null : currentIndex
                    ))}
                  />
                );
              })}
            </div>
          </div>
        </div>

        <div className="relative h-4 text-xs tabular-nums text-gray-500">
          {getTimelineTicks(effectiveTimelineDurationSeconds).map((tick) => (
            <span
              key={tick.seconds}
              className="absolute top-0 whitespace-nowrap"
              style={{
                left: `${tick.percent}%`,
                transform: tick.percent <= 0
                  ? 'translateX(0)'
                  : tick.percent >= 92
                    ? 'translateX(-100%)'
                    : 'translateX(-50%)',
              }}
            >
              {formatTimelineLabel(tick.seconds)}
            </span>
          ))}
        </div>

        <div className="flex items-center gap-5 pt-1 text-xs text-gray-500">
          {legendBaseLabel && (
            <span className="flex items-center gap-2">
              <span className={`${timelineLegendSwatchClass} bg-gray-200`}>
                <span className={timelineContentOverlayClass} />
              </span>
              {legendBaseLabel}
            </span>
          )}
          <span className="flex items-center gap-2">
            <span
              className={isDensity
                ? `h-3 w-1.5 shrink-0 rounded-t-sm ${segmentClassName}`
                : `${timelineLegendSwatchClass} ${segmentClassName}`}
            />
            {legendSegmentLabel}
          </span>
        </div>
      </div>
    </div>
  );
}
