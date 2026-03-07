import axios from 'axios';

// Create axios instance with consistent base URL for all environments
// This ensures the same behavior in development and production with nginx
export const axiosInstance = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
  // Timeout for API requests (60s covers filter queries under heavy processing load)
  timeout: 60000,
  // Let Axios handle 4xx and 5xx as errors appropriately
  validateStatus: (status) => status >= 200 && status < 300,
  // Enable automatic redirect following
  maxRedirects: 5,
  // Send cookies with every request (httpOnly auth cookies)
  withCredentials: true,
});

export default axiosInstance;

// Helper to read the csrf_token cookie (non-httpOnly, readable by JS)
// Exported for use by code that bypasses axiosInstance (e.g. raw fetch)
export function getCsrfToken(): string | undefined {
  return document.cookie
    .split(';')
    .find((c) => c.trim().startsWith('csrf_token='))
    ?.split('=')[1];
}

// Request interceptor to add CSRF token on mutating requests
axiosInstance.interceptors.request.use(
  (config) => {
    // Add CSRF token for mutating requests (double-submit pattern)
    const method = (config.method || '').toLowerCase();
    if (['post', 'put', 'patch', 'delete'].includes(method)) {
      const csrfToken = getCsrfToken();
      if (csrfToken) {
        config.headers['X-CSRF-Token'] = csrfToken;
      }
    }
    return config;
  },
  (error) => {
    console.error('[Axios] Request error:', error);
    return Promise.reject(error);
  }
);

// Token refresh state — shared across concurrent 401s so only one refresh fires
let isRefreshing = false;
let refreshQueue: Array<{
  resolve: (value?: unknown) => void;
  reject: (reason?: unknown) => void;
}> = [];

function processQueue(error: unknown | null) {
  refreshQueue.forEach((p) => (error ? p.reject(error) : p.resolve()));
  refreshQueue = [];
}

// Response interceptor — auto-refresh on 401, log 5xx
axiosInstance.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Auto-refresh: if we get a 401 and haven't already retried this request
    if (
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      // Don't try to refresh on auth endpoints themselves
      !originalRequest.url?.includes('/auth/login') &&
      !originalRequest.url?.includes('/auth/token/refresh') &&
      !originalRequest.url?.includes('/auth/me')
    ) {
      if (isRefreshing) {
        // Another refresh is in progress — queue this request
        return new Promise((resolve, reject) => {
          refreshQueue.push({ resolve, reject });
        }).then(() => axiosInstance(originalRequest));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        // Call refresh endpoint — refresh_token cookie is sent automatically
        // (it's scoped to /api/auth path)
        await axiosInstance.post('/auth/token/refresh', {});

        // Refresh succeeded — new cookies are set, retry queued requests
        processQueue(null);

        // Retry the original failed request
        return axiosInstance(originalRequest);
      } catch (refreshError) {
        // Refresh failed — session is truly expired, redirect to login
        processQueue(refreshError);

        // Lazy import to avoid circular dependency
        const { authStore } = await import('../stores/auth');
        authStore.reset();

        // Only redirect if we're not already on the login page
        if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
          window.location.href = '/login';
        }

        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    // Log server errors (5xx) - client errors are often expected
    if (error.response?.status >= 500) {
      console.error(
        `Server error for ${error.config?.url}: ${error.response.status} - ${JSON.stringify(
          error.response.data
        )}`
      );
    }
    return Promise.reject(error);
  }
);
