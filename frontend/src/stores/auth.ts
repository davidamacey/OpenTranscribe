import { writable, derived, get } from 'svelte/store';
import axios from 'axios';
import axiosInstance from '../lib/axios';

// Define user interface
export interface User {
  id: string;
  email: string;
  full_name: string;  // Added full_name field
  role: 'user' | 'admin';
  created_at: string;
  updated_at: string;
}

// Define auth store interface
export interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  ready: boolean;
  token: string | null;
}

// Define the extended auth store type with helper methods
type AuthStore = {
  subscribe: (run: (value: AuthState) => void, invalidate?: (value?: AuthState) => void) => () => void;
  set: (value: AuthState) => void;
  update: (updater: (value: AuthState) => AuthState) => void;
  // Helper methods
  setUser: (userData: User | null) => void;
  setToken: (tokenValue: string | null) => void;
  setReady: (isReady: boolean) => void;
  reset: () => void;
};

// Create a single auth store to avoid circular dependencies
const createAuthStore = (): AuthStore => {
  const store = writable<AuthState>({
    user: null,
    isAuthenticated: false,
    ready: false,
    token: null
  });
  
  return {
    ...store,
    // Helper methods to update specific parts of the state
    setUser: (userData: User | null) => {
      store.update(state => ({ ...state, user: userData }));
      // Always update localStorage when user data changes
      if (userData) {
        localStorage.setItem('user', JSON.stringify(userData));
      }
    },
    setToken: (tokenValue: string | null) => {
      store.update(state => ({ 
        ...state, 
        token: tokenValue,
        isAuthenticated: tokenValue !== null
      }));
    },
    setReady: (isReady: boolean) => {
      store.update(state => ({ ...state, ready: isReady }));
    },
    reset: () => {
      store.set({
        user: null,
        isAuthenticated: false,
        ready: true,
        token: null
      });
    }
  };
};

// Create the auth store with helper methods
export const authStore = createAuthStore();

// Create convenience derived stores
export const user = derived(authStore, $store => $store.user);
export const isAuthenticated = derived(authStore, $store => $store.isAuthenticated);
export const authReady = derived(authStore, $store => $store.ready);
export const token = derived(authStore, $store => $store.token);

// Initialize auth state from localStorage
export async function initAuth() { 
  authStore.setReady(false); 

  const resetAndFinalize = (reason: string) => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    authStore.reset(); 
  };

  try {
    const storedToken = localStorage.getItem('token');

    if (!storedToken) {
      resetAndFinalize("No token found");
      return;
    }

    try {
      const tokenParts = storedToken.split('.');
      if (tokenParts.length !== 3) throw new Error('Invalid token format');
      const tokenPayload = JSON.parse(atob(tokenParts[1]));
      if (tokenPayload.exp && tokenPayload.exp < (Date.now() / 1000)) {
        resetAndFinalize("Token expired");
        return;
      }
    } catch (e) {
      const errorMessage = e instanceof Error ? e.message : String(e);
      resetAndFinalize(`Token validation error: ${errorMessage}`);
      return;
    }

    authStore.setToken(storedToken); 

    const storedUser = localStorage.getItem('user');
    let userDataSet = false;
    if (storedUser) {
      try {
        const userData: User = JSON.parse(storedUser);
        authStore.setUser(userData);
        userDataSet = true;
      } catch (error) {
        console.warn('auth.ts: initAuth - Failed to parse stored user. Will attempt to fetch from API.', error);
      }
    }

    if (!userDataSet) { 
      const fetchedUser = await fetchUserInfo(); 
      if (!fetchedUser) {
        if (!get(authStore).ready) {
            resetAndFinalize("fetchUserInfo failed and ready state was not set by reset");
        }
        return;
      }
    }

    if (!get(authStore).ready) { 
        authStore.setReady(true);
    }

  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    resetAndFinalize(`Unexpected error in initAuth: ${errorMessage}`);
  }
}

// Fetch current user info from API
export async function fetchUserInfo() {
  try {
    const response = await axiosInstance.get('auth/me');
    const userData = response.data;
    
    authStore.setUser(userData);
    
    localStorage.setItem('user', JSON.stringify(userData));
    
    return userData;
  } catch (error: any) {
    console.error('auth.ts: Failed to fetch user info:', error);
    logout();
    return null;
  }
}

// Login function
export async function login(email: string, password: string) {
  try {
    const params = new URLSearchParams();
    params.append('username', email);
    params.append('password', password);
    
    // Use the axiosInstance which handles URL formats consistently
    // But we need to customize headers for this specific request
    const response = await axiosInstance.post('auth/login', params, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded'
      }
    });
    
    if (response.status !== 200 || !response.data.access_token) {
      console.error('auth.ts: Invalid login response');
      return { success: false, message: 'Invalid login response from server' };
    }
    
    const tokenValue = response.data.access_token;
    
    localStorage.setItem('token', tokenValue);
    
    authStore.setToken(tokenValue);
    
    await fetchUserInfo();
    
    authStore.setReady(true);
    
    return { success: true };
  } catch (err: any) {
    console.error("auth.ts: Login error:", err);
    
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    authStore.reset();
    
    // Extract meaningful error message from backend response
    let errorMessage = 'Login failed. Please check your credentials and try again.';
    
    if (err.response) {
      // Server responded with an error status
      switch (err.response.status) {
        case 401:
          errorMessage = err.response.data?.detail || 'Invalid email or password. Please try again.';
          break;
        case 400:
          errorMessage = err.response.data?.detail || 'Invalid request. Please check your input.';
          break;
        case 429:
          errorMessage = 'Too many login attempts. Please try again later.';
          break;
        case 500:
        case 502:
        case 503:
          errorMessage = 'Server error. Please try again later.';
          break;
        default:
          errorMessage = err.response.data?.detail || err.response.data?.message || 'Login failed. Please try again.';
      }
    } else if (err.request) {
      // Network error - no response received
      errorMessage = 'Unable to connect to the server. Please check your internet connection.';
    } else if (err.message) {
      // Something else happened
      errorMessage = 'An unexpected error occurred. Please try again.';
    }
    
    return {
      success: false,
      message: errorMessage
    };
  }
}

// Register function
export async function register(email: string, fullName: string, password: string) {
  try {
    // Use consistent URL format without leading slash
    const response = await axiosInstance.post('auth/register', {
      email,
      full_name: fullName,
      password
    });
    
    return { success: true, user: response.data };
  } catch (error: any) {
    console.error('auth.ts: Registration error:', error);
    
    return {
      success: false,
      message: error.response?.data?.detail || 'Registration failed. Please try again.'
    };
  }
}

// Logout function
export function logout() {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  
  authStore.reset();
}
