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
        console.log('auth.ts: User data updated in localStorage:', userData);
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
  console.log('auth.ts: initAuth - Started');
  authStore.setReady(false); 

  const resetAndFinalize = (reason: string) => {
    console.log(`auth.ts: initAuth - ${reason}. Resetting auth state.`);
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    authStore.reset(); 
    console.log('auth.ts: initAuth - Reset complete. Final state:', get(authStore));
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
        console.log('auth.ts: initAuth - User set from localStorage');
      } catch (error) {
        console.warn('auth.ts: initAuth - Failed to parse stored user. Will attempt to fetch from API.', error);
      }
    }

    if (!userDataSet) { 
      console.log('auth.ts: initAuth - Attempting to fetch user info from API.');
      const fetchedUser = await fetchUserInfo(); 
      if (!fetchedUser) {
        if (!get(authStore).ready) {
            resetAndFinalize("fetchUserInfo failed and ready state was not set by reset");
        }
        return;
      }
      console.log('auth.ts: initAuth - User info fetched from API.');
    }

    if (!get(authStore).ready) { 
        authStore.setReady(true);
    }
    console.log('auth.ts: initAuth - Successfully completed. Final state:', get(authStore));

  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    resetAndFinalize(`Unexpected error in initAuth: ${errorMessage}`);
  }
}

// Fetch current user info from API
export async function fetchUserInfo() {
  try {
    console.log('auth.ts: Fetching user info');
    // Use consistent URL format without leading slash
    const response = await axiosInstance.get('auth/me');
    console.log('auth.ts: User info response received:', response.status);
    const userData = response.data;
    
    authStore.setUser(userData);
    
    localStorage.setItem('user', JSON.stringify(userData));
    
    console.log('auth.ts: User info fetched successfully');
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
    console.log(`auth.ts: Attempting login with: ${email}`);
    
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
    
    // Add debug logging
    console.log('auth.ts: Login response received');
    
    console.log('auth.ts: Login response:', response.status);
    
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
  } catch (err) {
    console.error("auth.ts: Login error:", err);
    
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    authStore.reset();
    
    return {
      success: false,
      message: err instanceof Error ? err.message : 'Login failed'
    };
  }
}

// Register function
export async function register(email: string, fullName: string, password: string) {
  try {
    console.log('auth.ts: Attempting registration for:', email);
    
    // Use consistent URL format without leading slash
    const response = await axiosInstance.post('auth/register', {
      email,
      full_name: fullName,
      password
    });
    
    // Add debug logging
    console.log('auth.ts: Registration response received:', response.status);
    
    console.log('auth.ts: Registration successful');
    
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
  console.log('auth.ts: Logging out');
  
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  
  authStore.reset();
}
