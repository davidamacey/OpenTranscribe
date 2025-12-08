<script lang="ts">
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';
  import axiosInstance from '../lib/axios';
  import { toastStore } from '../stores/toast';
  import {
    getTranscriptionSettings,
    getTranscriptionSystemDefaults,
    type TranscriptionSettings,
    type TranscriptionSystemDefaults,
    DEFAULT_TRANSCRIPTION_SETTINGS
  } from '../lib/api/transcriptionSettings';

  export let file: any = null;
  export let reprocessing: boolean = false;

  const dispatch = createEventDispatcher();

  // Container reference for click-outside detection
  let containerRef: HTMLDivElement;

  // Dropdown state
  let showDropdown = false;
  let dropdownMode: 'settings' | 'confirmation' = 'settings';
  let fadeTimeout: ReturnType<typeof setTimeout> | null = null;

  // Speaker settings
  let minSpeakers: number | null = null;
  let maxSpeakers: number | null = null;
  let numSpeakers: number | null = null;

  // User transcription preferences
  let transcriptionSettings: TranscriptionSettings | null = null;
  let transcriptionSystemDefaults: TranscriptionSystemDefaults | null = null;
  let prefsLoaded = false;

  // Click outside handler
  function handleClickOutside(event: MouseEvent) {
    if (showDropdown && containerRef && !containerRef.contains(event.target as Node)) {
      closeDropdown();
    }
  }

  // Load user preferences on mount
  onMount(async () => {
    // Add click-outside listener
    document.addEventListener('click', handleClickOutside);

    try {
      const [userSettings, systemDefaults] = await Promise.all([
        getTranscriptionSettings(),
        getTranscriptionSystemDefaults()
      ]);
      transcriptionSettings = userSettings;
      transcriptionSystemDefaults = systemDefaults;
    } catch (err) {
      console.error('Failed to load transcription settings:', err);
      transcriptionSettings = { ...DEFAULT_TRANSCRIPTION_SETTINGS };
    } finally {
      prefsLoaded = true;
    }
  });

  onDestroy(() => {
    if (fadeTimeout) clearTimeout(fadeTimeout);
    document.removeEventListener('click', handleClickOutside);
  });

  // Reactive validation
  $: if (minSpeakers !== null && minSpeakers < 1) minSpeakers = 1;
  $: if (maxSpeakers !== null && maxSpeakers < 1) maxSpeakers = 1;
  $: if (numSpeakers !== null && numSpeakers < 1) numSpeakers = 1;
  $: isValid = !(minSpeakers !== null && maxSpeakers !== null && minSpeakers > maxSpeakers);

  function handleReprocessClick() {
    if (!prefsLoaded || !transcriptionSettings) {
      // Default to showing settings
      openSettingsDropdown();
      return;
    }

    const behavior = transcriptionSettings.speaker_prompt_behavior;

    if (behavior === 'always_prompt') {
      // Pre-fill with user's saved values and show settings
      minSpeakers = transcriptionSettings.min_speakers || null;
      maxSpeakers = transcriptionSettings.max_speakers || null;
      openSettingsDropdown();
    } else {
      // Show confirmation message briefly, then start processing
      showConfirmationAndProcess();
    }
  }

  function openSettingsDropdown() {
    dropdownMode = 'settings';
    showDropdown = true;
  }

  function showConfirmationAndProcess() {
    dropdownMode = 'confirmation';
    showDropdown = true;
  }

  function closeDropdown() {
    showDropdown = false;
    if (fadeTimeout) {
      clearTimeout(fadeTimeout);
      fadeTimeout = null;
    }
  }

  function handleCustomize() {
    // Switch to settings mode
    if (fadeTimeout) {
      clearTimeout(fadeTimeout);
      fadeTimeout = null;
    }

    // Pre-fill with current effective values
    if (transcriptionSettings) {
      if (transcriptionSettings.speaker_prompt_behavior === 'use_custom') {
        minSpeakers = transcriptionSettings.min_speakers || null;
        maxSpeakers = transcriptionSettings.max_speakers || null;
      } else if (transcriptionSystemDefaults) {
        minSpeakers = transcriptionSystemDefaults.min_speakers;
        maxSpeakers = transcriptionSystemDefaults.max_speakers;
      }
    }
    dropdownMode = 'settings';
  }

  async function executeReprocess() {
    if (!file?.id || reprocessing) return;

    try {
      reprocessing = true;
      showDropdown = false;

      // Determine effective speaker settings
      let effectiveMin: number | null = null;
      let effectiveMax: number | null = null;
      let effectiveNum: number | null = null;

      if (dropdownMode === 'settings') {
        // User was in settings mode - use form values
        effectiveMin = minSpeakers;
        effectiveMax = maxSpeakers;
        effectiveNum = numSpeakers;
      } else if (transcriptionSettings) {
        // Confirmation mode - use behavior-based settings
        if (transcriptionSettings.speaker_prompt_behavior === 'use_custom') {
          effectiveMin = transcriptionSettings.min_speakers || null;
          effectiveMax = transcriptionSettings.max_speakers || null;
        }
        // 'use_defaults' sends null values (backend uses system defaults)
      }

      // Build request body
      const requestBody: any = {};
      if (effectiveMin !== null) requestBody.min_speakers = effectiveMin;
      if (effectiveMax !== null) requestBody.max_speakers = effectiveMax;
      if (effectiveNum !== null) requestBody.num_speakers = effectiveNum;

      await axiosInstance.post(
        `/api/files/${file.id}/reprocess`,
        Object.keys(requestBody).length > 0 ? requestBody : undefined
      );

      // Reset form
      minSpeakers = null;
      maxSpeakers = null;
      numSpeakers = null;

      dispatch('reprocess', { fileId: file.id });
    } catch (error) {
      console.error('Error reprocessing file:', error);
      toastStore.error('Failed to start reprocessing');
      reprocessing = false;
    }
  }

  function getConfirmationMessage(): string {
    if (!transcriptionSettings) return '';

    if (transcriptionSettings.speaker_prompt_behavior === 'use_defaults') {
      const min = transcriptionSystemDefaults?.min_speakers ?? 1;
      const max = transcriptionSystemDefaults?.max_speakers ?? 20;
      return `Using system defaults (${min}-${max} speakers)`;
    } else if (transcriptionSettings.speaker_prompt_behavior === 'use_custom') {
      return `Using your settings (${transcriptionSettings.min_speakers}-${transcriptionSettings.max_speakers} speakers)`;
    }
    return '';
  }
</script>

{#if file && (file.status === 'error' || file.status === 'completed' || file.status === 'failed')}
  <div class="reprocess-container" bind:this={containerRef}>
    <button
      class="reprocess-button"
      on:click={handleReprocessClick}
      disabled={reprocessing}
      title="Reprocess this file with the transcription AI"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M23 4v6h-6"></path>
        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
      </svg>
      {reprocessing ? 'Reprocessing...' : 'Reprocess'}
    </button>

    {#if showDropdown}
      <div class="dropdown">
        {#if dropdownMode === 'confirmation'}
          <!-- Confirmation message -->
          <div class="confirmation-content">
            <div class="confirmation-info">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="16" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12.01" y2="8"></line>
              </svg>
              <span class="confirmation-message">{getConfirmationMessage()}</span>
            </div>
            <div class="confirmation-actions">
              <button class="btn-customize" on:click={handleCustomize}>Customize</button>
              <button class="btn-start" on:click={executeReprocess}>Start</button>
            </div>
          </div>
        {:else}
          <!-- Speaker settings form -->
          <div class="settings-header">
            <h4>Speaker Diarization Settings</h4>
            <p>Leave empty to use defaults.</p>
          </div>

          <div class="settings-row">
            <div class="setting-field">
              <label for="reprocess-min-speakers">Min Speakers</label>
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
              <label for="reprocess-max-speakers">Max Speakers</label>
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
              Fixed Count
              <span class="hint">(overrides min/max)</span>
            </label>
            <input
              id="reprocess-num-speakers"
              type="number"
              min="1"
              placeholder="Auto"
              bind:value={numSpeakers}
            />
          </div>

          {#if !isValid}
            <div class="validation-error">
              Min must be ≤ max
            </div>
          {/if}

          <div class="settings-actions">
            <button class="btn-cancel" on:click={closeDropdown}>Cancel</button>
            <button class="btn-start" on:click={executeReprocess} disabled={!isValid}>
              Start
            </button>
          </div>
        {/if}
      </div>
    {/if}
  </div>
{/if}

<style>
  .reprocess-container {
    position: relative;
    display: inline-block;
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

  /* Dropdown */
  .dropdown {
    position: absolute;
    top: calc(100% + 8px);
    right: 0;
    min-width: 280px;
    padding: 1rem;
    background-color: var(--card-background, #fff);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    z-index: 1000;
    animation: slideDown 0.15s ease;
  }

  @keyframes slideDown {
    from {
      opacity: 0;
      transform: translateY(-8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  /* Confirmation content */
  .confirmation-content {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .confirmation-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background-color: rgba(59, 130, 246, 0.08);
    border: 1px solid rgba(59, 130, 246, 0.2);
    border-radius: 6px;
  }

  .confirmation-info svg {
    color: var(--primary-color, #3b82f6);
    flex-shrink: 0;
  }

  .confirmation-message {
    font-size: 0.85rem;
    color: var(--text-primary);
  }

  .confirmation-actions {
    display: flex;
    gap: 0.5rem;
    justify-content: flex-end;
  }

  .btn-customize {
    padding: 0.4rem 0.8rem;
    background: #6b7280;
    border: 1px solid #6b7280;
    border-radius: 10px;
    color: white;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .btn-customize:hover {
    background: #4b5563;
    border-color: #4b5563;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(75, 85, 99, 0.25);
  }

  .btn-customize:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(75, 85, 99, 0.2);
  }

  .btn-start {
    padding: 0.4rem 0.8rem;
    background: #3b82f6;
    border: none;
    border-radius: 10px;
    color: white;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .btn-start:hover:not(:disabled) {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .btn-start:active:not(:disabled) {
    transform: translateY(0);
  }

  .btn-start:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  /* Settings form */
  .settings-header {
    margin-bottom: 0.75rem;
  }

  .settings-header h4 {
    margin: 0;
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  .settings-header p {
    margin: 0.25rem 0 0 0;
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  .settings-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
  }

  .setting-field {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .setting-field label {
    font-size: 0.8rem;
    font-weight: 500;
    color: var(--text-primary);
  }

  .setting-field .hint {
    font-weight: 400;
    color: var(--text-secondary);
    font-size: 0.7rem;
  }

  .setting-field input {
    padding: 0.4rem 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background-color: var(--input-background, var(--card-background));
    color: var(--text-primary);
    font-size: 0.85rem;
  }

  .setting-field input:focus {
    outline: none;
    border-color: var(--primary-color);
  }

  .setting-field input:disabled {
    opacity: 0.5;
  }

  .setting-field input::placeholder {
    color: var(--text-muted);
  }

  .validation-error {
    padding: 0.4rem;
    background-color: rgba(239, 68, 68, 0.1);
    border-radius: 4px;
    color: #dc2626;
    font-size: 0.75rem;
    margin-bottom: 0.5rem;
  }

  .settings-actions {
    display: flex;
    gap: 0.5rem;
    justify-content: flex-end;
    margin-top: 0.75rem;
  }

  .btn-cancel {
    padding: 0.4rem 0.8rem;
    background: #6b7280;
    border: 1px solid #6b7280;
    border-radius: 10px;
    color: white;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .btn-cancel:hover {
    background: #4b5563;
    border-color: #4b5563;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(75, 85, 99, 0.25);
  }

  .btn-cancel:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(75, 85, 99, 0.2);
  }

  :global(.dark) .dropdown {
    background-color: var(--card-background, #1a1a2e);
  }

  :global(.dark) .validation-error {
    color: #f87171;
  }
</style>
