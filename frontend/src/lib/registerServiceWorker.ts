/// <reference lib="webworker" />

// Service Worker registration and caching logic
const CACHE_NAME = 'transcribe-app-cache-v1';
const ASSETS_TO_CACHE: string[] = [
  '/',
  '/index.html',
  '/global.css',
  '/build/bundle.css',
  '/build/bundle.js',
  '/fonts/Poppins-Light.woff2',
  '/fonts/Poppins-Regular.woff2',
  '/fonts/Poppins-Medium.woff2',
  '/fonts/Poppins-SemiBold.woff2',
  '/fonts/Poppins-Bold.woff2',
  '/favicon.ico',
  '/favicon.svg',
  // Add other static assets that should be cached
];

// TypeScript type assertions for service worker events
interface InstallEvent extends Event {
  waitUntil(promise: Promise<any>): void;
}

interface ActivateEvent extends Event {
  waitUntil(promise: Promise<any>): void;
}

interface FetchEvent extends Event {
  request: Request;
  respondWith(response: Promise<Response> | Response): void;
}

// Service Worker event listeners
// Install event - cache all static assets
self.addEventListener('install', (event: Event) => {
  const installEvent = event as InstallEvent;
  installEvent.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        return cache.addAll(ASSETS_TO_CACHE);
      })
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event: Event) => {
  const activateEvent = event as ActivateEvent;
  activateEvent.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
});

// Fetch event - serve from cache, falling back to network
self.addEventListener('fetch', (event: Event) => {
  const fetchEvent = event as unknown as FetchEvent;
  // Skip non-GET requests and chrome-extension URLs
  const request = fetchEvent.request;
  if (request.method !== 'GET' || request.url.startsWith('chrome-extension://')) {
    return;
  }

  // Handle API requests
  if (request.url.includes('/api/')) {
    // For API requests, try network first, then fall back to cache if offline
    fetchEvent.respondWith(
      fetch(request)
        .then((response) => {
          // Clone the response to save it to cache
          const responseToCache = response.clone();
          caches.open(CACHE_NAME)
            .then((cache) => {
              cache.put(request, responseToCache);
            });
          return response;
        })
        .catch(() => {
          // If network fails, try to get from cache
          return caches.match(request) as Promise<Response>;
        })
    );
  } else {
    // For static assets, try cache first, then network
    fetchEvent.respondWith(
      (async () => {
        const cachedResponse = await caches.match(request);
        // Return cached response if found
        if (cachedResponse) {
          return cachedResponse;
        }
        // Otherwise, fetch from network
        try {
          const response = await fetch(request);
          // Don't cache responses with error status codes
          if (!response || response.status !== 200 || response.type !== 'basic') {
            return response;
          }
          // Clone the response to save it to cache
          const responseToCache = response.clone();
          caches.open(CACHE_NAME)
            .then((cache) => {
              cache.put(request, responseToCache);
            });
          return response;
        } catch (error) {
          console.error('Fetch failed; returning offline page instead.', error);
          return new Response('Network error happened', {
            status: 408,
            headers: { 'Content-Type': 'text/plain' },
          });
        }
      })()
    );
  }
});

// Service Worker registration function
export function register() {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/service-worker.js')
        .then((registration) => {
          // ServiceWorker registration successful
        })
        .catch((error) => {
          console.error('ServiceWorker registration failed: ', error);
        });
    });
  }
}

// Service Worker unregistration function
export function unregister() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.ready.then((registration) => {
      registration.unregister();
    });
  }
}
