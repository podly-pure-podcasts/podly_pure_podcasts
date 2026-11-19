import { useConfigContext, ADVANCED_SUBTABS } from '../ConfigContext';
import {
  LLMSection,
  WhisperSection,
  ProcessingSection,
  OutputSection,
  AppSection,
} from '../sections';

export default function AdvancedTab() {
  const { activeSubtab, setActiveSubtab } = useConfigContext();

  return (
    <div className="space-y-6 lg:space-y-0">
      {/* From `lg` these subtabs live in the settings sidebar instead. */}
      <div className="flex flex-wrap gap-2 lg:hidden" role="tablist" aria-label="Advanced settings">
        {ADVANCED_SUBTABS.map((subtab) => {
          const selected = activeSubtab === subtab.id;
          return (
            <button
              key={subtab.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => setActiveSubtab(subtab.id)}
              className={`btn btn-sm ${
                selected ? 'bg-gray-100 text-gray-900' : 'btn-ghost text-gray-600'
              }`}
            >
              {subtab.label}
            </button>
          );
        })}
      </div>

      <div>
        {activeSubtab === 'llm' && <LLMSection />}
        {activeSubtab === 'whisper' && <WhisperSection />}
        {activeSubtab === 'processing' && <ProcessingSection />}
        {activeSubtab === 'output' && <OutputSection />}
        {activeSubtab === 'app' && <AppSection />}
      </div>
    </div>
  );
}
