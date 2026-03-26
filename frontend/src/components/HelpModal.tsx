import { useState } from 'react';
import { createPortal } from 'react-dom';
import { useEscapeKey } from '../hooks/useEscapeKey';

interface HelpModalProps {
  isOpen: boolean;
  onClose: () => void;
  onReplayTutorial?: () => void;
}

type TabId = 'getting-started' | 'processing' | 'subscribing' | 'presets' | 'tips';

interface Tab {
  id: TabId;
  label: string;
  icon: React.ReactNode;
}

const tabs: Tab[] = [
  {
    id: 'getting-started',
    label: 'Getting Started',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
  },
  {
    id: 'processing',
    label: 'Processing',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    ),
  },
  {
    id: 'subscribing',
    label: 'Podcast Apps',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
      </svg>
    ),
  },
  {
    id: 'presets',
    label: 'Ad Detection',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
      </svg>
    ),
  },
  {
    id: 'tips',
    label: 'Tips',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
      </svg>
    ),
  },
];

export default function HelpModal({ isOpen, onClose, onReplayTutorial }: HelpModalProps) {
  const [activeTab, setActiveTab] = useState<TabId>('getting-started');
  useEscapeKey(isOpen, onClose);

  if (!isOpen) return null;

  const renderContent = () => {
    switch (activeTab) {
      case 'getting-started':
        return (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-purple-900 dark:text-purple-100">Welcome to Podly!</h3>
            <p className="text-gray-600 dark:text-gray-300">
              Podly automatically removes ads from your favorite podcasts using AI.
            </p>
            
            <div className="space-y-3">
              <div className="flex gap-3 p-3 bg-purple-50 dark:bg-purple-900/30 rounded-lg">
                <div className="flex-shrink-0 w-8 h-8 bg-purple-500 text-white rounded-full flex items-center justify-center font-bold">1</div>
                <div>
                  <p className="font-medium text-purple-900 dark:text-purple-100">Add a Podcast</p>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Click "Add Podcast" and search by name, or paste an RSS feed URL</p>
                </div>
              </div>
              
              <div className="flex gap-3 p-3 bg-purple-50 dark:bg-purple-900/30 rounded-lg">
                <div className="flex-shrink-0 w-8 h-8 bg-purple-500 text-white rounded-full flex items-center justify-center font-bold">2</div>
                <div>
                <p className="font-medium text-purple-900 dark:text-purple-100">Process Episodes</p>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Start processing from the web UI ("Process") or from your podcast app using the trigger link at the bottom of each episode's notes/description</p>
                </div>
              </div>
              
              <div className="flex gap-3 p-3 bg-purple-50 dark:bg-purple-900/30 rounded-lg">
                <div className="flex-shrink-0 w-8 h-8 bg-purple-500 text-white rounded-full flex items-center justify-center font-bold">3</div>
                <div>
                  <p className="font-medium text-purple-900 dark:text-purple-100">Subscribe in Your App</p>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Copy the Podly RSS URL to your podcast app</p>
                </div>
              </div>
            </div>

            <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-700 rounded-lg">
              <p className="text-sm text-green-800 dark:text-green-200">
                <strong>Tip:</strong> Use the built-in search to find podcasts by name — no need to hunt for RSS feeds!
              </p>
            </div>
          </div>
        );

      case 'processing':
        return (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-purple-900 dark:text-purple-100">Episode Processing</h3>
            
            <div className="space-y-3">
              <h4 className="font-medium text-purple-800 dark:text-purple-200">Episode States</h4>
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">Enabled</span>
                  <span className="text-sm text-gray-600 dark:text-gray-300">Ready to be processed</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 bg-gray-100 text-gray-500 text-xs rounded-full border border-dashed border-gray-400">Disabled</span>
                  <span className="text-sm text-gray-600 dark:text-gray-300">Skipped, won't appear in RSS</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full">Ready</span>
                  <span className="text-sm text-gray-600 dark:text-gray-300">Processed and ready to play</span>
                </div>
              </div>
            </div>

            <div className="space-y-3">
              <h4 className="font-medium text-purple-800 dark:text-purple-200">How to Process</h4>
              <div className="space-y-2 text-sm text-gray-600 dark:text-gray-300">
                <p><strong>Manual:</strong> Click the purple "Process" button on any enabled episode</p>
                <p><strong>On-Demand:</strong> In your podcast app, open an episode and tap "Process this episode (remove ads)" at the bottom of the episode notes/description</p>
                <p><strong>After processing:</strong> When the trigger page shows "Episode Ready", close the tab and refresh your podcast app feed</p>
              </div>
            </div>

            <div className="space-y-3">
              <h4 className="font-medium text-purple-800 dark:text-purple-200">Reprocessing</h4>
              <p className="text-sm text-gray-600 dark:text-gray-300">
                Click the orange "Reprocess" button to re-run ad detection with different settings.
              </p>
            </div>

            <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-lg">
              <p className="text-sm text-blue-800 dark:text-blue-200">
                Processing typically takes 2-5 minutes depending on episode length.
              </p>
            </div>
          </div>
        );

      case 'subscribing':
        return (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-purple-900 dark:text-purple-100">Subscribe in Your Podcast App</h3>
            
            <div className="space-y-3">
              <h4 className="font-medium text-purple-800 dark:text-purple-200">Get Your RSS URL</h4>
              <ol className="list-decimal list-inside space-y-1 text-sm text-gray-600 dark:text-gray-300">
                <li>Go to any podcast in Podly</li>
                <li>Click "Subscribe to Podly RSS"</li>
                <li>Copy the URL</li>
              </ol>
            </div>

            <div className="space-y-3">
              <h4 className="font-medium text-purple-800 dark:text-purple-200">Add to Your App</h4>
              <div className="space-y-2 text-sm">
                <div className="p-2 bg-gray-50 dark:bg-gray-800 rounded">
                  <p className="font-medium text-gray-900 dark:text-gray-100">Apple Podcasts</p>
                  <p className="text-gray-600 dark:text-gray-400">File → Add a Show by URL</p>
                </div>
                <div className="p-2 bg-gray-50 dark:bg-gray-800 rounded">
                  <p className="font-medium text-gray-900 dark:text-gray-100">Overcast</p>
                  <p className="text-gray-600 dark:text-gray-400">Tap + → Add URL</p>
                </div>
                <div className="p-2 bg-gray-50 dark:bg-gray-800 rounded">
                  <p className="font-medium text-gray-900 dark:text-gray-100">Pocket Casts</p>
                  <p className="text-gray-600 dark:text-gray-400">Search → "Add by URL"</p>
                </div>
                <div className="p-2 bg-gray-50 dark:bg-gray-800 rounded">
                  <p className="font-medium text-gray-900 dark:text-gray-100">Other Apps</p>
                  <p className="text-gray-600 dark:text-gray-400">Look for "Add by URL" or "Add RSS feed"</p>
                </div>
              </div>
            </div>

            <div className="p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg">
              <p className="text-sm text-amber-800 dark:text-amber-200">
                <strong>Note:</strong> With auth enabled, the Podly RSS URL includes your feed token. Don't share it publicly.
              </p>
            </div>
            <div className="p-3 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg">
              <p className="text-sm text-gray-700 dark:text-gray-300">
                <strong>Auth mode:</strong> Tokenized podcast-app trigger/download links work best with <code>REQUIRE_AUTH=true</code>.
              </p>
            </div>
          </div>
        );

      case 'presets':
        return (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-purple-900 dark:text-purple-100">Ad Detection Presets</h3>
            <p className="text-gray-600 dark:text-gray-300">
              Presets control how aggressively Podly removes ads.
            </p>

            <div className="space-y-3">
              <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-700 rounded-lg">
                <p className="font-medium text-green-800 dark:text-green-200">Conservative</p>
                <p className="text-sm text-green-700 dark:text-green-300">Only obvious ads — sponsor reads, "brought to you by"</p>
              </div>
              
              <div className="p-3 bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-700 rounded-lg">
                <p className="font-medium text-purple-800 dark:text-purple-200">Balanced (Default)</p>
                <p className="text-sm text-purple-700 dark:text-purple-300">Typical podcast ads while preserving content</p>
              </div>
              
              <div className="p-3 bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-700 rounded-lg">
                <p className="font-medium text-orange-800 dark:text-orange-200">Aggressive</p>
                <p className="text-sm text-orange-700 dark:text-orange-300">All promotional content including self-promotion</p>
              </div>
            </div>

            <div className="space-y-2">
              <h4 className="font-medium text-purple-800 dark:text-purple-200">Changing Presets</h4>
              <p className="text-sm text-gray-600 dark:text-gray-300">
                Go to <strong>Settings → Ad Detection</strong> to change your preset. New episodes will use the selected preset.
              </p>
              <p className="text-sm text-gray-600 dark:text-gray-300">
                Already-processed episodes keep their original preset. Use <strong>Reprocess</strong> to apply a new preset.
              </p>
            </div>
          </div>
        );

      case 'tips':
        return (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-purple-900 dark:text-purple-100">Tips & Troubleshooting</h3>

            <div className="space-y-3">
              <h4 className="font-medium text-purple-800 dark:text-purple-200">Finding Podcasts</h4>
              <ul className="list-disc list-inside space-y-1 text-sm text-gray-600 dark:text-gray-300">
                <li><strong>Easiest:</strong> Use the built-in search when adding a podcast</li>
                <li>Or paste an RSS feed URL directly</li>
                <li>Spotify-exclusive podcasts don't have RSS feeds</li>
              </ul>
            </div>

            <div className="space-y-3">
              <h4 className="font-medium text-purple-800 dark:text-purple-200">Optimizing Detection</h4>
              <ul className="list-disc list-inside space-y-1 text-sm text-gray-600 dark:text-gray-300">
                <li>Start with Balanced preset</li>
                <li>If too many ads remain, try Aggressive</li>
                <li>If content is removed, try Conservative</li>
                <li>Check episode stats to see what was removed</li>
              </ul>
            </div>

            <div className="space-y-3">
              <h4 className="font-medium text-purple-800 dark:text-purple-200">Common Issues</h4>
              <div className="space-y-2 text-sm">
                <div className="p-2 bg-gray-50 dark:bg-gray-800 rounded">
                  <p className="font-medium text-gray-900 dark:text-gray-100">Episode won't process</p>
                  <p className="text-gray-600 dark:text-gray-400">Check that it's Enabled (not disabled/not whitelisted), then use the trigger link or Process button</p>
                </div>
                <div className="p-2 bg-gray-50 dark:bg-gray-800 rounded">
                  <p className="font-medium text-gray-900 dark:text-gray-100">Podcast app shows old episodes</p>
                  <p className="text-gray-600 dark:text-gray-400">Refresh the feed in your app — they cache aggressively</p>
                </div>
                <div className="p-2 bg-gray-50 dark:bg-gray-800 rounded">
                  <p className="font-medium text-gray-900 dark:text-gray-100">Ads not being detected</p>
                  <p className="text-gray-600 dark:text-gray-400">Try a more aggressive preset or reprocess the episode</p>
                </div>
              </div>
            </div>

            <div className="p-3 bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-700 rounded-lg">
              <p className="text-sm text-purple-800 dark:text-purple-200">
                <strong>Storage:</strong> Processed files are auto-deleted after 14 days (configurable in Settings).
              </p>
            </div>
          </div>
        );
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/80"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="relative bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-purple-100 dark:border-purple-800 bg-gradient-to-r from-purple-50 to-pink-50 dark:from-purple-900/30 dark:to-pink-900/30">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-purple-900 dark:text-purple-100">How to Use Podly</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-purple-100 dark:hover:bg-purple-800 text-gray-500 dark:text-gray-400 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-4 py-2 border-b border-gray-100 dark:border-gray-800 overflow-x-auto">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
                activeTab === tab.id
                  ? 'bg-purple-100 dark:bg-purple-800 text-purple-700 dark:text-purple-200'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {renderContent()}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
          <div className="flex items-center justify-between">
            {onReplayTutorial ? (
              <button
                onClick={() => {
                  onClose();
                  onReplayTutorial();
                }}
                className="text-xs text-purple-600 dark:text-purple-400 hover:underline flex items-center gap-1"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Replay Tutorial
              </button>
            ) : (
              <span />
            )}
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Need more help?{' '}
              <a 
                href="https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues" 
                target="_blank" 
                rel="noopener noreferrer"
                className="text-purple-600 dark:text-purple-400 hover:underline"
              >
                Open an issue on GitHub
              </a>
            </p>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
