/**
 * Prefetch service for hover-based and post-login data preloading.
 *
 * Provides debounced hover prefetch for gallery/search cards,
 * post-login dashboard data prefetch, and search next-page prefetch.
 */

import axiosInstance from '$lib/axios';
import { apiCache, CacheTTL, cacheKey } from '$lib/apiCache';
import { getMediaStreamUrl } from '$lib/api/mediaUrl';

/** Track in-flight prefetch UUIDs to avoid duplicate requests */
const inflight = new Set<string>();

/** Track recently failed UUIDs to avoid retry spam (cached for 10s) */
const failedCache = new Map<string, number>();
const FAILED_CACHE_TTL = 10_000;

let pendingTimer: ReturnType<typeof setTimeout> | null = null;

/**
 * Prefetch file details and stream URL on hover.
 * Debounced at 200ms to handle virtual scroll thrashing.
 */
export function prefetchFileDetails(fileUuid: string): void {
  cancelPrefetch();

  pendingTimer = setTimeout(() => {
    pendingTimer = null;

    // Skip if already in-flight or recently failed
    if (inflight.has(fileUuid)) return;
    const failedAt = failedCache.get(fileUuid);
    if (failedAt && Date.now() - failedAt < FAILED_CACHE_TTL) return;

    // Skip if already cached
    const cached = apiCache.get(cacheKey.fileDetail(fileUuid));
    if (cached) return;

    inflight.add(fileUuid);

    // Fire both requests in parallel, silently
    Promise.all([
      apiCache.getOrFetch(
        cacheKey.fileDetail(fileUuid),
        () => axiosInstance.get(`/files/${fileUuid}`).then((r) => r.data),
        CacheTTL.FILES
      ),
      getMediaStreamUrl(fileUuid, 'video').catch(() => null),
    ])
      .catch(() => {
        failedCache.set(fileUuid, Date.now());
      })
      .finally(() => {
        inflight.delete(fileUuid);
      });
  }, 200);
}

/**
 * Cancel any pending prefetch (call on mouseleave).
 */
export function cancelPrefetch(): void {
  if (pendingTimer) {
    clearTimeout(pendingTimer);
    pendingTimer = null;
  }
}

/**
 * Prefetch dashboard data (file list + user settings) after login.
 * Fires in parallel, fails silently.
 */
export function prefetchDashboardData(): void {
  // Prefetch the first page of files
  const filesKey = cacheKey.files(1, '');
  apiCache
    .getOrFetch(filesKey, () => axiosInstance.get('/files').then((r) => r.data), CacheTTL.FILES)
    .catch(() => {});

  // Prefetch collections
  apiCache
    .getOrFetch(
      cacheKey.collections(),
      () => axiosInstance.get('/collections').then((r) => r.data),
      CacheTTL.COLLECTIONS
    )
    .catch(() => {});
}

/**
 * Prefetch speakers page data on hover.
 * Fires all three tab endpoints in parallel, fails silently.
 */
export function prefetchSpeakersData(): void {
  apiCache
    .getOrFetch(
      'speakers:clusters',
      () =>
        axiosInstance
          .get('/speaker-clusters', { params: { page: 1, per_page: 20 } })
          .then((r) => r.data),
      CacheTTL.SPEAKERS
    )
    .catch(() => {});

  apiCache
    .getOrFetch(
      'speakers:profiles',
      () => axiosInstance.get('/speaker-profiles/profiles').then((r) => r.data),
      CacheTTL.SPEAKERS
    )
    .catch(() => {});

  apiCache
    .getOrFetch(
      'speakers:inbox',
      () =>
        axiosInstance
          .get('/speaker-clusters/unverified/inbox', { params: { page: 1, per_page: 20 } })
          .then((r) => r.data),
      CacheTTL.SPEAKERS
    )
    .catch(() => {});
}

/**
 * Prefetch the next page of search results after current page loads.
 * Delayed by 1 second to avoid competing with current page rendering.
 */
export function prefetchNextSearchPage(
  currentQuery: string,
  currentPage: number,
  totalPages: number,
  searchParams: Record<string, unknown>
): void {
  if (currentPage >= totalPages) return;

  setTimeout(() => {
    const nextPage = currentPage + 1;
    const prefetchKey = `search:${currentQuery}:page:${nextPage}`;

    // Skip if already cached
    if (apiCache.get(prefetchKey)) return;

    apiCache
      .getOrFetch(
        prefetchKey,
        () =>
          axiosInstance
            .get('/search', {
              params: { ...searchParams, page: nextPage },
              paramsSerializer: (params: Record<string, unknown>) => {
                const sp = new URLSearchParams();
                Object.entries(params).forEach(([key, value]) => {
                  if (value === undefined) return;
                  if (Array.isArray(value)) {
                    value.forEach((v) => sp.append(key, String(v)));
                  } else {
                    sp.set(key, String(value));
                  }
                });
                return sp.toString();
              },
            })
            .then((r) => r.data),
        CacheTTL.FILES
      )
      .catch(() => {});
  }, 1000);
}
