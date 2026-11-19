import type { ReactNode } from 'react';
import { CloseIcon } from '../icons';

export function StatsHeader({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex items-center justify-between p-6 border-b">
      <h2 className="text-xl font-bold text-gray-900 text-left">Processing statistics & debug</h2>
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="btn btn-ghost btn-icon"
      >
        <CloseIcon className="h-5 w-5" />
      </button>
    </div>
  );
}

export function StatsTabBarShell({ children }: { children: ReactNode }) {
  return (
    <div className="border-b overflow-x-auto [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
      {children}
    </div>
  );
}

export function StatsTabBarPlaceholder() {
  return (
    <div className="flex min-w-max space-x-8 px-6" aria-hidden="true">
      {[72, 112, 88, 104].map((width) => (
        <span key={width} className="block border-b-2 border-transparent px-1 py-4">
          <span className="block h-5 rounded-full bg-gray-100" style={{ width }} />
        </span>
      ))}
    </div>
  );
}

// Suspense fallback with the same chrome the stats bodies show while loading.
export default function StatsLoadingFrame({ onClose }: { onClose: () => void }) {
  return (
    <>
      <StatsHeader onClose={onClose} />
      <StatsTabBarShell>
        <StatsTabBarPlaceholder />
      </StatsTabBarShell>
      <div className="flex-1 min-h-0 overflow-y-auto p-6" />
    </>
  );
}
