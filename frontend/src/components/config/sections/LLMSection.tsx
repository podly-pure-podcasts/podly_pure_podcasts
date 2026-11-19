import { toast } from 'react-hot-toast';
import { configApi } from '../../../services/api';
import { useConfigContext } from '../ConfigContext';
import { Section, Field, ToggleField, SaveButton, TestButton } from '../shared';
import type { LLMConfig } from '../../../types';

const LLM_MODEL_ALIASES: string[] = [
  'openai/gpt-4',
  'openai/gpt-4o',
  'anthropic/claude-3.5-sonnet',
  'anthropic/claude-3.5-haiku',
  'gemini/gemini-3-flash-preview',
  'gemini/gemini-2.0-flash',
  'gemini/gemini-1.5-pro',
  'gemini/gemini-1.5-flash',
  'groq/openai/gpt-oss-120b',
];

const numberOrNull = (value: string) => (value === '' ? null : Number(value));

export default function LLMSection() {
  const { pending, setField, getEnvHint, isFieldReadOnly, handleSave, isSaving } = useConfigContext();

  if (!pending) return null;

  const apiKeyReadOnly = isFieldReadOnly('llm.llm_api_key');
  const baseUrlReadOnly = isFieldReadOnly('llm.openai_base_url');
  const modelReadOnly = isFieldReadOnly('llm.llm_model');
  const timeoutReadOnly = isFieldReadOnly('llm.openai_timeout');
  const maxTokensReadOnly = isFieldReadOnly('llm.openai_max_tokens');
  const maxConcurrentReadOnly = isFieldReadOnly('llm.llm_max_concurrent_calls');
  const maxRetriesReadOnly = isFieldReadOnly('llm.llm_max_retry_attempts');
  const tokenRateLimitReadOnly = isFieldReadOnly('llm.llm_enable_token_rate_limiting');
  const maxInputPerCallReadOnly = isFieldReadOnly('llm.llm_max_input_tokens_per_call');
  const maxInputPerMinReadOnly = isFieldReadOnly('llm.llm_max_input_tokens_per_minute');
  const serviceTierReadOnly = isFieldReadOnly('llm.llm_service_tier');

  const handleTestLLM = () => {
    toast.promise(configApi.testLLM({ llm: pending.llm as LLMConfig }), {
      loading: 'Testing connection…',
      success: (res: { ok: boolean; message?: string }) => res?.message || 'LLM connection OK',
      error: (err: unknown) => {
        const e = err as {
          response?: { data?: { error?: string; message?: string } };
          message?: string;
        };
        return (
          e?.response?.data?.error ||
          e?.response?.data?.message ||
          e?.message ||
          'LLM connection failed'
        );
      },
    });
  };

  return (
    <div className="space-y-6">
      <Section title="Connection">
        <Field label="Model" envMeta={getEnvHint('llm.llm_model')}>
          <input
            list="llm-model-datalist"
            className="input"
            type="text"
            value={pending?.llm?.llm_model ?? ''}
            onChange={(e) => setField(['llm', 'llm_model'], e.target.value)}
            placeholder="e.g. groq/openai/gpt-oss-120b"
            disabled={modelReadOnly}
          />
        </Field>
        <Field label="API key" envMeta={getEnvHint('llm.llm_api_key')}>
          <input
            className="input"
            type="text"
            placeholder={pending?.llm?.llm_api_key_preview || ''}
            value={pending?.llm?.llm_api_key || ''}
            onChange={(e) => setField(['llm', 'llm_api_key'], e.target.value)}
            disabled={apiKeyReadOnly}
          />
        </Field>
        <Field
          label="Base URL"
          envMeta={getEnvHint('llm.openai_base_url')}
          hint="Only used for models without a provider prefix, such as gpt-4o, or a self-hosted OpenAI-compatible server. Leave blank for Groq, Anthropic and Gemini models."
        >
          <input
            className="input"
            type="text"
            placeholder="https://api.openai.com/v1"
            value={pending?.llm?.openai_base_url || ''}
            onChange={(e) => setField(['llm', 'openai_base_url'], e.target.value)}
            disabled={baseUrlReadOnly}
          />
        </Field>
        <Field
          label="Service tier"
          hint="Forwarded to providers that support it (OpenAI, Gemini). Flex is about 50% cheaper but may return 429/503 under load; those calls retry with exponential backoff, then fall back to the standard tier."
          envMeta={getEnvHint('llm.llm_service_tier')}
        >
          <select
            className="input"
            value={pending?.llm?.llm_service_tier ?? 'default'}
            onChange={(e) => setField(['llm', 'llm_service_tier'], e.target.value)}
            disabled={serviceTierReadOnly}
          >
            <option value="default">default</option>
            <option value="flex">flex (cheaper, slower, may 429/503)</option>
            <option value="priority">priority (faster, pricier)</option>
            <option value="auto">auto</option>
          </select>
        </Field>
        <TestButton onClick={handleTestLLM} label="Test connection" />
      </Section>

      <Section title="Ad detection">
        <div className="space-y-4">
          <ToggleField
            label="Refine ad boundaries"
            hint="Uses extra LLM calls to tighten where each ad starts and ends."
            checked={pending?.llm?.enable_boundary_refinement ?? true}
            onChange={(checked) => setField(['llm', 'enable_boundary_refinement'], checked)}
          />
          <ToggleField
            label="Refine boundaries at word level"
            hint="Uses a word-position heuristic to estimate where an ad starts within a transcript segment."
            checked={!!pending?.llm?.enable_word_level_boundary_refinder}
            onChange={(checked) => setField(['llm', 'enable_word_level_boundary_refinder'], checked)}
          />
        </div>
      </Section>

      <Section title="Chapters">
        <div className="space-y-4">
          <ToggleField
            label="Tag chapters with the LLM"
            hint="Keeps embedded chapters when present; otherwise builds chapters from the description or transcript."
            checked={!!pending?.llm?.enable_llm_chapter_fallback_tagging}
            onChange={(checked) => setField(['llm', 'enable_llm_chapter_fallback_tagging'], checked)}
          />
        </div>
      </Section>

      <Section title="Limits and cost" collapsible>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Timeout (seconds)" envMeta={getEnvHint('llm.openai_timeout')}>
            <input
              className="input"
              type="number"
              value={pending?.llm?.openai_timeout ?? 300}
              onChange={(e) => setField(['llm', 'openai_timeout'], Number(e.target.value))}
              disabled={timeoutReadOnly}
            />
          </Field>
          <Field label="Max output tokens" envMeta={getEnvHint('llm.openai_max_tokens')}>
            <input
              className="input"
              type="number"
              value={pending?.llm?.openai_max_tokens ?? 4096}
              onChange={(e) => setField(['llm', 'openai_max_tokens'], Number(e.target.value))}
              disabled={maxTokensReadOnly}
            />
          </Field>
          <Field label="Max concurrent calls" envMeta={getEnvHint('llm.llm_max_concurrent_calls')}>
            <input
              className="input"
              type="number"
              value={pending?.llm?.llm_max_concurrent_calls ?? 3}
              onChange={(e) => setField(['llm', 'llm_max_concurrent_calls'], Number(e.target.value))}
              disabled={maxConcurrentReadOnly}
            />
          </Field>
          <Field label="Max retry attempts" envMeta={getEnvHint('llm.llm_max_retry_attempts')}>
            <input
              className="input"
              type="number"
              value={pending?.llm?.llm_max_retry_attempts ?? 5}
              onChange={(e) => setField(['llm', 'llm_max_retry_attempts'], Number(e.target.value))}
              disabled={maxRetriesReadOnly}
            />
          </Field>
        </div>
        <ToggleField
          label="Limit tokens per minute"
          hint="Throttles requests on this server to stay under provider rate limits."
          envMeta={getEnvHint('llm.llm_enable_token_rate_limiting')}
          checked={!!pending?.llm?.llm_enable_token_rate_limiting}
          onChange={(checked) => setField(['llm', 'llm_enable_token_rate_limiting'], checked)}
          disabled={tokenRateLimitReadOnly}
        />
        <div className="grid gap-5 sm:grid-cols-2">
          <Field
            label="Max input tokens per call (optional)"
            hint="Leave blank for no limit."
            envMeta={getEnvHint('llm.llm_max_input_tokens_per_call')}
          >
            <input
              className="input"
              type="number"
              value={pending?.llm?.llm_max_input_tokens_per_call ?? ''}
              onChange={(e) =>
                setField(['llm', 'llm_max_input_tokens_per_call'], numberOrNull(e.target.value))
              }
              disabled={maxInputPerCallReadOnly}
            />
          </Field>
          <Field
            label="Max input tokens per minute (optional)"
            hint="Used when token limiting is on. Leave blank to use the model's default limit."
            envMeta={getEnvHint('llm.llm_max_input_tokens_per_minute')}
          >
            <input
              className="input"
              type="number"
              value={pending?.llm?.llm_max_input_tokens_per_minute ?? ''}
              onChange={(e) =>
                setField(['llm', 'llm_max_input_tokens_per_minute'], numberOrNull(e.target.value))
              }
              disabled={maxInputPerMinReadOnly}
            />
          </Field>
        </div>
      </Section>

      <SaveButton onSave={handleSave} isPending={isSaving} />

      <datalist id="llm-model-datalist">
        {LLM_MODEL_ALIASES.map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>
    </div>
  );
}
