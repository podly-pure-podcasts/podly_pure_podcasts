import { useState } from 'react';
import { useConfigContext } from '../ConfigContext';
import { Section, Field, ConnectionStatusCard } from '../shared';
import type { LLMConfig, WhisperConfig } from '../../../types';

const GEMINI_MODELS = [
  'gemini/gemini-2.5-flash-lite',
  'gemini/gemini-3.1-flash-lite',
];

export default function DefaultTab() {
  const {
    pending,
    updatePending,
    llmStatus,
    whisperStatus,
    probeConnections,
    getEnvHint,
    applyGeminiKey,
    geminiRecommendedModel,
  } = useConfigContext();

  const [showHelp, setShowHelp] = useState(false);

  if (!pending) return null;

  const currentApiKey = pending?.llm?.llm_api_key || '';
  const currentModel = pending?.llm?.llm_model || geminiRecommendedModel;

  const handleKeyChange = (val: string) => {
    updatePending((prevConfig) => ({
      ...prevConfig,
      llm: {
        ...(prevConfig.llm as LLMConfig),
          llm_api_key: val,
      },
      whisper: {
        ...(prevConfig.whisper as WhisperConfig),
        whisper_type: 'google',
        api_key: val,
        model:
          ((prevConfig.llm as LLMConfig).llm_model || geminiRecommendedModel).replace(
            'gemini/',
            ''
          ),
        language: 'sv-SE',
        timeout_sec: 600,
        chunksize_mb: 6,
      } as WhisperConfig,
    }));
  };

  const handleKeyApply = (key: string) => {
    if (!key.trim()) return;
    void applyGeminiKey(key.trim());
  };

  return (
    <div className="space-y-6">
      <Section title="Connection Status">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <ConnectionStatusCard
            title="LLM"
            status={llmStatus.status}
            message={llmStatus.message}
            error={llmStatus.error}
            onRetry={() => void probeConnections()}
          />
          <ConnectionStatusCard
            title="Whisper"
            status={whisperStatus.status}
            message={whisperStatus.message}
            error={whisperStatus.error}
            onRetry={() => void probeConnections()}
          />
        </div>
      </Section>

      <Section title="Quick Setup">
        <div className="text-sm text-gray-700 mb-2 flex items-center gap-2 flex-wrap">
          <span>Enter your own Gemini API key for transcription and ad detection.</span>
          <button
            type="button"
            className="text-indigo-600 hover:underline"
            onClick={() => setShowHelp((v) => !v)}
          >
            {showHelp ? 'Hide help' : '(what key do I use?)'}
          </button>
        </div>

        {showHelp && <GeminiHelpBox />}

        <Field
          label="Gemini API Key"
          envMeta={getEnvHint('llm.llm_api_key', { env_var: 'GEMINI_API_KEY' })}
        >
          <input
            className="input"
            type="text"
            placeholder="AIza..."
            value={currentApiKey}
            onChange={(e) => handleKeyChange(e.target.value)}
            onBlur={(e) => handleKeyApply(e.target.value)}
            onPaste={(e) => {
              const text = e.clipboardData.getData('text').trim();
              if (text) handleKeyApply(text);
            }}
          />
        </Field>

        <Field label="Gemini Model" envMeta={getEnvHint('llm.llm_model')}>
          <select
            className="input"
            value={currentModel}
            onChange={(e) => updatePending((prev) => ({
              ...prev,
              llm: {
                ...(prev.llm as LLMConfig),
                llm_model: e.target.value,
              },
              whisper: {
                ...(prev.whisper as WhisperConfig),
                whisper_type: 'google',
                model: e.target.value.replace('gemini/', ''),
                language: 'sv-SE',
                timeout_sec: 600,
                chunksize_mb: 6,
              },
            }))}
          >
            {GEMINI_MODELS.map((model) => (
              <option key={model} value={model}>
                {model.replace('gemini/', '')}
              </option>
            ))}
          </select>
        </Field>
      </Section>

      <style>{`.input{width:100%;padding:0.5rem;border:1px solid #e5e7eb;border-radius:0.375rem;font-size:0.875rem}`}</style>
    </div>
  );
}

function GeminiHelpBox() {
  return (
    <div className="text-sm text-gray-700 mb-2 bg-indigo-50 border border-indigo-200 rounded p-3 space-y-2">
      <ol className="list-decimal pl-5 space-y-1">
        <li>
          Create a key in the{' '}
          <a
            className="text-indigo-700 underline"
            href="https://aistudio.google.com/app/apikey"
            target="_blank"
            rel="noreferrer"
          >
            Google AI Studio API key page
          </a>
          .
        </li>
        <li>Paste the key here.</li>
        <li>Pick the cheaper 2.5 model or the newer 3.1 model.</li>
        <li>The same key is used for Swedish audio transcription and ad detection.</li>
      </ol>
    </div>
  );
}
