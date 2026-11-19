import { useConfigContext } from '../ConfigContext';
import { Section, Field, SaveButton } from '../shared';

export default function OutputSection() {
  const { pending, setField, handleSave, isSaving } = useConfigContext();

  if (!pending) return null;

  return (
    <div className="space-y-6">
      <Section title="Ad cuts">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field
            label="Min confidence"
            hint="Only ads the LLM rates at or above this confidence are cut. Higher keeps more borderline audio."
          >
            <input
              className="input"
              type="number"
              step="0.01"
              value={pending?.output?.min_confidence ?? 0.8}
              onChange={(e) => setField(['output', 'min_confidence'], Number(e.target.value))}
            />
          </Field>
          <Field
            label="Fade (milliseconds)"
            hint="Length of the fade at each cut. Each cut keeps this much ad audio at its edges, faded out and in."
          >
            <input
              className="input"
              type="number"
              value={pending?.output?.fade_ms ?? 3000}
              onChange={(e) => setField(['output', 'fade_ms'], Number(e.target.value))}
            />
          </Field>
          <Field
            label="Min ad length (seconds)"
            hint="Detected ads shorter than this are left in the episode."
          >
            <input
              className="input"
              type="number"
              value={pending?.output?.min_ad_segment_length_seconds ?? 14}
              onChange={(e) =>
                setField(['output', 'min_ad_segment_length_seconds'], Number(e.target.value))
              }
            />
          </Field>
          <Field
            label="Min gap between ads (seconds)"
            hint="Ads closer together than this are merged into one cut, removing the content between them."
          >
            <input
              className="input"
              type="number"
              value={pending?.output?.min_ad_segement_separation_seconds ?? 60}
              onChange={(e) =>
                setField(['output', 'min_ad_segement_separation_seconds'], Number(e.target.value))
              }
            />
          </Field>
        </div>
      </Section>

      <SaveButton onSave={handleSave} isPending={isSaving} />
    </div>
  );
}
