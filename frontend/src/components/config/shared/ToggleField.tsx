import type { ReactNode } from 'react';
import type { EnvOverrideEntry } from '../../../types';
import EnvVarHint from './EnvVarHint';

interface ToggleFieldProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  hint?: ReactNode;
  disabled?: boolean;
  envMeta?: EnvOverrideEntry;
}

/** An on/off setting: label and hint on the left, checkbox on the right. The whole row is the tap target. */
export default function ToggleField({
  label,
  checked,
  onChange,
  hint,
  disabled = false,
  envMeta,
}: ToggleFieldProps) {
  return (
    <label
      className={`flex items-start justify-between gap-4 ${
        disabled ? 'cursor-not-allowed' : 'cursor-pointer'
      }`}
    >
      <span className="min-w-0">
        <span className="block text-sm font-medium text-gray-800">{label}</span>
        {hint ? <span className="mt-0.5 block text-xs text-gray-600">{hint}</span> : null}
        <EnvVarHint meta={envMeta} />
      </span>
      <input
        type="checkbox"
        className="mt-0.5 h-4 w-4 shrink-0 cursor-[inherit] accent-blue-600"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
      />
    </label>
  );
}
