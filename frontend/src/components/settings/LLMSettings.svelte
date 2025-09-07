<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { LLMSettingsApi, type UserLLMSettings, type ProviderDefaults, type ConnectionTestResponse } from '../../lib/api/llmSettings';
  import { toastStore } from '../../stores/toast';
  import { llmStatusStore } from '../../stores/llmStatus';

  export let onSettingsChange: (() => void) | null = null;

  // State variables
  let loading = false;
  let saving = false;
  let testing = false;
  let error = '';
  let success = '';
  
  let currentSettings: UserLLMSettings | null = null;
  let supportedProviders: ProviderDefaults[] = [];
  let hasSettings = false;
  
  // Form data
  let formData = {
    provider: '' as any,
    model_name: '',
    api_key: '',
    base_url: '',
    max_tokens: 4096,
    temperature: '0.3',
    timeout: 60,
    is_active: true
  };
  
  let showApiKey = false;
  let testResult: ConnectionTestResponse | null = null;
  let isDirty = false;
  let connectionStatus: 'unknown' | 'connected' | 'disconnected' = 'unknown';
  let statusMessage = '';
  let statusLastChecked: Date | null = null;
  let statusTimer: NodeJS.Timeout;
  let checkingStatus = false;

  // Load initial data
  onMount(async () => {
    await loadData();
  });

  // Cleanup on destroy
  onDestroy(() => {
    // Cleanup is handled by the centralized store
  });

  async function loadData() {
    loading = true;
    error = '';
    
    try {
      // Load supported providers
      const providersResponse = await LLMSettingsApi.getSupportedProviders();
      supportedProviders = providersResponse.providers;

      // Try to load user settings
      try {
        currentSettings = await LLMSettingsApi.getUserSettings();
        hasSettings = true;
        populateForm();
      } catch (err: any) {
        if (err.response?.status === 404) {
          // No settings yet, use defaults
          hasSettings = false;
          if (supportedProviders.length > 0) {
            const defaultProvider = supportedProviders[0];
            const defaults = LLMSettingsApi.getProviderDefaults(defaultProvider.provider);
            formData = { ...formData, ...defaults };
          }
        } else {
          throw err;
        }
      }
    } catch (err: any) {
      console.error('Error loading LLM settings:', err);
      error = err.response?.data?.detail || 'Failed to load LLM settings';
    } finally {
      loading = false;
    }
    
    // Check initial status if settings exist and update the central store
    if (hasSettings) {
      await checkCurrentStatus();
    }
  }

  async function checkCurrentStatus() {
    if (checkingStatus || !hasSettings) return;
    
    try {
      checkingStatus = true;
      
      // Use the saved settings endpoint since it has access to the encrypted API key
      const statusResult = await LLMSettingsApi.testCurrentSettings();
      connectionStatus = statusResult.success ? 'connected' : 'disconnected';
      statusMessage = statusResult.message;
      statusLastChecked = new Date();
      
      // Update the global store
      llmStatusStore.setStatus({
        available: statusResult.success,
        user_id: 0, // Will be set by the API response if needed
        provider: statusResult.success ? formData.provider : null,
        model: statusResult.success ? formData.model_name : null,
        message: statusResult.message
      });
      
      console.log('Settings page status check result:', statusResult);
    } catch (err: any) {
      console.error('Settings page status check error:', err);
      connectionStatus = 'disconnected';
      statusMessage = err.response?.data?.detail || 'Unable to check connection status';
      statusLastChecked = new Date();
      
      // Update the global store with error state
      llmStatusStore.setStatus({
        available: false,
        user_id: 0,
        provider: null,
        model: null,
        message: statusMessage
      });
    } finally {
      checkingStatus = false;
    }
  }

  function populateForm() {
    if (!currentSettings) return;
    
    formData = {
      provider: currentSettings.provider,
      model_name: currentSettings.model_name,
      api_key: '', // Never populate API key for security
      base_url: currentSettings.base_url || '',
      max_tokens: currentSettings.max_tokens,
      temperature: currentSettings.temperature,
      timeout: currentSettings.timeout,
      is_active: currentSettings.is_active
    };
  }

  function onProviderChange() {
    const selectedProvider = supportedProviders.find(p => p.provider === formData.provider);
    if (selectedProvider) {
      const defaults = LLMSettingsApi.getProviderDefaults(selectedProvider.provider);
      formData = {
        ...formData,
        model_name: defaults.model_name || '',
        base_url: defaults.base_url || '',
        max_tokens: defaults.max_tokens || 4096,
        temperature: defaults.temperature || '0.3',
        timeout: defaults.timeout || 60
      };
      markDirty();
    }
  }

  function markDirty() {
    isDirty = true;
    testResult = null;
  }

  async function testConnection() {
    if (!formData.provider || !formData.model_name) {
      toastStore.error('Please select a provider and model first');
      return;
    }

    testing = true;
    error = '';
    testResult = null;

    try {
      testResult = await LLMSettingsApi.testConnection({
        provider: formData.provider,
        model_name: formData.model_name,
        api_key: formData.api_key || undefined,
        base_url: formData.base_url || undefined,
        timeout: formData.timeout
      });

      if (testResult.success) {
        toastStore.success(`Connection test successful! Response time: ${testResult.response_time_ms}ms`, 5000);
        
        // Immediately update the centralized LLM status store
        llmStatusStore.setStatus({
          available: true,
          user_id: 0,
          provider: formData.provider,
          model: formData.model_name,
          message: testResult.message
        });
      } else {
        toastStore.error(testResult.message, 5000);
        
        // Update the centralized store with error state
        llmStatusStore.setStatus({
          available: false,
          user_id: 0,
          provider: null,
          model: null,
          message: testResult.message
        });
      }
    } catch (err: any) {
      console.error('Connection test failed:', err);
      const errorMsg = err.response?.data?.detail || 'Connection test failed';
      toastStore.error(errorMsg, 5000);
      
      // Update the centralized store with error state
      llmStatusStore.setStatus({
        available: false,
        user_id: 0,
        provider: null,
        model: null,
        message: errorMsg
      });
    } finally {
      testing = false;
    }
  }

  async function testSavedSettings() {
    if (!hasSettings) {
      toastStore.error('No saved settings to test. Please save settings first.');
      return;
    }

    testing = true;
    error = '';
    testResult = null;

    try {
      testResult = await LLMSettingsApi.testCurrentSettings();

      if (testResult.success) {
        toastStore.success(`Saved settings test successful! Response time: ${testResult.response_time_ms}ms`, 5000);
        
        // Update connection status and global store
        connectionStatus = 'connected';
        statusMessage = testResult.message;
        statusLastChecked = new Date();
        
        // Update the centralized LLM status store
        llmStatusStore.setStatus({
          available: true,
          user_id: 0,
          provider: currentSettings?.provider || null,
          model: currentSettings?.model_name || null,
          message: testResult.message
        });
      } else {
        toastStore.error(testResult.message, 5000);
        
        // Update connection status and global store
        connectionStatus = 'disconnected';
        statusMessage = testResult.message;
        statusLastChecked = new Date();
        
        // Update the centralized store with error state
        llmStatusStore.setStatus({
          available: false,
          user_id: 0,
          provider: null,
          model: null,
          message: testResult.message
        });
      }
    } catch (err: any) {
      console.error('Saved settings test failed:', err);
      const errorMsg = err.response?.data?.detail || 'Connection test failed';
      toastStore.error(errorMsg, 5000);
      
      // Update connection status and global store
      connectionStatus = 'disconnected';
      statusMessage = errorMsg;
      statusLastChecked = new Date();
      
      // Update the centralized store with error state
      llmStatusStore.setStatus({
        available: false,
        user_id: 0,
        provider: null,
        model: null,
        message: errorMsg
      });
    } finally {
      testing = false;
    }
  }

  async function saveSettings() {
    saving = true;
    error = '';
    success = '';

    try {
      if (hasSettings) {
        // Update existing settings
        const updateData: any = { ...formData };
        if (!formData.api_key) {
          delete updateData.api_key; // Don't update API key if empty
        }
        
        currentSettings = await LLMSettingsApi.updateSettings(updateData);
      } else {
        // Create new settings
        currentSettings = await LLMSettingsApi.createSettings(formData);
        hasSettings = true;
      }

      success = 'LLM settings saved successfully';
      isDirty = false;
      
      // Check connection status after saving and update central store
      await checkCurrentStatus();
      
      // Trigger parent component update
      if (onSettingsChange) {
        onSettingsChange();
      }
    } catch (err: any) {
      console.error('Error saving settings:', err);
      error = err.response?.data?.detail || 'Failed to save LLM settings';
    } finally {
      saving = false;
    }
  }

  async function deleteSettings() {
    if (!hasSettings || !confirm('Are you sure you want to delete your LLM settings? You will revert to system defaults.')) {
      return;
    }

    saving = true;
    error = '';

    try {
      await LLMSettingsApi.deleteSettings();
      currentSettings = null;
      hasSettings = false;
      isDirty = false;
      success = 'LLM settings deleted. Using system defaults.';
      
      // Reset status and global store
      connectionStatus = 'unknown';
      statusMessage = '';
      statusLastChecked = null;
      
      // Reset global LLM status store
      llmStatusStore.reset();
      
      // Reset form to defaults
      if (supportedProviders.length > 0) {
        const defaultProvider = supportedProviders[0];
        const defaults = LLMSettingsApi.getProviderDefaults(defaultProvider.provider);
        formData = { ...formData, ...defaults, api_key: '' };
      }
      
      if (onSettingsChange) {
        onSettingsChange();
      }
    } catch (err: any) {
      console.error('Error deleting settings:', err);
      error = err.response?.data?.detail || 'Failed to delete LLM settings';
    } finally {
      saving = false;
    }
  }

  function getProviderDisplayName(provider: string): string {
    return LLMSettingsApi.getProviderDisplayName(provider as any);
  }

  function isFormValid(): boolean {
    return !!(formData.provider && formData.model_name);
  }
</script>

<div class="llm-settings">
  <div class="settings-header">
    <h3>LLM Provider Configuration</h3>
    <p>Configure your preferred Large Language Model provider for AI summarization and speaker identification.</p>
  </div>

  {#if success}
    <div class="message success">
      {success}
    </div>
  {/if}

  {#if error}
    <div class="message error">
      {error}
    </div>
  {/if}

  <!-- Connection Status Badge -->
  {#if hasSettings && connectionStatus !== 'unknown'}
    <div class="connection-status {connectionStatus}" title={statusMessage}>
      <div class="status-indicator">
        {#if checkingStatus}
          <div class="spinner-mini"></div>
        {:else if connectionStatus === 'connected'}
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
            <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
          </svg>
        {:else}
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"/>
          </svg>
        {/if}
      </div>
      <span class="status-text">
        {#if checkingStatus}
          Checking...
        {:else if connectionStatus === 'connected'}
          Connected
        {:else}
          Disconnected
        {/if}
      </span>
      {#if statusLastChecked}
        <span class="status-timestamp">
          {statusLastChecked.toLocaleTimeString()}
        </span>
      {/if}
    </div>
  {/if}

  {#if loading}
    <div class="loading">Loading LLM settings...</div>
  {:else}
    <form on:submit|preventDefault={saveSettings} class="llm-form">
      <!-- Provider Selection -->
      <div class="form-group">
        <label for="provider">LLM Provider *</label>
        <select
          id="provider"
          bind:value={formData.provider}
          on:change={onProviderChange}
          disabled={saving}
          class="form-control"
        >
          <option value="">Select a provider...</option>
          {#each supportedProviders as provider}
            <option value={provider.provider}>
              {getProviderDisplayName(provider.provider)} - {provider.description}
            </option>
          {/each}
        </select>
      </div>

      {#if formData.provider}
        <!-- Model Name -->
        <div class="form-group">
          <label for="model_name">Model Name *</label>
          <input
            type="text"
            id="model_name"
            bind:value={formData.model_name}
            on:input={markDirty}
            disabled={saving}
            class="form-control"
            placeholder="e.g., gpt-4o-mini, llama2:7b-chat"
            required
          />
        </div>

        <!-- API Key (if required) -->
        {#if supportedProviders.find(p => p.provider === formData.provider)?.requires_api_key}
          <div class="form-group">
            <label for="api_key">
              API Key
              {#if currentSettings?.has_api_key}
                <span class="api-key-status">(Currently stored - leave blank to keep existing)</span>
              {/if}
            </label>
            <div class="api-key-input">
              {#if showApiKey}
                <input
                  type="text"
                  id="api_key"
                  bind:value={formData.api_key}
                  on:input={markDirty}
                  disabled={saving}
                  class="form-control"
                  placeholder="Enter your API key..."
                />
              {:else}
                <input
                  type="password"
                  id="api_key"
                  bind:value={formData.api_key}
                  on:input={markDirty}
                  disabled={saving}
                  class="form-control"
                  placeholder="Enter your API key..."
                />
              {/if}
              <button
                type="button"
                class="toggle-visibility"
                on:click={() => showApiKey = !showApiKey}
                title={showApiKey ? 'Hide API key' : 'Show API key'}
              >
{#if showApiKey}
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
                    <line x1="1" y1="1" x2="23" y2="23"></line>
                  </svg>
                {:else}
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                    <circle cx="12" cy="12" r="3"></circle>
                  </svg>
                {/if}
              </button>
            </div>
          </div>
        {/if}

        <!-- Custom Base URL -->
        {#if supportedProviders.find(p => p.provider === formData.provider)?.supports_custom_url}
          <div class="form-group">
            <label for="base_url">Base URL</label>
            <input
              type="url"
              id="base_url"
              bind:value={formData.base_url}
              on:input={markDirty}
              disabled={saving}
              class="form-control"
              placeholder="e.g., http://localhost:8012/v1"
            />
            <small class="form-text">Custom endpoint URL for your LLM provider</small>
          </div>
        {/if}

        <!-- Test Connection Buttons (for all providers) -->
        <div class="form-group">
          <div class="test-section">
            <div class="test-buttons">
              <button
                type="button"
                class="test-button"
                on:click={testConnection}
                disabled={testing || saving || !isFormValid()}
              >
                {#if testing}
                  <svg class="spinner-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 12a9 9 0 11-6.219-8.56"/>
                  </svg>
                  Testing Connection...
                {:else}
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="23 4 23 10 17 10"></polyline>
                    <polyline points="1 20 1 14 7 14"></polyline>
                    <path d="m3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                  </svg>
                  Test Connection
                {/if}
              </button>

              {#if hasSettings}
                <button
                  type="button"
                  class="test-button secondary"
                  on:click={testSavedSettings}
                  disabled={testing || saving}
                  title="Test using your saved settings"
                >
                  {#if testing}
                    <svg class="spinner-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M21 12a9 9 0 11-6.219-8.56"/>
                    </svg>
                    Testing Saved...
                  {:else}
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="23 4 23 10 17 10"></polyline>
                      <polyline points="1 20 1 14 7 14"></polyline>
                      <path d="m3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                    </svg>
                    Test Saved Settings
                  {/if}
                </button>
              {/if}
            </div>

            {#if testResult}
              <div class="test-result {testResult.success ? 'success' : 'error'}">
                {testResult.message}
                {#if testResult.success && testResult.response_time_ms}
                  <div class="response-time">Response time: {testResult.response_time_ms}ms</div>
                {/if}
              </div>
            {/if}
          </div>
        </div>

        <!-- Advanced Settings -->
        <details class="advanced-settings">
          <summary>Advanced Settings</summary>
          
          <div class="form-row">
            <div class="form-group">
              <label for="max_tokens">Max Tokens</label>
              <input
                type="number"
                id="max_tokens"
                bind:value={formData.max_tokens}
                on:input={markDirty}
                disabled={saving}
                class="form-control"
                min="1"
                max="200000"
              />
            </div>

            <div class="form-group">
              <label for="temperature">Temperature</label>
              <input
                type="number"
                id="temperature"
                bind:value={formData.temperature}
                on:input={markDirty}
                disabled={saving}
                class="form-control"
                min="0"
                max="2"
                step="0.1"
              />
            </div>

            <div class="form-group">
              <label for="timeout">Timeout (seconds)</label>
              <input
                type="number"
                id="timeout"
                bind:value={formData.timeout}
                on:input={markDirty}
                disabled={saving}
                class="form-control"
                min="5"
                max="600"
              />
            </div>
          </div>

          <div class="form-group checkbox-group">
            <label class="checkbox-container">
              <input
                type="checkbox"
                bind:checked={formData.is_active}
                on:change={markDirty}
                disabled={saving}
              />
              <span class="checkbox-text">Enable LLM (summarize and speaker ID)</span>
            </label>
            <small class="form-text">When disabled, AI summarization and speaker identification features will not be available. Transcription will still work normally.</small>
          </div>
        </details>


        <!-- Form Actions -->
        <div class="form-actions">
          <button
            type="submit"
            class="save-button primary"
            disabled={saving || !isFormValid()}
          >
            {#if saving}
              <div class="spinner"></div>
              Saving...
            {:else}
              Save Configuration
            {/if}
          </button>

          {#if hasSettings}
            <button
              type="button"
              class="delete-button danger"
              on:click={deleteSettings}
              disabled={saving}
            >
              Delete Settings
            </button>
          {/if}
        </div>
      {/if}
    </form>
  {/if}
</div>

<style>
  .llm-settings {
    max-width: 600px;
  }

  .settings-header h3 {
    margin: 0 0 0.5rem 0;
    color: var(--text-color);
  }

  .settings-header p {
    margin: 0 0 1.5rem 0;
    color: var(--text-light);
    font-size: 0.9rem;
  }

  .message {
    padding: 0.75rem 1rem;
    border-radius: 4px;
    margin-bottom: 1rem;
    font-size: 0.9rem;
  }

  .message.success {
    background-color: rgba(16, 185, 129, 0.1);
    color: var(--success-color);
    border: 1px solid rgba(16, 185, 129, 0.2);
  }

  .message.error {
    background-color: rgba(239, 68, 68, 0.1);
    color: var(--error-color);
    border: 1px solid rgba(239, 68, 68, 0.2);
  }

  .loading {
    text-align: center;
    padding: 2rem;
    color: var(--text-light);
  }

  .llm-form {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .form-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1rem;
  }

  label {
    font-weight: 500;
    font-size: 0.9rem;
    color: var(--text-color);
  }

  .form-control {
    padding: 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 0.9rem;
    background-color: var(--background-color);
    color: var(--text-color);
    transition: border-color 0.2s ease;
  }

  .form-control:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
  }

  .form-control:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .form-text {
    font-size: 0.8rem;
    color: var(--text-light);
    margin-top: 0.25rem;
  }

  .checkbox-group {
    margin-bottom: 1rem !important;
    padding-top: 1rem !important;
  }

  .checkbox-container {
    display: inline-flex !important;
    align-items: center !important;
    gap: 6px !important;
    cursor: pointer !important;
    font-weight: 500 !important;
    margin: 0 !important;
    padding: 0 !important;
    width: auto !important;
    max-width: none !important;
    justify-content: flex-start !important;
  }

  .checkbox-container input[type="checkbox"] {
    margin: 0 !important;
    padding: 0 !important;
    cursor: pointer !important;
    flex-shrink: 0 !important;
    width: auto !important;
  }

  .checkbox-text {
    margin: 0 !important;
    padding: 0 !important;
    line-height: 1.2 !important;
    display: inline !important;
    width: auto !important;
  }

  .api-key-status {
    font-weight: normal;
    color: var(--success-color);
    font-size: 0.8rem;
  }

  .api-key-input {
    display: flex;
    gap: 0.5rem;
  }

  .api-key-input .form-control {
    flex: 1;
  }

  .toggle-visibility {
    padding: 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background-color: var(--surface-color);
    cursor: pointer;
    font-size: 1rem;
  }

  .toggle-visibility:hover {
    background-color: var(--hover-bg);
  }

  .input-with-test {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  .input-with-test .form-control {
    flex: 1;
  }

  .test-icon-button {
    padding: 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background-color: var(--surface-color);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
  }

  .test-icon-button:hover:not(:disabled) {
    background-color: var(--primary-color);
    border-color: var(--primary-color);
    color: white;
  }

  .test-icon-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .spinner-icon {
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .advanced-settings {
    border: 1px solid var(--border-color);
    border-radius: 4px;
    padding: 1rem;
  }

  .advanced-settings summary {
    cursor: pointer;
    font-weight: 500;
    margin-bottom: 1rem;
    user-select: none;
  }

  .test-section {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    padding: 1rem;
    background-color: var(--surface-color);
    border-radius: 4px;
    border: 1px solid var(--border-color);
  }

  .test-buttons {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  .test-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.25rem;
    border: 1px solid var(--primary-color);
    border-radius: 4px;
    background-color: transparent;
    color: var(--primary-color);
    cursor: pointer;
    font-weight: 500;
    transition: all 0.2s ease;
  }

  .test-button:hover:not(:disabled) {
    background-color: var(--primary-color);
    color: white;
  }

  .test-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .test-button.secondary {
    background-color: transparent;
    border: 1px solid var(--border-color);
    color: var(--text-color);
  }

  .test-button.secondary:hover:not(:disabled) {
    background-color: var(--hover-bg);
    border-color: var(--primary-color);
  }

  .test-result {
    padding: 0.75rem;
    border-radius: 4px;
    font-size: 0.9rem;
  }

  .test-result.success {
    background-color: rgba(16, 185, 129, 0.1);
    color: var(--success-color);
    border: 1px solid rgba(16, 185, 129, 0.2);
  }

  .test-result.error {
    background-color: rgba(239, 68, 68, 0.1);
    color: var(--error-color);
    border: 1px solid rgba(239, 68, 68, 0.2);
  }

  .response-time {
    font-size: 0.8rem;
    margin-top: 0.25rem;
    opacity: 0.8;
  }

  .form-actions {
    display: flex;
    gap: 1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border-color);
  }

  .save-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    border: none;
    border-radius: 4px;
    background-color: var(--primary-color);
    color: white;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .save-button:hover:not(:disabled) {
    background-color: var(--primary-dark);
  }

  .save-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .delete-button {
    padding: 0.75rem 1.25rem;
    border: 1px solid var(--error-color);
    border-radius: 4px;
    background-color: transparent;
    color: var(--error-color);
    cursor: pointer;
    font-weight: 500;
    transition: all 0.2s ease;
  }

  .delete-button:hover:not(:disabled) {
    background-color: var(--error-color);
    color: white;
  }

  .delete-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top: 2px solid currentColor;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  @media (max-width: 768px) {
    .form-row {
      grid-template-columns: 1fr;
    }

    .form-actions {
      flex-direction: column;
    }

    .api-key-input {
      flex-direction: column;
    }

    .test-buttons {
      flex-direction: column;
    }
  }

  /* Connection Status Badge */
  .connection-status {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    border-radius: 8px;
    font-size: 0.9rem;
    margin: 1rem 0;
    border: 1px solid;
  }

  .connection-status.connected {
    background-color: var(--success-bg, #f0f9f0);
    border-color: var(--success-border, #c6f6c6);
    color: var(--success-text, #16a34a);
  }

  .connection-status.disconnected {
    background-color: var(--error-bg, #fef2f2);
    border-color: var(--error-border, #fecaca);
    color: var(--error-text, #dc2626);
  }

  .status-indicator {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .status-text {
    font-weight: 500;
    flex-grow: 1;
  }

  .status-timestamp {
    font-size: 0.8rem;
    opacity: 0.7;
    font-weight: normal;
  }

  .spinner-mini {
    width: 12px;
    height: 12px;
    border: 2px solid rgba(0, 0, 0, 0.1);
    border-top: 2px solid currentColor;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }
</style>