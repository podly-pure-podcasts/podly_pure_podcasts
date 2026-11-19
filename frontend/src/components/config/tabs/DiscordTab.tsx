import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import { discordApi } from '../../../services/api';
import { Section, Field, ToggleField } from '../shared';

export default function DiscordTab() {
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['discord-config'],
    queryFn: discordApi.getConfig,
  });

  const [form, setForm] = useState({
    client_id: '',
    client_secret: '',
    redirect_uri: '',
    guild_ids: '',
    allow_registration: true,
  });

  const [hasSecretChange, setHasSecretChange] = useState(false);

  useEffect(() => {
    if (data?.config) {
      setForm({
        client_id: data.config.client_id || '',
        client_secret: '', // never prefilled
        redirect_uri: data.config.redirect_uri || '',
        guild_ids: data.config.guild_ids || '',
        allow_registration: data.config.allow_registration,
      });
      setHasSecretChange(false);
    }
  }, [data]);

  const mutation = useMutation({
    mutationFn: discordApi.updateConfig,
    onSuccess: () => {
      toast.success('Discord settings saved');
      queryClient.invalidateQueries({ queryKey: ['discord-config'] });
      queryClient.invalidateQueries({ queryKey: ['discord-status'] });
      setHasSecretChange(false);
    },
    onError: (err: Error) => {
      toast.error(
        `Could not save Discord settings: ${err.message}. Check the values and try again.`
      );
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const payload: Record<string, unknown> = {
      client_id: form.client_id,
      redirect_uri: form.redirect_uri,
      guild_ids: form.guild_ids,
      allow_registration: form.allow_registration,
    };

    // Only include secret if it was changed
    if (hasSecretChange && form.client_secret) {
      payload.client_secret = form.client_secret;
    }

    mutation.mutate(payload);
  };

  const envOverrides = data?.env_overrides || {};

  if (isLoading) {
    return <div className="text-sm text-gray-600">Loading Discord settings…</div>;
  }

  if (error) {
    return (
      <div className="text-sm text-red-600">
        Could not load Discord settings. Reload the page, or check the server log if it keeps
        failing.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Section title="Sign-in with Discord">
        <StatusIndicator enabled={data?.config.enabled ?? false} />

        <form onSubmit={handleSubmit} className="max-w-xl space-y-5">
          <Field label="Client ID" envMeta={envOverrides.client_id}>
            <input
              type="text"
              className="input"
              value={form.client_id}
              onChange={(e) => setForm({ ...form, client_id: e.target.value })}
              placeholder="Your Discord application Client ID"
              disabled={!!envOverrides.client_id}
            />
          </Field>

          <Field
            label="Client secret"
            hint={
              data?.config.client_secret_preview
                ? `Current secret: ${data.config.client_secret_preview}. Leave blank to keep it.`
                : undefined
            }
            envMeta={envOverrides.client_secret}
          >
            <input
              type="password"
              className="input"
              value={form.client_secret}
              onChange={(e) => {
                setForm({ ...form, client_secret: e.target.value });
                setHasSecretChange(true);
              }}
              placeholder={
                data?.config.client_secret_preview
                  ? '••••••••'
                  : 'Your Discord application Client Secret'
              }
              disabled={!!envOverrides.client_secret}
            />
          </Field>

          <Field
            label="Redirect URI"
            hint="Must match the redirect URI in the Discord Developer Portal."
            envMeta={envOverrides.redirect_uri}
          >
            <input
              type="url"
              className="input"
              value={form.redirect_uri}
              onChange={(e) => setForm({ ...form, redirect_uri: e.target.value })}
              placeholder="https://your-domain.com/api/auth/discord/callback"
              disabled={!!envOverrides.redirect_uri}
            />
          </Field>

          <Field
            label="Guild IDs (optional)"
            hint="Comma-separated Discord server IDs to restrict access to."
            envMeta={envOverrides.guild_ids}
          >
            <input
              type="text"
              className="input"
              value={form.guild_ids}
              onChange={(e) => setForm({ ...form, guild_ids: e.target.value })}
              placeholder="123456789,987654321"
              disabled={!!envOverrides.guild_ids}
            />
          </Field>

          <ToggleField
            label="Allow new users to register with Discord"
            checked={form.allow_registration}
            onChange={(checked) => setForm({ ...form, allow_registration: checked })}
            disabled={!!envOverrides.allow_registration}
            envMeta={envOverrides.allow_registration}
          />

          <div>
            <button type="submit" disabled={mutation.isPending} className="btn btn-primary">
              {mutation.isPending ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </form>
      </Section>

      <Section title="Setup steps">
        <SetupInstructions />
      </Section>
    </div>
  );
}

function StatusIndicator({ enabled }: { enabled: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className={`h-3 w-3 rounded-full ${enabled ? 'bg-green-500' : 'bg-gray-300'}`} />
      <span className="text-sm font-medium text-gray-900">
        {enabled ? 'Discord sign-in is enabled' : 'Discord sign-in is not configured'}
      </span>
    </div>
  );
}

function SetupInstructions() {
  return (
    <div className="space-y-3 text-sm text-gray-700">
      <ol className="list-decimal space-y-1.5 pl-5">
        <li>
          Open the{' '}
          <a
            href="https://discord.com/developers/applications"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-700 underline hover:text-blue-800"
          >
            Discord Developer Portal
          </a>{' '}
          and create an application, or pick an existing one.
        </li>
        <li>
          Go to <strong>OAuth2 → General</strong> and copy the <strong>Client ID</strong> and{' '}
          <strong>Client Secret</strong> into the form above.
        </li>
        <li>
          Add <code>https://your-domain/api/auth/discord/callback</code> (with your own
          domain) as a redirect, and enter the same URI above.
        </li>
      </ol>
      <p className="text-xs text-gray-600">
        Environment variables (DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET and so on) take
        precedence over values saved here.
      </p>
    </div>
  );
}
