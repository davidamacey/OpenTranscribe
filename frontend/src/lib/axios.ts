import axios from "axios";

// Create axios instance with consistent base URL for all environments
// This ensures the same behavior in development and production with nginx
export const axiosInstance = axios.create({
  baseURL: "/api",
  headers: {
    "Content-Type": "application/json",
  },
  // Reasonable timeout for API requests
  timeout: 30000, // Increased timeout for larger file uploads
  // Let Axios handle 4xx and 5xx as errors appropriately
  validateStatus: (status) => status >= 200 && status < 300,
  // Enable automatic redirect following
  maxRedirects: 5,
});

export default axiosInstance;

// Request interceptor for consistent URL handling and logging
axiosInstance.interceptors.request.use(
  (config) => {
    // Get token from localStorage
    const token = localStorage.getItem("token");

    // Add token to headers if it exists
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    const isDevMode =
      typeof window !== "undefined" && window.location.hostname === "localhost";

    // Just ensure URL starts with a slash if it's a relative path
    if (
      config.url &&
      !config.url.startsWith("/") &&
      !config.url.startsWith("http")
    ) {
      config.url = `/${config.url}`;
    }

    // If URL already starts with /api, remove the prefix since baseURL will add it
    if (config.url?.startsWith("/api/")) {
      config.url = config.url.substring(4); // Remove '/api' prefix
    }

    // Handle empty URL edge cases - if URL becomes empty after processing, set to root
    if (!config.url || config.url === "") {
      config.url = "/";
    }

    // Ensure URL starts with / if it doesn't already (for relative URLs)
    if (!config.url.startsWith("/") && !config.url.startsWith("http")) {
      config.url = `/${config.url}`;
    }

    return config;
  },
  (error) => {
    console.error("[Axios] Request error:", error);
    return Promise.reject(error);
  },
);

// Add response logging
axiosInstance.interceptors.response.use(
  (response) => {
    // Response received
    return response;
  },
  (error) => {
    // Skip logging expected 404s for optional resources
    const expectedNotFoundEndpoints = ["/llm-settings/", "/suggestions"];
    const isExpected404 =
      error.response?.status === 404 &&
      expectedNotFoundEndpoints.some(
        (endpoint) => error.config?.url?.includes(endpoint),
      );

    if (!isExpected404) {
      if (error.response) {
        console.error(
          `Error response for ${error.config?.url}: ${
            error.response.status
          } - ${JSON.stringify(error.response.data)}`,
        );
      } else if (error.request) {
        console.error(
          `No response received for ${error.config?.url}:`,
          error.request,
        );
      } else {
        console.error(
          `Error setting up request for ${error.config?.url}:`,
          error.message,
        );
      }
    }
    return Promise.reject(error);
  },
);
