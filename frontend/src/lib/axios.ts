import axios from 'axios';

// Create axios instance with consistent base URL for all environments
// This ensures the same behavior in development and production with nginx
const axiosInstance = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
  // Reasonable timeout for API requests
  timeout: 30000, // Increased timeout for larger file uploads
  // Let Axios handle 4xx and 5xx as errors appropriately
  validateStatus: status => status >= 200 && status < 300,
  // Enable automatic redirect following
  maxRedirects: 5,
});

// Request interceptor for consistent URL handling and logging
axiosInstance.interceptors.request.use(
  config => {
    // Get token from localStorage
    const token = localStorage.getItem('token');
    
    // Add token to headers if it exists
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    // Development mode logging
    const isDevMode = typeof window !== 'undefined' && window.location.hostname === 'localhost';
    
    // Log the request URL for debugging
    if (isDevMode) {
      // Axios: Processing request URL
    }
    
    // We don't need to add /api prefix since baseURL already has it
    // Just ensure URL starts with a slash if it's a relative path
    if (config.url && !config.url.startsWith('/') && !config.url.startsWith('http')) {
      config.url = `/${config.url}`;
      if (isDevMode) {
        // Ensured URL starts with slash
      }
    }
    
    // If URL already starts with /api, remove the prefix since baseURL will add it
    if (config.url?.startsWith('/api/')) {
      config.url = config.url.substring(4); // Remove '/api' prefix
      if (isDevMode) {
        // Removed duplicate /api prefix
      }
    }

    // Handle empty URL edge cases
    if (!config.url) {
      config.url = '/';
    }
    
    // Ensure URL starts with / if it doesn't already
    if (!config.url.startsWith('/') && !config.url.startsWith('http')) {
      config.url = `/${config.url}`;
      if (isDevMode) {
        // Ensured URL starts with slash
      }
    }
    
    if (isDevMode) {
      // Axios: Final URL processed
    }
    
    return config;
  },
  error => {
    console.error('[Axios] Request error:', error);
    return Promise.reject(error);
  }
);

// Add response logging
axiosInstance.interceptors.response.use(
  (response) => {
    // Response received
    return response;
  },
  (error) => {
    if (error.response) {
      console.error(`Error response for ${error.config?.url}: ${error.response.status} - ${JSON.stringify(error.response.data)}`);
    } else if (error.request) {
      console.error(`No response received for ${error.config?.url}:`, error.request);
    } else {
      console.error(`Error setting up request for ${error.config?.url}:`, error.message);
    }
    return Promise.reject(error);
  }
);

// Add request interceptor to set auth token for every request
axiosInstance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      // Ensure the token is properly set in the Authorization header
      config.headers = config.headers || {};
      
      // Special handling for file uploads - don't change Content-Type for multipart/form-data
      if (config.url && config.url.includes('files') && config.method === 'post') {
        // For file uploads, ensure we only set Authorization and don't interfere with Content-Type
        config.headers.Authorization = `Bearer ${token}`;
      } else {
        // For normal API calls
        config.headers.Authorization = `Bearer ${token}`;
      }
      
      // Log the token being used (first 10 chars only for security) in dev mode
      const isDevMode = typeof window !== 'undefined' && window.location.hostname === 'localhost';
      if (isDevMode) {
        // Using auth token for request
      }
    } else if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
      // Log when no token is available - helpful for debugging
      console.warn('No auth token available for request to: ' + config.url);
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Add response interceptor to handle common errors
axiosInstance.interceptors.response.use(
  (response) => response,
  (error) => {
    // Log detailed error information for debugging
    const isDevMode = typeof window !== 'undefined' && window.location.hostname === 'localhost';
    if (isDevMode) {
      console.error('API Error:', {
        url: error.config?.url,
        method: error.config?.method,
        status: error.response?.status,
        data: error.response?.data,
        error: error.message
      });
    }

    // Handle authentication errors
    if (error.response && error.response.status === 401) {
      console.warn('Authentication failed - clearing credentials');
      
      // Clear token if it's invalid/expired
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      
      // Only redirect to login if not already on login/register page
      const currentPath = window.location.pathname;
      if (currentPath !== '/login' && currentPath !== '/register') {
        window.location.href = '/login';
      }
    }
    
    // Let the error propagate to the component
    return Promise.reject(error);
  }
);

export default axiosInstance;
