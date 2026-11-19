import { createContext, useContext } from 'react';

export const AudioTimeContext = createContext<number>(0);

export function useAudioTime(): number {
  return useContext(AudioTimeContext);
}
