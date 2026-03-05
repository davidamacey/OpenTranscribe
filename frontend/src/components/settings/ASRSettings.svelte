<script lang="ts">
  import { onMount } from 'svelte';
  import { ASRSettingsApi, type UserASRSettings, type ASRProviderDefaults, type ConnectionStatus } from '../../lib/api/asrSettings';
  import ConfirmationModal from '../ConfirmationModal.svelte';
  import { toastStore } from '../../stores/toast';
  import { t } from '$stores/locale';

  export let onSettingsChange: (() => void) | null = null;

  // State
  let loading = false;
  let saving = false;
  let testing = false;

  let configurations: UserASRSettings[] = [];
  let activeConfigurationId: string | null = null;
  let supportedProviders: ASRProviderDefaults[] = [];

  // Form state
  let showForm = false;
  let editingConfig: UserASRSettings | null = null;
  let formName = '';
  let formProvider: 'deepgram' | 'whisperx' = 'deepgram';
  let formModelName = 'nova-3-medical';
  let formApiKey = '';
  let showApiKey = false;

  // Delete confirmation
  let showDeleteModal = false;
  let configToDelete: UserASRSettings | null = null;

  // Test results
  let testResults: Record<string, { status: ConnectionStatus; message: string }> = {};

  onMount(async () => {
    await loadData();
  });

  async function loadData() {
    loading = true;
    try {
      const [providersRes, configsRes] = await Promise.all([
        ASRSettingsApi.getSupportedProviders(),
        ASRSettingsApi.getUserConfigurations(),
      ]);
      supportedProviders = providersRes.providers;
      configurations = configsRes.configurations;
      activeConfigurationId = configsRes.active_configuration_id || null;
    } catch (err: any) {
      console.error('Error loading ASR settings:', err);
    } finally {
      loading = false;
    }
  }

  function openAddForm() {
    editingConfig = null;
    formName = '';
    formProvider = 'deepgram';
    formModelName = 'nova-3-medical';
    formApiKey = '';
    showApiKey = false;
    showForm = true;
  }

  async function openEditForm(config: UserASRSettings) {
    editingConfig = config;
    formName = config.name;
    formProvider = config.provider;
    formModelName = config.model_name;
    showApiKey = false;

    // Load the decrypted API key for editing
    if (config.has_api_key) {
      try {
        const keyRes = await ASRSettingsApi.getConfigApiKey(config.uuid);
        formApiKey = keyRes.api_key || '';
      } catch {
        formApiKey = '';
      }
    } else {
      formApiKey = '';
    }

    showForm = true;
  }

  function onProviderChange() {
    const defaults = ASRSettingsApi.getProviderDefaults(formProvider);
    formModelName = defaults.model_name || formModelName;
  }

  async function saveConfig() {
    if (!formName.trim()) {
      toastStore.error('Please enter a configuration name');
      return;
    }

    saving = true;
    try {
      if (editingConfig) {
        await ASRSettingsApi.updateSettings(editingConfig.uuid, {
          name: formName,
          provider: formProvider,
          model_name: formModelName,
          api_key: formApiKey || undefined,
        });
        toastStore.success('ASR configuration updated');
      } else {
        await ASRSettingsApi.createSettings({
          name: formName,
          provider: formProvider,
          model_name: formModelName,
          api_key: formApiKey || undefined,
        });
        toastStore.success('ASR configuration created');
      }

      showForm = false;
      await loadData();
      if (onSettingsChange) onSettingsChange();
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to save configuration';
      toastStore.error(detail);
    } finally {
      saving = false;
    }
  }

  async function setActive(config: UserASRSettings) {
    try {
      await ASRSettingsApi.setActiveConfiguration(config.uuid);
      activeConfigurationId = config.uuid;
      toastStore.success(`"${config.name}" set as active`);
      if (onSettingsChange) onSettingsChange();
    } catch (err: any) {
      toastStore.error('Failed to set active configuration');
    }
  }

  function confirmDelete(config: UserASRSettings) {
    configToDelete = config;
    showDeleteModal = true;
  }

  async function deleteConfig() {
    if (!configToDelete) return;
    try {
      await ASRSettingsApi.deleteConfiguration(configToDelete.uuid);
      toastStore.success('Configuration deleted');
      showDeleteModal = false;
      configToDelete = null;
      await loadData();
      if (onSettingsChange) onSettingsChange();
    } catch (err: any) {
      toastStore.error('Failed to delete configuration');
    }
  }

  async function testConfig(config: UserASRSettings) {
    testing = true;
    testResults[config.uuid] = { status: 'pending', message: 'Testing...' };
    try {
      const result = await ASRSettingsApi.testConfiguration(config.uuid);
      testResults[config.uuid] = {
        status: result.status,
        message: result.message,
      };
      // Reload to get updated test_status on the config
      await loadData();
    } catch (err: any) {
      testResults[config.uuid] = {
        status: 'failed',
        message: 'Test request failed',
      };
    } finally {
      testing = false;
    }
  }

  function getStatusClass(status?: string): string {
    switch (status) {
      case 'success': return 'status-success';
      case 'failed': return 'status-error';
      case 'pending': return 'status-pending';
      default: return 'status-neutral';
    }
  }

  function getStatusIcon(status?: string): string {
    switch (status) {
      case 'success': return '✓';
      case 'failed': return '✗';
      case 'pending': return '...';
      default: return '?';
    }
  }
</script>

<div class="asr-settings">
  {#if loading}
    <div class="loading-state">
      <span class="spinner"></span>
      <span>Loading ASR settings...</span>
    </div>
  {:else}
    <!-- Configurations List -->
    <div class="configs-section">
      <div class="configs-header">
        <h4>ASR Configurations</h4>
        <button class="btn btn-primary btn-sm" on:click={openAddForm}>
          + Add Configuration
        </button>
      </div>

      {#if configurations.length === 0}
        <div class="empty-state">
          <p>No ASR configurations yet. Using environment defaults.</p>
          <p class="hint">Add a configuration to store your Deepgram API key securely.</p>
        </div>
      {:else}
        <div class="configs-list">
          {#each configurations as config (config.uuid)}
            <div class="config-card" class:active={config.uuid === activeConfigurationId}>
              <div class="config-header">
                <div class="config-info">
                  <span class="config-name">{config.name}</span>
                  <span class="config-provider">{ASRSettingsApi.getProviderDisplayName(config.provider)}</span>
                  <span class="config-model">{config.model_name}</span>
                  {#if config.uuid === activeConfigurationId}
                    <span class="active-badge">Active</span>
                  {/if}
                </div>
                <div class="config-status">
                  {#if testResults[config.uuid]?.status === 'pending'}
                    <span class="status-indicator status-pending">...</span>
                  {:else}
                    <span class="status-indicator {getStatusClass(config.test_status)}"
                      title={config.test_message || ''}>
                      {getStatusIcon(config.test_status)}
                    </span>
                  {/if}
                </div>
              </div>

              <div class="config-meta">
                {#if config.has_api_key}
                  <span class="meta-item key-set">API Key Set</span>
                {:else}
                  <span class="meta-item key-missing">No API Key</span>
                {/if}
                {#if config.test_message}
                  <span class="meta-item test-msg" title={config.test_message}>
                    {config.test_message.substring(0, 60)}{config.test_message.length > 60 ? '...' : ''}
                  </span>
                {/if}
              </div>

              <div class="config-actions">
                {#if config.uuid !== activeConfigurationId}
                  <button class="btn btn-sm btn-outline" on:click={() => setActive(config)}>
                    Set Active
                  </button>
                {/if}
                <button class="btn btn-sm btn-outline" on:click={() => testConfig(config)}
                  disabled={testing}>
                  Test
                </button>
                <button class="btn btn-sm btn-outline" on:click={() => openEditForm(config)}>
                  Edit
                </button>
                <button class="btn btn-sm btn-outline btn-danger" on:click={() => confirmDelete(config)}>
                  Delete
                </button>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </div>

    <!-- Add/Edit Form -->
    {#if showForm}
      <div class="config-form-overlay">
        <div class="config-form">
          <h4>{editingConfig ? 'Edit Configuration' : 'Add ASR Configuration'}</h4>

          <div class="form-group">
            <label for="asr-name">Configuration Name</label>
            <input
              id="asr-name"
              type="text"
              bind:value={formName}
              placeholder="e.g., My Deepgram Config"
            />
          </div>

          <div class="form-group">
            <label for="asr-provider">Provider</label>
            <select id="asr-provider" bind:value={formProvider} on:change={onProviderChange}>
              {#each supportedProviders as provider}
                <option value={provider.provider}>
                  {ASRSettingsApi.getProviderDisplayName(provider.provider)}
                </option>
              {/each}
            </select>
            {#if supportedProviders.length > 0}
              <p class="form-hint">
                {supportedProviders.find(p => p.provider === formProvider)?.description || ''}
              </p>
            {/if}
          </div>

          <div class="form-group">
            <label for="asr-model">Model</label>
            <input
              id="asr-model"
              type="text"
              bind:value={formModelName}
              placeholder="e.g., nova-3-medical"
            />
          </div>

          {#if formProvider === 'deepgram'}
            <div class="form-group">
              <label for="asr-api-key">
                API Key
                {#if editingConfig?.has_api_key}
                  <span class="label-hint">(leave blank to keep existing)</span>
                {/if}
              </label>
              <div class="api-key-input">
                {#if showApiKey}
                  <input
                    id="asr-api-key"
                    type="text"
                    bind:value={formApiKey}
                    placeholder="Enter your Deepgram API key"
                  />
                {:else}
                  <input
                    id="asr-api-key"
                    type="password"
                    bind:value={formApiKey}
                    placeholder="Enter your Deepgram API key"
                  />
                {/if}
                <button
                  class="btn btn-sm btn-icon"
                  type="button"
                  on:click={() => showApiKey = !showApiKey}
                  title={showApiKey ? 'Hide' : 'Show'}
                >
                  {showApiKey ? '🙈' : '👁'}
                </button>
              </div>
            </div>
          {/if}

          <div class="form-actions">
            <button class="btn btn-outline" on:click={() => showForm = false}>
              Cancel
            </button>
            <button class="btn btn-primary" on:click={saveConfig} disabled={saving}>
              {#if saving}
                Saving...
              {:else}
                {editingConfig ? 'Update' : 'Create'}
              {/if}
            </button>
          </div>
        </div>
      </div>
    {/if}
  {/if}

  <!-- Delete Confirmation -->
  {#if showDeleteModal && configToDelete}
    <ConfirmationModal
      title="Delete Configuration"
      message={`Are you sure you want to delete "${configToDelete.name}"? This action cannot be undone.`}
      confirmText="Delete"
      confirmClass="danger"
      on:confirm={deleteConfig}
      on:cancel={() => { showDeleteModal = false; configToDelete = null; }}
    />
  {/if}
</div>

<style>
  .asr-settings {
    width: 100%;
  }

  .loading-state {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 2rem;
    justify-content: center;
    color: var(--text-secondary, #6b7280);
  }

  .spinner {
    width: 1rem;
    height: 1rem;
    border: 2px solid var(--border-color, #e5e7eb);
    border-top-color: var(--primary-color, #3b82f6);
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .configs-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }

  .configs-header h4 {
    margin: 0;
    font-size: 1rem;
    color: var(--text-primary, #1f2937);
  }

  .empty-state {
    text-align: center;
    padding: 2rem;
    color: var(--text-secondary, #6b7280);
    border: 1px dashed var(--border-color, #e5e7eb);
    border-radius: 8px;
  }

  .empty-state .hint {
    font-size: 0.85rem;
    margin-top: 0.5rem;
    opacity: 0.8;
  }

  .configs-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .config-card {
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 8px;
    padding: 1rem;
    background: var(--bg-secondary, #f9fafb);
    transition: border-color 0.2s;
  }

  .config-card.active {
    border-color: var(--primary-color, #3b82f6);
    background: var(--bg-primary, #fff);
  }

  .config-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.5rem;
  }

  .config-info {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
  }

  .config-name {
    font-weight: 600;
    color: var(--text-primary, #1f2937);
  }

  .config-provider {
    font-size: 0.8rem;
    padding: 0.1rem 0.4rem;
    border-radius: 4px;
    background: var(--primary-color, #3b82f6);
    color: white;
  }

  .config-model {
    font-size: 0.8rem;
    color: var(--text-secondary, #6b7280);
    font-family: monospace;
  }

  .active-badge {
    font-size: 0.75rem;
    padding: 0.1rem 0.5rem;
    border-radius: 10px;
    background: var(--success-color, #10b981);
    color: white;
    font-weight: 500;
  }

  .config-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
    font-size: 0.8rem;
  }

  .meta-item.key-set {
    color: var(--success-color, #10b981);
  }

  .meta-item.key-missing {
    color: var(--warning-color, #f59e0b);
  }

  .meta-item.test-msg {
    color: var(--text-secondary, #6b7280);
  }

  .config-actions {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .status-indicator {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.5rem;
    height: 1.5rem;
    border-radius: 50%;
    font-size: 0.75rem;
    font-weight: bold;
  }

  .status-success { background: var(--success-color, #10b981); color: white; }
  .status-error { background: var(--error-color, #ef4444); color: white; }
  .status-pending { background: var(--warning-color, #f59e0b); color: white; }
  .status-neutral { background: var(--border-color, #e5e7eb); color: var(--text-secondary, #6b7280); }

  /* Form overlay */
  .config-form-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .config-form {
    background: var(--bg-primary, #fff);
    border-radius: 12px;
    padding: 1.5rem;
    width: 90%;
    max-width: 500px;
    max-height: 90vh;
    overflow-y: auto;
  }

  .config-form h4 {
    margin: 0 0 1.25rem;
    font-size: 1.1rem;
    color: var(--text-primary, #1f2937);
  }

  .form-group {
    margin-bottom: 1rem;
  }

  .form-group label {
    display: block;
    font-size: 0.85rem;
    font-weight: 500;
    margin-bottom: 0.35rem;
    color: var(--text-primary, #1f2937);
  }

  .label-hint {
    font-weight: 400;
    color: var(--text-secondary, #6b7280);
    font-size: 0.8rem;
  }

  .form-group input,
  .form-group select {
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 6px;
    font-size: 0.9rem;
    background: var(--bg-primary, #fff);
    color: var(--text-primary, #1f2937);
  }

  .form-group input:focus,
  .form-group select:focus {
    outline: none;
    border-color: var(--primary-color, #3b82f6);
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
  }

  .form-hint {
    font-size: 0.8rem;
    color: var(--text-secondary, #6b7280);
    margin: 0.35rem 0 0;
  }

  .api-key-input {
    display: flex;
    gap: 0.5rem;
  }

  .api-key-input input {
    flex: 1;
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: 1.5rem;
  }

  /* Button styles */
  .btn {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.5rem 1rem;
    border: 1px solid transparent;
    border-radius: 6px;
    font-size: 0.85rem;
    cursor: pointer;
    transition: all 0.15s;
    font-weight: 500;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-sm {
    padding: 0.3rem 0.6rem;
    font-size: 0.8rem;
  }

  .btn-primary {
    background: var(--primary-color, #3b82f6);
    color: white;
    border-color: var(--primary-color, #3b82f6);
  }

  .btn-primary:hover:not(:disabled) {
    opacity: 0.9;
  }

  .btn-outline {
    background: transparent;
    border-color: var(--border-color, #e5e7eb);
    color: var(--text-primary, #1f2937);
  }

  .btn-outline:hover:not(:disabled) {
    background: var(--bg-secondary, #f9fafb);
  }

  .btn-danger {
    color: var(--error-color, #ef4444);
    border-color: var(--error-color, #ef4444);
  }

  .btn-danger:hover:not(:disabled) {
    background: var(--error-color, #ef4444);
    color: white;
  }

  .btn-icon {
    padding: 0.3rem 0.5rem;
    border: 1px solid var(--border-color, #e5e7eb);
    background: transparent;
  }
</style>
