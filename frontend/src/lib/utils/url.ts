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
 * Supports VITE_FLOWER_PORT for localhost development.
 * Uses relative path /flower/ for production with Nginx.
 */
export function getFlowerUrl(): string {
  if (typeof window === 'undefined') return '';
  
  const viteFlowerPort = import.meta.env.VITE_FLOWER_PORT;
  const urlPrefix = import.meta.env.VITE_FLOWER_URL_PREFIX || 'flower';
  
  // Localhost mode: use specific port if defined
  if (viteFlowerPort) {
    const protocol = window.location.protocol;
    const host = window.location.hostname;
    // Construct URL like http://localhost:5175/flower/
    // Ensure we handle urlPrefix correctly (it might or might not have leading/trailing slashes)
    const cleanPrefix = urlPrefix.replace(/^\/+|\/+$/g, '');
    return `${protocol}//${host}:${viteFlowerPort}/${cleanPrefix}/`;
  }
  
  // Production/nginx mode: use current origin with prefix
  const cleanPrefix = urlPrefix.replace(/^\/+|\/+$/g, '');
  return `${window.location.origin}/${cleanPrefix}/`;
}

/**
 * Constructs a video file URL.
 * @param fileId The UUID of the file
 */
export function getVideoUrl(fileId: string): string {
  const baseUrl = getAppBaseUrl();
  return `${baseUrl}/api/files/${fileId}/simple-video`;
}
