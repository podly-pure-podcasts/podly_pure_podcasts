import { useAudioPlayer } from '../contexts/AudioPlayerContext';
import type { Episode } from '../types';
import { PauseIcon, PlayIcon } from './icons';

interface PlayButtonProps {
  episode: Episode;
  className?: string;
}

export default function PlayButton({ episode, className = '' }: PlayButtonProps) {
  const { currentEpisode, isPlaying, isLoading, playEpisode, togglePlayPause } = useAudioPlayer();
  
  const isCurrentEpisode = currentEpisode?.id === episode.id;
  const canPlay = episode.has_processed_audio;

  const getDisabledReason = () => {
    if (!episode.has_processed_audio) {
      return 'Episode not processed yet';
    }
    return '';
  };

  const handleClick = () => {
    
    if (!canPlay) return;
    
    if (isCurrentEpisode) {
      togglePlayPause();
    } else {
      playEpisode(episode);
    }
  };

  const isDisabled = !canPlay || (isLoading && isCurrentEpisode);
  const disabledReason = getDisabledReason();
  const title = isDisabled && disabledReason 
    ? disabledReason 
    : isCurrentEpisode 
      ? (isPlaying ? 'Pause' : 'Play') 
      : 'Play episode';

  return (
    <button
      onClick={handleClick}
      disabled={isDisabled}
      className={`touch-target inline-flex h-8 w-8 items-center justify-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 ${
        isDisabled 
          ? 'bg-gray-200 text-gray-600 cursor-not-allowed' 
          : 'bg-gray-900 text-surface hover:bg-gray-700'
      } ${className}`}
      title={title}
      aria-label={title}
    >
      {isLoading && isCurrentEpisode ? (
        <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
      ) : isCurrentEpisode && isPlaying ? (
        <PauseIcon className="w-4 h-4" />
      ) : (
        <PlayIcon className="w-4 h-4" />
      )}
    </button>
  );
} 