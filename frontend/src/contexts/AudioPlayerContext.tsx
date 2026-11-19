import React, { createContext, useContext, useReducer, useRef, useEffect, useCallback, useMemo } from 'react';
import type { Episode } from '../types';
import { feedsApi } from '../services/api';
import { AudioTimeContext } from './AudioTimeContext';

interface AudioPlayerState {
  currentEpisode: Episode | null;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  volume: number;
  isLoading: boolean;
  error: string | null;
}

interface AudioPlayerContextType extends Omit<AudioPlayerState, 'currentTime'> {
  playEpisode: (episode: Episode) => void;
  togglePlayPause: () => void;
  seekTo: (time: number) => void;
  setVolume: (volume: number) => void;
  audioRef: React.RefObject<HTMLAudioElement | null>;
}

type AudioPlayerAction =
  | { type: 'SET_EPISODE'; payload: Episode }
  | { type: 'SET_PLAYING'; payload: boolean }
  | { type: 'SET_CURRENT_TIME'; payload: number }
  | { type: 'SET_DURATION'; payload: number }
  | { type: 'SET_VOLUME'; payload: number }
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_ERROR'; payload: string | null };

const initialState: AudioPlayerState = {
  currentEpisode: null,
  isPlaying: false,
  currentTime: 0,
  duration: 0,
  volume: 1,
  isLoading: false,
  error: null,
};

function audioPlayerReducer(state: AudioPlayerState, action: AudioPlayerAction): AudioPlayerState {
  switch (action.type) {
    case 'SET_EPISODE':
      return { ...state, currentEpisode: action.payload, currentTime: 0, error: null };
    case 'SET_PLAYING':
      return { ...state, isPlaying: action.payload };
    case 'SET_CURRENT_TIME':
      return { ...state, currentTime: action.payload };
    case 'SET_DURATION':
      return { ...state, duration: action.payload };
    case 'SET_VOLUME':
      return { ...state, volume: action.payload };
    case 'SET_LOADING':
      return { ...state, isLoading: action.payload };
    case 'SET_ERROR':
      return { ...state, error: action.payload, isLoading: false };
    default:
      return state;
  }
}

const AudioPlayerContext = createContext<AudioPlayerContextType | undefined>(undefined);

export function AudioPlayerProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(audioPlayerReducer, initialState);
  const audioRef = useRef<HTMLAudioElement>(null);

  // Lets stable callbacks and the keyboard handler read current state without re-binding.
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const playEpisode = useCallback((episode: Episode) => {
    if (!episode.has_processed_audio) {
      dispatch({ type: 'SET_ERROR', payload: 'Post needs to be processed first' });
      return;
    }

    dispatch({ type: 'SET_EPISODE', payload: episode });
    dispatch({ type: 'SET_LOADING', payload: true });

    if (audioRef.current) {
      audioRef.current.src = feedsApi.getPostAudioUrl(episode.guid);
      audioRef.current.load();

      // Start playback immediately so the first click both opens the player and plays audio.
      audioRef.current.play().catch((error) => {
        dispatch({ type: 'SET_ERROR', payload: 'Failed to play audio' });
        console.error('Audio play error:', error);
      });
    }
  }, []);

  const togglePlayPause = useCallback(() => {
    const { currentEpisode, isPlaying } = stateRef.current;
    if (!audioRef.current || !currentEpisode) return;

    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play().catch((error) => {
        dispatch({ type: 'SET_ERROR', payload: 'Failed to play audio' });
        console.error('Audio play error:', error);
      });
    }
  }, []);

  const seekTo = useCallback((time: number) => {
    if (audioRef.current) {
      const targetTime = Math.max(0, Math.min(time, stateRef.current.duration || time));
      audioRef.current.currentTime = targetTime;
      dispatch({ type: 'SET_CURRENT_TIME', payload: targetTime });
    }
  }, []);

  const setVolume = useCallback((volume: number) => {
    if (audioRef.current) {
      audioRef.current.volume = volume;
      dispatch({ type: 'SET_VOLUME', payload: volume });
    }
  }, []);

  // Audio event handlers
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const handleLoadedData = () => {
      dispatch({ type: 'SET_DURATION', payload: audio.duration });
      dispatch({ type: 'SET_LOADING', payload: false });
    };

    const handleTimeUpdate = () => {
      dispatch({ type: 'SET_CURRENT_TIME', payload: audio.currentTime });
    };

    const handlePlay = () => {
      dispatch({ type: 'SET_PLAYING', payload: true });
    };

    const handlePause = () => {
      dispatch({ type: 'SET_PLAYING', payload: false });
    };

    const handleEnded = () => {
      dispatch({ type: 'SET_PLAYING', payload: false });
      dispatch({ type: 'SET_CURRENT_TIME', payload: 0 });
    };

    const handleError = () => {
      const audio = audioRef.current;
      if (!audio) return;

      // Get more specific error information
      let errorMessage = 'Failed to load audio';
      
      if (audio.error) {
        switch (audio.error.code) {
          case MediaError.MEDIA_ERR_ABORTED:
            errorMessage = 'Audio loading was aborted';
            break;
          case MediaError.MEDIA_ERR_NETWORK:
            errorMessage = 'Network error while loading audio';
            break;
          case MediaError.MEDIA_ERR_DECODE:
            errorMessage = 'Audio file is corrupted or unsupported';
            break;
          case MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED:
            errorMessage = 'Audio format not supported or file not found';
            break;
          default:
            errorMessage = 'Unknown audio error';
        }
      }

      // Check if it's a network error that might indicate specific HTTP status
      if (audio.error?.code === MediaError.MEDIA_ERR_NETWORK || 
          audio.error?.code === MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED) {
        // For network errors, provide more helpful messages
        if (state.currentEpisode) {
          if (!state.currentEpisode.has_processed_audio) {
            errorMessage = 'Post needs to be processed first';
          } else if (!state.currentEpisode.whitelisted) {
            errorMessage = 'Post is not whitelisted';
          } else {
            errorMessage = 'Audio file not available - try processing the post again';
          }
        }
      }

      console.error('Audio error:', audio.error, 'Message:', errorMessage);
      dispatch({ type: 'SET_ERROR', payload: errorMessage });
    };

    const handleCanPlay = () => {
      dispatch({ type: 'SET_LOADING', payload: false });
    };

    audio.addEventListener('loadeddata', handleLoadedData);
    audio.addEventListener('timeupdate', handleTimeUpdate);
    audio.addEventListener('play', handlePlay);
    audio.addEventListener('pause', handlePause);
    audio.addEventListener('ended', handleEnded);
    audio.addEventListener('error', handleError);
    audio.addEventListener('canplay', handleCanPlay);

    return () => {
      audio.removeEventListener('loadeddata', handleLoadedData);
      audio.removeEventListener('timeupdate', handleTimeUpdate);
      audio.removeEventListener('play', handlePlay);
      audio.removeEventListener('pause', handlePause);
      audio.removeEventListener('ended', handleEnded);
      audio.removeEventListener('error', handleError);
      audio.removeEventListener('canplay', handleCanPlay);
    };
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const { currentEpisode, currentTime, duration, volume } = stateRef.current;
      // Only handle shortcuts when there's a current episode and not typing in an input
      if (!currentEpisode ||
          event.target instanceof HTMLInputElement ||
          event.target instanceof HTMLTextAreaElement) {
        return;
      }

      switch (event.code) {
        case 'Space':
          event.preventDefault();
          togglePlayPause();
          break;
        case 'ArrowLeft':
          event.preventDefault();
          seekTo(Math.max(0, currentTime - 10));
          break;
        case 'ArrowRight':
          event.preventDefault();
          seekTo(Math.min(duration, currentTime + 10));
          break;
        case 'ArrowUp':
          event.preventDefault();
          setVolume(Math.min(1, volume + 0.1));
          break;
        case 'ArrowDown':
          event.preventDefault();
          setVolume(Math.max(0, volume - 0.1));
          break;
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [togglePlayPause, seekTo, setVolume]);

  const { currentEpisode, isPlaying, duration, volume, isLoading, error, currentTime } = state;
  const contextValue = useMemo<AudioPlayerContextType>(() => ({
    currentEpisode,
    isPlaying,
    duration,
    volume,
    isLoading,
    error,
    playEpisode,
    togglePlayPause,
    seekTo,
    setVolume,
    audioRef,
  }), [currentEpisode, isPlaying, duration, volume, isLoading, error, playEpisode, togglePlayPause, seekTo, setVolume]);

  return (
    <AudioPlayerContext.Provider value={contextValue}>
      <AudioTimeContext.Provider value={currentTime}>
        {children}
      </AudioTimeContext.Provider>
      <audio ref={audioRef} preload="metadata" />
    </AudioPlayerContext.Provider>
  );
}

export function useAudioPlayer() {
  const context = useContext(AudioPlayerContext);
  if (context === undefined) {
    throw new Error('useAudioPlayer must be used within an AudioPlayerProvider');
  }
  return context;
}
