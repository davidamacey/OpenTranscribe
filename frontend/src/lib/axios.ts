import axios from 'axios';

// Create axios instance with consistent base URL for all environments
// This ensures the same behavior in development and production with nginx
export const axiosInstance = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
  // Reasonable timeout for API requests
  timeout: 30000, // Increased timeout for larger file uploads
  // Let Axios handle 4xx and 5xx as errors appropriately
  validateStatus: (status) => status >= 200 && status < 300,
  // Enable automatic redirect following
  maxRedirects: 5,
});

export default axiosInstance;

// Request interceptor to add authentication token
axiosInstance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    console.error('[Axios] Request error:', error);
    return Promise.reject(error);
  }
);

// Response interceptor - only log server errors
axiosInstance.interceptors.response.use(
  (response) => response,
  (error) => {
    // Only log server errors (5xx) - client errors are often expected
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
