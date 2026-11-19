import { useMemo, useEffect, useCallback, useRef } from 'react';
import { useCascade } from '../../hooks/useCascade';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import useConfigState from '../../hooks/useConfigState';
import {
  ADVANCED_SUBTABS,
  ConfigContext,
  type ConfigTabId,
  type AdvancedSubtab,
} from './ConfigContext';
import { EnvOverrideWarningModal } from './shared';
import DefaultTab from './tabs/DefaultTab';
import AdvancedTab from './tabs/AdvancedTab';
import UserManagementTab from './tabs/UserManagementTab';
import DiscordTab from './tabs/DiscordTab';
import CostsTab from './tabs/CostsTab';
import BranchedMenu, { type BranchedMenuItem } from '../reactbits/BranchedMenu/BranchedMenu';

const TABS: { id: ConfigTabId; label: string; adminOnly?: boolean }[] = [
  { id: 'default', label: 'Basics' },
  { id: 'advanced', label: 'Advanced' },
  { id: 'users', label: 'Users', adminOnly: true },
  { id: 'discord', label: 'Discord', adminOnly: true },
  { id: 'costs', label: 'Costs', adminOnly: true },
];

const ADVANCED_SUBTAB_IDS = new Set<string>(ADVANCED_SUBTABS.map((subtab) => subtab.id));

export default function ConfigTabs() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, requireAuth } = useAuth();
  const configState = useConfigState();

  const showSecurityControls = requireAuth && !!user;
  const isAdmin = !requireAuth || (showSecurityControls && user?.role === 'admin');

  // Get tab from URL or default
  const activeTab = useMemo<ConfigTabId>(() => {
    const urlTab = searchParams.get('tab') as ConfigTabId | null;
    if (urlTab && TABS.some((t) => t.id === urlTab)) {
      // Check admin-only tabs
      const tab = TABS.find((t) => t.id === urlTab);
      if (tab?.adminOnly && !isAdmin) {
        return 'default';
      }
      if (urlTab === 'users' && !requireAuth) {
        return 'default';
      }
      return urlTab;
    }
    return 'default';
  }, [searchParams, isAdmin, requireAuth]);

  const activeSubtab = useMemo<AdvancedSubtab>(() => {
    const urlSubtab = searchParams.get('section') as AdvancedSubtab | null;
    if (urlSubtab && ['llm', 'whisper', 'processing', 'output', 'app'].includes(urlSubtab)) {
      return urlSubtab;
    }
    return 'llm';
  }, [searchParams]);

  const setActiveTab = useCallback((tab: ConfigTabId) => {
    setSearchParams((prev) => {
      const newParams = new URLSearchParams(prev);
      newParams.set('tab', tab);
      if (tab !== 'advanced') {
        newParams.delete('section');
      }
      return newParams;
    }, { replace: true });
  }, [setSearchParams]);

  const setActiveSubtab = useCallback((subtab: AdvancedSubtab) => {
    setSearchParams((prev) => {
      const newParams = new URLSearchParams(prev);
      newParams.set('section', subtab);
      return newParams;
    }, { replace: true });
  }, [setSearchParams]);

  // Redirect if on admin-only tab without permission
  useEffect(() => {
    const tab = TABS.find((t) => t.id === activeTab);
    if (tab?.adminOnly && !isAdmin) {
      setActiveTab('default');
    }
  }, [isAdmin, activeTab, setActiveTab]);

  const contextValue = useMemo(
    () => ({
      ...configState,
      activeTab,
      setActiveTab,
      activeSubtab,
      setActiveSubtab,
      isAdmin,
      showSecurityControls,
    }),
    [configState, activeTab, setActiveTab, activeSubtab, setActiveSubtab, isAdmin, showSecurityControls]
  );

  const contentRef = useRef<HTMLDivElement>(null);
  // The page transition covers the first arrival; tab changes cascade.
  useCascade(contentRef, {
    playKey: activeTab === 'advanced' ? `advanced:${activeSubtab}` : activeTab,
    ready: !configState.isLoading && !!configState.pending,
    selector: 'section, details',
    skipFirst: true,
  });

  const visibleTabs = TABS.filter((tab) => {
    if (tab.id === 'users' && !requireAuth) return false;
    return !tab.adminOnly || isAdmin;
  });

  const sidebarItems: BranchedMenuItem[] = visibleTabs.map((tab) =>
    tab.id === 'advanced'
      ? { label: tab.label, children: ADVANCED_SUBTABS.map(({ id, label }) => ({ value: id, label })) }
      : { label: tab.label, value: tab.id }
  );
  const advancedIndex = visibleTabs.findIndex((tab) => tab.id === 'advanced');

  // One URL update, so picking a subtab from another tab doesn't race two setters.
  const selectSidebarItem = (value: string) => {
    if (!ADVANCED_SUBTAB_IDS.has(value)) {
      setActiveTab(value as ConfigTabId);
      return;
    }
    setSearchParams((prev) => {
      const newParams = new URLSearchParams(prev);
      newParams.set('tab', 'advanced');
      newParams.set('section', value);
      return newParams;
    }, { replace: true });
  };

  if (configState.isLoading || !configState.pending) {
    return <div className="text-sm text-gray-700">Loading settings…</div>;
  }

  return (
    <ConfigContext.Provider value={contextValue}>
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold text-gray-900">Settings</h1>

        {/* Below `lg`: tabs across the top. */}
        <div className="overflow-x-auto border-b border-gray-200 lg:hidden">
          <nav className="flex min-w-max space-x-8" role="tablist" aria-label="Settings">
            {visibleTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={activeTab === tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`py-3 px-1 border-b-2 font-medium text-sm whitespace-nowrap transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500 ${
                  activeTab === tab.id
                    ? 'border-blue-600 text-gray-900'
                    : 'border-transparent text-gray-600 hover:text-gray-900'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        <div className="lg:grid lg:grid-cols-[12rem_minmax(0,1fr)] lg:gap-12">
          {/* From `lg`: a sticky sidebar; the Advanced subtabs branch off Advanced. */}
          <div className="hidden lg:block">
            <div className="sticky top-6">
              <BranchedMenu
                aria-label="Settings"
                items={sidebarItems}
                value={activeTab === 'advanced' ? activeSubtab : activeTab}
                defaultOpen={activeTab === 'advanced' ? advancedIndex : -1}
                onSelect={selectSidebarItem}
                onToggle={(index, open) => {
                  if (index === advancedIndex && open && activeTab !== 'advanced') {
                    setActiveTab('advanced');
                  }
                }}
                color="rgb(var(--gray-900))"
                accentColor="rgb(var(--gray-900))"
                mutedColor="rgb(var(--gray-600))"
                lineColor="rgb(var(--gray-300))"
                width={192}
                rowHeight={32}
                fontSize={14}
                drawDuration={360}
                foldDuration={280}
                className="w-full"
              />
            </div>
          </div>

          {/* Forms stay at a readable width; Costs keeps the full width for its tables. */}
          <div ref={contentRef} className={`min-w-0 ${activeTab === 'costs' ? '' : 'max-w-5xl'}`}>
            {activeTab === 'default' && <DefaultTab />}
            {activeTab === 'advanced' && <AdvancedTab />}
            {activeTab === 'users' && isAdmin && <UserManagementTab />}
            {activeTab === 'discord' && isAdmin && <DiscordTab />}
            {activeTab === 'costs' && isAdmin && <CostsTab />}
          </div>
        </div>

        {/* Env Warning Modal */}
        {configState.showEnvWarning && configState.envWarningPaths.length > 0 && (
          <EnvOverrideWarningModal
            paths={configState.envWarningPaths}
            overrides={configState.envOverrides}
            onCancel={configState.handleDismissEnvWarning}
            onConfirm={configState.handleConfirmEnvWarning}
          />
        )}

        {/* Keeps the last settings clear of the audio player overlay. */}
        <div className="h-24"></div>
      </div>
    </ConfigContext.Provider>
  );
}
