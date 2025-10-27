<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { LLMSettingsApi, type UserLLMSettings, type ProviderDefaults, type ConnectionTestResponse, type UserLLMConfigurationsList } from '../../lib/api/llmSettings';
  import ConfirmationModal from '../ConfirmationModal.svelte';
  import LLMConfigModal from './LLMConfigModal.svelte';
  import { toastStore } from '../../stores/toast';
  import { llmStatusStore } from '../../stores/llmStatus';

  export let onSettingsChange: (() => void) | null = null;

  // State variables
  let loading = false;
  let saving = false;
  let testing = false;

  let currentSettings: UserLLMSettings | null = null;
  let supportedProviders: ProviderDefaults[] = [];
  let hasSettings = false;
  let savedConfigurations: UserLLMSettings[] = [];
  let activeConfigurationId: string | null = null;
  let editingConfiguration: UserLLMSettings | null = null;

  // Modal state
  let showConfigModal = false;

  // Confirmation modals
  let showDeleteConfigModal = false;
  let configToDelete: UserLLMSettings | null = null;
  let showDeleteAllModal = false;

  // Connection status for active configuration
  let connectionStatus: 'unknown' | 'connected' | 'disconnected' = 'unknown';
  let statusMessage = '';
  let statusLastChecked: Date | null = null;
  let checkingStatus = false;

  // Load initial data
  onMount(async () => {
    await loadData();
  });

  // Cleanup on destroy
  onDestroy(() => {
    // Cleanup if needed
  });

  async function loadData() {
    loading = true;

    try {
      // Load supported providers
      const providersResponse = await LLMSettingsApi.getSupportedProviders();
      supportedProviders = providersResponse.providers;

      // Try to load user configurations
      try {
        const configurationsResponse = await LLMSettingsApi.getUserConfigurations();
        savedConfigurations = configurationsResponse.configurations;
        activeConfigurationId = configurationsResponse.active_configuration_id || null;

        if (activeConfigurationId && savedConfigurations.length > 0) {
          currentSettings = savedConfigurations.find(c => c.id === activeConfigurationId) || null;
          hasSettings = true;

          // Check initial status if settings exist and update the central store
          await checkCurrentStatus();
        } else {
          currentSettings = null;
          hasSettings = false;
          llmStatusStore.reset();
        }
      } catch (err: any) {
        // Handle cases where there are no configurations gracefully
        if (err.response?.status !== 404 && err.response?.status !== 403) {
          throw err;
        }
        // Set empty state for 404 (not found) or 403 (forbidden/no configs)
        currentSettings = null;
        hasSettings = false;
        llmStatusStore.reset();
      }
    } catch (err: any) {
      // Only show error for serious provider loading issues
      console.error('Error loading LLM providers:', err);
      // Only show error if it's not related to missing user configurations
      if (!err.message?.includes('LLM') && !err.response?.data?.detail?.includes('configuration')) {
        const errorMsg = err.response?.data?.detail || 'Failed to load LLM providers';
        toastStore.error(errorMsg, 5000);
      }
    } finally {
      loading = false;
    }
  }

  async function checkCurrentStatus() {
    if (!hasSettings || !activeConfigurationId) {
      connectionStatus = 'unknown';
      statusMessage = '';
      return;
    }

    checkingStatus = true;

    try {
      const result = await LLMSettingsApi.testCurrentSettings();

      if (result.success) {
        connectionStatus = 'connected';
        statusMessage = result.message;
        statusLastChecked = new Date();

        // Refresh the global LLM status store from backend
        await llmStatusStore.refreshStatus();
      } else {
        connectionStatus = 'disconnected';
        statusMessage = result.message;
        statusLastChecked = new Date();

        // Refresh the global LLM status store from backend
        await llmStatusStore.refreshStatus();
      }
    } catch (err: any) {
      connectionStatus = 'disconnected';
      const errorMsg = err.response?.data?.detail || 'Connection test failed';
      statusMessage = errorMsg;
      statusLastChecked = new Date();

      // Refresh the global LLM status store from backend
      await llmStatusStore.refreshStatus();
    } finally {
      checkingStatus = false;
    }
  }

  // Modal management functions
  function openCreateModal() {
    showConfigModal = true;
    editingConfiguration = null;
  }

  function openEditModal(config: UserLLMSettings) {
    showConfigModal = true;
    editingConfiguration = config;
  }

  function editConfiguration(config: UserLLMSettings) {
    openEditModal(config);
  }

  async function activateConfiguration(configId: number) {
    if (configId === activeConfigurationId) {
      toastStore.success('Configuration is already active', 3000);
      return;
    }

    saving = true;

    try {
      await LLMSettingsApi.setActiveConfiguration(configId);

      // Update local state
      activeConfigurationId = configId;
      currentSettings = savedConfigurations.find(c => c.id === configId) || null;
      hasSettings = true;

      // Check status of newly activated configuration
      await checkCurrentStatus();

      toastStore.success('Configuration activated successfully', 5000);

      // Trigger parent component update
      if (onSettingsChange) {
        onSettingsChange();
      }
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to activate configuration';
      toastStore.error(errorMsg, 5000);
    } finally {
      saving = false;
    }
  }

  async function testSavedConfiguration(config: UserLLMSettings): Promise<void> {
    testing = true;

    try {
      const result = await LLMSettingsApi.testConfiguration(config.id);

      if (result.success) {
        toastStore.success(`${config.name}: ${result.message}`, 5000);
      } else {
        toastStore.error(`${config.name}: ${result.message}`, 8000);
      }
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Connection test failed';
      toastStore.error(`${config.name}: ${errorMsg}`, 8000);
    } finally {
      testing = false;
    }
  }

  function confirmDeleteConfiguration(config: UserLLMSettings) {
    configToDelete = config;
    showDeleteConfigModal = true;
  }

  async function deleteConfiguration() {
    if (!configToDelete) return;

    saving = true;

    try {
      await LLMSettingsApi.deleteConfiguration(configToDelete.id);

      // Remove from saved configurations
      savedConfigurations = savedConfigurations.filter(c => c.id !== configToDelete.id);

      // If this was the active configuration, clear it
      if (configToDelete.id === activeConfigurationId) {
        activeConfigurationId = null;
        currentSettings = null;
        hasSettings = false;

        // Reset global LLM status store
        llmStatusStore.reset();
      }

      toastStore.success(`Configuration "${configToDelete.name}" deleted successfully`, 5000);

      configToDelete = null;
      showDeleteConfigModal = false;

      // Trigger parent component update
      if (onSettingsChange) {
        onSettingsChange();
      }
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to delete configuration';
      toastStore.error(errorMsg, 5000);
    } finally {
      saving = false;
    }
  }

  function confirmDeleteAll() {
    showDeleteAllModal = true;
  }

  async function deleteAllSettings() {
    if (!hasSettings) {
      toastStore.error('No settings to delete');
      return;
    }

    saving = true;

    try {
      await LLMSettingsApi.deleteSettings();

      // Reset all local state
      savedConfigurations = [];
      activeConfigurationId = null;
      currentSettings = null;
      hasSettings = false;
      connectionStatus = 'unknown';
      statusMessage = '';
      statusLastChecked = null;

      // Reset global LLM status store
      llmStatusStore.reset();

      toastStore.success('All LLM configurations deleted successfully', 5000);

      showDeleteAllModal = false;

      // Trigger parent component update
      if (onSettingsChange) {
        onSettingsChange();
      }
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to delete LLM settings';
      toastStore.error(errorMsg, 5000);
    } finally {
      saving = false;
    }
  }

  function handleConfigSaved(event: CustomEvent<UserLLMSettings>) {
    const savedConfig = event.detail;

    // Update the configurations list
    if (editingConfiguration) {
      // Update existing configuration
      const index = savedConfigurations.findIndex(c => c.id === savedConfig.id);
      if (index !== -1) {
        savedConfigurations[index] = savedConfig;
        savedConfigurations = [...savedConfigurations];
      }
    } else {
      // Add new configuration
      savedConfigurations = [...savedConfigurations, savedConfig];
    }

    // Update hasSettings flag
    hasSettings = savedConfigurations.length > 0;

    // Trigger parent component update
    if (onSettingsChange) {
      onSettingsChange();
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

  // Modal overflow management - prevent main page scrolling when any modal is open
  $: {
    if (showConfigModal || showDeleteConfigModal || showDeleteAllModal) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
  }

  // Handle keyboard shortcuts for modals
  let keydownHandler: ((event: KeyboardEvent) => void) | null = null;

  $: {
    // Clean up previous listener if exists
    if (keydownHandler) {
      document.removeEventListener('keydown', keydownHandler);
      keydownHandler = null;
    }

    // Add new listener if modal is open
    if (showConfigModal) {
      keydownHandler = (event: KeyboardEvent) => {
        if (event.key === 'Escape') {
          showConfigModal = false;
        }
      };
      document.addEventListener('keydown', keydownHandler);
    }
  }
</script>

<div class="llm-settings">
  {#if loading}
    <div class="loading">Loading LLM settings...</div>
  {:else}
    <!-- Saved Configurations -->
    <div class="saved-configs-section">
      <div class="section-header">
        <h4>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
          </svg>
          Saved Configurations
        </h4>
        {#if savedConfigurations.length > 0}
          <button class="create-config-button" on:click={openCreateModal} title="Create new LLM configuration">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Create Configuration
          </button>
        {/if}
      </div>

      {#if savedConfigurations.length > 0}
        <div class="config-list">
          {#each savedConfigurations as config}
            <div class="config-item" class:active={config.id === activeConfigurationId}>
              <div class="config-info">
                <div class="config-name">{config.name}</div>
                <div class="config-provider">{getProviderDisplayName(config.provider)} • {config.model_name}</div>
                {#if config.base_url}
                  <div class="config-url">{config.base_url}</div>
                {/if}
              </div>

              <div class="config-actions">
                {#if config.id === activeConfigurationId}
                  <div class="config-status currently-active" title={statusMessage}>
                    <div class="status-indicator">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20,6 9,17 4,12"/>
                      </svg>
                    </div>
                    <span class="status-text">Currently Active</span>
                  </div>
                {:else}
                  <button
                    class="activate-button"
                    on:click={() => activateConfiguration(config.id)}
                    disabled={saving}
                    title="Make this configuration active"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
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
                    Activate
                  </button>
                {/if}

                <button
                  class="test-connection-button"
                  on:click={() => testSavedConfiguration(config)}
                  disabled={testing}
                  title={`Test connection for ${config.name}`}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="1 4 1 10 7 10"/>
                    <polyline points="23 20 23 14 17 14"/>
                    <path d="m20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
                  </svg>
                </button>

                <button
                  class="edit-button"
                  on:click={() => editConfiguration(config)}
                  disabled={saving}
                  title="Edit this configuration"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                    <path d="m18.5 2.5 a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                  </svg>
                </button>

                <button
                  class="delete-config-button"
                  on:click={() => confirmDeleteConfiguration(config)}
                  disabled={saving}
                  title={`Delete configuration: ${config.name}`}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="3,6 5,6 21,6"/>
                    <path d="m19,6v14a2,2 0 0,1 -2,2H7a2,2 0 0,1 -2,-2V6m3,0V4a2,2 0 0,1 2,-2h4a2,2 0 0,1 2,2v2"/>
                    <line x1="10" y1="11" x2="10" y2="17"/>
                    <line x1="14" y1="11" x2="14" y2="17"/>
                  </svg>
                </button>
              </div>
            </div>
          {/each}
        </div>

        <!-- Delete All Button -->
        {#if savedConfigurations.length > 0}
          <div class="delete-all-section">
            <button
              class="delete-all-button"
              on:click={confirmDeleteAll}
              disabled={saving}
              title="Delete all saved configurations (LLM features will be disabled)"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3,6 5,6 21,6"/>
                <path d="m19,6v14a2,2 0 0,1 -2,2H7a2,2 0 0,1 -2,-2V6m3,0V4a2,2 0 0,1 2,-2h4a2,2 0 0,1 2,2v2"/>
                <line x1="10" y1="11" x2="10" y2="17"/>
                <line x1="14" y1="11" x2="14" y2="17"/>
              </svg>
              Delete All Configurations
            </button>
          </div>
        {/if}
      {:else}
        <div class="empty-state">
          <div class="empty-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14.828 14.828a4 4 0 0 1-5.656 0M9 10h.01M15 10h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 0 1-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/>
            </svg>
          </div>
          <h4>No LLM Configurations</h4>
          <p>Create your first LLM configuration to enable AI summarization and speaker identification.</p>
          <button class="create-first-config-btn" on:click={openCreateModal}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Create First Configuration
          </button>
        </div>
      {/if}
    </div>
  {/if}
</div>

<!-- LLM Configuration Modal -->
<LLMConfigModal
  bind:show={showConfigModal}
  editingConfig={editingConfiguration}
  {supportedProviders}
  on:saved={handleConfigSaved}
  on:close={() => {
    showConfigModal = false;
    editingConfiguration = null;
  }}
/>

<!-- Confirmation Modals -->
<ConfirmationModal
  bind:isOpen={showDeleteConfigModal}
  title="Delete Configuration"
  message={configToDelete ? `Are you sure you want to delete the configuration "${configToDelete.name}"? This action cannot be undone.` : ''}
  confirmText="Delete"
  cancelText="Cancel"
  confirmButtonClass="modal-delete-button"
  cancelButtonClass="modal-cancel-button"
  on:confirm={deleteConfiguration}
  on:cancel={() => { configToDelete = null; showDeleteConfigModal = false; }}
  on:close={() => { configToDelete = null; showDeleteConfigModal = false; }}
/>

<ConfirmationModal
  bind:isOpen={showDeleteAllModal}
  title="Delete All Configurations"
  message="Are you sure you want to delete all LLM configurations? This will disable AI features (summarization and speaker identification) until you create a new configuration. This action cannot be undone."
  confirmText="Delete All"
  cancelText="Cancel"
  confirmButtonClass="modal-delete-button"
  cancelButtonClass="modal-cancel-button"
  on:confirm={deleteAllSettings}
  on:cancel={() => showDeleteAllModal = false}
  on:close={() => showDeleteAllModal = false}
/>

<style>
  .llm-settings {
    max-width: 800px;
    margin: 0 auto;
  }

  .loading {
    text-align: center;
    padding: 3rem;
    color: var(--text-muted);
    font-size: 0.8125rem;
  }

  .saved-configs-section {
    margin-bottom: 2rem;
  }

  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .section-header h4 {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0;
    font-size: 1.125rem;
    font-weight: 500;
    color: var(--text-color);
  }

  .create-config-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: #3b82f6;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.8125rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .create-config-button:hover {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .create-config-button:active {
    transform: translateY(0);
  }

  .config-list {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .config-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--card-bg);
    transition: all 0.2s ease;
  }

  .config-item.active {
    border-color: var(--primary-color);
    background: var(--primary-bg);
  }

  .config-item:hover:not(.active) {
    border-color: var(--border-hover);
    background: var(--hover-color);
  }

  .config-info {
    flex: 1;
    min-width: 0;
  }

  .config-name {
    font-weight: 500;
    color: var(--text-color);
    font-size: 0.8125rem;
    margin-bottom: 0.25rem;
  }

  .config-provider {
    font-size: 0.8rem;
    color: var(--text-muted);
    margin-bottom: 0.25rem;
  }

  .config-url {
    font-size: 0.75rem;
    color: var(--text-muted);
    font-family: var(--font-mono);
    opacity: 0.7;
  }

  .config-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
  }

  .config-status {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.375rem 0.75rem;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 500;
    width: fit-content;
  }

  .config-status.currently-active {
    background-color: var(--success-bg);
    color: var(--success-color);
    border: 1px solid var(--success-border);
  }

  .status-indicator {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .activate-button, .edit-button, .delete-config-button, .test-connection-button {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.5rem 0.75rem;
    border-radius: 4px;
    font-size: 0.8rem;
    cursor: pointer;
    transition: all 0.2s ease;
    border: 1px solid;
    height: 32px;
    box-sizing: border-box;
  }

  .activate-button {
    background-color: var(--success-color);
    border-color: var(--success-color);
    color: white;
    padding: 0.5rem 0.5rem;
  }

  .activate-button:hover:not(:disabled) {
    background-color: #059669;
    border-color: #059669;
  }

  .test-connection-button {
    background-color: transparent;
    border-color: #3b82f6;
    color: #3b82f6;
  }

  .test-connection-button:hover:not(:disabled) {
    background-color: #3b82f6;
    border-color: #3b82f6;
    color: white;
  }

  .edit-button {
    background-color: transparent;
    border-color: var(--border-color);
    color: var(--text-color);
  }

  .edit-button:hover:not(:disabled) {
    background-color: #3b82f6;
    border-color: #3b82f6;
    color: white;
  }

  .delete-config-button {
    background-color: transparent;
    border-color: var(--error-color);
    color: var(--error-color);
  }

  .delete-config-button:hover:not(:disabled) {
    background-color: var(--error-color);
    border-color: var(--error-color);
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(239, 68, 68, 0.25);
  }

  .delete-config-button:active:not(:disabled) {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2);
  }

  .delete-all-section {
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border-color);
    text-align: center;
  }

  .delete-all-button {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background: #ef4444;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.8125rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2);
  }

  .delete-all-button:hover:not(:disabled) {
    background: #dc2626;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(239, 68, 68, 0.25);
  }

  .delete-all-button:active:not(:disabled) {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2);
  }

  .delete-all-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .empty-state {
    text-align: center;
    padding: 3rem 2rem;
    border: 2px dashed var(--border-color);
    border-radius: 8px;
    background: var(--card-bg);
  }

  .empty-icon {
    margin-bottom: 1rem;
    color: var(--text-muted);
    opacity: 0.6;
  }

  .empty-state h4 {
    margin: 0 0 0.5rem;
    color: var(--text-color);
    font-size: 1.125rem;
    font-weight: 500;
  }

  .empty-state p {
    margin: 0 0 1.5rem;
    color: var(--text-muted);
    font-size: 0.8125rem;
    line-height: 1.5;
  }

  .create-first-config-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background: #3b82f6;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.8125rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .create-first-config-btn:hover {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .create-first-config-btn:active {
    transform: translateY(0);
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
</style>
