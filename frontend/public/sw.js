const CACHE_VERSION = 'v5';
const APP_SHELL_CACHE = `podly-shell-${CACHE_VERSION}`;
const RUNTIME_CACHE = `podly-runtime-${CACHE_VERSION}`;

const APP_SHELL_ASSETS = [
  '/',
  '/manifest.json',
  '/images/logos/apple-touch-icon.png',
  '/images/logos/favicon-96x96.png',
  '/images/logos/favicon.ico',
  '/images/logos/web-app-manifest-192x192.png',
  '/images/logos/web-app-manifest-512x512.png',
  '/images/logos/manifest-icon-192.maskable.png',
  '/images/logos/manifest-icon-512.maskable.png',
];

const NETWORK_ONLY_PREFIXES = [
  '/api/',
  '/feed',
  '/post/',
  '/trigger',
  '/rss/',
  '/set_whitelist/',
];

const CACHE_FIRST_PREFIXES = [
  '/assets/',
  '/images/logos/',
];

const CACHE_FIRST_PATHS = new Set([
  '/manifest.json',
  '/favicon.ico',
]);

function getPath(url) {
  return new URL(url).pathname;
}

function isSameOrigin(url) {
  return new URL(url).origin === self.location.origin;
}

function isNetworkOnly(path) {
  return NETWORK_ONLY_PREFIXES.some((prefix) => path.startsWith(prefix));
}

function isCacheFirst(path) {
  return (
    CACHE_FIRST_PATHS.has(path) ||
    CACHE_FIRST_PREFIXES.some((prefix) => path.startsWith(prefix))
  );
}

async function putInCache(cacheName, request, response) {
  if (!response.ok || !isSameOrigin(request.url)) {
    return;
  }

  const cache = await caches.open(cacheName);
  await cache.put(request, response.clone());
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) {
    return cached;
  }

  const response = await fetch(request);
  await putInCache(APP_SHELL_CACHE, request, response);
  return response;
}

async function networkFirst(request, fallbackRequest) {
  try {
    const response = await fetch(request);
    await putInCache(RUNTIME_CACHE, request, response);
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }

    if (fallbackRequest) {
      const fallback = await caches.match(fallbackRequest);
      if (fallback) {
        return fallback;
      }
    }

    throw error;
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(APP_SHELL_CACHE).then((cache) => cache.addAll(APP_SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => ![APP_SHELL_CACHE, RUNTIME_CACHE].includes(key))
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;

  if (request.method !== 'GET' || !isSameOrigin(request.url)) {
    return;
  }

  const path = getPath(request.url);

  if (isNetworkOnly(path)) {
    event.respondWith(fetch(request));
    return;
  }

  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request, '/'));
    return;
  }

  if (isCacheFirst(path)) {
    event.respondWith(cacheFirst(request));
    return;
  }

  event.respondWith(networkFirst(request));
});
