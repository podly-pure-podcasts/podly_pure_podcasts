import React, { useState, useRef, useEffect } from 'react';
import { useAudioPlayer } from '../contexts/AudioPlayerContext';
import { useAudioTime } from '../contexts/AudioTimeContext';
import { CloseIcon, MusicIcon, PauseIcon, PlayIcon, SpeakerMuteIcon, SpeakerWaveIcon } from './icons';

const formatTime = (seconds: number) => {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
  }
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
};

interface PointerSliderProps {
  className?: string;
  fraction: number;
  disabled?: boolean;
  ariaLabel: string;
  ariaMin: number;
  ariaMax: number;
  ariaNow: number;
  ariaValueText: string;
  onDrag: (fraction: number) => void;
  onCommit: (fraction: number) => void;
  onDragCancel?: () => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLDivElement>) => void;
}

// Pointer-captured slider: one active pointer at a time, so a second finger
// is ignored and a drag keeps tracking after the pointer leaves the track.
// The 4px track sits inside a 24px-tall hit area.
function PointerSlider({
  className = '',
  fraction,
  disabled,
  ariaLabel,
  ariaMin,
  ariaMax,
  ariaNow,
  ariaValueText,
  onDrag,
  onCommit,
  onDragCancel,
  onKeyDown,
}: PointerSliderProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const activePointer = useRef<number | null>(null);
  const lastFraction = useRef(0);
  const [dragging, setDragging] = useState(false);

  const fractionFromEvent = (e: React.PointerEvent) => {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return null;
    return Math.max(0, Math.min((e.clientX - rect.left) / rect.width, 1));
  };

  const end = () => {
    activePointer.current = null;
    setDragging(false);
  };

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (disabled || activePointer.current !== null) return;
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    const f = fractionFromEvent(e);
    if (f === null) return;
    activePointer.current = e.pointerId;
    e.currentTarget.setPointerCapture(e.pointerId);
    lastFraction.current = f;
    setDragging(true);
    onDrag(f);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.pointerId !== activePointer.current) return;
    const f = fractionFromEvent(e);
    if (f === null) return;
    lastFraction.current = f;
    onDrag(f);
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.pointerId !== activePointer.current) return;
    const f = fractionFromEvent(e) ?? lastFraction.current;
    end();
    onCommit(f);
  };

  const handlePointerCancel = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.pointerId !== activePointer.current) return;
    end();
    onDragCancel?.();
  };

  return (
    <div
      role="slider"
      tabIndex={disabled ? -1 : 0}
      aria-label={ariaLabel}
      aria-valuemin={ariaMin}
      aria-valuemax={ariaMax}
      aria-valuenow={ariaNow}
      aria-valuetext={ariaValueText}
      aria-disabled={disabled || undefined}
      data-dragging={dragging}
      className={`player-slider cursor-pointer touch-none rounded-full py-[10px] outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${className}`}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerCancel}
      onKeyDown={onKeyDown}
    >
      <div ref={trackRef} className="relative h-1 rounded-full bg-gray-200">
        <div className="h-full rounded-full bg-gray-900" style={{ width: `${fraction * 100}%` }} />
        <div
          className="player-thumb absolute top-1/2 h-3 w-3 rounded-full bg-gray-900"
          style={{ left: `${fraction * 100}%` }}
        />
      </div>
    </div>
  );
}

export default function AudioPlayer() {
  const {
    currentEpisode,
    isPlaying,
    duration,
    volume,
    isLoading,
    error,
    togglePlayPause,
    seekTo,
    setVolume
  } = useAudioPlayer();
  const currentTime = useAudioTime();

  const [dragTime, setDragTime] = useState<number | null>(null);
  const [showVolume, setShowVolume] = useState(false);
  const [dismissedError, setDismissedError] = useState<string | null>(null);
  const volumeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error && error !== dismissedError) {
      setDismissedError(null);
    }
  }, [error, dismissedError]);

  useEffect(() => {
    if (!showVolume) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (volumeRef.current && !volumeRef.current.contains(event.target as Node)) {
        setShowVolume(false);
      }
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setShowVolume(false);
    };
    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKey);
    };
  }, [showVolume]);

  if (!currentEpisode) {
    return null;
  }

  const isFineHover = (e: React.PointerEvent) =>
    e.pointerType === 'mouse' && window.matchMedia('(hover: hover) and (pointer: fine)').matches;

  const handleSeekKey = (e: React.KeyboardEvent) => {
    const steps: Record<string, number> = { ArrowLeft: -5, ArrowRight: 5, PageDown: -30, PageUp: 30 };
    let target: number | null = null;
    if (e.key in steps) target = currentTime + steps[e.key];
    else if (e.key === 'Home') target = 0;
    else if (e.key === 'End') target = duration;
    if (target === null) return;
    e.preventDefault();
    e.stopPropagation();
    seekTo(Math.max(0, Math.min(target, duration || 0)));
  };

  const handleVolumeKey = (e: React.KeyboardEvent) => {
    const steps: Record<string, number> = { ArrowUp: 0.05, ArrowRight: 0.05, ArrowDown: -0.05, ArrowLeft: -0.05 };
    let target: number | null = null;
    if (e.key in steps) target = Math.round((volume + steps[e.key]) * 100) / 100;
    else if (e.key === 'Home') target = 0;
    else if (e.key === 'End') target = 1;
    if (target === null) return;
    e.preventDefault();
    e.stopPropagation();
    setVolume(Math.max(0, Math.min(target, 1)));
  };

  const toggleMute = () => {
    setVolume(volume > 0 ? 0 : 1);
  };

  const displayTime = dragTime ?? currentTime;
  const shouldShowError = error && error !== dismissedError;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-gray-200 bg-surface shadow-lg">
      <div className="mx-auto max-w-7xl px-4 py-3">
        {shouldShowError && (
          <div className="mb-2 flex items-center justify-between rounded border border-red-300 bg-red-100 p-2 text-sm text-red-700">
            <span className="min-w-0 break-words">{error}</span>
            <button
              onClick={() => setDismissedError(error)}
              className="ml-2 flex-shrink-0 rounded p-1 transition-colors hover:bg-red-200 focus-visible:ring-2 focus-visible:ring-blue-500"
              aria-label="Dismiss error"
            >
              <CloseIcon className="h-4 w-4" />
            </button>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {/* Episode Info */}
          <div className="order-1 min-w-0 flex-1 basis-0">
            <div className="flex items-center gap-3">
              {currentEpisode.image_url ? (
                <img
                  src={currentEpisode.image_url}
                  alt=""
                  className="h-12 w-12 flex-shrink-0 rounded object-cover"
                />
              ) : (
                <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded bg-gray-200 text-gray-500">
                  <MusicIcon className="h-5 w-5" />
                </div>
              )}
              <div className="min-w-0 flex-1">
                <h4 className="truncate text-sm font-semibold text-gray-900">
                  {currentEpisode.title}
                </h4>
                <p className="truncate text-xs text-gray-600">
                  Episode • {formatTime(duration)}
                </p>
              </div>
            </div>
          </div>

          {/* Player Controls */}
          <div className="order-3 w-full min-w-0 md:order-2 md:w-auto md:max-w-2xl md:flex-1">
            <div className="player-tip-host relative mb-1 flex items-center justify-center">
              <button
                onClick={togglePlayPause}
                disabled={isLoading}
                aria-label={isPlaying ? 'Pause' : 'Play'}
                className="rounded-full bg-gray-900 p-2 text-surface transition-colors hover:bg-gray-800 focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isLoading ? (
                  <div className="h-6 w-6 animate-spin rounded-full border-2 border-current border-t-transparent" />
                ) : isPlaying ? (
                  <PauseIcon className="h-6 w-6" />
                ) : (
                  <PlayIcon className="h-6 w-6" />
                )}
              </button>

              <div
                role="tooltip"
                className="player-tip absolute bottom-full left-1/2 z-10 mb-2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-900 px-3 py-2 text-xs text-surface"
              >
                <div className="space-y-1">
                  <div>Space: Play/Pause</div>
                  <div>← →: Seek ±10s</div>
                  <div>↑ ↓: Volume ±10%</div>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 text-xs font-medium tabular-nums text-gray-600">
              <span className="w-10 text-right">{formatTime(displayTime)}</span>
              <PointerSlider
                className="min-w-0 flex-1"
                fraction={duration > 0 ? Math.min(displayTime / duration, 1) : 0}
                disabled={!duration}
                ariaLabel="Seek"
                ariaMin={0}
                ariaMax={Math.floor(duration || 0)}
                ariaNow={Math.floor(displayTime)}
                ariaValueText={`${formatTime(displayTime)} of ${formatTime(duration)}`}
                onDrag={(f) => setDragTime(f * duration)}
                onCommit={(f) => {
                  seekTo(f * duration);
                  setDragTime(null);
                }}
                onDragCancel={() => setDragTime(null)}
                onKeyDown={handleSeekKey}
              />
              <span className="w-10">{formatTime(duration)}</span>
            </div>
          </div>

          {/* Volume Control */}
          <div
            ref={volumeRef}
            className="relative order-2 flex items-center md:order-3"
            onPointerEnter={(e) => isFineHover(e) && setShowVolume(true)}
            onPointerLeave={(e) => isFineHover(e) && setShowVolume(false)}
          >
            <button
              onClick={() => setShowVolume((v) => !v)}
              aria-label="Volume"
              aria-expanded={showVolume}
              className="rounded-md p-2 text-gray-600 transition-colors hover:text-gray-900 focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              {volume === 0 ? <SpeakerMuteIcon className="h-5 w-5" /> : <SpeakerWaveIcon className="h-5 w-5" />}
            </button>

            {showVolume && (
              <div className="absolute bottom-full right-0 z-10 pb-1">
                <div className="flex origin-bottom-right animate-pop-in items-center gap-1 rounded-md border border-gray-200 bg-surface p-1 shadow-lg">
                  <button
                    onClick={toggleMute}
                    aria-label={volume === 0 ? 'Unmute' : 'Mute'}
                    className="rounded-md p-2 text-gray-600 transition-colors hover:text-gray-900 focus-visible:ring-2 focus-visible:ring-blue-500"
                  >
                    {volume === 0 ? <SpeakerMuteIcon className="h-4 w-4" /> : <SpeakerWaveIcon className="h-4 w-4" />}
                  </button>
                  <PointerSlider
                    className="w-24 px-1"
                    fraction={volume}
                    ariaLabel="Volume"
                    ariaMin={0}
                    ariaMax={100}
                    ariaNow={Math.round(volume * 100)}
                    ariaValueText={`${Math.round(volume * 100)}%`}
                    onDrag={setVolume}
                    onCommit={setVolume}
                    onKeyDown={handleVolumeKey}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
