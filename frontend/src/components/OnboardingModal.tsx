import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useEscapeKey } from '../hooks/useEscapeKey';

interface OnboardingModalProps {
  onClose: () => void;
}

const ONBOARDING_STEPS = [
  {
    title: 'Welcome to Podly! 🎧',
    icon: '👋',
    content: (
      <div className="space-y-3">
        <p>Podly automatically removes ads from your favorite podcasts using AI.</p>
        <p>Let's get you started in just a few steps!</p>
      </div>
    ),
  },
  {
    title: 'Step 1: Find a Podcast',
    icon: '🔍',
    content: (
      <div className="space-y-3">
        <p>Go to the <strong>Podcasts</strong> page and click <strong>"Add Podcast"</strong>.</p>
        <p>You have three options:</p>
        <ul className="list-disc list-inside space-y-1.5 ml-2 text-sm">
          <li><strong>Browse Server:</strong> See shows already added by other users</li>
          <li><strong>Search:</strong> Use our global podcast lookup to find any show</li>
          <li><strong>Manual:</strong> Paste an RSS feed URL directly</li>
        </ul>
        <div className="bg-purple-50 dark:bg-purple-900/30 rounded-lg p-3 text-sm">
          <strong>Privacy:</strong> You can add feeds as <em>private</em> so they won't appear when others browse the server.
        </div>
      </div>
    ),
  },
  {
    title: 'Step 2: Episodes Auto-Enable',
    icon: '✅',
    content: (
      <div className="space-y-3">
        <p>When you add a podcast, the <strong>most recent episodes are automatically enabled</strong> for processing.</p>
        <p><strong>New episodes</strong> are also automatically enabled as they're released.</p>
        <div className="bg-purple-50 dark:bg-purple-900/30 rounded-lg p-3 text-sm">
          <strong>Auto-Process:</strong> For shows you always listen to, enable "Auto-Process" in the show settings. Episodes will be processed automatically so they're ready when you want them!
        </div>
      </div>
    ),
  },
  {
    title: 'Step 3: Subscribe in Your App',
    icon: '📱',
    content: (
      <div className="space-y-3">
        <p>You have two options to add feeds to your podcast app:</p>
        <ul className="list-disc list-inside space-y-1.5 ml-2 text-sm">
          <li><strong>Per-show:</strong> Click "Podly RSS" on each podcast for individual feeds</li>
          <li><strong>All-in-One:</strong> Click "All-in-One Podly RSS" to get ONE feed with ALL your shows combined!</li>
        </ul>
        <p className="text-sm">Paste the URL into your favorite podcast app (Apple Podcasts, Overcast, Pocket Casts, etc.).</p>
        <div className="bg-amber-50 dark:bg-amber-900/30 rounded-lg p-3 text-sm border border-amber-200 dark:border-amber-800">
          <strong>Important:</strong> Processing starts when you tap the "Process this episode (remove ads)" link at the bottom of each episode's notes/description. Once it says "Episode Ready", close the tab and refresh your podcast app.
        </div>
      </div>
    ),
  },
  {
    title: 'Step 4: Listen Ad-Free! 🎧',
    icon: '🎉',
    content: (
      <div className="space-y-3">
        <p>Once processed, episodes are available ad-free through:</p>
        <ul className="list-disc list-inside space-y-2 ml-2">
          <li>Your podcast app (via Podly RSS)</li>
          <li>Direct download from the web interface</li>
          <li>The built-in audio player</li>
        </ul>
        <div className="bg-purple-50 dark:bg-purple-900/30 rounded-lg p-3 text-sm">
          <strong>Tip:</strong> You can start processing either from your podcast app (trigger link at the bottom of episode notes) or from the web UI ("Process" button).
        </div>
        <p className="text-purple-600 dark:text-purple-300 font-medium">Enjoy your ad-free podcasts! ✨</p>
      </div>
    ),
  },
];

export default function OnboardingModal({ onClose }: OnboardingModalProps) {
  const [currentStep, setCurrentStep] = useState(0);
  useEscapeKey(true, onClose);

  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = '';
    };
  }, []);

  const handleNext = () => {
    if (currentStep < ONBOARDING_STEPS.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      onClose();
    }
  };

  const handlePrev = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleSkip = () => {
    onClose();
  };

  const step = ONBOARDING_STEPS[currentStep];
  const isLastStep = currentStep === ONBOARDING_STEPS.length - 1;

  const modal = (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.6)' }}
    >
      <div
        className="relative w-full max-w-lg rounded-2xl shadow-2xl overflow-hidden"
        style={{ backgroundColor: 'white' }}
      >
        {/* Progress bar */}
        <div className="h-1 bg-gray-200">
          <div
            className="h-full bg-gradient-to-r from-pink-500 via-purple-500 to-cyan-500 transition-all duration-300"
            style={{ width: `${((currentStep + 1) / ONBOARDING_STEPS.length) * 100}%` }}
          />
        </div>

        {/* Header */}
        <div className="p-6 pb-4 bg-gradient-to-r from-pink-50 via-purple-50 to-cyan-50 dark:from-slate-800 dark:via-purple-900 dark:to-slate-800">
          <div className="flex items-center gap-4">
            <div className="text-4xl">{step.icon}</div>
            <div>
              <h2 className="text-xl font-bold text-purple-900 dark:text-white">{step.title}</h2>
              <p className="text-sm text-purple-600 dark:text-purple-300">
                Step {currentStep + 1} of {ONBOARDING_STEPS.length}
              </p>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 text-gray-700 dark:text-gray-200 min-h-[180px]">
          {step.content}
        </div>

        {/* Footer */}
        <div className="p-6 pt-4 border-t border-gray-100 dark:border-gray-700 flex items-center justify-between bg-gray-50 dark:bg-slate-800">
          <div>
            {currentStep === 0 ? (
              <button
                onClick={handleSkip}
                className="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              >
                Skip tutorial
              </button>
            ) : (
              <button
                onClick={handlePrev}
                className="flex items-center gap-1 text-sm text-purple-600 hover:text-purple-700 dark:text-purple-400 dark:hover:text-purple-300"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                Back
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Step indicators */}
            <div className="flex gap-1.5 mr-4">
              {ONBOARDING_STEPS.map((_, idx) => (
                <button
                  key={idx}
                  onClick={() => setCurrentStep(idx)}
                  className={`w-2 h-2 rounded-full transition-all ${
                    idx === currentStep
                      ? 'bg-purple-600 w-4'
                      : idx < currentStep
                      ? 'bg-purple-400'
                      : 'bg-gray-300'
                  }`}
                />
              ))}
            </div>

            <button
              onClick={handleNext}
              className="px-5 py-2 bg-gradient-to-r from-pink-500 via-purple-500 to-cyan-500 text-white font-medium rounded-lg hover:shadow-lg hover:shadow-purple-500/30 transition-all"
            >
              {isLastStep ? "Let's Go!" : 'Next'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  return createPortal(modal, document.body);
}

const ONBOARDING_STORAGE_KEY = 'podly_onboarding_completed';

export function useOnboarding() {
  const [showOnboarding, setShowOnboarding] = useState(false);

  useEffect(() => {
    const completed = localStorage.getItem(ONBOARDING_STORAGE_KEY);
    if (!completed) {
      // Small delay to let the app render first
      const timer = setTimeout(() => setShowOnboarding(true), 500);
      return () => clearTimeout(timer);
    }
  }, []);

  const completeOnboarding = () => {
    localStorage.setItem(ONBOARDING_STORAGE_KEY, 'true');
    setShowOnboarding(false);
  };

  const resetOnboarding = () => {
    localStorage.removeItem(ONBOARDING_STORAGE_KEY);
  };

  return { showOnboarding, completeOnboarding, resetOnboarding };
}
