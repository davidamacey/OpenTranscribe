/**
 * Utility functions for constructing URLs based on environment configuration.
 * Handles differences between localhost development (with specific ports) and
 * production deployment (behind Nginx reverse proxy).
 */

/**
 * Gets the base URL for the application API.
 * In dev mode with VITE_API_BASE_URL set, it uses that (e.g. http://localhost:5174).
 * In production, it uses the current window origin.
 */
export function getAppBaseUrl(): string {
  if (typeof window === 'undefined') return '';

  const viteApiBaseUrl = import.meta.env.VITE_API_BASE_URL;
  if (viteApiBaseUrl) {
    // Remove /api suffix if present to get clean host
    return viteApiBaseUrl.replace(/\/api\/?$/, '');
  }

  // Production/nginx mode: use current location without port
  return window.location.origin;
}

/**
 * Constructs the Flower Dashboard URL.
 * Supports VITE_FLOWER_PORT for localhost development with embedded Basic Auth credentials.
 * Uses relative path /flower/ for production with Nginx (nginx injects auth header).
 */
export function getFlowerUrl(): string {
  if (typeof window === 'undefined') return '';

  const viteFlowerPort = import.meta.env.VITE_FLOWER_PORT;
  const urlPrefix = import.meta.env.VITE_FLOWER_URL_PREFIX || 'flower';
  const cleanPrefix = urlPrefix.replace(/^\/+|\/+$/g, '');

  // Localhost mode: use specific port with embedded credentials for seamless auth
  // (works for HTTP localhost; production uses nginx auth header injection instead)
  if (viteFlowerPort) {
    const protocol = window.location.protocol;
    const host = window.location.hostname;
    const user = import.meta.env.VITE_FLOWER_USER;
    const password = import.meta.env.VITE_FLOWER_PASSWORD;
    if (user && password) {
      return `${protocol}//${user}:${password}@${host}:${viteFlowerPort}/${cleanPrefix}/`;
    }
    return `${protocol}//${host}:${viteFlowerPort}/${cleanPrefix}/`;
  }

  // Production/nginx mode: nginx injects Authorization header automatically,
  // so the browser never needs to present credentials
  return `${window.location.origin}/${cleanPrefix}/`;
}

/**
 * Constructs a video file URL.
 *
 * @deprecated Use `getMediaStreamUrl()` from '$lib/api/mediaUrl' instead.
 * This returns an unauthenticated URL that will fail for private files.
 * The new presigned URL approach is more secure and follows AWS/GCS best practices.
 *
 * @param fileId The UUID of the file
 */
export function getVideoUrl(fileId: string): string {
  const baseUrl = getAppBaseUrl();
  return `${baseUrl}/api/files/${fileId}/simple-video`;
}

/**
 * Constructs a thumbnail file URL.
 *
 * @deprecated Use `getMediaStreamUrl(fileId, 'thumbnail')` from '$lib/api/mediaUrl' instead.
 * This returns an unauthenticated URL that will fail for private files.
 *
 * @param fileId The UUID of the file
 */
export function getThumbnailUrl(fileId: string): string {
  const baseUrl = getAppBaseUrl();
  return `${baseUrl}/api/files/${fileId}/thumbnail`;
}
