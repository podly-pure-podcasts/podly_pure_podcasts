import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { feedsApi } from '../services/api';

export function useEpisodeStatus(episodeGuid: string, isWhitelisted: boolean, hasProcessedAudio: boolean, feedId?: number) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ['episode-status', episodeGuid],
    queryFn: () => feedsApi.getPostStatus(episodeGuid),
    enabled: isWhitelisted && !hasProcessedAudio,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'pending' || status === 'running' || status === 'starting' || status === 'processing') {
        return 3000;
      }
      return false;
    },
  });

  useEffect(() => {
    const status = query.data?.status;
    if ((status === 'completed' || status === 'failed') && feedId) {
      // Invalidate episodes list to refresh UI (show Play button). A failed job
      // can still have published the episode without ad removal.
      queryClient.invalidateQueries({ queryKey: ['episodes', feedId] });
    }
  }, [query.data?.status, feedId, queryClient]);

  return query;
}
