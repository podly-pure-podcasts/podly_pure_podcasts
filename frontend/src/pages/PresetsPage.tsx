import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { presetsApi } from '../services/api';
import { toast } from 'react-hot-toast';
import type { PromptPreset } from '../types';

export default function PresetsPage() {
  const queryClient = useQueryClient();
  const [selectedPreset, setSelectedPreset] = useState<PromptPreset | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [editForm, setEditForm] = useState({
    name: '',
    description: '',
    aggressiveness: 'balanced' as PromptPreset['aggressiveness'],
    min_confidence: 0.7,
    system_prompt: '',
    user_prompt_template: '',
  });

  const { data: presets, isLoading } = useQuery({
    queryKey: ['presets'],
    queryFn: presetsApi.getPresets,
  });

  const { data: statsSummary } = useQuery({
    queryKey: ['stats-summary', 'global'],
    queryFn: () => presetsApi.getStatsSummary({ scope: 'global' }),
  });

  const activatePresetMutation = useMutation({
    mutationFn: (presetId: number) => presetsApi.activatePreset(presetId),
    onSuccess: (data: { message: string }) => {
      toast.success(data.message);
      queryClient.invalidateQueries({ queryKey: ['presets'] });
    },
    onError: () => {
      toast.error('Failed to activate preset');
    },
  });

  const updatePresetMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<PromptPreset> }) => 
      presetsApi.updatePreset(id, data),
    onSuccess: () => {
      toast.success('Preset updated successfully');
      queryClient.invalidateQueries({ queryKey: ['presets'] });
      setIsEditing(false);
    },
    onError: () => {
      toast.error('Failed to update preset');
    },
  });

  const createPresetMutation = useMutation({
    mutationFn: (data: Partial<PromptPreset>) => presetsApi.createPreset(data),
    onSuccess: () => {
      toast.success('Preset created successfully');
      queryClient.invalidateQueries({ queryKey: ['presets'] });
      setIsCreating(false);
      resetForm();
    },
    onError: () => {
      toast.error('Failed to create preset');
    },
  });

  const deletePresetMutation = useMutation({
    mutationFn: (id: number) => presetsApi.deletePreset(id),
    onSuccess: () => {
      toast.success('Preset deleted successfully');
      queryClient.invalidateQueries({ queryKey: ['presets'] });
      setSelectedPreset(null);
    },
    onError: () => {
      toast.error('Failed to delete preset');
    },
  });

  const resetForm = () => {
    setEditForm({
      name: '',
      description: '',
      aggressiveness: 'balanced',
      min_confidence: 0.7,
      system_prompt: '',
      user_prompt_template: '',
    });
  };

  const handleEditPreset = (preset: PromptPreset) => {
    setEditForm({
      name: preset.name,
      description: preset.description || '',
      aggressiveness: preset.aggressiveness,
      min_confidence: preset.min_confidence,
      system_prompt: preset.system_prompt || '',
      user_prompt_template: preset.user_prompt_template || '',
    });
    setSelectedPreset(preset);
    setIsEditing(true);
    setIsCreating(false);
  };

  const handleCreateNew = () => {
    resetForm();
    setSelectedPreset(null);
    setIsCreating(true);
    setIsEditing(false);
  };

  const handleSave = () => {
    if (isCreating) {
      createPresetMutation.mutate(editForm);
    } else if (selectedPreset) {
      updatePresetMutation.mutate({ id: selectedPreset.id, data: editForm });
    }
  };

  const handleDelete = (preset: PromptPreset) => {
    if (confirm(`Are you sure you want to delete "${preset.name}"? This cannot be undone.`)) {
      deletePresetMutation.mutate(preset.id);
    }
  };

  const getAggressivenessColor = (level: string) => {
    switch (level) {
      case 'conservative': return { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-400', border: 'border-green-300 dark:border-green-700', ring: 'ring-green-500' };
      case 'balanced': return { bg: 'bg-yellow-100 dark:bg-yellow-900/30', text: 'text-yellow-700 dark:text-yellow-400', border: 'border-yellow-300 dark:border-yellow-700', ring: 'ring-yellow-500' };
      case 'aggressive': return { bg: 'bg-orange-100 dark:bg-orange-900/30', text: 'text-orange-700 dark:text-orange-400', border: 'border-orange-300 dark:border-orange-700', ring: 'ring-orange-500' };
      case 'maximum': return { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-700 dark:text-red-400', border: 'border-red-300 dark:border-red-700', ring: 'ring-red-500' };
      default: return { bg: 'bg-gray-100 dark:bg-gray-800/30', text: 'text-gray-700 dark:text-gray-400', border: 'border-gray-300 dark:border-gray-700', ring: 'ring-gray-500' };
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Ad Detection Presets</h1>
          <p className="text-gray-500 mt-1">Configure how aggressively ads are detected and removed</p>
        </div>
        <button
          onClick={handleCreateNew}
          className="flex items-center gap-2 px-3 sm:px-4 py-2 bg-gradient-to-r from-pink-500 via-purple-500 to-cyan-500 text-white rounded-xl hover:shadow-lg hover:shadow-purple-500/30 transition-all text-sm sm:text-base"
        >
          <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          <span className="hidden sm:inline">Create Preset</span>
          <span className="sm:hidden">Create</span>
        </button>
      </div>

      {/* Stats Summary */}
      {statsSummary && (
        <div className="bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-xl p-6 text-white">
          <h2 className="text-lg font-semibold mb-4">Overall Performance</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div>
              <p className="text-3xl font-bold">{statsSummary.total_episodes_processed}</p>
              <p className="text-sm opacity-80">Episodes Processed</p>
            </div>
            <div>
              <p className="text-3xl font-bold">{statsSummary.total_ad_segments_removed}</p>
              <p className="text-sm opacity-80">Ads Removed</p>
            </div>
            <div>
              <p className="text-3xl font-bold">{statsSummary.total_time_saved_formatted}</p>
              <p className="text-sm opacity-80">Time Saved</p>
            </div>
            <div>
              <p className="text-3xl font-bold">{statsSummary.average_percentage_removed.toFixed(1)}%</p>
              <p className="text-sm opacity-80">Avg Removed</p>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Presets List */}
        <div className="lg:col-span-1 space-y-4">
          <h2 className="text-lg font-semibold text-gray-900">Available Presets</h2>
          <div className="bg-white/80 dark:bg-purple-950/50 rounded-xl border border-purple-200/50 dark:border-purple-700/30 overflow-hidden">
            {presets?.map((preset: PromptPreset, idx: number) => (
              <div
                key={preset.id}
                onClick={() => {
                  setSelectedPreset(preset);
                  setIsEditing(false);
                  setIsCreating(false);
                }}
                className={`px-4 py-3 cursor-pointer transition-colors ${
                  idx > 0 ? 'border-t border-purple-100/40 dark:border-purple-800/20' : ''
                } ${
                  selectedPreset?.id === preset.id
                    ? `${getAggressivenessColor(preset.aggressiveness).bg}`
                    : 'hover:bg-purple-50 dark:hover:bg-purple-900/20'
                }`}
              >
                <div className="flex items-center gap-2 mb-0.5">
                  <h3 className="font-semibold text-sm text-gray-900 dark:text-gray-100">{preset.name}</h3>
                  {preset.is_active && (
                    <span className="px-1.5 py-0.5 text-[10px] font-medium bg-blue-500 text-white rounded-full">
                      Active
                    </span>
                  )}
                  <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded-full ${getAggressivenessColor(preset.aggressiveness).bg} ${getAggressivenessColor(preset.aggressiveness).text}`}>
                    {preset.aggressiveness}
                  </span>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2">{preset.description}</p>
                <span className="text-[11px] text-gray-400 dark:text-gray-500 mt-0.5">
                  {(preset.min_confidence * 100).toFixed(0)}% min confidence
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Preset Detail / Editor */}
        <div className="lg:col-span-2">
          {(selectedPreset || isCreating) ? (
            <div className="bg-white/80 dark:bg-purple-950/50 rounded-xl border border-purple-200/50 dark:border-purple-700/30 shadow-sm overflow-hidden">
              <div className="p-6 border-b border-purple-100/50 dark:border-purple-800/30">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-gray-900">
                    {isCreating ? 'Create New Preset' : isEditing ? 'Edit Preset' : 'Preset Details'}
                  </h2>
                  <div className="flex items-center gap-2">
                    {!isCreating && selectedPreset && !isEditing && (
                      <>
                        <button
                          onClick={() => handleEditPreset(selectedPreset)}
                          className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                        >
                          Edit
                        </button>
                        {!selectedPreset.is_active && (
                          <button
                            onClick={() => activatePresetMutation.mutate(selectedPreset.id)}
                            disabled={activatePresetMutation.isPending}
                            className="px-3 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
                          >
                            Activate
                          </button>
                        )}
                        {!selectedPreset.is_default && (
                          <button
                            onClick={() => handleDelete(selectedPreset)}
                            className="px-3 py-1.5 text-sm font-medium text-red-600 bg-red-50 rounded-lg hover:bg-red-100 transition-colors"
                          >
                            Delete
                          </button>
                        )}
                      </>
                    )}
                    {(isEditing || isCreating) && (
                      <>
                        <button
                          onClick={() => {
                            setIsEditing(false);
                            setIsCreating(false);
                          }}
                          className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={handleSave}
                          disabled={updatePresetMutation.isPending || createPresetMutation.isPending}
                          className="px-3 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
                        >
                          {isCreating ? 'Create' : 'Save Changes'}
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>

              <div className="p-6 space-y-6">
                {(isEditing || isCreating) ? (
                  <>
                    {/* Basic Info */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                        <input
                          type="text"
                          value={editForm.name}
                          onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          placeholder="My Custom Preset"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Aggressiveness</label>
                        <select
                          value={editForm.aggressiveness}
                          onChange={(e) => setEditForm({ ...editForm, aggressiveness: e.target.value as PromptPreset['aggressiveness'] })}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        >
                          <option value="conservative">Conservative</option>
                          <option value="balanced">Balanced</option>
                          <option value="aggressive">Aggressive</option>
                          <option value="maximum">Maximum</option>
                        </select>
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                      <textarea
                        value={editForm.description}
                        onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                        rows={2}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        placeholder="Describe what this preset does..."
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Minimum Confidence: {(editForm.min_confidence * 100).toFixed(0)}%
                      </label>
                      <input
                        type="range"
                        min="0.3"
                        max="0.95"
                        step="0.05"
                        value={editForm.min_confidence}
                        onChange={(e) => setEditForm({ ...editForm, min_confidence: parseFloat(e.target.value) })}
                        className="w-full"
                      />
                      <div className="flex justify-between text-xs text-gray-500 mt-1">
                        <span>More aggressive (30%)</span>
                        <span>More conservative (95%)</span>
                      </div>
                    </div>

                    {/* System Prompt */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        System Prompt
                        <span className="text-gray-400 font-normal ml-2">Instructions for the AI</span>
                      </label>
                      <textarea
                        value={editForm.system_prompt}
                        onChange={(e) => setEditForm({ ...editForm, system_prompt: e.target.value })}
                        rows={12}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
                        placeholder="Enter the system prompt that instructs the AI how to detect ads..."
                      />
                    </div>

                    {/* User Prompt Template */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        User Prompt Template
                        <span className="text-gray-400 font-normal ml-2">Use {'{{podcast_title}}'}, {'{{podcast_topic}}'}, {'{{transcript}}'}</span>
                      </label>
                      <textarea
                        value={editForm.user_prompt_template}
                        onChange={(e) => setEditForm({ ...editForm, user_prompt_template: e.target.value })}
                        rows={4}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
                        placeholder="This is the podcast {{podcast_title}}..."
                      />
                    </div>
                  </>
                ) : selectedPreset && (
                  <>
                    {/* View Mode */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="bg-gray-50 rounded-lg p-4">
                        <p className="text-sm text-gray-500">Aggressiveness</p>
                        <p className={`text-lg font-semibold capitalize ${getAggressivenessColor(selectedPreset.aggressiveness).text}`}>
                          {selectedPreset.aggressiveness}
                        </p>
                      </div>
                      <div className="bg-gray-50 rounded-lg p-4">
                        <p className="text-sm text-gray-500">Min Confidence</p>
                        <p className="text-lg font-semibold text-gray-900">
                          {(selectedPreset.min_confidence * 100).toFixed(0)}%
                        </p>
                      </div>
                      <div className="bg-gray-50 rounded-lg p-4">
                        <p className="text-sm text-gray-500">Status</p>
                        <p className="text-lg font-semibold text-gray-900">
                          {selectedPreset.is_active ? 'Active' : 'Inactive'}
                        </p>
                      </div>
                    </div>

                    <div>
                      <p className="text-sm text-gray-500 mb-1">Description</p>
                      <p className="text-gray-900">{selectedPreset.description || 'No description'}</p>
                    </div>

                    <div>
                      <p className="text-sm text-gray-500 mb-2">System Prompt</p>
                      <div className="bg-gray-50 rounded-lg p-4 max-h-64 overflow-y-auto">
                        <pre className="text-sm text-gray-800 whitespace-pre-wrap font-mono">
                          {selectedPreset.system_prompt || 'No system prompt defined'}
                        </pre>
                      </div>
                    </div>

                    <div>
                      <p className="text-sm text-gray-500 mb-2">User Prompt Template</p>
                      <div className="bg-gray-50 rounded-lg p-4">
                        <pre className="text-sm text-gray-800 whitespace-pre-wrap font-mono">
                          {selectedPreset.user_prompt_template || 'No user prompt template defined'}
                        </pre>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          ) : (
            <div className="bg-gray-50 rounded-xl border-2 border-dashed border-gray-300 flex items-center justify-center h-96">
              <div className="text-center">
                <svg className="w-12 h-12 text-gray-400 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                </svg>
                <p className="text-gray-500">Select a preset to view details</p>
                <p className="text-sm text-gray-400 mt-1">or create a new one</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
