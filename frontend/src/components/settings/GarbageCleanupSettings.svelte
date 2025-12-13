<script lang="ts">
  import { onMount } from 'svelte';
  import { AdminSettingsApi, type GarbageCleanupConfig } from '../../lib/api/adminSettings';
  import { toastStore } from '../../stores/toast';
  import { t } from '$stores/locale';

  // State
  let loading = true;
  let saving = false;
  let config: GarbageCleanupConfig | null = null;

  // Form state
  let garbageCleanupEnabled = true;
  let maxWordLength = 50;
  let hasChanges = false;

  // Track original values for change detection
  let originalGarbageCleanupEnabled = true;
  let originalMaxWordLength = 50;

  onMount(async () => {
    await loadConfig();
  });

  async function loadConfig() {
    loading = true;
    try {
      config = await AdminSettingsApi.getGarbageCleanupConfig();
      garbageCleanupEnabled = config.garbage_cleanup_enabled;
      maxWordLength = config.max_word_length;
      originalGarbageCleanupEnabled = garbageCleanupEnabled;
      originalMaxWordLength = maxWordLength;
      hasChanges = false;
    } catch (err: any) {
      console.error('Error loading garbage cleanup config:', err);
      toastStore.error($t('settings.garbageCleanup.loadFailed'));
    } finally {
      loading = false;
    }
  }

  function checkForChanges() {
    hasChanges = garbageCleanupEnabled !== originalGarbageCleanupEnabled || maxWordLength !== originalMaxWordLength;
  }

  $: {
    // Reactive change detection
    garbageCleanupEnabled;
    maxWordLength;
    checkForChanges();
  }

  async function saveConfig() {
    saving = true;
    try {
      config = await AdminSettingsApi.updateGarbageCleanupConfig({
        garbage_cleanup_enabled: garbageCleanupEnabled,
        max_word_length: maxWordLength
      });
      originalGarbageCleanupEnabled = config.garbage_cleanup_enabled;
      originalMaxWordLength = config.max_word_length;
      hasChanges = false;
      toastStore.success($t('settings.garbageCleanup.saved'));
    } catch (err: any) {
      console.error('Error saving garbage cleanup config:', err);
      const errorMsg = err.response?.data?.detail || $t('settings.garbageCleanup.saveFailed');
      toastStore.error(errorMsg);
    } finally {
      saving = false;
    }
  }

  function resetToDefaults() {
    garbageCleanupEnabled = true;
    maxWordLength = 50;
  }
</script>

<div class="garbage-cleanup-settings">
  <div class="title-row">
    <h3 class="section-title">{$t('settings.garbageCleanup.title')}</h3>
    <span class="info-icon">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="16" x2="12" y2="12"></line>
        <line x1="12" y1="8" x2="12.01" y2="8"></line>
      </svg>
      <span class="tooltip">{$t('settings.garbageCleanup.tooltip')}</span>
    </span>
  </div>
  <p class="section-desc">{$t('settings.garbageCleanup.desc')}</p>

  {#if loading}
    <div class="loading-state">
      <div class="spinner"></div>
    </div>
  {:else}
    <div class="setting-row">
      <div class="setting-controls">
        <label class="toggle-label">
          <input type="checkbox" bind:checked={garbageCleanupEnabled} class="toggle-input" />
          <span class="toggle-switch"></span>
          <span class="toggle-text">{$t('settings.garbageCleanup.enableCleanup')}</span>
        </label>
        <div class="inline-input">
          <span class="input-label">{$t('settings.garbageCleanup.threshold')}</span>
          <input
            type="number"
            bind:value={maxWordLength}
            min="20"
            max="200"
            class="form-input number-input"
            disabled={!garbageCleanupEnabled}
          />
          <span class="input-suffix">{$t('settings.garbageCleanup.chars')}</span>
        </div>
      </div>
      <div class="button-row">
        <button type="button" class="btn btn-secondary" on:click={resetToDefaults} disabled={saving}>
          {$t('settings.garbageCleanup.reset')}
        </button>
        <button type="button" class="btn btn-primary" on:click={saveConfig} disabled={saving || !hasChanges}>
          {saving ? $t('settings.garbageCleanup.saving') : $t('settings.garbageCleanup.save')}
        </button>
      </div>
    </div>
  {/if}
</div>

<style>
  .garbage-cleanup-settings {
    padding: 0.5rem 0;
  }

  .title-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .section-title {
    font-size: 0.95rem;
    font-weight: 600;
    margin: 0;
    color: var(--text-color);
  }

  .info-icon {
    position: relative;
    color: var(--text-muted);
    cursor: help;
    display: flex;
    align-items: center;
  }

  .info-icon:hover {
    color: var(--text-color);
  }

  .tooltip {
    visibility: hidden;
    opacity: 0;
    position: absolute;
    left: 50%;
    top: calc(100% + 8px);
    transform: translateX(-50%);
    background-color: var(--surface-color, #333);
    color: var(--text-color);
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    font-size: 0.75rem;
    line-height: 1.4;
    width: 260px;
    z-index: 100;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    border: 1px solid var(--border-color);
    transition: opacity 0.1s ease;
  }

  .info-icon:hover .tooltip {
    visibility: visible;
    opacity: 1;
  }

  .section-desc {
    font-size: 0.8rem;
    color: var(--text-muted);
    margin: 0 0 1rem 0;
  }

  .loading-state {
    display: flex;
    align-items: center;
    padding: 1rem;
  }

  .spinner {
    width: 18px;
    height: 18px;
    border: 2px solid var(--border-color);
    border-top-color: var(--primary-color);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .setting-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
  }

  .setting-controls {
    display: flex;
    align-items: center;
    gap: 1.5rem;
  }

  .toggle-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    user-select: none;
  }

  .toggle-input {
    position: absolute;
    opacity: 0;
    width: 0;
    height: 0;
  }

  .toggle-switch {
    position: relative;
    width: 36px;
    height: 20px;
    background-color: var(--border-color);
    border-radius: 10px;
    transition: background-color 0.2s ease;
    flex-shrink: 0;
  }

  .toggle-switch::after {
    content: '';
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    background-color: white;
    border-radius: 50%;
    transition: transform 0.2s ease;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
  }

  .toggle-input:checked + .toggle-switch {
    background-color: var(--primary-color);
  }

  .toggle-input:checked + .toggle-switch::after {
    transform: translateX(16px);
  }

  .toggle-text {
    font-size: 0.875rem;
    color: var(--text-color);
  }

  .inline-input {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .input-label {
    font-size: 0.8rem;
    color: var(--text-muted);
  }

  .input-suffix {
    font-size: 0.75rem;
    color: var(--text-muted);
  }

  .form-input {
    padding: 0.375rem 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background-color: var(--background-color);
    color: var(--text-color);
    font-size: 0.875rem;
  }

  .form-input:focus {
    outline: none;
    border-color: var(--primary-color);
  }

  .form-input:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .number-input {
    width: 60px;
    text-align: center;
  }

  .button-row {
    display: flex;
    gap: 0.5rem;
  }

  .btn {
    padding: 0.375rem 0.75rem;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-primary {
    background-color: var(--primary-color);
    color: white;
  }

  .btn-primary:hover:not(:disabled) {
    background-color: var(--primary-color-dark);
  }

  .btn-secondary {
    background-color: transparent;
    color: var(--text-color);
    border: 1px solid var(--border-color);
  }

  .btn-secondary:hover:not(:disabled) {
    background-color: var(--background-secondary);
  }
</style>
