<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import axiosInstance from '../lib/axios';
  import { toastStore } from '../stores/toast';

  export let file: any = null;
  export let reprocessing: boolean = false;

  const dispatch = createEventDispatcher();

  // Advanced settings state
  let showAdvancedSettings = false;
  let minSpeakers: number | null = null;
  let maxSpeakers: number | null = null;
  let numSpeakers: number | null = null;

  async function handleReprocess() {
    if (!file?.id || reprocessing) return;

    try {
      reprocessing = true;

      // Build request body with speaker parameters if provided
      const requestBody: any = {};
      if (minSpeakers !== null) {
        requestBody.min_speakers = minSpeakers;
      }
      if (maxSpeakers !== null) {
        requestBody.max_speakers = maxSpeakers;
      }
      if (numSpeakers !== null) {
        requestBody.num_speakers = numSpeakers;
      }

      // Send request with optional body
      await axiosInstance.post(`/api/files/${file.id}/reprocess`, Object.keys(requestBody).length > 0 ? requestBody : undefined);

      // Reset settings after successful reprocess
      showAdvancedSettings = false;
      minSpeakers = null;
      maxSpeakers = null;
      numSpeakers = null;

      // Dispatch to parent for handling UI updates
      dispatch('reprocess', { fileId: file.id });
    } catch (error) {
      console.error('Error reprocessing file:', error);
      toastStore.error('Failed to start reprocessing');
      reprocessing = false;
    }
  }

  // Validation
  $: isValid = !(minSpeakers !== null && maxSpeakers !== null && minSpeakers > maxSpeakers);
</script>

{#if file && (file.status === 'error' || file.status === 'completed' || file.status === 'failed')}
  <div class="reprocess-container">
    <button
      class="reprocess-button"
      on:click={() => showAdvancedSettings = !showAdvancedSettings}
      disabled={reprocessing}
      title="Reprocess this file with the transcription AI"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M23 4v6h-6"></path>
        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
      </svg>
      {reprocessing ? 'Reprocessing...' : 'Reprocess'}
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="chevron {showAdvancedSettings ? 'open' : ''}">
        <polyline points="6 9 12 15 18 9"></polyline>
      </svg>
    </button>

    {#if showAdvancedSettings}
      <div class="advanced-settings">
        <div class="settings-header">
          <h4>Speaker Diarization Settings</h4>
          <p>Configure speaker detection for reprocessing. Leave empty to use system defaults.</p>
        </div>

        <div class="settings-row">
          <div class="setting-field">
            <label for="reprocess-min-speakers">
              Min Speakers
              <span class="setting-hint">Minimum expected</span>
            </label>
            <input
              id="reprocess-min-speakers"
              type="number"
              min="1"
              placeholder="Default"
              bind:value={minSpeakers}
              disabled={numSpeakers !== null}
            />
          </div>

          <div class="setting-field">
            <label for="reprocess-max-speakers">
              Max Speakers
              <span class="setting-hint">Maximum expected</span>
            </label>
            <input
              id="reprocess-max-speakers"
              type="number"
              min="1"
              placeholder="Default"
              bind:value={maxSpeakers}
              disabled={numSpeakers !== null}
            />
          </div>
        </div>

        <div class="setting-field">
          <label for="reprocess-num-speakers">
            Fixed Speaker Count
            <span class="setting-hint">Exact number (overrides min/max)</span>
          </label>
          <input
            id="reprocess-num-speakers"
            type="number"
            min="1"
            placeholder="Default"
            bind:value={numSpeakers}
          />
        </div>

        {#if !isValid}
          <div class="validation-error">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            Min speakers must be less than or equal to max speakers
          </div>
        {/if}

        <div class="settings-actions">
          <button
            class="btn-confirm"
            on:click={handleReprocess}
            disabled={reprocessing || !isValid}
          >
            Start Reprocessing
          </button>
        </div>
      </div>
    {/if}
  </div>
{/if}

<style>
  .reprocess-container {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .reprocess-button {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .reprocess-button:hover:not(:disabled) {
    background: var(--surface-hover);
    border-color: var(--border-hover);
  }

  .reprocess-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .reprocess-button .chevron {
    margin-left: auto;
    transition: transform 0.2s ease;
  }

  .reprocess-button .chevron.open {
    transform: rotate(180deg);
  }

  .advanced-settings {
    padding: 1rem;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background-color: var(--card-background);
    animation: slideDown 0.2s ease;
  }

  @keyframes slideDown {
    from {
      opacity: 0;
      transform: translateY(-10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .settings-header {
    margin-bottom: 1rem;
  }

  .settings-header h4 {
    margin: 0 0 0.25rem 0;
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  .settings-header p {
    margin: 0;
    font-size: 0.85rem;
    color: var(--text-secondary);
  }

  .settings-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .setting-field {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .setting-field label {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--text-primary);
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .setting-hint {
    font-size: 0.75rem;
    font-weight: 400;
    color: var(--text-secondary);
  }

  .setting-field input {
    padding: 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background-color: var(--input-background, var(--card-background));
    color: var(--text-primary);
    font-size: 0.9rem;
    transition: all 0.2s ease;
  }

  .setting-field input:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .setting-field input:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    background-color: var(--disabled-background, #f5f5f5);
  }

  :global(.dark) .setting-field input:disabled {
    background-color: rgba(255, 255, 255, 0.05);
  }

  .setting-field input::placeholder {
    color: var(--text-light);
  }

  .validation-error {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem;
    background-color: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 6px;
    color: #dc2626;
    font-size: 0.85rem;
    margin-bottom: 0.75rem;
  }

  :global(.dark) .validation-error {
    background-color: rgba(239, 68, 68, 0.15);
    border-color: rgba(239, 68, 68, 0.4);
    color: #f87171;
  }

  .validation-error svg {
    flex-shrink: 0;
  }

  .settings-actions {
    display: flex;
    justify-content: flex-end;
  }

  .btn-confirm {
    padding: 0.6rem 1.2rem;
    background: var(--primary-color);
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .btn-confirm:hover:not(:disabled) {
    background: var(--primary-hover);
    transform: translateY(-1px);
  }

  .btn-confirm:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
</style>
