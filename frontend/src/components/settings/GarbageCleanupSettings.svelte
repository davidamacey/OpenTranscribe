<script lang="ts">
  import { onMount } from 'svelte';
  import { AdminSettingsApi, type GarbageCleanupConfig } from '../../lib/api/adminSettings';
  import { toastStore } from '../../stores/toast';

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
      toastStore.error('Failed to load garbage cleanup configuration');
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
      toastStore.success('Garbage cleanup configuration saved successfully');
    } catch (err: any) {
      console.error('Error saving garbage cleanup config:', err);
      const errorMsg = err.response?.data?.detail || 'Failed to save garbage cleanup configuration';
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
  <h3 class="section-title">Garbage Word Cleanup</h3>
  <p class="section-description">
    Automatically detect and replace garbage transcription words. WhisperX can sometimes misinterpret background noise (fans, static, rumbling) as extremely long "words" with no spaces.
  </p>

  {#if loading}
    <div class="loading-state">
      <div class="spinner"></div>
      <span>Loading configuration...</span>
    </div>
  {:else}
    <div class="settings-form">
      <!-- Enable/Disable Toggle -->
      <div class="form-group">
        <label class="toggle-label">
          <input
            type="checkbox"
            bind:checked={garbageCleanupEnabled}
            class="toggle-input"
          />
          <span class="toggle-switch"></span>
          <span class="toggle-text">Enable garbage word cleanup</span>
        </label>
        <p class="help-text">
          When enabled, words exceeding the length threshold are automatically replaced with [background noise] during transcription.
        </p>
      </div>

      <!-- Max Word Length Input (only shown when enabled) -->
      {#if garbageCleanupEnabled}
        <div class="form-group">
          <label for="maxWordLength" class="form-label">Maximum word length threshold</label>
          <div class="input-with-hint">
            <input
              type="number"
              id="maxWordLength"
              bind:value={maxWordLength}
              min="20"
              max="200"
              class="form-input number-input"
            />
            <span class="input-hint">characters (20-200)</span>
          </div>
          <p class="help-text">
            Words longer than this threshold (without spaces) are considered garbage and replaced.
            Default is 50 characters. Lower values are more aggressive.
          </p>
        </div>
      {/if}

      <!-- Current Status -->
      <div class="status-box">
        <div class="status-icon">
          {#if garbageCleanupEnabled}
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
            </svg>
          {:else}
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="4.93" y1="4.93" x2="19.07" y2="19.07"></line>
            </svg>
          {/if}
        </div>
        <div class="status-text">
          {#if garbageCleanupEnabled}
            <strong>Garbage cleanup enabled</strong> - Words longer than {maxWordLength} characters will be replaced with [background noise].
          {:else}
            <strong>Garbage cleanup disabled</strong> - Long garbage words will appear in transcripts as-is.
          {/if}
        </div>
      </div>

      <!-- Action Buttons -->
      <div class="button-group">
        <button
          type="button"
          class="btn btn-secondary"
          on:click={resetToDefaults}
          disabled={saving}
        >
          Reset to Defaults
        </button>
        <button
          type="button"
          class="btn btn-primary"
          on:click={saveConfig}
          disabled={saving || !hasChanges}
        >
          {#if saving}
            <span class="spinner-small"></span>
            Saving...
          {:else}
            Save Changes
          {/if}
        </button>
      </div>
    </div>
  {/if}
</div>

<style>
  .garbage-cleanup-settings {
    padding: 0.5rem;
  }

  .section-title {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--text-color);
    margin: 0 0 0.5rem 0;
  }

  .section-description {
    color: var(--text-secondary);
    font-size: 0.875rem;
    margin: 0 0 1.5rem 0;
  }

  .loading-state {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 2rem;
    color: var(--text-secondary);
  }

  .spinner {
    width: 24px;
    height: 24px;
    border: 2px solid var(--border-color);
    border-top-color: var(--primary-color);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  .spinner-small {
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    display: inline-block;
    margin-right: 0.5rem;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .settings-form {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .form-label {
    font-weight: 500;
    color: var(--text-color);
    font-size: 0.875rem;
  }

  .toggle-label {
    display: flex;
    align-items: center;
    gap: 0.75rem;
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
    width: 44px;
    height: 24px;
    background-color: var(--border-color);
    border-radius: 12px;
    transition: background-color 0.2s ease;
    flex-shrink: 0;
  }

  .toggle-switch::after {
    content: '';
    position: absolute;
    top: 2px;
    left: 2px;
    width: 20px;
    height: 20px;
    background-color: white;
    border-radius: 50%;
    transition: transform 0.2s ease;
  }

  .toggle-input:checked + .toggle-switch {
    background-color: var(--primary-color);
  }

  .toggle-input:checked + .toggle-switch::after {
    transform: translateX(20px);
  }

  .toggle-text {
    font-weight: 500;
    color: var(--text-color);
  }

  .help-text {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    margin: 0;
    line-height: 1.4;
  }

  .input-with-hint {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .form-input {
    padding: 0.625rem 0.875rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background-color: var(--background-color);
    color: var(--text-color);
    font-size: 0.875rem;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
  }

  .form-input:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .number-input {
    width: 100px;
  }

  .input-hint {
    font-size: 0.8125rem;
    color: var(--text-secondary);
  }

  .status-box {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 1rem;
    background-color: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
  }

  .status-icon {
    color: var(--text-secondary);
    flex-shrink: 0;
    margin-top: 2px;
  }

  .status-text {
    font-size: 0.875rem;
    color: var(--text-color);
    line-height: 1.5;
  }

  .status-text strong {
    display: block;
    margin-bottom: 0.25rem;
  }

  .button-group {
    display: flex;
    gap: 0.75rem;
    justify-content: flex-end;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border-color);
    margin-top: 0.5rem;
  }

  .btn {
    padding: 0.625rem 1.25rem;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .btn-primary {
    background-color: var(--primary-color);
    color: white;
  }

  .btn-primary:hover:not(:disabled) {
    background-color: var(--primary-hover);
  }

  .btn-secondary {
    background-color: var(--surface-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
  }

  .btn-secondary:hover:not(:disabled) {
    background-color: var(--background-color);
  }
</style>
