<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { LLMSettingsApi, type UserLLMSettings, type ProviderDefaults, type ConnectionTestResponse } from '../../lib/api/llmSettings';
  import { toastStore } from '../../stores/toast';
  import ConfirmationModal from '../ConfirmationModal.svelte';

  export let show = false;
  export let editingConfig: UserLLMSettings | null = null;
  export let supportedProviders: ProviderDefaults[] = [];

  const dispatch = createEventDispatcher();

  // Form data
  let formData = {
    name: '',
    provider: '' as any,
    model_name: '',
    api_key: '',
    base_url: '',
    max_tokens: 4096,
    temperature: '0.3',
    is_active: true
  };

  // Form state
  let saving = false;
  let testing = false;
  let testResult: ConnectionTestResponse | null = null;
  let showApiKey = false;
  let isDirty = false;
  let originalFormData = {
    name: '',
    provider: '' as any,
    model_name: '',
    api_key: '',
    base_url: '',
    max_tokens: 4096,
    temperature: '0.3',
    is_active: true
  };

  // Ollama model discovery
  let loadingOllamaModels = false;
  let ollamaModels: Array<{
    name: string;
    size: number;
    modified_at: string;
    digest: string;
    details: any;
    display_name: string;
  }> = [];
  let ollamaModelsError = '';
  let showModelSelector = false;

  // OpenAI-compatible model discovery
  let loadingOpenAIModels = false;
  let openaiCompatibleModels: Array<{
    name: string;
    id: string;
    owned_by: string;
    created: number;
  }> = [];
  let openaiModelsError = '';
  let showOpenAIModelSelector = false;

  // Auto-fade timer for test results
  let testResultTimer: NodeJS.Timeout;
  
  // Unsaved changes modal
  let showUnsavedChangesModal = false;
  let pendingCloseAction: (() => void) | null = null;

  // Track when the modal was last opened to prevent repeated form population
  let lastEditingConfigId: string | null = null;

  // Only populate form when modal opens or editingConfig changes
  $: if (show) {
    if (editingConfig && editingConfig.id !== lastEditingConfigId) {
      populateForm(editingConfig);
      lastEditingConfigId = editingConfig.id;
    } else if (!editingConfig && lastEditingConfigId !== null) {
      resetForm();
      lastEditingConfigId = null;
    }
  } else {
    // Reset tracking when modal closes
    lastEditingConfigId = null;
  }

  // Track form changes for dirty state
  $: isDirty = JSON.stringify(formData) !== JSON.stringify(originalFormData);

  // Form validation
  $: isFormValid = (() => {
    if (!formData.name.trim() || !formData.provider || !formData.model_name.trim()) {
      return false;
    }

    // Provider-specific validation
    const providerConfig = getProviderDefaults(formData.provider);
    if (!providerConfig) return false;

    // Check if API key is required (only for new configurations)
    if (providerConfig.requires_api_key && !formData.api_key.trim() && !editingConfig) {
      return false;
    }

    // Check base URL for providers that support custom URLs
    if (providerConfig.supports_custom_url && !formData.base_url.trim()) {
      return false;
    }

    return true;
  })();

  // Connection test validation
  $: isConnectionTestValid = (() => {
    if (!formData.provider || !formData.model_name) {
      return false;
    }
    if (formData.provider === 'ollama' && !formData.base_url) {
      return false;
    }
    return true;
  })();

  // Masked API key indicator for edit mode
  const MASKED_API_KEY = '••••••••••••••••';

  function populateForm(config: UserLLMSettings) {
    formData = {
      name: config.name,
      provider: config.provider as any,
      model_name: config.model_name,
      api_key: config.has_api_key ? MASKED_API_KEY : '', // Show masked indicator if key exists
      base_url: config.base_url || '',
      max_tokens: config.max_tokens,
      temperature: config.temperature,
      is_active: config.is_active
    };
    originalFormData = { ...formData };
  }

  function resetForm() {
    formData = {
      name: '',
      provider: '' as any,
      model_name: '',
      api_key: '',
      base_url: '',
      max_tokens: 4096,
      temperature: '0.3',
      is_active: true
    };
    originalFormData = { ...formData };
    testResult = null;
    ollamaModels = [];
    ollamaModelsError = '';
    showModelSelector = false;
    openaiCompatibleModels = [];
    openaiModelsError = '';
    showOpenAIModelSelector = false;
  }


  function getProviderDefaults(provider: any): ProviderDefaults | undefined {
    return supportedProviders.find(p => p.provider === provider);
  }

  // Function to position tooltip dynamically
  function positionTooltip(event) {
    const rect = event.target.closest('.info-tooltip').getBoundingClientRect();
    const tooltip = event.target.closest('.info-tooltip');
    
    tooltip.style.setProperty('--tooltip-left', `${rect.left + rect.width / 2}px`);
    tooltip.style.setProperty('--tooltip-top', `${rect.bottom}px`);
  }

  function closeModal(force: boolean = false) {
    if (!force && isDirty) {
      // Show professional confirmation modal instead of browser alert
      pendingCloseAction = () => executeCloseModal();
      showUnsavedChangesModal = true;
      return;
    }
    
    executeCloseModal();
  }

  function executeCloseModal() {
    show = false;
    dispatch('close');
    // Reset form state
    resetForm();
  }
  
  function handleUnsavedChangesConfirm() {
    if (pendingCloseAction) {
      pendingCloseAction();
      pendingCloseAction = null;
    }
    showUnsavedChangesModal = false;
  }
  
  function handleUnsavedChangesCancel() {
    showUnsavedChangesModal = false;
    pendingCloseAction = null;
  }

  async function saveConfiguration() {
    if (!isFormValid) return;

    saving = true;

    try {
      let savedConfig;
      // Prepare data - don't send masked API key placeholder
      const dataToSave = { ...formData };
      if (dataToSave.api_key === MASKED_API_KEY) {
        // User didn't change the API key, don't send it (backend keeps existing)
        delete dataToSave.api_key;
      }

      if (editingConfig) {
        savedConfig = await LLMSettingsApi.updateSettings(editingConfig.id, dataToSave);
        toastStore.success('Configuration updated successfully', 5000);
      } else {
        savedConfig = await LLMSettingsApi.createSettings(dataToSave);
        toastStore.success('Configuration created successfully', 5000);
      }

      dispatch('saved', savedConfig);
      closeModal(true);
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to save configuration';
      toastStore.error(errorMsg, 8000);
    } finally {
      saving = false;
    }
  }

  async function testConnection() {
    if (!isConnectionTestValid) return;

    testing = true;
    testResult = null;

    try {
      // Don't send masked placeholder as actual API key
      const apiKeyToSend = (formData.api_key && formData.api_key !== MASKED_API_KEY)
        ? formData.api_key
        : undefined;
      const result = await LLMSettingsApi.testConnection({
        provider: formData.provider,
        model_name: formData.model_name,
        api_key: apiKeyToSend,
        base_url: formData.base_url || undefined,
        config_id: editingConfig?.id  // Pass config ID to use stored key
      });
      
      testResult = result;
      
      if (result.success) {
        toastStore.success(result.message, 5000);
      } else {
        toastStore.error(result.message, 8000);
      }
      
      // Auto-fade test result
      clearTimeout(testResultTimer);
      testResultTimer = setTimeout(() => testResult = null, result.success ? 5000 : 8000);
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Connection test failed';
      toastStore.error(errorMsg, 8000);
      
      testResult = {
        success: false,
        status: 'failed',
        message: errorMsg
      };
      
      // Auto-fade test result
      clearTimeout(testResultTimer);
      testResultTimer = setTimeout(() => testResult = null, 8000);
    } finally {
      testing = false;
    }
  }

  async function loadOllamaModels() {
    if (!formData.base_url) {
      ollamaModelsError = 'Please enter a base URL first';
      return;
    }

    loadingOllamaModels = true;
    ollamaModelsError = '';

    try {
      const result = await LLMSettingsApi.getOllamaModels(formData.base_url);
      if (result.success && result.models) {
        ollamaModels = result.models;
        showModelSelector = true;
      } else {
        ollamaModelsError = result.message;
      }
    } catch (err: any) {
      ollamaModelsError = err.response?.data?.detail || 'Failed to load Ollama models';
    } finally {
      loadingOllamaModels = false;
    }
  }

  function selectOllamaModel(modelName: string, model?: any) {
    formData.model_name = modelName;
    formData = { ...formData }; // Force reactivity update
    showModelSelector = false;
  }

  function formatModelSize(size: number): string {
    if (size === 0) return '';
    const gb = (size / (1024 ** 3)).toFixed(1);
    return `${gb}GB`;
  }

  async function loadOpenAICompatibleModels() {
    if (!formData.base_url) {
      openaiModelsError = 'Please enter a base URL first';
      return;
    }

    // Check if API key is required for this provider
    const providerConfig = getProviderDefaults(formData.provider);
    const hasValidApiKey = formData.api_key && formData.api_key !== MASKED_API_KEY;
    const hasStoredApiKey = editingConfig?.has_api_key;
    if (providerConfig?.requires_api_key && !hasValidApiKey && !hasStoredApiKey) {
      openaiModelsError = 'Please enter an API key first';
      return;
    }

    loadingOpenAIModels = true;
    openaiModelsError = '';

    try {
      // Don't send masked placeholder as actual API key
      const apiKeyToSend = (formData.api_key && formData.api_key !== MASKED_API_KEY)
        ? formData.api_key
        : undefined;
      const result = await LLMSettingsApi.getOpenAICompatibleModels(
        formData.base_url,
        apiKeyToSend,
        editingConfig?.id  // Pass config ID for edit mode to use stored key
      );
      if (result.success && result.models) {
        openaiCompatibleModels = result.models;
        showOpenAIModelSelector = true;
      } else {
        openaiModelsError = result.message;
      }
    } catch (err: any) {
      openaiModelsError = err.response?.data?.detail || 'Failed to load models';
    } finally {
      loadingOpenAIModels = false;
    }
  }

  function selectOpenAIModel(modelId: string) {
    formData.model_name = modelId;
    formData = { ...formData }; // Force reactivity update
    showOpenAIModelSelector = false;
  }

  // Apply provider defaults when provider changes
  $: if (formData.provider) {
    const defaults = getProviderDefaults(formData.provider);
    if (defaults && !editingConfig) {
      // Only apply defaults for new configurations
      if (!formData.base_url && defaults.default_base_url) {
        formData.base_url = defaults.default_base_url;
      }
      if (!formData.model_name && defaults.default_model) {
        formData.model_name = defaults.default_model;
      }
    }
  }

  // Modal overflow management - prevent main page scrolling
  $: {
    if (show || showUnsavedChangesModal) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
  }

  function getProviderDisplayName(provider: string): string {
    const displayNames: Record<string, string> = {
      openai: 'OpenAI',
      vllm: 'vLLM',
      ollama: 'Ollama',
      claude: 'Claude (Anthropic)',
      anthropic: 'Anthropic Claude',
      openrouter: 'OpenRouter',
      custom: 'Custom Provider'
    };
    return displayNames[provider] || provider;
  }
</script>

{#if show}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    class="modal-overlay"
    role="presentation"
    on:click={() => closeModal()}
    on:keydown={(e) => e.key === 'Escape' && closeModal()}
  >
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <!-- svelte-ignore a11y_interactive_supports_focus -->
    <div
      class="modal-content"
      role="dialog"
      aria-modal="true"
      on:click|stopPropagation
      on:keydown|stopPropagation
    >
      <div class="modal-header">
        <h3>
          {editingConfig ? 'Edit Configuration' : 'Create LLM Configuration'}
          {#if isDirty}
            <span class="unsaved-indicator" title="You have unsaved changes">•</span>
          {/if}
        </h3>
        <button class="close-button" on:click={() => closeModal()} title={isDirty ? 'Close (unsaved changes will be lost)' : 'Close'}>×</button>
      </div>

      <form on:submit|preventDefault={saveConfiguration} class="config-form">
        <!-- Configuration Name -->
        <div class="form-group">
          <label for="config-name">Configuration Name *</label>
          <input
            type="text"
            id="config-name"
            bind:value={formData.name}
            disabled={saving}
            class="form-control"
            placeholder="e.g., My Ollama Setup"
            required
          />
        </div>

        <!-- Provider Selection -->
        <div class="form-group">
          <label for="provider">Provider *</label>
          <select
            id="provider"
            bind:value={formData.provider}
            disabled={saving}
            class="form-control"
            required
          >
            <option value="">Select a provider...</option>
            {#each supportedProviders.sort((a, b) => getProviderDisplayName(a.provider).localeCompare(getProviderDisplayName(b.provider))) as provider}
              <option value={provider.provider}>{getProviderDisplayName(provider.provider)}</option>
            {/each}
          </select>
        </div>

        {#if formData.provider}
          <!-- Base URL (if supported) -->
          {#if getProviderDefaults(formData.provider)?.supports_custom_url}
            <div class="form-group">
              <label for="base-url">
                <span class="label-with-tooltip">
                  Base URL *
                  {#if formData.provider === 'vllm' || formData.provider === 'ollama'}
                    <span
                      class="info-tooltip"
                      role="tooltip"
                      data-tooltip="For local installations, use your server's IP address (e.g., http://192.168.1.10:11434). Ensure the port is open and accessible from your network."
                      on:mouseenter={positionTooltip}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M12 16v-4"/>
                        <path d="M12 8h.01"/>
                      </svg>
                    </span>
                  {:else if formData.provider === 'openrouter'}
                    <span
                      class="info-tooltip"
                      role="tooltip"
                      data-tooltip="OpenRouter is a cloud service. Use the default URL (https://openrouter.ai/api/v1) unless you have a custom endpoint."
                      on:mouseenter={positionTooltip}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M12 16v-4"/>
                        <path d="M12 8h.01"/>
                      </svg>
                    </span>
                  {/if}
                </span>
              </label>
              <input
                type="url"
                id="base-url"
                bind:value={formData.base_url}
                disabled={saving}
                class="form-control"
                placeholder={getProviderDefaults(formData.provider)?.default_base_url || 'https://api.example.com/v1'}
                required
              />
            </div>
          {/if}

          <!-- Model Selection -->
          <div class="form-group">
            <label for="model-name">
              Model Name *
              {#if formData.provider === 'ollama'}
                <button
                  type="button"
                  class="discover-models-btn"
                  on:click={loadOllamaModels}
                  disabled={loadingOllamaModels || saving || !formData.base_url}
                  title="Discover available models from Ollama instance"
                >
                  {#if loadingOllamaModels}
                    <div class="spinner-mini"></div>
                  {:else}
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <circle cx="12" cy="12" r="3"/>
                      <circle cx="12" cy="1" r="1"/>
                      <circle cx="12" cy="23" r="1"/>
                      <circle cx="4.22" cy="4.22" r="1"/>
                      <circle cx="19.78" cy="19.78" r="1"/>
                      <circle cx="1" cy="12" r="1"/>
                      <circle cx="23" cy="12" r="1"/>
                      <circle cx="4.22" cy="19.78" r="1"/>
                      <circle cx="19.78" cy="4.22" r="1"/>
                    </svg>
                  {/if}
                  Discover Models
                </button>
              {:else if formData.provider === 'openai' || formData.provider === 'vllm' || formData.provider === 'openrouter'}
                <button
                  type="button"
                  class="discover-models-btn"
                  on:click={loadOpenAICompatibleModels}
                  disabled={loadingOpenAIModels || saving || !formData.base_url || (getProviderDefaults(formData.provider)?.requires_api_key && !formData.api_key && !editingConfig?.has_api_key)}
                  title="Discover available models from API endpoint"
                >
                  {#if loadingOpenAIModels}
                    <div class="spinner-mini"></div>
                  {:else}
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <circle cx="12" cy="12" r="3"/>
                      <circle cx="12" cy="1" r="1"/>
                      <circle cx="12" cy="23" r="1"/>
                      <circle cx="4.22" cy="4.22" r="1"/>
                      <circle cx="19.78" cy="19.78" r="1"/>
                      <circle cx="1" cy="12" r="1"/>
                      <circle cx="23" cy="12" r="1"/>
                      <circle cx="4.22" cy="19.78" r="1"/>
                      <circle cx="19.78" cy="4.22" r="1"/>
                    </svg>
                  {/if}
                  Discover Models
                </button>
              {/if}
            </label>
            <input
              type="text"
              id="model-name"
              bind:value={formData.model_name}
              disabled={saving}
              class="form-control"
              placeholder={getProviderDefaults(formData.provider)?.default_model || 'Enter model name'}
              required
            />

            <!-- Ollama Model Selector -->
            {#if showModelSelector && ollamaModels.length > 0}
              <div class="model-selector">
                <h4>Available Models:</h4>
                <div class="model-list">
                  {#each ollamaModels as model}
                    <button
                      type="button"
                      class="model-item"
                      on:click={() => selectOllamaModel(model.name, model)}
                    >
                      <div class="model-info">
                        <div class="model-name">{model.display_name}</div>
                        <div class="model-details">{formatModelSize(model.size)}</div>
                      </div>
                    </button>
                  {/each}
                </div>
                <button type="button" class="close-selector" on:click={() => showModelSelector = false}>
                  Close
                </button>
              </div>
            {/if}

            {#if ollamaModelsError}
              <div class="error-text">{ollamaModelsError}</div>
            {/if}

            <!-- OpenAI-Compatible Model Selector -->
            {#if showOpenAIModelSelector && openaiCompatibleModels.length > 0}
              <div class="model-selector">
                <h4>Available Models:</h4>
                <div class="model-list">
                  {#each openaiCompatibleModels as model}
                    <button
                      type="button"
                      class="model-item"
                      on:click={() => selectOpenAIModel(model.id)}
                    >
                      <div class="model-info">
                        <div class="model-name">{model.id}</div>
                        {#if model.owned_by}
                          <div class="model-details">{model.owned_by}</div>
                        {/if}
                      </div>
                    </button>
                  {/each}
                </div>
                <button type="button" class="close-selector" on:click={() => showOpenAIModelSelector = false}>
                  Close
                </button>
              </div>
            {/if}

            {#if openaiModelsError}
              <div class="error-text">{openaiModelsError}</div>
            {/if}
          </div>

          <!-- API Key (if required) -->
          {#if getProviderDefaults(formData.provider)?.requires_api_key || (editingConfig && editingConfig.has_api_key)}
            <div class="form-group">
              <label for="api-key">
                API Key {#if !editingConfig}*{/if}
                {#if editingConfig?.has_api_key}
                  <span class="stored-indicator" title="API key is currently stored">✓ stored</span>
                {/if}
              </label>
              <div class="api-key-input">
                {#if showApiKey}
                  <input
                    type="text"
                    id="api-key"
                    bind:value={formData.api_key}
                    disabled={saving}
                    class="form-control"
                    placeholder={editingConfig?.has_api_key ? '' : 'Enter your API key'}
                    required={!editingConfig}
                  />
                {:else}
                  <input
                    type="password"
                    id="api-key"
                    bind:value={formData.api_key}
                    disabled={saving}
                    class="form-control"
                    placeholder={editingConfig?.has_api_key ? '' : 'Enter your API key'}
                    required={!editingConfig}
                  />
                {/if}
                <button 
                  type="button" 
                  class="toggle-visibility"
                  on:click={() => showApiKey = !showApiKey}
                  title={showApiKey ? 'Hide API key' : 'Show API key'}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    {#if showApiKey}
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                      <line x1="1" y1="1" x2="23" y2="23"/>
                    {:else}
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                      <circle cx="12" cy="12" r="3"/>
                    {/if}
                  </svg>
                </button>
              </div>
            </div>
          {/if}

          <!-- Advanced Settings -->
          <div class="advanced-settings">
            <h4>Advanced Settings</h4>
            
            <div class="form-row">
              <div class="form-group">
                <label for="max-tokens">Max Tokens</label>
                <input
                  type="number"
                  id="max-tokens"
                  bind:value={formData.max_tokens}
                  disabled={saving}
                  class="form-control"
                  min="100"
                  max="200000"
                />
              </div>
              
              <div class="form-group">
                <label for="temperature">Temperature</label>
                <input
                  type="text"
                  id="temperature"
                  bind:value={formData.temperature}
                  disabled={saving}
                  class="form-control"
                  placeholder="0.3"
                />
              </div>
              
            </div>
          </div>

          <!-- Test Connection -->
          <div class="test-section">
            <button
              type="button"
              class="test-connection-btn"
              on:click={testConnection}
              disabled={testing || !isConnectionTestValid}
              title="Test the connection with current settings"
            >
              {#if testing}
                <div class="spinner-mini"></div>
                Testing...
              {:else}
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="22,12 18,12 15,21 9,3 6,12 2,12"/>
                </svg>
                Test Connection
              {/if}
            </button>
            
            {#if testResult}
              <div class="test-result {testResult.success ? 'success' : 'error'}">
                {testResult.message}
                {#if testResult.response_time_ms}
                  <span class="response-time">({testResult.response_time_ms}ms)</span>
                {/if}
              </div>
            {/if}
          </div>
        {/if}

        <!-- Form Actions -->
        <div class="form-actions">
          <button type="button" class="cancel-button" on:click={() => closeModal()} disabled={saving}>
            Cancel
          </button>
          <button
            type="submit"
            class="save-button primary"
            disabled={saving || !isFormValid}
          >
            {#if saving}
              <div class="spinner-mini"></div>
              Saving...
            {:else}
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                <polyline points="17,21 17,13 7,13 7,21"/>
                <polyline points="7,3 7,8 15,8"/>
              </svg>
              {editingConfig ? 'Update Configuration' : 'Save Configuration'}
            {/if}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

<!-- Unsaved Changes Modal -->
<ConfirmationModal
  bind:isOpen={showUnsavedChangesModal}
  title="Unsaved Changes"
  message="You have unsaved changes that will be lost. Are you sure you want to continue without saving?"
  confirmText="Discard Changes"
  cancelText="Keep Editing"
  confirmButtonClass="modal-warning-button"
  cancelButtonClass="modal-primary-button"
  on:confirm={handleUnsavedChangesConfirm}
  on:cancel={handleUnsavedChangesCancel}
  on:close={handleUnsavedChangesCancel}
/>

<style>
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
  }

  .modal-content {
    background-color: var(--background-color);
    border-radius: 8px;
    max-width: 600px;
    width: 100%;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem 1.5rem 1rem 1.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .modal-header h3 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-color);
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .unsaved-indicator {
    color: var(--warning-color);
    font-size: 1.5rem;
    line-height: 1;
  }

  .close-button {
    background: none;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    color: var(--text-light);
    padding: 0;
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .close-button:hover {
    color: var(--text-color);
  }

  .config-form {
    padding: 1.5rem;
  }

  .form-group {
    margin-bottom: 1.5rem;
  }

  .form-group label {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.5rem;
    font-weight: 500;
    color: var(--text-color);
  }

  .form-control {
    width: 100%;
    padding: 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background-color: var(--input-bg);
    color: var(--text-color);
    font-size: 0.875rem;
    transition: border-color 0.2s ease;
  }

  .form-control:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .discover-models-btn {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    background: #3b82f6;
    color: white;
    border: none;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    cursor: pointer;
    transition: background-color 0.2s ease;
  }

  .discover-models-btn:hover:not(:disabled) {
    background: #2563eb;
  }

  .discover-models-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .api-key-input {
    position: relative;
  }

  .toggle-visibility {
    position: absolute;
    right: 8px;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-muted);
    padding: 4px;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .toggle-visibility:hover {
    background-color: var(--hover-color);
    color: var(--text-color);
  }

  .advanced-settings {
    margin: 1.5rem 0;
    padding: 1rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--card-bg);
  }

  .advanced-settings h4 {
    margin: 0 0 1rem;
    font-size: 1rem;
    font-weight: 500;
    color: var(--text-color);
  }

  .form-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1rem;
  }

  .model-selector {
    margin-top: 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--card-bg);
    padding: 1rem;
  }

  .model-selector h4 {
    margin: 0 0 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
  }

  .model-list {
    max-height: 200px;
    overflow-y: auto;
    margin-bottom: 0.5rem;
  }

  .model-item {
    width: 100%;
    text-align: left;
    padding: 0.5rem;
    border: 1px solid var(--border-color);
    background: var(--input-bg);
    margin-bottom: 0.25rem;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .model-item:hover {
    background: var(--hover-color);
    border-color: var(--primary-color);
  }

  .model-name {
    font-weight: 500;
    font-size: 0.875rem;
  }

  .model-details {
    font-size: 0.75rem;
    color: var(--text-muted);
  }

  .close-selector {
    background: var(--secondary-color);
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.875rem;
  }

  .test-section {
    margin: 1.5rem 0;
    padding: 1rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--card-bg);
  }

  .test-connection-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: #3b82f6;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .test-connection-btn:hover:not(:disabled) {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }
  
  .test-connection-btn:active:not(:disabled) {
    transform: translateY(0);
  }

  .test-connection-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .test-result {
    margin-top: 0.75rem;
    padding: 0.75rem;
    border-radius: 4px;
    font-size: 0.875rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .test-result.success {
    background-color: var(--success-bg);
    color: var(--success-color);
    border: 1px solid var(--success-border);
  }

  .test-result.error {
    background-color: var(--error-bg);
    color: var(--error-color);
    border: 1px solid var(--error-border);
  }

  .response-time {
    font-size: 0.75rem;
    opacity: 0.8;
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
    gap: 1rem;
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border-color);
  }

  .cancel-button {
    background: var(--surface-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .cancel-button:hover:not(:disabled) {
    background: #3b82f6;
    color: white;
    border-color: #3b82f6;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }
  
  .cancel-button:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .save-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: #3b82f6;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .save-button:hover:not(:disabled) {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }
  
  .save-button:active:not(:disabled) {
    transform: translateY(0);
  }

  .save-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .spinner-mini {
    width: 16px;
    height: 16px;
    border: 2px solid transparent;
    border-top: 2px solid currentColor;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  .error-text {
    color: var(--error-color);
    font-size: 0.75rem;
    margin-top: 0.25rem;
  }

  /* Tooltip styles */
  .info-tooltip {
    display: inline-flex;
    align-items: center;
    color: var(--text-muted);
    opacity: 0.6;
    cursor: help;
    transition: opacity 0.2s ease;
    position: relative;
    margin-left: 0.5rem;
  }

  .info-tooltip:hover {
    opacity: 1;
    color: var(--primary-color);
  }

  .info-tooltip[data-tooltip]:hover::after {
    content: attr(data-tooltip);
    position: fixed;
    left: var(--tooltip-left, 50%);
    top: var(--tooltip-top, 50%);
    background: #1a1a1a;
    color: white;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: normal;
    max-width: 320px;
    white-space: normal;
    z-index: 9999;
    line-height: 1.4;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    text-align: left;
    pointer-events: none;
    transform: translate(-50%, 8px);
  }

  label {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-weight: 500;
    font-size: 0.9rem;
    color: var(--text-color);
    margin-bottom: 0.5rem;
  }

  .label-with-tooltip {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  /* Modal button styles to ensure consistency with other modals */
  :global(.modal-primary-button) {
    background-color: #3b82f6 !important;
    color: white !important;
    border: none !important;
    padding: 0.6rem 1.2rem !important;
    border-radius: 10px !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2) !important;
  }

  :global(.modal-primary-button:hover) {
    background-color: #2563eb !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25) !important;
  }

  :global(.modal-primary-button:active) {
    transform: translateY(0) !important;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2) !important;
  }

  :global(.modal-warning-button) {
    background-color: #f59e0b !important;
    color: white !important;
    border: none !important;
    padding: 0.6rem 1.2rem !important;
    border-radius: 10px !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 4px rgba(245, 158, 11, 0.2) !important;
  }

  :global(.modal-warning-button:hover) {
    background-color: #d97706 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(245, 158, 11, 0.25) !important;
  }

  :global(.modal-warning-button:active) {
    transform: translateY(0) !important;
    box-shadow: 0 2px 4px rgba(245, 158, 11, 0.2) !important;
  }

  .stored-indicator {
    color: #10b981;
    font-size: 0.75rem;
    font-weight: 500;
    margin-left: 0.5rem;
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
  }
</style>