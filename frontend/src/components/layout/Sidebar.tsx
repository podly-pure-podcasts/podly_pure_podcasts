import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';
import HelpModal from '../HelpModal';
import UserProfileModal from '../UserProfileModal';
import { authApi } from '../../services/api';
import {
  getNextTheme,
  getThemeBrandClass,
  getThemeBrandName,
  getThemeLabel,
  getThemeLogoPath,
  getThemeSwitchTitle,
  type Theme,
} from '../../theme';

const ONBOARDING_STORAGE_KEY = 'podly_onboarding_completed';

interface NavItem {
  path: string;
  label: string;
  icon: React.ReactNode;
  adminOnly?: boolean;
}

const navItems: NavItem[] = [
  {
    path: '/',
    label: 'Dashboard',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
  },
  {
    path: '/podcasts',
    label: 'Podcasts',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
      </svg>
    ),
  },
  {
    path: '/jobs',
    label: 'Jobs',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    ),
  },
  {
    path: '/subscriptions',
    label: 'Subscriptions',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
      </svg>
    ),
    adminOnly: true,
  },
  {
    path: '/presets',
    label: 'Presets',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
      </svg>
    ),
    adminOnly: true,
  },
  {
    path: '/settings',
    label: 'Settings',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
    adminOnly: true,
  },
];

interface SidebarProps {
  collapsed?: boolean;
  onToggle?: () => void;
  onNavigate?: () => void;
  isMobile?: boolean;
}

export default function Sidebar({ collapsed = false, onToggle, onNavigate, isMobile = false }: SidebarProps) {
  const location = useLocation();
  const { requireAuth, user, logout } = useAuth();
  const { theme, setTheme, toggleTheme } = useTheme();
  const [helpOpen, setHelpOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const logoPath = getThemeLogoPath(theme);
  const brandName = getThemeBrandName(theme);
  const brandClass = getThemeBrandClass(theme);
  const nextThemeLabel = getThemeLabel(getNextTheme(theme));

  const { data: pendingCount } = useQuery<{ count: number }>({
    queryKey: ['pending-users-count'],
    queryFn: authApi.getPendingUsersCount,
    enabled: requireAuth && user?.role === 'admin',
    refetchInterval: 30_000,
  });

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  const filteredNavItems = navItems.filter(item => {
    if (item.adminOnly) {
      return !requireAuth || user?.role === 'admin';
    }
    return true;
  });

  // Solid sidebar colors - no transparency for better readability
  const sidebarClasses = theme === 'original'
    ? 'bg-gradient-to-b from-blue-700 via-blue-800 to-blue-950'
    : theme === 'dark'
      ? 'bg-gradient-to-b from-slate-900 via-purple-950 to-slate-950'
      : 'bg-gradient-to-b from-purple-800 via-purple-900 to-slate-900';

  const navActiveClasses = theme === 'original'
    ? 'bg-gradient-to-r from-blue-500/45 via-sky-500/35 to-cyan-500/35 text-white shadow-md shadow-blue-500/15 border border-blue-300/20'
    : 'bg-gradient-to-r from-pink-500/80 via-purple-500/80 to-cyan-500/80 text-white shadow-lg shadow-purple-500/30';

  const navInactiveClasses = theme === 'original'
    ? 'text-blue-100 hover:text-white hover:bg-blue-600/20'
    : 'text-purple-200 hover:text-white hover:bg-purple-800/40';

  return (
    <aside className={`${sidebarClasses} text-white flex flex-col transition-all duration-300 ${isMobile ? 'w-64' : (collapsed ? 'w-16' : 'w-64')} shadow-xl h-full`}>
      {/* Logo */}
      <div className={`h-16 flex items-center px-4 border-b ${theme === 'original' ? 'border-blue-400/25' : 'border-purple-800/50'}`}>
        <Link to="/" className="flex items-center gap-3">
          <img 
            src={logoPath}
            alt={brandName}
            className="h-10 w-10 object-contain"
          />
          {(!collapsed || isMobile) && (
            <span className={`text-lg font-bold ${brandClass}`}>
              {brandName}
            </span>
          )}
        </Link>
        {onToggle && !isMobile && (
          <button
            onClick={onToggle}
            className={`ml-auto p-2 rounded-lg transition-colors border ${
              theme === 'original'
                ? 'bg-blue-600/35 hover:bg-blue-500/45 border-blue-300/25'
                : 'bg-purple-700/50 hover:bg-purple-600/70 border-purple-500/30'
            }`}
          >
            <svg className={`w-5 h-5 transition-transform text-white ${collapsed ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
          </button>
        )}
      </div>

      {/* Navigation - scrollable */}
      <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
        {filteredNavItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            onClick={onNavigate}
            className={`flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all ${
              isActive(item.path)
                ? navActiveClasses
                : navInactiveClasses
            }`}
            title={collapsed && !isMobile ? item.label : undefined}
          >
            {item.icon}
            {(!collapsed || isMobile) && (
              <div className="flex items-center justify-between flex-1 min-w-0">
                <span className="font-medium">{item.label}</span>
                {item.path === '/settings' && (pendingCount?.count ?? 0) > 0 && (
                  <span className="ml-2 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 text-[10px] font-bold rounded-full bg-pink-500 text-white">
                    {pendingCount?.count}
                  </span>
                )}
              </div>
            )}
          </Link>
        ))}
      </nav>

      {/* Help, Community & Theme toggle */}
      <div className={`px-4 py-2 border-t space-y-1 ${theme === 'original' ? 'border-blue-400/25 bg-blue-950/35 backdrop-blur-sm' : 'border-purple-800/30'}`}>
        <button
          onClick={() => setHelpOpen(true)}
          className={`w-full flex items-center ${collapsed && !isMobile ? 'justify-center' : 'gap-3'} px-3 py-2 rounded-lg transition-colors ${
            theme === 'original'
              ? 'hover:bg-blue-700/35 text-blue-100 hover:text-white'
              : 'hover:bg-purple-800/30 text-purple-200 hover:text-white'
          }`}
          title="How to use Podly"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {(!collapsed || isMobile) && (
            <span className="text-sm font-medium">Help</span>
          )}
        </button>
        <a
          href="https://discord.gg/FRB98GtF6N"
          target="_blank"
          rel="noopener noreferrer"
          className={`w-full flex items-center ${collapsed && !isMobile ? 'justify-center' : 'gap-3'} px-3 py-2 rounded-lg transition-colors ${
            theme === 'original'
              ? 'text-blue-200 hover:text-white hover:bg-blue-700/35'
              : 'hover:bg-[#5865F2]/20 text-[#5865F2] hover:text-[#5865F2]'
          }`}
          title="Join our Discord community"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
            <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
          </svg>
          {(!collapsed || isMobile) && (
            <span className="text-sm font-medium">Community</span>
          )}
        </a>
        {(!collapsed || isMobile) && (
          <div className={`grid grid-cols-3 gap-1 p-1 rounded-lg border ${
            theme === 'original'
              ? 'bg-blue-950/65 border-blue-300/25'
              : 'bg-black/20 border-white/10'
          }`}>
            {(['light', 'dark', 'original'] as Theme[]).map((themeOption) => {
              const selected = theme === themeOption;
              return (
                <button
                  key={themeOption}
                  onClick={() => setTheme(themeOption)}
                  className={`px-2 py-1 text-xs rounded-md transition-colors ${
                    selected
                      ? themeOption === 'original'
                        ? 'bg-blue-500/70 text-white'
                        : 'bg-white/20 text-white'
                      : theme === 'original'
                        ? 'text-blue-200 hover:text-white hover:bg-blue-700/35'
                        : 'text-white/70 hover:text-white hover:bg-white/10'
                  }`}
                  title={`Switch to ${getThemeLabel(themeOption)} theme`}
                >
                  {themeOption === 'original' ? 'Blue' : getThemeLabel(themeOption)}
                </button>
              );
            })}
          </div>
        )}
        <button
          onClick={toggleTheme}
          className={`w-full flex items-center ${collapsed && !isMobile ? 'justify-center' : 'gap-3'} px-3 py-2 rounded-lg transition-colors ${
            theme === 'original'
              ? 'hover:bg-blue-700/35 text-blue-100 hover:text-white'
              : 'hover:bg-purple-800/30 text-purple-200 hover:text-white'
          }`}
          title={getThemeSwitchTitle(theme)}
        >
          {theme === 'light' ? (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
            </svg>
          ) : theme === 'dark' ? (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.073 3.306a1 1 0 00.95.69h3.476c.969 0 1.371 1.24.588 1.81l-2.812 2.043a1 1 0 00-.364 1.118l1.074 3.305c.3.922-.755 1.688-1.538 1.118l-2.812-2.043a1 1 0 00-1.176 0l-2.812 2.043c-.784.57-1.838-.196-1.539-1.118l1.074-3.305a1 1 0 00-.363-1.118L4.962 8.733c-.783-.57-.38-1.81.588-1.81h3.476a1 1 0 00.95-.69l1.073-3.306z" />
            </svg>
          ) : (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
          )}
          {(!collapsed || isMobile) && (
            <span className="text-sm font-medium">
              Switch to {nextThemeLabel}
            </span>
          )}
        </button>
      </div>

      {/* Help Modal */}
      <HelpModal 
        isOpen={helpOpen} 
        onClose={() => setHelpOpen(false)} 
        onReplayTutorial={() => {
          localStorage.removeItem(ONBOARDING_STORAGE_KEY);
          window.location.reload();
        }}
      />

      {/* User Profile Modal */}
      <UserProfileModal isOpen={profileOpen} onClose={() => setProfileOpen(false)} />

      {/* User section */}
      {requireAuth && user && (
        <div className={`p-4 border-t ${theme === 'original' ? 'border-blue-400/25 bg-blue-950/45' : 'border-purple-800/30'}`}>
          <div className={`flex items-center ${collapsed && !isMobile ? 'justify-center' : 'gap-3'}`}>
            <button
              onClick={() => setProfileOpen(true)}
              className="w-8 h-8 rounded-full bg-gradient-to-br from-pink-400 via-purple-400 to-cyan-400 flex items-center justify-center text-sm font-bold shadow-lg hover:scale-110 transition-transform cursor-pointer"
              title="Account settings"
            >
              {user.username.charAt(0).toUpperCase()}
            </button>
            {(!collapsed || isMobile) && (
              <button
                onClick={() => setProfileOpen(true)}
                className={`flex-1 min-w-0 text-left rounded-lg px-2 py-1 -mx-2 transition-colors ${theme === 'original' ? 'hover:bg-blue-700/35' : 'hover:bg-purple-800/20'}`}
                title="Account settings"
              >
                <p className="text-sm font-medium truncate">{user.username}</p>
                <p className={`text-xs capitalize ${theme === 'original' ? 'text-blue-200' : 'text-purple-300'}`}>{user.role}</p>
              </button>
            )}
            {(!collapsed || isMobile) && (
              <button
                onClick={logout}
                className={`p-1.5 rounded-lg transition-colors ${
                  theme === 'original'
                    ? 'hover:bg-blue-700/35 text-blue-200 hover:text-white'
                    : 'hover:bg-purple-800/30 text-purple-300 hover:text-white'
                }`}
                title="Logout"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
              </button>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}
