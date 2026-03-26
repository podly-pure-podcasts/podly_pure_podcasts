import { useQuery } from '@tanstack/react-query';
import { presetsApi } from '../../services/api';
import type { PromptPreset } from '../../types';

export default function GlobalStatsBar() {
  const { data: presets } = useQuery({
    queryKey: ['presets'],
    queryFn: presetsApi.getPresets,
  });

  const { data: statsSummary } = useQuery({
    queryKey: ['stats-summary', 'global'],
    queryFn: () => presetsApi.getStatsSummary({ scope: 'global' }),
  });

  const activePreset = presets?.find((p: PromptPreset) => p.is_active);

  const getAggressivenessColor = (level: string) => {
    switch (level) {
      case 'conservative': return 'bg-green-500';
      case 'balanced': return 'bg-yellow-500';
      case 'aggressive': return 'bg-orange-500';
      case 'maximum': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  return (
    <div className="bg-white border-b border-gray-200 px-6 py-3">
      <div className="flex items-center justify-between gap-6">
        {/* Active Preset Indicator */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className={`w-2.5 h-2.5 rounded-full ${activePreset ? getAggressivenessColor(activePreset.aggressiveness) : 'bg-gray-400'}`} />
            <span className="text-sm font-medium text-gray-700">
              {activePreset ? activePreset.name : 'No preset active'}
            </span>
          </div>
          {activePreset && (
            <span className="text-xs text-gray-500 hidden sm:inline">
              Min confidence: {(activePreset.min_confidence * 100).toFixed(0)}%
            </span>
          )}
        </div>

        {/* Quick Stats */}
        {statsSummary && (
          <div className="flex items-center gap-6 text-sm">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
              </svg>
              <span className="text-gray-600">
                <span className="font-semibold text-gray-900">{statsSummary.total_episodes_processed}</span> processed
              </span>
            </div>
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
              </svg>
              <span className="text-gray-600">
                <span className="font-semibold text-gray-900">{statsSummary.total_ad_segments_removed}</span> ads removed
              </span>
            </div>
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-gray-600">
                <span className="font-semibold text-gray-900">{statsSummary.total_time_saved_formatted}</span> saved
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
