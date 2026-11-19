import type { EnvOverrideEntry } from '../../../types';

interface EnvVarHintProps {
  meta?: EnvOverrideEntry;
}

/** Shown only when an environment variable controls the field, which also locks it. */
export default function EnvVarHint({ meta }: EnvVarHintProps) {
  if (!meta?.env_var) {
    return null;
  }

  return (
    <span className="mt-1 block text-xs text-amber-700">
      Set by <code className="font-mono">{meta.env_var}</code> in your environment.
    </span>
  );
}
