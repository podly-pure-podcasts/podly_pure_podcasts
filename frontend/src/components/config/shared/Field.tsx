import type { ReactNode } from 'react';
import type { EnvOverrideEntry } from '../../../types';
import EnvVarHint from './EnvVarHint';

interface FieldProps {
  label: string;
  children: ReactNode;
  envMeta?: EnvOverrideEntry;
  hint?: ReactNode;
}

/**
 * A labelled text, number or select control. Use ToggleField for checkboxes.
 * Fills its grid cell and pins the control to the bottom, so side-by-side fields
 * line up even when one hint wraps to more lines than its neighbour's.
 */
export default function Field({ label, children, envMeta, hint }: FieldProps) {
  return (
    <label className="flex h-full min-w-0 flex-col">
      <span className="block text-sm font-medium text-gray-800">{label}</span>
      {hint ? <span className="mt-0.5 block text-xs text-gray-600">{hint}</span> : null}
      <div className="mt-auto pt-1.5">{children}</div>
      <EnvVarHint meta={envMeta} />
    </label>
  );
}
