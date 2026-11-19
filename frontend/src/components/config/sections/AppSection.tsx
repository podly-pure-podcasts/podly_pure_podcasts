import { useConfigContext } from '../ConfigContext';
import { Section, Field, ToggleField, SaveButton } from '../shared';

const numberOrNull = (value: string) => (value === '' ? null : Number(value));

export default function AppSection() {
  const { pending, setField, handleSave, isSaving } = useConfigContext();

  if (!pending) return null;

  return (
    <div className="space-y-6">
      <Section title="Feeds and episodes">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field
            label="Background refresh interval (minutes)"
            hint="How often feeds are checked for new episodes."
          >
            <input
              className="input"
              type="number"
              value={pending?.app?.background_update_interval_minute ?? ''}
              onChange={(e) =>
                setField(['app', 'background_update_interval_minute'], numberOrNull(e.target.value))
              }
            />
          </Field>
          <Field
            label="Episodes to enable on new feeds"
            hint="How many archive episodes are enabled when a feed is added."
          >
            <input
              className="input"
              type="number"
              value={pending?.app?.number_of_episodes_to_whitelist_from_archive_of_new_feed ?? 1}
              onChange={(e) =>
                setField(
                  ['app', 'number_of_episodes_to_whitelist_from_archive_of_new_feed'],
                  Number(e.target.value)
                )
              }
            />
          </Field>
        </div>

        <div className="space-y-4">
          <ToggleField
            label="Auto-enable new episodes"
            hint="Newly published episodes are enabled and processed automatically."
            checked={!!pending?.app?.automatically_whitelist_new_episodes}
            onChange={(checked) =>
              setField(['app', 'automatically_whitelist_new_episodes'], checked)
            }
          />
          <ToggleField
            label="Process on first download"
            hint="Lists every episode in the RSS feed; one that is not enabled is queued for processing when a podcast app first downloads it."
            checked={!!pending?.app?.autoprocess_on_download}
            onChange={(checked) => setField(['app', 'autoprocess_on_download'], checked)}
          />
        </div>

        <Field
          label="Retention (days)"
          hint="Processed episodes older than this lose their audio files and are disabled; each feed's newest episode is always kept. Leave blank to keep everything."
        >
          <input
            className="input"
            type="number"
            min={0}
            value={pending?.app?.post_cleanup_retention_days ?? ''}
            onChange={(e) =>
              setField(['app', 'post_cleanup_retention_days'], numberOrNull(e.target.value))
            }
          />
        </Field>
      </Section>

      <Section title="Cost estimates" description="Used by the Costs tab to estimate spend.">
        <Field label="Legacy processing rate ($ per hour)">
          <input
            className="input"
            type="number"
            step="0.01"
            min="0"
            value={pending?.app?.cost_rate_per_hour ?? 0.04}
            onChange={(e) => setField(['app', 'cost_rate_per_hour'], Number(e.target.value))}
          />
        </Field>
        <Field label="Whisper rate ($ per hour)">
          <input
            className="input"
            type="number"
            step="0.01"
            min="0"
            value={pending?.app?.whisper_cost_rate_per_hour ?? 0.04}
            onChange={(e) =>
              setField(['app', 'whisper_cost_rate_per_hour'], Number(e.target.value))
            }
          />
        </Field>
      </Section>

      <Section title="Public site">
        <ToggleField
          label="Show the public landing page"
          checked={!!pending?.app?.enable_public_landing_page}
          onChange={(checked) => setField(['app', 'enable_public_landing_page'], checked)}
        />
      </Section>

      <SaveButton onSave={handleSave} isPending={isSaving} />
    </div>
  );
}
