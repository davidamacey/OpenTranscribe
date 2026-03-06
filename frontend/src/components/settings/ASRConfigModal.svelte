<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import {
    ASRSettingsApi,
    type UserASRSettingsResponse,
    type ASRProviderInfo,
    type ASRModelInfo,
    type ASRProvider,
  } from '../../lib/api/asrSettings';
  import { toastStore } from '../../stores/toast';
  import { t } from '$stores/locale';

  export let show = false;
  export let editingConfig: UserASRSettingsResponse | null = null;
  export let providers: ASRProviderInfo[] = [];

  const dispatch = createEventDispatcher();

  let saving = false;
  let testing = false;
  let testResult: { success: boolean; message: string } | null = null;
  let showApiKey = false;
  let isDirty = false;

  let formData = {
    name: '',
    provider: '' as ASRProvider | '',
    model_name: '',
    api_key: '',
    region: '',
    base_url: '',
    is_active: true,
  };

  let originalFormData = { ...formData };
  let lastEditingConfigId: string | null = null;

  const AZURE_REGIONS = ['westus', 'eastus', 'eastus2', 'westeurope', 'northeurope', 'uksouth', 'australiaeast'];
  const AWS_REGIONS = ['us-east-1', 'us-west-2', 'eu-west-1', 'eu-central-1', 'ap-southeast-1', 'ap-northeast-1'];

  $: if (show) {
    if (editingConfig && editingConfig.uuid !== lastEditingConfigId) {
      populateForm(editingConfig);
      lastEditingConfigId = editingConfig.uuid;
    } else if (!editingConfig && lastEditingConfigId !== null) {
      resetForm();
      lastEditingConfigId = null;
    }
  } else {
    lastEditingConfigId = null;
    testResult = null;
  }

  $: isDirty = JSON.stringify(formData) !== JSON.stringify(originalFormData);

  $: selectedProvider = providers.find(p => p.provider === formData.provider) || null;
  $: availableModels = selectedProvider?.models || [];

  $: selectedModel = availableModels.find(m => m.id === formData.model_name) || null;

  $: estimatedCostPerHour = selectedModel?.price_per_min_batch
    ? ASRSettingsApi.formatPricePerHour(selectedModel.price_per_min_batch)
    : null;

  $: isFormValid = !!(
    formData.name.trim() &&
    formData.provider &&
    formData.model_name.trim() &&
    (formData.provider === 'local' || !selectedProvider?.requires_api_key || formData.api_key.trim() || editingConfig?.has_api_key)
  );

  $: needsRegion = formData.provider === 'azure' || formData.provider === 'aws';
  $: regionOptions = formData.provider === 'azure' ? AZURE_REGIONS : formData.provider === 'aws' ? AWS_REGIONS : [];

  function populateForm(config: UserASRSettingsResponse) {
    formData = {
      name: config.name,
      provider: config.provider,
      model_name: config.model_name,
      api_key: '',
      region: config.region || '',
      base_url: config.base_url || '',
      is_active: config.is_active,
    };
    originalFormData = { ...formData };
    testResult = null;
  }

  function resetForm() {
    formData = {
      name: '',
      provider: '' as ASRProvider | '',
      model_name: '',
      api_key: '',
      region: '',
      base_url: '',
      is_active: true,
    };
    originalFormData = { ...formData };
    testResult = null;
    showApiKey = false;
  }

  function onProviderChange() {
    formData.model_name = '';
    formData.region = '';
    testResult = null;
    // Set default name if not set
    if (!formData.name && formData.provider) {
      formData.name = ASRSettingsApi.getProviderDisplayName(formData.provider);
    }
  }

  function onModelChange() {
    testResult = null;
  }

  async function handleSave() {
    if (!isFormValid) return;
    saving = true;
    try {
      const payload: any = {
        name: formData.name.trim(),
        provider: formData.provider,
        model_name: formData.model_name.trim(),
        is_active: formData.is_active,
      };
      if (formData.api_key.trim()) payload.api_key = formData.api_key.trim();
      if (formData.region.trim()) payload.region = formData.region.trim();
      if (formData.base_url.trim()) payload.base_url = formData.base_url.trim();

      let result: UserASRSettingsResponse;
      if (editingConfig) {
        result = await ASRSettingsApi.updateConfig(editingConfig.uuid, payload);
        toastStore.success(`"${result.name}" updated`);
      } else {
        result = await ASRSettingsApi.createConfig(payload);
        toastStore.success(`"${result.name}" created`);
      }
      dispatch('saved', result);
      handleClose();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      toastStore.error(typeof detail === 'string' ? detail : 'Failed to save ASR configuration', 5000);
    } finally {
      saving = false;
    }
  }

  async function handleTest() {
    if (!formData.provider || !formData.model_name) return;
    testing = true;
    testResult = null;
    try {
      const params: any = {
        provider: formData.provider,
        model_name: formData.model_name,
      };
      if (formData.api_key.trim()) params.api_key = formData.api_key.trim();
      else if (editingConfig?.has_api_key) params.config_id = editingConfig.uuid;
      if (formData.region.trim()) params.region = formData.region.trim();
      if (formData.base_url.trim()) params.base_url = formData.base_url.trim();

      const result = await ASRSettingsApi.testConnection(params);
      testResult = { success: result.success, message: result.message };
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      testResult = { success: false, message: typeof detail === 'string' ? detail : 'Connection test failed' };
    } finally {
      testing = false;
    }
  }

  function handleClose() {
    show = false;
    dispatch('close');
    resetForm();
  }

  function handleBackdropClick(e: MouseEvent) {
    if (e.target === e.currentTarget) handleClose();
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.key === 'Escape') handleClose();
  }
</script>

{#if show}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div class="modal-overlay" on:click={handleBackdropClick} on:keydown={handleKeyDown}>
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="asr-modal-title">
      <div class="modal-header">
        <h3 id="asr-modal-title">{editingConfig ? $t('settings.asrProvider.editConfig') : $t('settings.asrProvider.addConfig')}</h3>
        <button class="close-btn" on:click={handleClose} aria-label={$t('common.close')} title={$t('common.close')}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <div class="modal-body">
        <!-- Name -->
        <div class="form-group">
          <label for="asr-name">{$t('settings.asrProvider.fields.name')}</label>
          <input
            id="asr-name"
            type="text"
            bind:value={formData.name}
            placeholder="e.g., Deepgram Production"
            class="form-input"
          />
        </div>

        <!-- Provider -->
        <div class="form-group">
          <label for="asr-provider">{$t('settings.asrProvider.fields.provider')}</label>
          <select
            id="asr-provider"
            bind:value={formData.provider}
            on:change={onProviderChange}
            class="form-select"
            disabled={!!editingConfig}
            title={editingConfig ? $t('settings.asrProvider.providerLockedOnEdit') : undefined}
          >
            <option value="">Select provider...</option>
            {#each providers as p}
              <option value={p.provider}>
                {ASRSettingsApi.getProviderDisplayName(p.provider)}
                {#if !p.sdk_available} ({$t('settings.asrProvider.missingSDK')}){/if}
              </option>
            {/each}
          </select>
          {#if editingConfig}
            <p class="field-hint">{$t('settings.asrProvider.providerLockedOnEdit')}</p>
          {/if}
        </div>

        {#if selectedProvider}
          <!-- Provider capabilities -->
          <div class="capabilities">
            {#if selectedProvider.supports_diarization}
              <span class="cap-badge">Diarization</span>
            {/if}
            {#if selectedProvider.supports_vocabulary}
              <span class="cap-badge">Vocabulary Boosting</span>
            {/if}
            {#if selectedProvider.supports_translation}
              <span class="cap-badge">Translation</span>
            {/if}
          </div>

          <!-- Model -->
          <div class="form-group">
            <label for="asr-model">{$t('settings.asrProvider.fields.model')}</label>
            {#if availableModels.length > 0}
              <select id="asr-model" bind:value={formData.model_name} on:change={onModelChange} class="form-select">
                <option value="">Select model...</option>
                {#each availableModels as m}
                  <option value={m.id}>
                    {m.name}{m.price_per_min_batch ? ` — $${m.price_per_min_batch}/min` : ''}{m.description ? ` — ${m.description}` : ''}
                  </option>
                {/each}
              </select>
            {:else}
              <input
                id="asr-model"
                type="text"
                bind:value={formData.model_name}
                placeholder="Model name"
                class="form-input"
              />
            {/if}
            {#if estimatedCostPerHour}
              <p class="cost-hint">{$t('settings.asrProvider.estimatedCost')}: <strong>{estimatedCostPerHour}</strong></p>
            {/if}
          </div>

          <!-- API Key -->
          {#if selectedProvider.requires_api_key}
            <div class="form-group">
              <label for="asr-apikey">{$t('settings.asrProvider.fields.apiKey')}</label>
              <div class="input-with-toggle">
                <input
                  id="asr-apikey"
                  type={showApiKey ? 'text' : 'password'}
                  bind:value={formData.api_key}
                  placeholder={editingConfig?.has_api_key ? '(stored — leave blank to keep)' : 'Enter API key'}
                  class="form-input"
                  autocomplete="off"
                />
                <button type="button" class="toggle-visibility" on:click={() => showApiKey = !showApiKey}>
                  {showApiKey ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>
          {/if}

          <!-- Region (Azure / AWS) -->
          {#if needsRegion}
            <div class="form-group">
              <label for="asr-region">{$t('settings.asrProvider.fields.region')}</label>
              <select id="asr-region" bind:value={formData.region} class="form-select">
                <option value="">Select region...</option>
                {#each regionOptions as r}
                  <option value={r}>{r}</option>
                {/each}
              </select>
            </div>
          {/if}

          <!-- Base URL -->
          {#if selectedProvider.supports_base_url}
            <div class="form-group">
              <label for="asr-baseurl">{$t('settings.asrProvider.fields.baseUrl')}</label>
              <input
                id="asr-baseurl"
                type="url"
                bind:value={formData.base_url}
                placeholder="https://..."
                class="form-input"
              />
            </div>
          {/if}
        {/if}

        <!-- Test result — aria-live so screen readers announce it after test completes -->
        <div role="status" aria-live="polite" aria-atomic="true">
          {#if testResult}
            <div class="test-result" class:success={testResult.success} class:failure={!testResult.success}>
              {testResult.success ? '✓' : '✗'} {testResult.message}
            </div>
          {/if}
        </div>

        <!-- Pricing disclaimer -->
        {#if estimatedCostPerHour}
          <p class="pricing-disclaimer">{$t('settings.asrProvider.pricingDisclaimer')}</p>
        {/if}
      </div>

      <div class="modal-footer">
        <button
          class="btn-test-conn"
          on:click={handleTest}
          disabled={testing || !formData.provider || !formData.model_name}
        >
          {#if testing}
            <span class="spinner-sm"></span> Testing...
          {:else}
            {$t('settings.asrProvider.testConnection')}
          {/if}
        </button>
        <div class="footer-actions">
          <button class="btn-cancel" on:click={handleClose}>{$t('common.cancel')}</button>
          <button class="btn-save" on:click={handleSave} disabled={saving || !isFormValid}>
            {saving ? 'Saving...' : (editingConfig ? 'Update' : 'Save')}
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
  }

  .modal {
    background: var(--bg-primary, var(--card-bg, #fff));
    border: 1px solid var(--border-color);
    border-radius: 12px;
    width: 100%;
    max-width: 520px;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.25rem 1.5rem 1rem;
    border-bottom: 1px solid var(--border-color);
  }

  .modal-header h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-color);
  }

  .close-btn {
    background: none;
    border: none;
    padding: 0.25rem;
    cursor: pointer;
    color: var(--text-muted);
    border-radius: 4px;
    transition: color 0.15s;
    display: flex;
    align-items: center;
  }

  .close-btn:hover { color: var(--text-color); }

  .modal-body {
    padding: 1.25rem 1.5rem;
    overflow-y: auto;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .form-group label {
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--text-color);
  }

  .form-input, .form-select {
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--bg-primary, var(--input-bg, transparent));
    color: var(--text-color);
    font-size: 0.8125rem;
    outline: none;
    transition: border-color 0.15s;
  }

  .form-input:focus, .form-select:focus {
    border-color: #3b82f6;
  }

  .input-with-toggle {
    display: flex;
    gap: 0.5rem;
  }

  .input-with-toggle .form-input {
    flex: 1;
  }

  .toggle-visibility {
    padding: 0.5rem 0.75rem;
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.75rem;
    color: var(--text-muted);
    white-space: nowrap;
  }

  .toggle-visibility:hover { color: var(--text-color); }

  .capabilities {
    display: flex;
    flex-wrap: wrap;
    gap: 0.375rem;
  }

  .cap-badge {
    padding: 0.2rem 0.5rem;
    background: rgba(99, 102, 241, 0.1);
    color: #6366f1;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 500;
  }

  .cost-hint {
    margin: 0.25rem 0 0;
    font-size: 0.775rem;
    color: var(--text-muted);
  }

  .field-hint {
    margin: 0.25rem 0 0;
    font-size: 0.75rem;
    color: var(--text-muted);
    font-style: italic;
  }

  .pricing-disclaimer {
    margin: 0;
    font-size: 0.75rem;
    color: var(--text-muted);
    font-style: italic;
  }

  .test-result {
    padding: 0.625rem 0.875rem;
    border-radius: 6px;
    font-size: 0.8125rem;
  }

  .test-result.success {
    background: rgba(16, 185, 129, 0.1);
    color: #10b981;
    border: 1px solid rgba(16, 185, 129, 0.2);
  }

  .test-result.failure {
    background: rgba(239, 68, 68, 0.1);
    color: #ef4444;
    border: 1px solid rgba(239, 68, 68, 0.2);
  }

  .modal-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.5rem;
    border-top: 1px solid var(--border-color);
    gap: 0.75rem;
  }

  .footer-actions {
    display: flex;
    gap: 0.5rem;
  }

  .btn-test-conn {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 0.875rem;
    border: 1px solid #3b82f6;
    color: #3b82f6;
    background: transparent;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.8125rem;
    transition: all 0.15s;
  }

  .btn-test-conn:hover:not(:disabled) {
    background: #3b82f6;
    color: white;
  }

  .btn-cancel {
    padding: 0.5rem 1rem;
    border: 1px solid var(--border-color);
    background: transparent;
    color: var(--text-muted);
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.8125rem;
    transition: all 0.15s;
  }

  .btn-cancel:hover { color: var(--text-color); border-color: var(--text-muted); }

  .btn-save {
    padding: 0.5rem 1.25rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.8125rem;
    font-weight: 500;
    transition: background 0.15s;
  }

  .btn-save:hover:not(:disabled) { background: #2563eb; }

  button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .spinner-sm {
    display: inline-block;
    width: 12px;
    height: 12px;
    border: 2px solid currentColor;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
