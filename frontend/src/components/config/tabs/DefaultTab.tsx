import { useState } from 'react';
import { useConfigContext } from '../ConfigContext';
import { Section, Field, ConnectionStatusCard } from '../shared';
import type { WhisperConfig, LLMConfig } from '../../../types';

export default function DefaultTab() {
  const {
    pending,
    updatePending,
    llmStatus,
    whisperStatus,
    probeConnections,
    getEnvHint,
    getWhisperApiKey,
    groqRecommendedModel,
    groqRecommendedWhisper,
    applyGroqKey,
  } = useConfigContext();

  const [showGroqHelp, setShowGroqHelp] = useState(false);
  const [showGroqPricing, setShowGroqPricing] = useState(false);

  if (!pending) return null;

  const handleGroqKeyChange = (val: string) => {
    updatePending((prevConfig) => {
      return {
        ...prevConfig,
        llm: {
          ...(prevConfig.llm as LLMConfig),
          llm_api_key: val,
          llm_model: groqRecommendedModel,
        },
        whisper: {
          whisper_type: 'groq',
          api_key: val,
          model: groqRecommendedWhisper,
          language: 'en',
          max_retries: 3,
        } as WhisperConfig,
      };
    });
  };

  const handleGroqKeyApply = (key: string) => {
    if (!key.trim()) return;
    void applyGroqKey(key.trim());
  };

  const currentGroqKey =
    pending?.whisper?.whisper_type === 'groq'
      ? getWhisperApiKey(pending?.whisper)
      : pending?.llm?.llm_api_key || '';

  const groqKeyPlaceholder =
    pending?.whisper?.whisper_type === 'groq'
      ? pending?.whisper?.api_key_preview || ''
      : pending?.llm?.llm_api_key_preview || '';

  return (
    <div className="space-y-6">
      <Section title="Connection status">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <ConnectionStatusCard
            title="LLM"
            status={llmStatus.status}
            message={llmStatus.message}
            error={llmStatus.error}
            onRetry={() => void probeConnections()}
          />
          <ConnectionStatusCard
            title="Transcription"
            status={whisperStatus.status}
            message={whisperStatus.message}
            error={whisperStatus.error}
            onRetry={() => void probeConnections()}
          />
        </div>
      </Section>

      <Section
        title="Quick setup"
        description="One Groq API key sets up both transcription and ad detection."
      >
        <Field label="Groq API key" envMeta={getEnvHint('groq.api_key')}>
          <input
            className="input"
            type="text"
            placeholder={groqKeyPlaceholder}
            value={currentGroqKey}
            onChange={(e) => handleGroqKeyChange(e.target.value)}
            onBlur={(e) => handleGroqKeyApply(e.target.value)}
            onPaste={(e) => {
              const text = e.clipboardData.getData('text').trim();
              if (text) handleGroqKeyApply(text);
            }}
          />
        </Field>

        <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <button
            type="button"
            className="text-blue-700 hover:text-blue-800 hover:underline"
            onClick={() => setShowGroqHelp((v) => !v)}
            aria-expanded={showGroqHelp}
          >
            {showGroqHelp ? 'Hide key instructions' : 'How to get a key'}
          </button>
          <button
            type="button"
            className="text-blue-700 hover:text-blue-800 hover:underline"
            onClick={() => setShowGroqPricing((v) => !v)}
            aria-expanded={showGroqPricing}
          >
            {showGroqPricing ? 'Hide pricing' : 'Pricing estimate'}
          </button>
        </div>

        {showGroqHelp && <GroqHelpBox />}
        {showGroqPricing && <GroqPricingBox />}
      </Section>
    </div>
  );
}

function GroqHelpBox() {
  return (
    <ol className="list-decimal space-y-1 pl-5 text-sm text-gray-700">
      <li>
        Sign in to the{' '}
        <a
          className="text-blue-700 underline hover:text-blue-800"
          href="https://console.groq.com/keys"
          target="_blank"
          rel="noreferrer"
        >
          Groq Console
        </a>{' '}
        (or create an account) and click &ldquo;Create API Key&rdquo;.
      </li>
      <li>
        Copy the key (it starts with <code>gsk_</code>) and paste it above.
      </li>
      <li>
        Recommended: set a limit under{' '}
        <a
          className="text-blue-700 underline hover:text-blue-800"
          href="https://console.groq.com/settings/billing"
          target="_blank"
          rel="noreferrer"
        >
          Settings → Billing → Limits
        </a>{' '}
        to control costs and get usage alerts.
      </li>
    </ol>
  );
}

function GroqPricingBox() {
  return (
    <div className="space-y-2 text-sm text-gray-700">
      <p>
        Prices for the recommended models, <code>whisper-large-v3-turbo</code> and{' '}
        <code>llama-3.3-70b-versatile</code>:
      </p>
      <ul className="list-disc space-y-1 pl-5">
        <li>
          Transcription: $0.04 per hour of audio, 216x real-time, 10-second minimum per
          request.
        </li>
        <li>
          Ad detection: $0.59 per 1M input tokens and $0.79 per 1M output tokens (1M tokens
          is about 750,000 words).
        </li>
      </ul>
      <p>
        Example, 6 podcasts at 6 hours per week: 24 hours/month of transcription is about
        $0.96, and about 2M tokens of ad detection is about $1.38, for roughly{' '}
        <strong>$2.34 per month</strong>. Actual cost varies with episode length and token
        use; a $5-10 monthly billing limit is a safe cap.
      </p>
    </div>
  );
}
