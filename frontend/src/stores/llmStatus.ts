/**
 * Reactive LLM Status Store
 * Manages LLM availability status across the application with WebSocket integration
 */

import { writable, derived, get } from 'svelte/store';
import type { LLMStatus } from '$lib/services/llmService';
import { llmService } from '$lib/services/llmService';

export interface LLMStatusState {
  status: LLMStatus | null;
  available: boolean;
  checking: boolean;
  lastChecked: Date | null;
}

// Initial state
const initialState: LLMStatusState = {
  status: null,
  available: false,
  checking: false,
  lastChecked: null
};

// Main LLM status store with centralized monitoring
function createLLMStatusStore() {
  const { subscribe, set, update } = writable<LLMStatusState>(initialState);
  let monitoringTimer: NodeJS.Timeout;
  let isInitialized = false;

  return {
    subscribe,
    
    // Initialize the store and start monitoring
    async initialize() {
      if (isInitialized) return;
      
      try {
        // Get initial status
        update(state => ({ ...state, checking: true }));
        const status = await llmService.getStatus(true);
        
        update(state => ({
          ...state,
          status,
          available: status.available,
          lastChecked: new Date(),
          checking: false
        }));

        // Start periodic monitoring
        this.startMonitoring();
        isInitialized = true;
        
        console.log('LLM Status Store initialized:', status);
      } catch (error) {
        console.error('Failed to initialize LLM status:', error);
        update(state => ({ ...state, checking: false }));
      }
    },

    // Start background monitoring
    startMonitoring() {
      if (monitoringTimer) clearInterval(monitoringTimer);
      
      monitoringTimer = setInterval(async () => {
        const currentState = get({ subscribe });
        if (!currentState.checking) {
          await this.refreshStatus();
        }
      }, 120000); // Check every 2 minutes
    },

    // Stop monitoring
    stopMonitoring() {
      if (monitoringTimer) {
        clearInterval(monitoringTimer);
        monitoringTimer = undefined;
      }
    },

    // Refresh status from backend
    async refreshStatus() {
      try {
        update(state => ({ ...state, checking: true }));
        const status = await llmService.getStatus(true);
        
        update(state => ({
          ...state,
          status,
          available: status.available,
          lastChecked: new Date(),
          checking: false
        }));
        
        return status;
      } catch (error) {
        console.error('Error refreshing LLM status:', error);
        update(state => ({ 
          ...state, 
          checking: false,
          available: false,
          status: {
            available: false,
            user_id: 0,
            provider: null,
            model: null,
            message: 'Unable to check LLM status'
          }
        }));
        return null;
      }
    },

    // Update the LLM status (external)
    setStatus: (status: LLMStatus) => {
      update(state => ({
        ...state,
        status,
        available: status.available,
        lastChecked: new Date(),
        checking: false
      }));
    },

    // Set checking state
    setChecking: (checking: boolean) => {
      update(state => ({ ...state, checking }));
    },

    // Clear status (reset to initial state)
    reset: () => {
      set(initialState);
      this.stopMonitoring();
      isInitialized = false;
    },

    // Handle WebSocket notifications
    handleNotification: (type: string, data: any) => {
      if (type === 'llm_settings_changed' || type === 'llm_status_changed') {
        console.log('LLM settings/status changed via WebSocket, refreshing...');
        this.refreshStatus();
      }
    }
  };
}

export const llmStatusStore = createLLMStatusStore();

// Derived stores for common use cases
export const isLLMAvailable = derived(llmStatusStore, $llmStatus => $llmStatus.available);
export const isLLMChecking = derived(llmStatusStore, $llmStatus => $llmStatus.checking);
export const llmStatusMessage = derived(llmStatusStore, $llmStatus => $llmStatus.status?.message || '');
export const llmProvider = derived(llmStatusStore, $llmStatus => $llmStatus.status?.provider || null);