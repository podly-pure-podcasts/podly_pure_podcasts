import { useConfigContext } from '../ConfigContext';
import { Section, Field, SaveButton } from '../shared';

export default function ProcessingSection() {
  const { pending, setField, handleSave, isSaving } = useConfigContext();

  if (!pending) return null;

  return (
    <div className="space-y-6">
      <Section title="Ad detection batching">
        <Field
          label="Transcript segments per LLM request"
          hint="More segments give the model more context per call but use more tokens per request; fewer make more, smaller calls."
        >
          <input
            className="input"
            type="number"
            value={pending?.processing?.num_segments_to_input_to_prompt ?? 30}
            onChange={(e) =>
              setField(['processing', 'num_segments_to_input_to_prompt'], Number(e.target.value))
            }
          />
        </Field>
      </Section>

      <SaveButton onSave={handleSave} isPending={isSaving} />
    </div>
  );
}
