import type { EnvOverrideEntry } from '../../../types';

interface EnvVarHintProps {
  meta?: EnvOverrideEntry;
}

export default function EnvVarHint({ meta }: EnvVarHintProps) {
  if (!meta?.env_var) {
    return null;
  }

  return (
    <div className="mt-1 flex items-center gap-1">
      <code className="text-xs text-gray-500 font-mono">{meta.env_var}</code>
      {meta.read_only && (
        <span className="text-xs text-amber-600 font-medium">(read-only)</span>
      )}
    </div>
  );
}
