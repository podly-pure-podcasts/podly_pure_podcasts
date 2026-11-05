import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { BrowserRouter as Router, Routes, Route, Link, NavLink, Navigate, useLocation } from 'react-router-dom';
import { AudioPlayerProvider } from './contexts/AudioPlayerContext';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { useQuery } from '@tanstack/react-query';
import { useState, useEffect, useRef, lazy, Suspense } from 'react';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import AudioPlayer from './components/AudioPlayer';
import { billingApi } from './services/api';
import { DiagnosticsProvider, useDiagnostics } from './contexts/DiagnosticsContext';
import ThemeToggle from './components/ThemeToggle';
import PageTransitionFrame from './components/PageTransitionFrame';
import NavHighlight from './components/NavHighlight';
import { ThemeProvider } from './contexts/ThemeContext';
import { CloseIcon, MenuIcon } from './components/icons';

// Shared between lazy() and the idle prefetch so each chunk is requested once.
const loadJobsPage = () => import('./pages/JobsPage');
const loadConfigPage = () => import('./pages/ConfigPage');
const loadBillingPage = () => import('./pages/BillingPage');
const loadLandingPage = () => import('./pages/LandingPage');
const loadDiagnosticsModal = () => import('./components/DiagnosticsModal');

const JobsPage = lazy(loadJobsPage);
const ConfigPage = lazy(loadConfigPage);
const BillingPage = lazy(loadBillingPage);
const LandingPage = lazy(loadLandingPage);
const DiagnosticsModal = lazy(loadDiagnosticsModal);

const navItemBase = 'rounded-md px-3 py-1.5 text-sm font-medium';
const navItemInactive = 'text-gray-700 hover:text-gray-900 hover:bg-gray-50';
const navItemActive = 'bg-gray-100 text-gray-900';

function navItemClass({ isActive }: { isActive: boolean }) {
  return `${navItemBase} ${isActive ? navItemActive : navItemInactive}`;
}

// Desktop items draw no fill of their own; NavHighlight slides one behind the current item.
const deskItemBase = `relative ${navItemBase}`;
const deskItemActive = 'text-gray-900';

function deskItemClass({ isActive }: { isActive: boolean }) {
  return `${deskItemBase} ${isActive ? deskItemActive : navItemInactive}`;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Data is always stale and refetches on mount/focus/reconnect; inactive
      // results are kept for five minutes so returning to a view shows the last
      // copy at once while that refetch runs.
      staleTime: 0,
      gcTime: 5 * 60_000,
      refetchOnMount: 'always',
      refetchOnWindowFocus: 'always',
      refetchOnReconnect: 'always',
    },
  },
});

function isHomeRoute(pathname: string): boolean {
  return pathname === '/' || pathname.startsWith('/feeds/');
}

function AppShell() {
  const {
    status,
    requireAuth,
    isAuthenticated,
    user,
    logout,
    landingPageEnabled,
  } = useAuth();
  const { open: openDiagnostics } = useDiagnostics();
  useEffect(() => {
    const prefetch = () => {
      void loadJobsPage();
      void loadConfigPage();
      void loadBillingPage();
      void loadDiagnosticsModal();
    };
    // Prefetch keeps the first navigation from waiting on a chunk fetch. It
    // waits out the first page's render: parsing these chunks mid-render
    // measurably stalls slow phones.
    let idleId: number | undefined;
    const timeoutId = window.setTimeout(() => {
      if (typeof window.requestIdleCallback === 'function') {
        idleId = window.requestIdleCallback(prefetch);
      } else {
        prefetch();
      }
    }, 5000);
    return () => {
      window.clearTimeout(timeoutId);
      if (idleId !== undefined) window.cancelIdleCallback(idleId);
    };
  }, []);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const mobileMenuRef = useRef<HTMLDivElement>(null);
  const desktopNavRef = useRef<HTMLElement>(null);
  const location = useLocation();
  const previousPathnameRef = useRef<string | null>(null);
  const { data: billingSummary } = useQuery({
    queryKey: ['billing', 'summary'],
    queryFn: billingApi.getSummary,
    enabled: !!user && requireAuth && isAuthenticated,
    retry: false,
  });

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    previousPathnameRef.current = location.pathname;
  }, [location.pathname]);

  // Close mobile menu when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (mobileMenuRef.current && !mobileMenuRef.current.contains(event.target as Node)) {
        setMobileMenuOpen(false);
      }
    }
    if (mobileMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [mobileMenuOpen]);

  if (status === 'loading') {
    return (
      <div className="h-dvh flex items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center gap-4">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600" />
          <p className="text-sm text-gray-600">Loading authentication…</p>
        </div>
      </div>
    );
  }

  // Show landing page for unauthenticated users when auth is required
  // But allow access to /login route
  if (requireAuth && !isAuthenticated) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        {landingPageEnabled ? (
          <Route path="*" element={<Suspense fallback={null}><LandingPage /></Suspense>} />
        ) : (
          <>
            <Route path="/" element={<Navigate to="/login" replace />} />
            <Route path="*" element={<Navigate to="/login" replace />} />
          </>
        )}
      </Routes>
    );
  }

  const isAdmin = !requireAuth || user?.role === 'admin';
  const showConfigLink = !requireAuth || isAdmin;
  const showJobsLink = !requireAuth || isAdmin;
  const showBillingLink = requireAuth && !isAdmin;
  const previousPathname = previousPathnameRef.current;
  const locationState = location.state as { fromPath?: string } | null;
  const homeNavigationState = { fromPath: location.pathname };
  const homeTransitionSources = ['/login', '/jobs', '/config', '/billing'];
  const homeTransitionSource = locationState?.fromPath ?? previousPathname;
  const shouldAnimateHomePage =
    isHomeRoute(location.pathname) &&
    Boolean(homeTransitionSource && homeTransitionSources.includes(homeTransitionSource));
  const homeTransitionKey = shouldAnimateHomePage
    ? `home-enter-${homeTransitionSource ?? 'unknown'}`
    : 'home';
  const homeRouteElement = (
    <PageTransitionFrame
      className="h-full"
      transitionKey={homeTransitionKey}
      animateOnMount={shouldAnimateHomePage}
    >
      <HomePage />
    </PageTransitionFrame>
  );

  return (
    <div className="h-dvh bg-gray-50 flex flex-col overflow-hidden">
      <header className="bg-surface border-b flex-shrink-0">
        <div className="px-2 sm:px-4 lg:px-6">
          <div className="flex items-center justify-between h-12">
            <div className="flex items-center">
              <Link to="/" state={homeNavigationState} className="flex items-center">
                <img
                  src="/images/logos/logo.webp"
                  alt="Podly"
                  className="h-6 w-auto"
                />
                <span className="ml-2 text-lg font-semibold text-gray-900">
                  Podly
                </span>
              </Link>
            </div>

            {/* Desktop Navigation */}
            <nav ref={desktopNavRef} className="relative hidden md:flex items-center space-x-2">
              <NavHighlight navRef={desktopNavRef} activeKey={location.pathname} />
              <NavLink
                to="/"
                state={homeNavigationState}
                className={`${deskItemBase} ${isHomeRoute(location.pathname) ? deskItemActive : navItemInactive}`}
                aria-current={isHomeRoute(location.pathname) ? 'page' : undefined}
              >
                Home
              </NavLink>
              {showBillingLink && (
                <NavLink to="/billing" className={deskItemClass}>
                  Billing
                </NavLink>
              )}
              {showJobsLink && (
                <NavLink to="/jobs" className={deskItemClass}>
                  Jobs
                </NavLink>
              )}
              {showConfigLink && (
                <NavLink to="/config" className={deskItemClass}>
                  Settings
                </NavLink>
              )}
              <button
                type="button"
                onClick={() => openDiagnostics()}
                className={`${deskItemBase} ${navItemInactive}`}
              >
                Report issue
              </button>
              <ThemeToggle className="ml-2" />
              {requireAuth && user && (
                <div className="flex items-center gap-3 ml-2 text-sm text-gray-600 flex-shrink-0">
                  {billingSummary && !isAdmin && (
                    <>
                      <div
                        className="px-2 py-1 rounded-md border border-blue-200 text-blue-700 bg-blue-50 text-xs whitespace-nowrap"
                        title="Feeds included in your plan"
                      >
                        Feeds {billingSummary.feeds_in_use}/{billingSummary.feed_allowance}
                      </div>
                      <Link to="/billing" className="btn btn-secondary whitespace-nowrap">
                        Change plan
                      </Link>
                    </>
                  )}
                  <span className="hidden sm:inline whitespace-nowrap">{user.username}</span>
                  <button onClick={logout} className="btn btn-secondary whitespace-nowrap">
                    Logout
                  </button>
                </div>
              )}
            </nav>

            {/* Mobile: Credits + Hamburger */}
            <div className="md:hidden flex items-center gap-2">
              {requireAuth && user && billingSummary && !isAdmin && (
                <>
                  <div
                    className="px-2 py-1 rounded-md border border-blue-200 text-blue-700 bg-blue-50 text-xs whitespace-nowrap"
                    title="Feeds included in your plan"
                  >
                    Feeds {billingSummary.feeds_in_use}/{billingSummary.feed_allowance}
                  </div>
                  <Link to="/billing" className="btn btn-secondary btn-sm whitespace-nowrap">
                    Change plan
                  </Link>
                </>
              )}

              <ThemeToggle />

              <div className="relative" ref={mobileMenuRef}>
                <button
                  type="button"
                  onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                  className="touch-target p-2 rounded-md text-gray-600 hover:text-gray-900 hover:bg-gray-100 transition-colors"
                  aria-label={mobileMenuOpen ? 'Close menu' : 'Open menu'}
                  aria-expanded={mobileMenuOpen}
                >
                  {mobileMenuOpen ? <CloseIcon className="h-6 w-6" /> : <MenuIcon className="h-6 w-6" />}
                </button>

                {mobileMenuOpen && (
                  <div className="animate-pop-in origin-top-right absolute right-0 top-full mt-2 w-56 bg-surface rounded-lg shadow-lg border border-gray-200 p-2 z-50">
                    <NavLink
                      to="/"
                      state={homeNavigationState}
                      className={`block ${navItemBase} ${isHomeRoute(location.pathname) ? navItemActive : navItemInactive}`}
                      aria-current={isHomeRoute(location.pathname) ? 'page' : undefined}
                    >
                      Home
                    </NavLink>
                    {showBillingLink && (
                      <NavLink to="/billing" className={({ isActive }) => `block ${navItemClass({ isActive })}`}>
                        Billing
                      </NavLink>
                    )}
                    {showJobsLink && (
                      <NavLink to="/jobs" className={({ isActive }) => `block ${navItemClass({ isActive })}`}>
                        Jobs
                      </NavLink>
                    )}
                    {showConfigLink && (
                      <NavLink to="/config" className={({ isActive }) => `block ${navItemClass({ isActive })}`}>
                        Settings
                      </NavLink>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        openDiagnostics();
                        setMobileMenuOpen(false);
                      }}
                      className={`block w-full text-left ${navItemBase} ${navItemInactive}`}
                    >
                      Report issue
                    </button>
                    {requireAuth && user && (
                      <>
                        <div className="border-t border-gray-100 my-2" />
                        <div className="px-3 py-1.5 text-sm text-gray-600">
                          {user.username}
                        </div>
                        <button
                          onClick={() => {
                            logout();
                            setMobileMenuOpen(false);
                          }}
                          className="btn btn-secondary btn-sm w-full mt-1"
                        >
                          Logout
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 px-2 sm:px-4 lg:px-6 py-4 overflow-auto">
        <Routes>
          <Route path="/" element={homeRouteElement} />
          <Route path="/feeds/:feedId" element={homeRouteElement} />
          {showBillingLink && (
            <Route
              path="/billing"
              element={
                <PageTransitionFrame key="billing" transitionKey="billing">
                  <Suspense fallback={null}>
                    <BillingPage />
                  </Suspense>
                </PageTransitionFrame>
              }
            />
          )}
          {showJobsLink && (
            <Route
              path="/jobs"
              element={
                <PageTransitionFrame key="jobs" transitionKey="jobs">
                  <Suspense fallback={null}>
                    <JobsPage />
                  </Suspense>
                </PageTransitionFrame>
              }
            />
          )}
          {showConfigLink && (
            <Route
              path="/config"
              element={
                <PageTransitionFrame key="config" transitionKey="config">
                  <Suspense fallback={null}>
                    <ConfigPage />
                  </Suspense>
                </PageTransitionFrame>
              }
            />
          )}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <AudioPlayer />
      <Suspense fallback={null}>
        <DiagnosticsModal />
      </Suspense>
      <Toaster
        position="top-center"
        toastOptions={{
          duration: 3000,
          style: {
            background: 'rgb(var(--surface))',
            color: 'rgb(var(--gray-900))',
            border: '1px solid rgb(var(--gray-200))',
          },
        }}
      />
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <AudioPlayerProvider>
            <DiagnosticsProvider>
              <Router>
                <AppShell />
              </Router>
            </DiagnosticsProvider>
          </AudioPlayerProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
