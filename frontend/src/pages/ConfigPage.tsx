import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { configApi, authApi, feedsApi } from '../services/api';
import { toast } from 'react-hot-toast';
import type {
  CombinedConfig,
  ConfigResponse,
  EnvOverrideEntry,
  EnvOverrideMap,
  LLMConfig,
  LLMOptionsResponse,
  ManagedUser,
  WhisperConfig,
} from '../types';
import { useAuth } from '../contexts/AuthContext';
import AdminUserStats from '../components/AdminUserStats';

const ENV_FIELD_LABELS: Record<string, string> = {
  'groq.api_key': 'Groq API Key',
  'llm.llm_api_key': 'LLM API Key',
  'llm.llm_model': 'LLM Model',
  'llm.openai_base_url': 'LLM Base URL',
  'whisper.whisper_type': 'Whisper Mode',
  'whisper.api_key': 'Whisper API Key',
  'whisper.model': 'Whisper Model',
  'whisper.base_url': 'Whisper Base URL',
  'whisper.timeout_sec': 'Whisper Timeout (sec)',
  'whisper.chunksize_mb': 'Whisper Chunk Size (MB)',
  'whisper.max_retries': 'Whisper Max Retries',
};

const DEFAULT_ENV_HINTS: Record<string, EnvOverrideEntry> = {
  'groq.api_key': { env_var: 'GROQ_API_KEY' },
  'llm.llm_api_key': { env_var: 'LLM_API_KEY' },
  'llm.llm_model': { env_var: 'LLM_MODEL' },
  'llm.openai_base_url': { env_var: 'OPENAI_BASE_URL' },
  'whisper.whisper_type': { env_var: 'WHISPER_TYPE' },
  'whisper.api_key': { env_var: 'WHISPER_REMOTE_API_KEY' },
  'whisper.base_url': { env_var: 'WHISPER_REMOTE_BASE_URL' },
  'whisper.model': { env_var: 'WHISPER_REMOTE_MODEL' },
  'whisper.timeout_sec': { env_var: 'WHISPER_REMOTE_TIMEOUT_SEC' },
  'whisper.chunksize_mb': { env_var: 'WHISPER_REMOTE_CHUNKSIZE_MB' },
  'whisper.max_retries': { env_var: 'GROQ_MAX_RETRIES' },
};

const getValueAtPath = (obj: unknown, path: string): unknown => {
  if (!obj || typeof obj !== 'object') {
    return undefined;
  }
  return path.split('.').reduce<unknown>((acc, key) => {
    if (!acc || typeof acc !== 'object') {
      return undefined;
    }
    return (acc as Record<string, unknown>)[key];
  }, obj);
};

const valuesDiffer = (a: unknown, b: unknown): boolean => {
  if (a === b) {
    return false;
  }
  const aEmpty = a === null || a === undefined || a === '';
  const bEmpty = b === null || b === undefined || b === '';
  if (aEmpty && bEmpty) {
    return false;
  }
  return true;
};

export default function ConfigPage() {
  const { data, isLoading, refetch } = useQuery<ConfigResponse>({
    queryKey: ['config'],
    queryFn: configApi.getConfig,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  const {
    data: llmOptions,
    refetch: refetchLlmOptions,
  } = useQuery<LLMOptionsResponse>({
    queryKey: ['llm-options'],
    queryFn: configApi.getLlmOptions,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  const configData = data?.config;
  const envOverrides = useMemo<EnvOverrideMap>(() => data?.env_overrides ?? {}, [data]);
  const getEnvHint = useCallback(
    (path: string, fallback?: EnvOverrideEntry) => envOverrides[path] ?? fallback ?? DEFAULT_ENV_HINTS[path],
    [envOverrides],
  );

  const { changePassword, refreshUser, user, logout, requireAuth } = useAuth();

  const [passwordForm, setPasswordForm] = useState({ current: '', next: '', confirm: '' });
  const [passwordSubmitting, setPasswordSubmitting] = useState(false);

  const [newUser, setNewUser] = useState({ username: '', password: '', confirm: '', role: 'user' });
  const [envWarningPaths, setEnvWarningPaths] = useState<string[]>([]);
  const [showEnvWarning, setShowEnvWarning] = useState(false);

  const showSecurityControls = requireAuth && !!user;

  const {
    data: managedUsers,
    refetch: refetchUsers,
  } = useQuery<ManagedUser[]>({
    queryKey: ['auth-users'],
    queryFn: async () => {
      const response = await authApi.listUsers();
      return response.users;
    },
    enabled: showSecurityControls && user.role === 'admin',
  });

  const queryClient = useQueryClient();

  const {
    data: pendingUsers,
    refetch: refetchPendingUsers,
  } = useQuery({
    queryKey: ['pending-users'],
    queryFn: authApi.listPendingUsers,
    enabled: showSecurityControls && user.role === 'admin',
  });

  const approvePendingMutation = useMutation({
    mutationFn: async (userId: number) => authApi.approvePendingUser(userId),
    onSuccess: async () => {
      toast.success('User approved.');
      await refetchPendingUsers();
      await refetchUsers();
      await queryClient.invalidateQueries({ queryKey: ['pending-users-count'] });
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, 'Failed to approve user.'));
    },
  });

  const deletePendingMutation = useMutation({
    mutationFn: async (userId: number) => authApi.deleteUserById(userId),
    onSuccess: async () => {
      toast.success('User deleted.');
      await refetchPendingUsers();
      await refetchUsers();
      await queryClient.invalidateQueries({ queryKey: ['pending-users-count'] });
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, 'Failed to delete user.'));
    },
  });

  const [pending, setPending] = useState<CombinedConfig | null>(null);
  const [hasEdits, setHasEdits] = useState(false);
  const [showBaseUrlInfo, setShowBaseUrlInfo] = useState(false);
  const [manualLlmKey, setManualLlmKey] = useState('');
  const [llmKeyProfileName, setLlmKeyProfileName] = useState('');
  const [localWhisperAvailable, setLocalWhisperAvailable] = useState<boolean | null>(null);
  const [llmStatus, setLlmStatus] = useState<'loading' | 'ok' | 'error'>('loading');
  const [llmMessage, setLlmMessage] = useState<string>('');
  const [llmError, setLlmError] = useState<string>('');
  const [whisperStatus, setWhisperStatus] = useState<'loading' | 'ok' | 'error'>('loading');
  const [whisperMessage, setWhisperMessage] = useState<string>('');
  const [whisperError, setWhisperError] = useState<string>('');
  const initialProbeDone = useRef(false);
  const groqRecommendedModel = useMemo(() => 'groq/openai/gpt-oss-120b', []);
  const groqRecommendedWhisper = useMemo(() => 'whisper-large-v3-turbo', []);

  const getErrorMessage = (error: unknown, fallback = 'Request failed.') => {
    if (axios.isAxiosError(error)) {
      return error.response?.data?.error || error.response?.data?.message || error.message || fallback;
    }
    if (error instanceof Error) {
      return error.message;
    }
    return fallback;
  };

  const handlePasswordSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (passwordForm.next !== passwordForm.confirm) {
      toast.error('New passwords do not match.');
      return;
    }

    setPasswordSubmitting(true);
    try {
      await changePassword(passwordForm.current, passwordForm.next);
      toast.success('Password updated. Update PODLY_ADMIN_PASSWORD to match.');
      setPasswordForm({ current: '', next: '', confirm: '' });
      await refreshUser();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to update password.'));
    } finally {
      setPasswordSubmitting(false);
    }
  };

  const handleCreateUser = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const username = newUser.username.trim();
    if (!username) {
      toast.error('Username is required.');
      return;
    }
    if (newUser.password !== newUser.confirm) {
      toast.error('Passwords do not match.');
      return;
    }

    try {
      await authApi.createUser({
        username,
        password: newUser.password,
        role: newUser.role,
      });
      toast.success(`User '${username}' created.`);
      setNewUser({ username: '', password: '', confirm: '', role: 'user' });
      await refetchUsers();
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to create user.'));
    }
  };

  const handleRoleChange = async (username: string, role: string) => {
    try {
      await authApi.updateUser(username, { role });
      toast.success(`Updated role for ${username}.`);
      await refetchUsers();
      if (user && user.username === username) {
        await refreshUser();
      }
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to update role.'));
    }
  };

  // handleResetPassword is now handled inline in AdminUserStats component

  const handleDeleteUser = async (username: string) => {
    const confirmed = window.confirm(`Delete user '${username}'? This action cannot be undone.`);
    if (!confirmed) {
      return;
    }
    try {
      await authApi.deleteUser(username);
      toast.success(`Deleted user '${username}'.`);
      await refetchUsers();
      await queryClient.invalidateQueries({ queryKey: ['admin-user-stats'] });
      if (user && user.username === username) {
        logout();
      }
    } catch (error) {
      toast.error(getErrorMessage(error, 'Failed to delete user.'));
    }
  };

  const getWhisperApiKey = (w: WhisperConfig | undefined): string => {
    if (!w) return '';
    if (w.whisper_type === 'remote') return w.api_key ?? '';
    if (w.whisper_type === 'groq') return w.api_key ?? '';
    return '';
  };

  const whisperApiKeyPreview =
    pending?.whisper?.whisper_type === 'remote' || pending?.whisper?.whisper_type === 'groq'
      ? pending.whisper.api_key_preview
      : undefined;

  const whisperApiKeyPlaceholder = useMemo(() => {
    if (pending?.whisper?.whisper_type === 'remote' || pending?.whisper?.whisper_type === 'groq') {
      if (whisperApiKeyPreview) {
        return whisperApiKeyPreview;
      }
      const override = envOverrides['whisper.api_key'];
      if (override) {
        return override.value_preview || override.value || '';
      }
    }
    return '';
  }, [whisperApiKeyPreview, pending?.whisper?.whisper_type, envOverrides]);

  const updatePending = useCallback(
    (
      transform: (prevConfig: CombinedConfig) => CombinedConfig,
      markDirty: boolean = true,
    ) => {
      let updated = false;
      setPending((prevConfig) => {
        if (!prevConfig) {
          return prevConfig;
        }
        const nextConfig = transform(prevConfig);
        if (nextConfig === prevConfig) {
          return prevConfig;
        }
        updated = true;
        return nextConfig;
      });

      if (updated && markDirty) {
        setHasEdits(true);
      }
    },
    [],
  );

  const setField = useCallback(
    (path: string[], value: unknown) => {
      updatePending((prevConfig) => {
        const prevRecord = prevConfig as unknown as Record<string, unknown>;
        const lastIndex = path.length - 1;

        let existingParent: Record<string, unknown> | null = prevRecord;
        for (let i = 0; i < lastIndex; i++) {
          const key = path[i];
          const rawNext: unknown = existingParent?.[key];
          const nextParent: Record<string, unknown> | null =
            rawNext && typeof rawNext === 'object'
              ? (rawNext as Record<string, unknown>)
              : null;
          if (!nextParent) {
            existingParent = null;
            break;
          }
          existingParent = nextParent;
        }

        if (existingParent) {
          const currentValue = existingParent[path[lastIndex]];
          if (Object.is(currentValue, value)) {
            return prevConfig;
          }
        }

        const next: Record<string, unknown> = { ...prevRecord };

        let cursor: Record<string, unknown> = next;
        let sourceCursor: Record<string, unknown> = prevRecord;

        for (let i = 0; i < lastIndex; i++) {
          const key = path[i];
          const currentSource =
            (sourceCursor?.[key] as Record<string, unknown>) ?? {};
          const clonedChild: Record<string, unknown> = { ...currentSource };
          cursor[key] = clonedChild;
          cursor = clonedChild;
          sourceCursor = currentSource;
        }

        cursor[path[lastIndex]] = value;

        return next as unknown as CombinedConfig;
      });
    },
    [updatePending],
  );

  const isLlmKeyReference = useCallback((value: unknown): value is string => {
    if (typeof value !== 'string') return false;
    return value.startsWith('env:') || value.startsWith('profile:');
  }, []);

  const inferProviderFromApiKey = useCallback((key: string): string | null => {
    const trimmed = key.trim();
    if (trimmed.startsWith('gsk_')) return 'groq';
    if (trimmed.startsWith('xai-')) return 'xai';
    if (trimmed.startsWith('sk-ant-')) return 'anthropic';
    if (trimmed.startsWith('sk-')) return 'openai';
    return null;
  }, []);

  const inferProviderFromModel = useCallback((model: unknown): string => {
    if (typeof model !== 'string' || model.trim() === '') return 'custom';
    const val = model.trim().toLowerCase();
    if (val.startsWith('groq/')) return 'groq';
    if (val.startsWith('xai/')) return 'xai';
    if (val.startsWith('anthropic/')) return 'anthropic';
    if (val.startsWith('gemini/')) return 'google';
    if (val.startsWith('gpt-') || val.startsWith('o1') || val.startsWith('o3') || val.startsWith('o4')) return 'openai';
    return 'custom';
  }, []);

  const currentLlmKeyRef = useMemo(() => {
    const fromRef = pending?.llm?.llm_api_key_ref;
    if (isLlmKeyReference(fromRef)) {
      return fromRef;
    }
    const raw = pending?.llm?.llm_api_key;
    if (isLlmKeyReference(raw)) {
      return raw;
    }
    return 'manual';
  }, [pending?.llm?.llm_api_key, pending?.llm?.llm_api_key_ref, isLlmKeyReference]);

  const currentLlmProvider = useMemo(() => {
    if (currentLlmKeyRef.startsWith('env:')) {
      const envMatch = llmOptions?.env_keys.find((item) => item.ref === currentLlmKeyRef);
      if (envMatch?.provider) {
        return envMatch.provider;
      }
    }
    if (currentLlmKeyRef.startsWith('profile:')) {
      const profileMatch = llmOptions?.saved_keys.find((item) => item.ref === currentLlmKeyRef);
      if (profileMatch?.provider) {
        return profileMatch.provider;
      }
    }
    return inferProviderFromModel(pending?.llm?.llm_model);
  }, [currentLlmKeyRef, llmOptions?.env_keys, llmOptions?.saved_keys, pending?.llm?.llm_model, inferProviderFromModel]);

  const providerModelOptions = useMemo(() => {
    const allModels = llmOptions?.models ?? [];
    return allModels.filter((item) => item.provider === currentLlmProvider);
  }, [llmOptions?.models, currentLlmProvider]);

  const selectedProfileId = useMemo(() => {
    if (!currentLlmKeyRef.startsWith('profile:')) return null;
    const raw = currentLlmKeyRef.slice('profile:'.length);
    return /^\d+$/.test(raw) ? Number(raw) : null;
  }, [currentLlmKeyRef]);

  const saveLlmProfileMutation = useMutation({
    mutationFn: async () => {
      const keyValue = manualLlmKey.trim();
      if (!keyValue) {
        throw new Error('Enter an API key first.');
      }
      const provider = currentLlmProvider || inferProviderFromModel(pending?.llm?.llm_model);
      return configApi.saveLlmKeyProfile({
        name: llmKeyProfileName.trim() || undefined,
        provider,
        api_key: keyValue,
        openai_base_url: pending?.llm?.openai_base_url || null,
        default_model: pending?.llm?.llm_model || null,
      });
    },
    onSuccess: async (result) => {
      const profileRef = result.profile.ref;
      setField(['llm', 'llm_api_key_ref'], profileRef);
      setField(['llm', 'llm_api_key'], profileRef);
      setManualLlmKey('');
      setLlmKeyProfileName('');
      await refetchLlmOptions();
      toast.success('Saved key profile.');
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, 'Failed to save key profile.'));
    },
  });

  const deleteLlmProfileMutation = useMutation({
    mutationFn: async (profileId: number) => configApi.deleteLlmKeyProfile(profileId),
    onSuccess: async () => {
      if (selectedProfileId !== null) {
        setField(['llm', 'llm_api_key_ref'], null);
        setField(['llm', 'llm_api_key'], '');
      }
      await refetchLlmOptions();
      toast.success('Deleted key profile.');
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, 'Failed to delete key profile.'));
    },
  });

  const handleLlmKeySourceChange = useCallback(
    (nextRef: string) => {
      if (nextRef === 'manual') {
        setField(['llm', 'llm_api_key_ref'], null);
        setField(['llm', 'llm_api_key'], manualLlmKey);
        return;
      }

      setField(['llm', 'llm_api_key_ref'], nextRef);
      setField(['llm', 'llm_api_key'], nextRef);

      const envMatch = llmOptions?.env_keys.find((item) => item.ref === nextRef);
      const savedMatch = llmOptions?.saved_keys.find((item) => item.ref === nextRef);
      const match = savedMatch ?? envMatch;
      if (match) {
        setField(['llm', 'llm_model'], match.default_model ?? '');
        setField(['llm', 'openai_base_url'], match.default_openai_base_url ?? '');
      }
    },
    [llmOptions?.env_keys, llmOptions?.saved_keys, manualLlmKey, setField],
  );

  useEffect(() => {
    if (!configData) {
      return;
    }
    setPending((prev) => {
      if (prev === null) {
        return configData;
      }
      if (hasEdits) {
        return prev;
      }
      return configData;
    });
  }, [configData, hasEdits]);

  const probeConnections = async () => {
    if (!pending) return;
    setLlmStatus('loading');
    setWhisperStatus('loading');
    setLlmMessage('');
    setLlmError('');
    setWhisperMessage('');
    setWhisperError('');
    try {
      const [llmRes, whisperRes] = await Promise.all([
        configApi.testLLM({ llm: pending.llm as LLMConfig }),
        configApi.testWhisper({ whisper: pending.whisper as WhisperConfig }),
      ]);

      if (llmRes?.ok) {
        setLlmStatus('ok');
        setLlmMessage(llmRes.message || 'LLM connection OK');
      } else {
        setLlmStatus('error');
        setLlmError(llmRes?.error || 'LLM connection failed');
      }

      if (whisperRes?.ok) {
        setWhisperStatus('ok');
        setWhisperMessage(whisperRes.message || 'Whisper connection OK');
      } else {
        setWhisperStatus('error');
        setWhisperError(whisperRes?.error || 'Whisper test failed');
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { error?: string; message?: string } }; message?: string };
      const msg = e?.response?.data?.error || e?.response?.data?.message || e?.message || 'Connection test failed';
      // Only set error status if we haven't already set a success status
      if (llmStatus !== 'ok') {
        setLlmStatus('error');
        setLlmError(msg);
      }
      if (whisperStatus !== 'ok') {
        setWhisperStatus('error');
        setWhisperError(msg);
      }
    }
  };

  useEffect(() => {
    if (!pending || initialProbeDone.current) return;
    initialProbeDone.current = true;
    void probeConnections();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      return configApi.updateConfig((pending ?? {}) as Partial<CombinedConfig>);
    },
    onSuccess: () => {
      setHasEdits(false);
      refetch();
    },
  });

  const saveToastMessages = {
    loading: 'Saving changes...',
    success: 'Configuration saved',
    error: (err: unknown) => {
      if (typeof err === 'object' && err !== null) {
        const e = err as {
          response?: { data?: { error?: string; details?: string; message?: string } };
          message?: string;
        };
        return (
          e.response?.data?.message ||
          e.response?.data?.error ||
          e.response?.data?.details ||
          e.message ||
          'Failed to save configuration'
        );
      }
      return 'Failed to save configuration';
    },
  } as const;

  const getEnvManagedConflicts = (): string[] => {
    if (!pending || !configData) {
      return [];
    }
    return Object.keys(envOverrides).filter((path) => {
      const baseline = getValueAtPath(configData, path);
      const current = getValueAtPath(pending, path);
      return valuesDiffer(current, baseline);
    });
  };

  const triggerSaveMutation = () => {
    toast.promise(saveMutation.mutateAsync(), saveToastMessages);
  };

  const handleSave = () => {
    if (saveMutation.isPending) {
      return;
    }
    const envConflicts = getEnvManagedConflicts();
    if (envConflicts.length > 0) {
      setEnvWarningPaths(envConflicts);
      setShowEnvWarning(true);
      return;
    }
    triggerSaveMutation();
  };

  const handleConfirmEnvWarning = () => {
    setShowEnvWarning(false);
    triggerSaveMutation();
  };

  const handleDismissEnvWarning = () => {
    setShowEnvWarning(false);
    setEnvWarningPaths([]);
  };


  const applyGroqKeyMutation = useMutation({
    mutationFn: async (key: string) => {
      const next = {
        llm: {
          ...(pending?.llm as LLMConfig),
          llm_api_key: key,
          llm_model: groqRecommendedModel,
        },
        whisper: {
          whisper_type: 'groq',
          api_key: key,
          model: groqRecommendedWhisper,
          language: 'en',
          max_retries: 3,
        },
      } as Partial<CombinedConfig>;

      updatePending((prevConfig) => ({
        ...prevConfig,
        llm: next.llm as LLMConfig,
        whisper: next.whisper as WhisperConfig,
      }));

      const [llmRes, whisperRes] = await Promise.all([
        configApi.testLLM({ llm: next.llm as LLMConfig }),
        configApi.testWhisper({ whisper: next.whisper as WhisperConfig }),
      ]);
      if (!llmRes?.ok) throw new Error(llmRes?.error || 'LLM test failed');
      if (!whisperRes?.ok) throw new Error(whisperRes?.error || 'Whisper test failed');

      return await configApi.updateConfig(next);
    },
    onSuccess: () => {
      setHasEdits(false);
      refetch();
      toast.success('Groq key verified and saved. Defaults applied.');
      setLlmStatus('ok');
      setLlmMessage(`Connected to ${groqRecommendedModel}`);
      setWhisperStatus('ok');
      setWhisperMessage('Whisper connection OK');
    },
  });

  // Probe whisper capabilities once and adapt UI/state
  useEffect(() => {
    let cancelled = false;
    configApi
      .getWhisperCapabilities()
      .then((res) => {
        if (!cancelled) setLocalWhisperAvailable(!!res.local_available);
      })
      .catch(() => {
        if (!cancelled) setLocalWhisperAvailable(false);
      });
    return () => {
        cancelled = true;
    };
  }, []);

  // If local is unavailable but selected, switch to a safe default
  useEffect(() => {
    if (!pending || localWhisperAvailable !== false) return;
    const currentType = pending.whisper.whisper_type;
    if (currentType === 'local') {
      setField(['whisper', 'whisper_type'], 'remote');
    }
  }, [localWhisperAvailable, pending]);

  if (isLoading || !pending) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-3">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
          <p className="text-sm text-gray-500">Loading configuration...</p>
        </div>
      </div>
    );
  }

  const handleWhisperTypeChange = (
    nextType: 'local' | 'remote' | 'groq'
  ) => {
    updatePending((prevConfig) => {
      const prevWhisper = {
        ...(prevConfig.whisper as unknown as Record<string, unknown>),
      };
      const prevModelRaw = (prevWhisper?.model as string | undefined) ?? '';
      const prevModel = String(prevModelRaw).toLowerCase();

      const isNonGroqDefault = prevModel === 'base' || prevModel === 'base.en' || prevModel === 'whisper-1';
      const isDeprecatedGroq = prevModel === 'distil-whisper-large-v3-en';

      let nextModel: string | undefined = prevWhisper?.model as string | undefined;

      if (nextType === 'groq') {
        if (!nextModel || isNonGroqDefault || isDeprecatedGroq) {
          nextModel = 'whisper-large-v3-turbo';
        }
      } else if (nextType === 'remote') {
        if (!nextModel || prevModel === 'base' || prevModel === 'base.en') {
          nextModel = 'whisper-1';
        }
      } else if (nextType === 'local') {
        if (!nextModel || prevModel === 'whisper-1' || prevModel.startsWith('whisper-large')) {
          nextModel = 'base.en';
        }
      }

      const nextWhisper: Record<string, unknown> = {
        ...prevWhisper,
        whisper_type: nextType,
      };

      if (nextType === 'groq') {
        nextWhisper.model = nextModel ?? 'whisper-large-v3-turbo';
        nextWhisper.language = (prevWhisper.language as string | undefined) || 'en';
        delete nextWhisper.base_url;
        delete nextWhisper.timeout_sec;
        delete nextWhisper.chunksize_mb;
      } else if (nextType === 'remote') {
        nextWhisper.model = nextModel ?? 'whisper-1';
        nextWhisper.language = (prevWhisper.language as string | undefined) || 'en';
      } else if (nextType === 'local') {
        nextWhisper.model = nextModel ?? 'base.en';
        delete nextWhisper.api_key;
      } else if (nextType === 'test') {
        delete nextWhisper.model;
        delete nextWhisper.api_key;
      }

      return {
        ...prevConfig,
        whisper: nextWhisper as unknown as WhisperConfig,
      } as CombinedConfig;
    });
  };


  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold rainbow-text">Settings ⚙️</h1>
          <div className="flex items-center gap-3 mt-1">
            <p className="text-purple-600">Configure your LLM and Whisper connections</p>
            <a
              href="https://t.me/+AV5-w_GSd2VjNjBk"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-[#229ED9] bg-[#229ED9]/10 rounded-full hover:bg-[#229ED9]/20 transition-colors"
            >
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
              </svg>
              Join Community
            </a>
          </div>
        </div>
      </div>

      {/* Pending Signups - Show at top for admins when there are pending users */}
      {showSecurityControls && user?.role === 'admin' && pendingUsers?.users && pendingUsers.users.length > 0 && (
        <div className="bg-amber-50 dark:bg-amber-900/30 backdrop-blur-sm rounded-xl border-2 border-amber-300 dark:border-amber-600 shadow-sm">
          <div className="px-4 py-3 border-b border-amber-200 dark:border-amber-700 bg-gradient-to-r from-amber-100/50 to-orange-100/50 dark:from-amber-900/50 dark:to-orange-900/50">
            <h3 className="text-sm font-semibold text-amber-900 dark:text-amber-100 flex items-center gap-2">
              ⚠️ Pending Signups ({pendingUsers.users.length})
            </h3>
          </div>
          <div className="p-4 space-y-2">
            {pendingUsers.users.map((u) => (
              <div key={u.id} className="border border-gray-200 dark:border-purple-700 rounded-lg p-3 bg-white dark:bg-slate-800/60 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-gray-900 dark:text-purple-100 truncate">{u.email || u.username}</div>
                  <div className="text-xs text-gray-500 dark:text-purple-400">Requested {new Date(u.created_at).toLocaleString()}</div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="px-3 py-1.5 rounded bg-gradient-to-r from-purple-600 to-pink-500 text-white text-sm hover:from-purple-700 hover:to-pink-600 disabled:opacity-50"
                    onClick={() => approvePendingMutation.mutate(u.id)}
                    disabled={approvePendingMutation.isPending}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    className="px-3 py-1.5 rounded border border-red-300 text-red-600 dark:text-red-400 text-sm hover:bg-red-50 dark:hover:bg-red-900/30 disabled:opacity-50"
                    onClick={() => {
                      const confirmed = window.confirm(`Reject and delete '${u.email || u.username}'?`);
                      if (confirmed) {
                        deletePendingMutation.mutate(u.id);
                      }
                    }}
                    disabled={deletePendingMutation.isPending}
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <Section title="Connection Status">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className={`flex items-center justify-between rounded-lg p-4 ${
            llmStatus === 'ok' ? 'bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-700' :
            llmStatus === 'error' ? 'bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700' :
            'bg-purple-50 dark:bg-purple-900/30 border border-purple-200 dark:border-purple-700'
          }`}>
            <div className="flex items-center gap-3">
              <div className={`w-3 h-3 rounded-full ${
                llmStatus === 'ok' ? 'bg-green-500' :
                llmStatus === 'error' ? 'bg-red-500' :
                'bg-purple-400 animate-pulse'
              }`} />
              <div>
                <div className="text-sm font-medium text-gray-900 dark:text-purple-100">LLM Connection</div>
                <div className={`text-xs ${
                  llmStatus === 'ok' ? 'text-green-700 dark:text-green-300' :
                  llmStatus === 'error' ? 'text-red-700 dark:text-red-300' :
                  'text-gray-600 dark:text-purple-300'
                }`}>
                  {llmStatus === 'loading' && 'Testing connection...'}
                  {llmStatus === 'ok' && (llmMessage || 'Connected')}
                  {llmStatus === 'error' && (llmError || 'Connection failed')}
                </div>
              </div>
            </div>
            <button
              type="button"
              className="px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-purple-200 bg-white dark:bg-purple-800 border border-gray-300 dark:border-purple-600 rounded-lg hover:bg-gray-50 dark:hover:bg-purple-700 transition-colors"
              onClick={() => void probeConnections()}
            >
              Test
            </button>
          </div>
          <div className={`flex items-center justify-between rounded-lg p-4 ${
            whisperStatus === 'ok' ? 'bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-700' :
            whisperStatus === 'error' ? 'bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700' :
            'bg-purple-50 dark:bg-purple-900/30 border border-purple-200 dark:border-purple-700'
          }`}>
            <div className="flex items-center gap-3">
              <div className={`w-3 h-3 rounded-full ${
                whisperStatus === 'ok' ? 'bg-green-500' :
                whisperStatus === 'error' ? 'bg-red-500' :
                'bg-purple-400 animate-pulse'
              }`} />
              <div>
                <div className="text-sm font-medium text-gray-900 dark:text-purple-100">Whisper Connection</div>
                <div className={`text-xs ${
                  whisperStatus === 'ok' ? 'text-green-700 dark:text-green-300' :
                  whisperStatus === 'error' ? 'text-red-700 dark:text-red-300' :
                  'text-gray-600 dark:text-purple-300'
                }`}>
                  {whisperStatus === 'loading' && 'Testing connection...'}
                  {whisperStatus === 'ok' && (whisperMessage || 'Connected')}
                  {whisperStatus === 'error' && (whisperError || 'Connection failed')}
                </div>
              </div>
            </div>
            <button
              type="button"
              className="px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-purple-200 bg-white dark:bg-purple-800 border border-gray-300 dark:border-purple-600 rounded-lg hover:bg-gray-50 dark:hover:bg-purple-700 transition-colors"
              onClick={() => void probeConnections()}
            >
              Test
            </button>
          </div>
        </div>
      </Section>


      {showSecurityControls && (
                  <Section title="Account Security">
            <form className="grid gap-3 max-w-md" onSubmit={handlePasswordSubmit}>
              <Field label="Current password">
                <input
                  className="input"
                  type="password"
                  autoComplete="current-password"
                  value={passwordForm.current}
                  onChange={(event) => setPasswordForm((prev) => ({ ...prev, current: event.target.value }))}
                  required
                />
              </Field>
              <Field label="New password">
                <input
                  className="input"
                  type="password"
                  autoComplete="new-password"
                  value={passwordForm.next}
                  onChange={(event) => setPasswordForm((prev) => ({ ...prev, next: event.target.value }))}
                  required
                />
              </Field>
              <Field label="Confirm new password">
                <input
                  className="input"
                  type="password"
                  autoComplete="new-password"
                  value={passwordForm.confirm}
                  onChange={(event) => setPasswordForm((prev) => ({ ...prev, confirm: event.target.value }))}
                  required
                />
              </Field>
              <div className="flex flex-col gap-2 pt-2">
                <button
                  type="submit"
                  className="w-fit px-6 py-2.5 rounded-lg bg-gradient-to-r from-purple-600 to-pink-500 text-white text-sm font-medium hover:from-purple-700 hover:to-pink-600 disabled:opacity-60 shadow-sm"
                  disabled={passwordSubmitting}
                >
                  {passwordSubmitting ? 'Updating…' : 'Update password'}
                </button>
                <p className="text-xs text-purple-500">
                  After updating, rotate <code className="font-mono bg-purple-50 px-1 rounded">PODLY_ADMIN_PASSWORD</code> to match.
                </p>
              </div>
            </form>
          </Section>
      )}
      {showSecurityControls && user?.role === 'admin' && (
        <Section title="User Management">
          <div className="space-y-4">
            <form className="grid gap-3 md:grid-cols-2" onSubmit={handleCreateUser}>
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-purple-200 mb-1">Username</label>
                <input
                  className="input"
                  type="text"
                  value={newUser.username}
                  onChange={(event) => setNewUser((prev) => ({ ...prev, username: event.target.value }))}
                  placeholder="new_user"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-purple-200 mb-1">Password</label>
                <input
                  className="input"
                  type="password"
                  value={newUser.password}
                  onChange={(event) => setNewUser((prev) => ({ ...prev, password: event.target.value }))}
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-purple-200 mb-1">Confirm password</label>
                <input
                  className="input"
                  type="password"
                  value={newUser.confirm}
                  onChange={(event) => setNewUser((prev) => ({ ...prev, confirm: event.target.value }))}
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-purple-200 mb-1">Role</label>
                <select
                  className="input"
                  value={newUser.role}
                  onChange={(event) => setNewUser((prev) => ({ ...prev, role: event.target.value }))}
                >
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </select>
              </div>
              <div className="md:col-span-2 flex items-center justify-start">
                <button
                  type="submit"
                  className="px-4 py-2 rounded bg-gradient-to-r from-purple-600 to-pink-500 text-white text-sm font-medium hover:from-purple-700 hover:to-pink-600"
                >
                  Add user
                </button>
              </div>
            </form>

            {/* User Statistics with integrated controls */}
            <AdminUserStats 
              onRoleChange={handleRoleChange}
              onDeleteUser={handleDeleteUser}
              onResetPassword={async (username, password) => {
                try {
                  await authApi.updateUser(username, { password });
                  toast.success(`Password updated for ${username}`);
                } catch {
                  toast.error('Failed to reset password');
                }
              }}
              adminCount={managedUsers?.filter(u => u.role === 'admin').length ?? 1}
              currentUsername={user?.username}
            />
          </div>
        </Section>
      )}

      {/* Database Maintenance - Admin only */}
      {showSecurityControls && user?.role === 'admin' && (
        <Section title="Database Maintenance">
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="text-sm font-medium text-gray-900 dark:text-purple-100">Repair Processed Audio Paths</h4>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Scan for processed audio files on disk and update database records where the path is missing.
                  Useful after database migrations or server moves.
                </p>
              </div>
              <button
                type="button"
                onClick={async () => {
                  try {
                    toast.loading('Scanning for processed files...', { id: 'repair-paths' });
                    const result = await feedsApi.repairProcessedPaths();
                    toast.success(
                      `Repaired ${result.repaired} of ${result.checked} posts checked${result.total_errors > 0 ? ` (${result.total_errors} errors)` : ''}`,
                      { id: 'repair-paths', duration: 5000 }
                    );
                  } catch (err) {
                    toast.error('Failed to repair paths', { id: 'repair-paths' });
                  }
                }}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium rounded-lg transition-colors whitespace-nowrap"
              >
                Repair Paths
              </button>
            </div>
          </div>
        </Section>
      )}

      <div className="space-y-6">
        <Section title="LLM Configuration">
            <Field label="Provider">
              <select
                className="input"
                value={currentLlmProvider}
                onChange={(e) => {
                  const nextProvider = e.target.value;
                  const providerDefaults = llmOptions?.providers.find((p) => p.id === nextProvider);
                  setField(['llm', 'llm_model'], providerDefaults?.default_model ?? '');
                  setField(['llm', 'openai_base_url'], providerDefaults?.default_openai_base_url ?? '');
                }}
              >
                {(llmOptions?.providers ?? []).map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.label}
                  </option>
                ))}
                {(llmOptions?.providers ?? []).length === 0 && <option value="custom">Custom / Other</option>}
              </select>
            </Field>
            <Field label="API Key Source" envMeta={getEnvHint('llm.llm_api_key')}>
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <select
                    className="input"
                    value={currentLlmKeyRef}
                    onChange={(e) => handleLlmKeySourceChange(e.target.value)}
                  >
                    <option value="manual">Manual key entry</option>
                    {(llmOptions?.env_keys ?? []).map((item) => (
                      <option key={item.ref} value={item.ref}>
                        {`Environment: ${item.env_var} (${item.api_key_preview || 'configured'})`}
                      </option>
                    ))}
                    {(llmOptions?.saved_keys ?? []).map((item) => (
                      <option key={item.ref} value={item.ref}>
                        {`Saved: ${item.name} (${item.api_key_preview})`}
                      </option>
                    ))}
                  </select>
                  {selectedProfileId !== null && (
                    <button
                      type="button"
                      className="px-3 py-2 text-xs rounded border border-red-300 text-red-600 hover:bg-red-50"
                      onClick={() => {
                        const confirmed = window.confirm('Delete this saved key profile?');
                        if (confirmed) {
                          void deleteLlmProfileMutation.mutateAsync(selectedProfileId);
                        }
                      }}
                      disabled={deleteLlmProfileMutation.isPending}
                    >
                      Delete
                    </button>
                  )}
                </div>
                {currentLlmKeyRef !== 'manual' && (
                  <p className="text-xs text-gray-600">
                    Selected key reference: <code className="font-mono">{currentLlmKeyRef}</code>
                  </p>
                )}
              </div>
            </Field>
            {currentLlmKeyRef === 'manual' && (
              <Field label="Manual API Key" envMeta={getEnvHint('llm.llm_api_key')}>
                <div className="space-y-2">
                  <input
                    className="input"
                    type="text"
                    placeholder={pending?.llm?.llm_api_key_preview || ''}
                    value={manualLlmKey}
                    onChange={(e) => {
                      const value = e.target.value;
                      setManualLlmKey(value);
                      setField(['llm', 'llm_api_key_ref'], null);
                      setField(['llm', 'llm_api_key'], value);

                      const detected = inferProviderFromApiKey(value);
                      if (detected) {
                        const providerDefaults = llmOptions?.providers.find((p) => p.id === detected);
                        if (providerDefaults) {
                          setField(['llm', 'llm_model'], providerDefaults.default_model ?? '');
                          setField(['llm', 'openai_base_url'], providerDefaults.default_openai_base_url ?? '');
                        }
                        if (detected === 'groq') {
                          setField(['whisper', 'whisper_type'], 'groq');
                          setField(['whisper', 'api_key'], value);
                          setField(['whisper', 'model'], groqRecommendedWhisper);
                        }
                      }
                    }}
                    onPaste={(e) => {
                      const text = e.clipboardData.getData('text').trim();
                      if (text.startsWith('gsk_')) {
                        e.preventDefault();
                        setManualLlmKey(text);
                        toast.promise(applyGroqKeyMutation.mutateAsync(text), {
                          loading: 'Verifying Groq key...',
                          success: 'Groq configured (LLM + Whisper)',
                          error: (err: unknown) => {
                            const er = err as { response?: { data?: { error?: string; message?: string } }; message?: string };
                            return er?.response?.data?.error || er?.response?.data?.message || er?.message || 'Failed to configure Groq';
                          },
                        });
                      }
                    }}
                  />
                  <div className="flex items-center gap-2">
                    <input
                      className="input"
                      type="text"
                      placeholder="Profile name (optional)"
                      value={llmKeyProfileName}
                      onChange={(e) => setLlmKeyProfileName(e.target.value)}
                    />
                    <button
                      type="button"
                      className="px-3 py-2 text-xs rounded bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-60"
                      onClick={() => {
                        void saveLlmProfileMutation.mutateAsync();
                      }}
                      disabled={saveLlmProfileMutation.isPending || manualLlmKey.trim() === ''}
                    >
                      Save Key
                    </button>
                  </div>
                  <p className="text-xs text-gray-500">
                    Saved keys are encrypted server-side and can be re-selected later.
                  </p>
                </div>
              </Field>
            )}
            <label className="flex items-start justify-between gap-3">
              <div className="w-60">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-700">OpenAI Base URL</span>
                  <button
                    type="button"
                    className="px-2 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50"
                    onClick={() => setShowBaseUrlInfo((v) => !v)}
                    title="When is this used?"
                  >
                    ⓘ
                  </button>
                </div>
                <EnvVarHint meta={getEnvHint('llm.openai_base_url')} />
              </div>
              <div className="flex-1">
                <input
                  className="input"
                  type="text"
                  placeholder="https://api.openai.com/v1"
                  value={pending?.llm?.openai_base_url || ''}
                  onChange={(e) => setField(['llm', 'openai_base_url'], e.target.value)}
                />
                {showBaseUrlInfo && (
                  <div className="mt-2 text-xs bg-blue-50 border border-blue-200 rounded p-3 space-y-2">
                    <p className="font-medium text-blue-800">When do you need a Base URL?</p>
                    <div className="text-blue-700 space-y-1">
                      <p>• <strong>Groq, Anthropic, Gemini</strong> — leave empty. Models with a provider prefix (e.g. <code className="bg-white px-1 rounded">groq/</code>, <code className="bg-white px-1 rounded">anthropic/</code>) are routed automatically.</p>
                      <p>• <strong>xAI Grok</strong> — set to <code className="bg-white px-1 rounded">https://api.x.ai/v1</code>. Models prefixed with <code className="bg-white px-1 rounded">xai/</code> also auto-route, so you can leave it empty if using <code className="bg-white px-1 rounded">xai/grok-3</code>.</p>
                      <p>• <strong>OpenAI</strong> — leave empty (uses default). Only set this if you use a custom OpenAI-compatible endpoint.</p>
                    </div>
                    <p className="text-blue-600 italic">Selecting a provider above auto-fills the correct Base URL for you.</p>
                  </div>
                )}
              </div>
              <style>{`.input{width:100%;padding:0.5rem;border:1px solid #e5e7eb;border-radius:0.375rem;font-size:0.875rem}`}</style>
            </label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Model" envMeta={getEnvHint('llm.llm_model')}>
                <div className="space-y-2">
                  <select
                    className="input"
                    value={pending?.llm?.llm_model ?? ''}
                    onChange={(e) => setField(['llm', 'llm_model'], e.target.value)}
                  >
                    <option value="">Select model</option>
                    {providerModelOptions.map((model) => (
                      <option key={model.value} value={model.value}>
                        {model.value}
                      </option>
                    ))}
                    {pending?.llm?.llm_model &&
                      !providerModelOptions.some((item) => item.value === pending.llm.llm_model) && (
                        <option value={pending.llm.llm_model}>{`${pending.llm.llm_model} (custom)`}</option>
                      )}
                  </select>
                  <input
                    list="llm-model-datalist"
                    className="input"
                    type="text"
                    value={pending?.llm?.llm_model ?? ''}
                    onChange={(e) => setField(['llm', 'llm_model'], e.target.value)}
                    placeholder="e.g. groq/openai/gpt-oss-120b"
                  />
                </div>
              </Field>
              <Field label="OpenAI Timeout (sec)">
                <input
                  className="input"
                  type="number"
                  value={pending?.llm?.openai_timeout ?? 300}
                  onChange={(e) => setField(['llm', 'openai_timeout'], Number(e.target.value))}
                />
              </Field>
              <Field label="OpenAI Max Tokens">
                <input
                  className="input"
                  type="number"
                  value={pending?.llm?.openai_max_tokens ?? 4096}
                  onChange={(e) => setField(['llm', 'openai_max_tokens'], Number(e.target.value))}
                />
              </Field>
              <Field label="Max Concurrent LLM Calls">
                <input
                  className="input"
                  type="number"
                  value={pending?.llm?.llm_max_concurrent_calls ?? 3}
                  onChange={(e) => setField(['llm', 'llm_max_concurrent_calls'], Number(e.target.value))}
                />
              </Field>
              <Field label="Max Retry Attempts">
                <input
                  className="input"
                  type="number"
                  value={pending?.llm?.llm_max_retry_attempts ?? 5}
                  onChange={(e) => setField(['llm', 'llm_max_retry_attempts'], Number(e.target.value))}
                />
              </Field>
              <Field label="Enable Token Rate Limiting">
                <input
                  type="checkbox"
                  checked={!!pending?.llm?.llm_enable_token_rate_limiting}
                  onChange={(e) => setField(['llm', 'llm_enable_token_rate_limiting'], e.target.checked)}
                />
              </Field>
              <Field label="Max Input Tokens Per Call (optional)">
                <input
                  className="input"
                  type="number"
                  value={pending?.llm?.llm_max_input_tokens_per_call ?? ''}
                  onChange={(e) => setField(['llm', 'llm_max_input_tokens_per_call'], e.target.value === '' ? null : Number(e.target.value))}
                />
              </Field>
              <Field label="Max Input Tokens Per Minute (optional)">
                <input
                  className="input"
                  type="number"
                  value={pending?.llm?.llm_max_input_tokens_per_minute ?? ''}
                  onChange={(e) => setField(['llm', 'llm_max_input_tokens_per_minute'], e.target.value === '' ? null : Number(e.target.value))}
                />
              </Field>
            </div>
            <div className="flex justify-center">
              <button
                onClick={() => {
                  toast.promise(
                    configApi.testLLM({ llm: pending.llm as LLMConfig }),
                    {
                      loading: 'Testing LLM connection...',
                      success: (res: { ok: boolean; message?: string }) => res?.message || 'LLM connection OK',
                      error: (err: unknown) => {
                        const e = err as { response?: { data?: { error?: string; message?: string } }; message?: string };
                        return (
                          e?.response?.data?.error ||
                          e?.response?.data?.message ||
                          e?.message ||
                          'LLM connection failed'
                        );
                      }
                    }
                  );
                }}
                className="mt-2 px-3 py-2 text-sm rounded bg-gradient-to-r from-purple-600 to-pink-500 text-white hover:from-purple-700 hover:to-pink-600"
              >
                Test LLM
              </button>
            </div>
          </Section>

          <Section title="Whisper">
            <Field label="Type" envMeta={getEnvHint('whisper.whisper_type')}>
              <select
                className="input"
                value={
                  (pending?.whisper?.whisper_type as string | undefined) ?? (localWhisperAvailable === false ? 'remote' : 'local')
                }
                onChange={(e) => handleWhisperTypeChange(e.target.value as 'local' | 'remote' | 'groq')}
              >
                {localWhisperAvailable !== false && <option value="local">local</option>}
                <option value="remote">remote</option>
                <option value="groq">groq</option>
              </select>
            </Field>
            {pending?.whisper?.whisper_type === 'local' && (
              <Field label="Local Model" envMeta={getEnvHint('whisper.model', { env_var: 'WHISPER_LOCAL_MODEL' })}>
                <div className="space-y-2">
                  <select
                    className="input"
                    value={LOCAL_WHISPER_MODELS.includes(pending?.whisper?.model || '') ? pending?.whisper?.model : '__custom__'}
                    onChange={(e) => {
                      if (e.target.value !== '__custom__') setField(['whisper', 'model'], e.target.value);
                    }}
                  >
                    {LOCAL_WHISPER_MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
                    {!LOCAL_WHISPER_MODELS.includes(pending?.whisper?.model || '') && (
                      <option value="__custom__">{pending?.whisper?.model ? `${pending.whisper.model} (custom)` : 'Custom...'}</option>
                    )}
                    <option value="__custom__">Custom...</option>
                  </select>
                  {!LOCAL_WHISPER_MODELS.includes(pending?.whisper?.model || '') && (
                    <input
                      className="input"
                      type="text"
                      placeholder="Enter custom model name"
                      value={pending?.whisper?.model || 'base'}
                      onChange={(e) => setField(['whisper', 'model'], e.target.value)}
                    />
                  )}
                </div>
              </Field>
            )}
            {pending?.whisper?.whisper_type === 'remote' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Field label="API Key" envMeta={getEnvHint('whisper.api_key', { env_var: 'WHISPER_REMOTE_API_KEY' })}>
                  <input
                    className="input"
                    type="text"
                    placeholder={whisperApiKeyPlaceholder}
                    value={getWhisperApiKey(pending?.whisper)}
                    onChange={(e) => setField(['whisper', 'api_key'], e.target.value)}
                  />
                </Field>
                <Field label="Remote Model" envMeta={getEnvHint('whisper.model', { env_var: 'WHISPER_REMOTE_MODEL' })}>
                  <div className="space-y-2">
                    <select
                      className="input"
                      value={REMOTE_WHISPER_MODELS.includes(pending?.whisper?.model || '') ? pending?.whisper?.model : '__custom__'}
                      onChange={(e) => {
                        if (e.target.value !== '__custom__') setField(['whisper', 'model'], e.target.value);
                      }}
                    >
                      {REMOTE_WHISPER_MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
                      {!REMOTE_WHISPER_MODELS.includes(pending?.whisper?.model || '') && (
                        <option value="__custom__">{pending?.whisper?.model ? `${pending.whisper.model} (custom)` : 'Custom...'}</option>
                      )}
                      <option value="__custom__">Custom...</option>
                    </select>
                    {!REMOTE_WHISPER_MODELS.includes(pending?.whisper?.model || '') && (
                      <input
                        className="input"
                        type="text"
                        placeholder="Enter custom model name"
                        value={pending?.whisper?.model || 'whisper-1'}
                        onChange={(e) => setField(['whisper', 'model'], e.target.value)}
                      />
                    )}
                  </div>
                </Field>
                <Field label="Base URL" envMeta={getEnvHint('whisper.base_url')}>
                  <input
                    className="input"
                    type="text"
                    placeholder="https://api.openai.com/v1"
                    value={pending?.whisper?.base_url || ''}
                    onChange={(e) => setField(['whisper', 'base_url'], e.target.value)}
                  />
                </Field>
                <Field label="Language">
                  <input
                    className="input"
                    type="text"
                    value={pending?.whisper?.language || 'en'}
                    onChange={(e) => setField(['whisper', 'language'], e.target.value)}
                  />
                </Field>
                <Field label="Timeout (sec)" envMeta={getEnvHint('whisper.timeout_sec')}>
                  <input
                    className="input"
                    type="number"
                    value={pending?.whisper?.timeout_sec ?? 600}
                    onChange={(e) => setField(['whisper', 'timeout_sec'], Number(e.target.value))}
                  />
                </Field>
                <Field label="Chunk Size (MB)" envMeta={getEnvHint('whisper.chunksize_mb')}>
                  <input
                    className="input"
                    type="number"
                    value={pending?.whisper?.chunksize_mb ?? 24}
                    onChange={(e) => setField(['whisper', 'chunksize_mb'], Number(e.target.value))}
                  />
                </Field>
              </div>
            )}
            {pending?.whisper?.whisper_type === 'groq' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Field label="API Key" envMeta={getEnvHint('whisper.api_key', { env_var: 'GROQ_API_KEY' })}>
                  <input
                    className="input"
                    type="text"
                    placeholder={whisperApiKeyPlaceholder}
                    value={getWhisperApiKey(pending?.whisper)}
                    onChange={(e) => setField(['whisper', 'api_key'], e.target.value)}
                  />
                </Field>
                <Field label="Model" envMeta={getEnvHint('whisper.model', { env_var: 'GROQ_WHISPER_MODEL' })}>
                  <div className="space-y-2">
                    <select
                      className="input"
                      value={GROQ_WHISPER_MODELS.includes(pending?.whisper?.model || '') ? pending?.whisper?.model : '__custom__'}
                      onChange={(e) => {
                        if (e.target.value !== '__custom__') setField(['whisper', 'model'], e.target.value);
                      }}
                    >
                      {GROQ_WHISPER_MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
                      {!GROQ_WHISPER_MODELS.includes(pending?.whisper?.model || '') && (
                        <option value="__custom__">{pending?.whisper?.model ? `${pending.whisper.model} (custom)` : 'Custom...'}</option>
                      )}
                      <option value="__custom__">Custom...</option>
                    </select>
                    {!GROQ_WHISPER_MODELS.includes(pending?.whisper?.model || '') && (
                      <input
                        className="input"
                        type="text"
                        placeholder="Enter custom model name"
                        value={pending?.whisper?.model || 'whisper-large-v3-turbo'}
                        onChange={(e) => setField(['whisper', 'model'], e.target.value)}
                      />
                    )}
                  </div>
                </Field>
                <Field label="Language">
                  <input
                    className="input"
                    type="text"
                    value={pending?.whisper?.language || 'en'}
                    onChange={(e) => setField(['whisper', 'language'], e.target.value)}
                  />
                </Field>
                <Field label="Max Retries" envMeta={getEnvHint('whisper.max_retries')}>
                  <input
                    className="input"
                    type="number"
                    value={pending?.whisper?.max_retries ?? 3}
                    onChange={(e) => setField(['whisper', 'max_retries'], Number(e.target.value))}
                  />
                </Field>
              </div>
            )}
            <div className="flex justify-center">
              <button
                onClick={() => {
                  toast.promise(
                    configApi.testWhisper({ whisper: pending.whisper as WhisperConfig }),
                    {
                      loading: 'Testing Whisper...',
                      success: (res: { ok: boolean; message?: string }) => res?.message || 'Whisper OK',
                      error: (err: unknown) => {
                        const e = err as { response?: { data?: { error?: string; message?: string } }; message?: string };
                        return (
                          e?.response?.data?.error ||
                          e?.response?.data?.message ||
                          e?.message ||
                          'Whisper test failed'
                        );
                      }
                    }
                  );
                }}
                className="mt-2 px-3 py-2 text-sm rounded bg-gradient-to-r from-purple-600 to-pink-500 text-white hover:from-purple-700 hover:to-pink-600"
              >
                Test Whisper
              </button>
            </div>
          </Section>

          <Section title="Processing">
            <Field label="Number of Segments per Prompt">
              <input
                className="input"
                type="number"
                value={pending?.processing?.num_segments_to_input_to_prompt ?? 30}
                onChange={(e) => setField(['processing', 'num_segments_to_input_to_prompt'], Number(e.target.value))}
              />
            </Field>
          </Section>

          <Section title="Output">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Fade (ms)">
                <input
                  className="input"
                  type="number"
                  value={pending?.output?.fade_ms ?? 3000}
                  onChange={(e) => setField(['output', 'fade_ms'], Number(e.target.value))}
                />
              </Field>
              <Field label="Min Segment Separation (sec)">
                <input
                  className="input"
                  type="number"
                  value={pending?.output?.min_ad_segement_separation_seconds ?? 60}
                  onChange={(e) => setField(['output', 'min_ad_segement_separation_seconds'], Number(e.target.value))}
                />
              </Field>
              <Field label="Min Segment Length (sec)">
                <input
                  className="input"
                  type="number"
                  value={pending?.output?.min_ad_segment_length_seconds ?? 14}
                  onChange={(e) => setField(['output', 'min_ad_segment_length_seconds'], Number(e.target.value))}
                />
              </Field>
              <Field label="Min Confidence">
                <input
                  className="input"
                  type="number"
                  step="0.01"
                  value={pending?.output?.min_confidence ?? 0.8}
                  onChange={(e) => setField(['output', 'min_confidence'], Number(e.target.value))}
                />
              </Field>
            </div>
          </Section>

          <Section title="App">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Feed Refresh Background Interval (min)">
                <input
                  className="input"
                  type="number"
                  value={pending?.app?.background_update_interval_minute ?? ''}
                  onChange={(e) => setField(['app', 'background_update_interval_minute'], e.target.value === '' ? null : Number(e.target.value))}
                />
              </Field>
              <Field label="Cleanup Retention (days)">
                <input
                  className="input"
                  type="number"
                  min={0}
                  value={pending?.app?.post_cleanup_retention_days ?? ''}
                  onChange={(e) => setField(['app', 'post_cleanup_retention_days'], e.target.value === '' ? null : Number(e.target.value))}
                />
              </Field>
              <Field label="Auto-whitelist new episodes">
                <input
                  type="checkbox"
                  checked={!!pending?.app?.automatically_whitelist_new_episodes}
                  onChange={(e) => setField(['app', 'automatically_whitelist_new_episodes'], e.target.checked)}
                />
              </Field>
              <Field label="Number of episodes to whitelist from new feed archive">
                <input
                  className="input"
                  type="number"
                  min="0"
                  value={pending?.app?.number_of_episodes_to_whitelist_from_archive_of_new_feed ?? 1}
                  onFocus={(e) => e.target.select()}
                  onChange={(e) => setField(['app', 'number_of_episodes_to_whitelist_from_archive_of_new_feed'], e.target.value === '' ? 0 : Number(e.target.value))}
                />
              </Field>
            </div>
          </Section>

          {showSecurityControls && user?.role === 'admin' && (
            <Section title="User Signups & Email">
              <div className="space-y-4">
                <div className="p-4 bg-purple-50 dark:bg-purple-900/30 border border-purple-200 dark:border-purple-700 rounded-lg">
                  <h4 className="text-sm font-semibold text-purple-900 dark:text-purple-100 mb-3">Signup Settings</h4>
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      id="allow-signup"
                      checked={!!pending?.app?.allow_signup}
                      onChange={(e) => setField(['app', 'allow_signup'], e.target.checked)}
                      className="w-4 h-4"
                    />
                    <label htmlFor="allow-signup" className="text-sm text-gray-700 dark:text-purple-200">
                      Allow new user signups (closed beta - requires admin approval)
                    </label>
                  </div>
                </div>
                
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-semibold text-gray-900 dark:text-purple-100">Email (SMTP) Configuration</h4>
                  {pending?.email?.smtp_host && pending?.email?.smtp_username ? (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300">
                      <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span>
                      Configured
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400">
                      Not configured
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-600 dark:text-purple-300 -mt-2">Configure SMTP to send approval notifications and password reset emails</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <Field label="SMTP Host">
                    <input
                      className="input"
                      type="text"
                      value={pending?.email?.smtp_host ?? ''}
                      onChange={(e) => setField(['email', 'smtp_host'], e.target.value)}
                      placeholder="smtp.example.com"
                    />
                  </Field>
                  <Field label="SMTP Port">
                    <input
                      className="input"
                      type="number"
                      value={pending?.email?.smtp_port ?? ''}
                      onChange={(e) => setField(['email', 'smtp_port'], e.target.value === '' ? null : Number(e.target.value))}
                      placeholder="587"
                    />
                  </Field>
                  <Field label="SMTP Username">
                    <input
                      className="input"
                      type="text"
                      value={pending?.email?.smtp_username ?? ''}
                      onChange={(e) => setField(['email', 'smtp_username'], e.target.value)}
                    />
                  </Field>
                  <Field label="SMTP Password">
                    <input
                      className="input"
                      type="password"
                      placeholder={pending?.email?.smtp_password_preview ?? ''}
                      value={pending?.email?.smtp_password ?? ''}
                      onChange={(e) => setField(['email', 'smtp_password'], e.target.value)}
                    />
                  </Field>
                  <Field label="Use TLS">
                    <input
                      type="checkbox"
                      checked={!!pending?.email?.smtp_use_tls}
                      onChange={(e) => setField(['email', 'smtp_use_tls'], e.target.checked)}
                    />
                  </Field>
                  <Field label="Use SSL">
                    <input
                      type="checkbox"
                      checked={!!pending?.email?.smtp_use_ssl}
                      onChange={(e) => setField(['email', 'smtp_use_ssl'], e.target.checked)}
                    />
                  </Field>
                  <Field label="From Email">
                    <input
                      className="input"
                      type="email"
                      value={pending?.email?.from_email ?? ''}
                      onChange={(e) => setField(['email', 'from_email'], e.target.value)}
                      placeholder="no-reply@yourdomain.com"
                    />
                  </Field>
                  <Field label="Admin Notify Email">
                    <input
                      className="input"
                      type="email"
                      value={pending?.email?.admin_notify_email ?? ''}
                      onChange={(e) => setField(['email', 'admin_notify_email'], e.target.value)}
                      placeholder="admin@yourdomain.com"
                    />
                  </Field>
                  <Field label="App Base URL">
                    <input
                      className="input"
                      type="text"
                      value={pending?.email?.app_base_url ?? ''}
                      onChange={(e) => setField(['email', 'app_base_url'], e.target.value)}
                      placeholder="https://podly.yourdomain.com"
                    />
                  </Field>
                </div>
                <div className="flex justify-center mt-4">
                  <button
                    type="button"
                    onClick={() => {
                      const toEmail = pending?.email?.admin_notify_email || pending?.email?.from_email;
                      if (!toEmail) {
                        toast.error('Please configure Admin Notify Email or From Email first');
                        return;
                      }
                      toast.promise(
                        configApi.testEmail(toEmail),
                        {
                          loading: 'Sending test email...',
                          success: (res) => res?.message || 'Test email sent!',
                          error: (err: unknown) => {
                            const e = err as { response?: { data?: { error?: string; message?: string } }; message?: string };
                            return (
                              e?.response?.data?.error ||
                              e?.response?.data?.message ||
                              e?.message ||
                              'Failed to send test email'
                            );
                          }
                        }
                      );
                    }}
                    className="px-4 py-2 text-sm rounded-lg bg-gradient-to-r from-purple-600 to-pink-500 text-white hover:from-purple-700 hover:to-pink-600 transition-colors"
                  >
                    Send Test Email
                  </button>
                </div>
              </div>
            </Section>
          )}

        </div>

      {showEnvWarning && envWarningPaths.length > 0 && (
        <EnvOverrideWarningModal
          paths={envWarningPaths}
          overrides={envOverrides}
          onCancel={handleDismissEnvWarning}
          onConfirm={handleConfirmEnvWarning}
        />
      )}
      
      {/* Sticky floating save bar */}
      {hasEdits && (
        <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-purple-200 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md shadow-[0_-4px_20px_rgba(0,0,0,0.1)]">
          <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-pink-600 dark:text-pink-400 font-medium">Unsaved changes</span>
            <div className="flex items-center gap-3">
              <button
                onClick={() => {
                  setPending(configData ?? null);
                  setHasEdits(false);
                }}
                className="px-4 py-2 text-sm font-medium text-purple-700 dark:text-purple-300 bg-white dark:bg-slate-800 border border-purple-200 dark:border-purple-600 rounded-xl hover:bg-purple-50 dark:hover:bg-purple-900/30 transition-colors"
              >
                Discard
              </button>
              <button
                onClick={handleSave}
                disabled={saveMutation.isPending}
                className="px-5 py-2 text-sm font-medium text-white bg-gradient-to-r from-pink-500 via-purple-500 to-cyan-500 rounded-xl hover:shadow-lg hover:shadow-purple-500/30 transition-all disabled:opacity-50"
              >
                {saveMutation.isPending ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Extra padding to prevent floating bar / audio player from obscuring bottom settings */}
      <div className={hasEdits ? 'h-32' : 'h-24'}></div>
      {/* Datalist options rendered once at end to ensure they exist in DOM */}
      <LlmModelDatalist models={llmOptions?.models ?? []} />
    </div>
  );
}

function EnvOverrideWarningModal({
  paths,
  overrides,
  onConfirm,
  onCancel,
}: {
  paths: string[];
  overrides: EnvOverrideMap;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!paths.length) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 py-6">
      <div className="w-full max-w-lg space-y-4 rounded-lg bg-white p-5 shadow-xl">
        <div>
          <h3 className="text-base font-semibold text-gray-900">Environment-managed settings</h3>
          <p className="text-sm text-gray-600">
            These fields are controlled by environment variables. Update the referenced variables in your
            <code className="mx-1 font-mono text-xs">.env</code>
            (or deployment secrets) to make the change persistent. Saving now will apply it temporarily until the
            service restarts.
          </p>
        </div>
        <ul className="space-y-3 text-sm">
          {paths.map((path) => {
            const meta = overrides[path];
            const label = ENV_FIELD_LABELS[path] ?? path;
            return (
              <li key={path} className="rounded border border-amber-200 bg-amber-50 p-3">
                <div className="font-medium text-gray-900">{label}</div>
                {meta?.env_var ? (
                  <p className="mt-1 text-xs text-gray-700">
                    Managed by <code className="font-mono">{meta.env_var}</code>
                    {meta?.value_preview && (
                      <span className="ml-1 text-gray-600">({meta.value_preview})</span>
                    )}
                    {!meta?.value_preview && meta?.value && (
                      <span className="ml-1 text-gray-600">({meta.value})</span>
                    )}
                  </p>
                ) : (
                  <p className="mt-1 text-xs text-gray-700">Managed by deployment environment</p>
                )}
              </li>
            );
          })}
        </ul>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            Go back
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded bg-gradient-to-r from-purple-600 to-pink-500 px-3 py-2 text-sm font-semibold text-white hover:from-purple-700 hover:to-pink-600"
          >
            Save anyway
          </button>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children, icon }: { title: string; children: ReactNode; icon?: ReactNode }) {
  return (
    <div className="bg-white/80 backdrop-blur-sm rounded-xl border border-purple-200/50 shadow-sm unicorn-card">
      <div className="px-4 py-3 border-b border-purple-100/50 bg-gradient-to-r from-pink-50/50 via-purple-50/50 to-cyan-50/50">
        <h3 className="text-sm font-semibold text-purple-900 flex items-center gap-2">
          {icon}
          {title}
        </h3>
      </div>
      <div className="p-4 space-y-3">{children}</div>
    </div>
  );
}

function Field({
  label,
  children,
  envMeta,
  description,
}: {
  label: string;
  children: ReactNode;
  envMeta?: EnvOverrideEntry;
  description?: string;
}) {
  return (
    <label className="block">
      <div className="flex items-start justify-between gap-3">
        <div className="w-40 flex-shrink-0">
          <span className="block text-sm text-gray-700">{label}</span>
          {description && <span className="block text-xs text-gray-500 mt-0.5">{description}</span>}
          <EnvVarHint meta={envMeta} />
        </div>
        <div className="flex-1">{children}</div>
      </div>
      <style>{`.input{width:100%;padding:0.5rem 0.75rem;border:1px solid #d1d5db;border-radius:0.375rem;font-size:0.875rem;transition:all 0.15s}.input:focus{outline:none;border-color:#3b82f6;box-shadow:0 0 0 2px rgba(59,130,246,0.1)}`}</style>
    </label>
  );
}

function EnvVarHint({ meta }: { meta?: EnvOverrideEntry }) {
  if (!meta?.env_var) {
    return null;
  }

  return (
    <code className="mt-1 block text-xs text-gray-500 font-mono">{meta.env_var}</code>
  );
}

const GROQ_WHISPER_MODELS: string[] = [
  'whisper-large-v3-turbo',
  'whisper-large-v3',
  'distil-whisper-large-v3-en',
];

const REMOTE_WHISPER_MODELS: string[] = [
  'whisper-1',
];

const LOCAL_WHISPER_MODELS: string[] = [
  'turbo',
  'large-v3',
  'large-v2',
  'large',
  'medium.en',
  'medium',
  'small.en',
  'small',
  'base.en',
  'base',
  'tiny.en',
  'tiny',
];

const FALLBACK_LLM_MODELS: string[] = [
  'groq/openai/gpt-oss-120b',
  'groq/llama-3.3-70b-versatile',
  'groq/deepseek-r1-distill-llama-70b',
  'groq/qwen-qwq-32b',
  'groq/llama-4-scout-17b-16e-instruct',
  'xai/grok-3',
  'xai/grok-3-mini',
  'gpt-4o',
  'gpt-4o-mini',
  'anthropic/claude-3-7-sonnet-latest',
  'gemini/gemini-2.0-flash',
];

function LlmModelDatalist({ models }: { models: Array<{ value: string }> }) {
  const allValues = new Set<string>([
    ...FALLBACK_LLM_MODELS,
    ...models.map((m) => m.value),
  ]);
  return (
    <datalist id="llm-model-datalist">
      {Array.from(allValues).map((m) => (
        <option key={m} value={m} />
      ))}
    </datalist>
  );
}
