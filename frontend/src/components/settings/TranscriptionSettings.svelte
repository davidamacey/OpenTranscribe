<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte';
  import {
    getTranscriptionSettings,
    updateTranscriptionSettings,
    resetTranscriptionSettings,
    getTranscriptionSystemDefaults,
    getSpeakerBehaviorLabel,
    getSpeakerBehaviorDescription,
    groupLanguages,
    type TranscriptionSettings,
    type TranscriptionSystemDefaults,
    type SpeakerPromptBehavior,
    type LanguageOption
  } from '$lib/api/transcriptionSettings';
  import { toastStore } from '$stores/toast';
  import { settingsModalStore } from '$stores/settingsModalStore';

  const dispatch = createEventDispatcher();

  // Settings state
  let minSpeakers = 1;
  let maxSpeakers = 20;
  let speakerBehavior: SpeakerPromptBehavior = 'always_prompt';
  let garbageCleanupEnabled = true;
  let garbageCleanupThreshold = 50;
  let sourceLanguage = 'auto';
  let translateToEnglish = false;
  let llmOutputLanguage = 'en';

  // Original values for change tracking
  let originalMinSpeakers = 1;
  let originalMaxSpeakers = 20;
  let originalSpeakerBehavior: SpeakerPromptBehavior = 'always_prompt';
  let originalGarbageCleanupEnabled = true;
  let originalGarbageCleanupThreshold = 50;
  let originalSourceLanguage = 'auto';
  let originalTranslateToEnglish = false;
  let originalLlmOutputLanguage = 'en';

  // System defaults
  let systemDefaults: TranscriptionSystemDefaults | null = null;

  // Grouped languages for dropdowns
  let sourceLanguageGroups: { common: LanguageOption[]; other: LanguageOption[] } = { common: [], other: [] };
  let llmLanguageOptions: LanguageOption[] = [];
  let languagesWithAlignment: Set<string> = new Set();

  // Loading states
  let loading = true;
  let saving = false;
  let resetting = false;

  // Validation
  let validationError = '';

  // Track if settings have changed
  $: settingsChanged =
    minSpeakers !== originalMinSpeakers ||
    maxSpeakers !== originalMaxSpeakers ||
    speakerBehavior !== originalSpeakerBehavior ||
    garbageCleanupEnabled !== originalGarbageCleanupEnabled ||
    garbageCleanupThreshold !== originalGarbageCleanupThreshold ||
    sourceLanguage !== originalSourceLanguage ||
    translateToEnglish !== originalTranslateToEnglish ||
    llmOutputLanguage !== originalLlmOutputLanguage;

  // Update dirty state in store
  $: {
    settingsModalStore.setDirty('transcription', settingsChanged);
    dispatch('change', { hasChanges: settingsChanged });
  }

  // Validate min/max speakers
  $: {
    if (minSpeakers > maxSpeakers) {
      validationError = 'Minimum speakers cannot be greater than maximum speakers';
    } else if (minSpeakers < 1 || minSpeakers > 50) {
      validationError = 'Minimum speakers must be between 1 and 50';
    } else if (maxSpeakers < 1 || maxSpeakers > 50) {
      validationError = 'Maximum speakers must be between 1 and 50';
    } else if (garbageCleanupThreshold < 20 || garbageCleanupThreshold > 200) {
      validationError = 'Garbage cleanup threshold must be between 20 and 200';
    } else {
      validationError = '';
    }
  }

  const speakerBehaviorOptions: SpeakerPromptBehavior[] = [
    'always_prompt',
    'use_defaults',
    'use_custom'
  ];

  onMount(async () => {
    await Promise.all([loadSettings(), loadSystemDefaults()]);
  });

  async function loadSettings() {
    loading = true;
    try {
      const settings = await getTranscriptionSettings();
      applySettings(settings);
      storeOriginalValues(settings);
    } catch (err) {
      console.error('Failed to load transcription settings:', err);
      toastStore.error('Failed to load transcription settings. Using defaults.');
    } finally {
      loading = false;
    }
  }

  async function loadSystemDefaults() {
    try {
      systemDefaults = await getTranscriptionSystemDefaults();

      // Process language options for dropdowns
      if (systemDefaults) {
        sourceLanguageGroups = groupLanguages(
          systemDefaults.available_source_languages,
          systemDefaults.common_languages
        );

        // LLM output languages (flat list, no grouping needed)
        llmLanguageOptions = Object.entries(systemDefaults.available_llm_output_languages)
          .map(([code, name]) => ({ code, name }));

        languagesWithAlignment = new Set(systemDefaults.languages_with_alignment);
      }
    } catch (err) {
      console.error('Failed to load system defaults:', err);
      // Non-critical, don't show error
    }
  }

  function applySettings(settings: TranscriptionSettings) {
    minSpeakers = settings.min_speakers;
    maxSpeakers = settings.max_speakers;
    speakerBehavior = settings.speaker_prompt_behavior;
    garbageCleanupEnabled = settings.garbage_cleanup_enabled;
    garbageCleanupThreshold = settings.garbage_cleanup_threshold;
    sourceLanguage = settings.source_language;
    translateToEnglish = settings.translate_to_english;
    llmOutputLanguage = settings.llm_output_language;
  }

  function storeOriginalValues(settings: TranscriptionSettings) {
    originalMinSpeakers = settings.min_speakers;
    originalMaxSpeakers = settings.max_speakers;
    originalSpeakerBehavior = settings.speaker_prompt_behavior;
    originalGarbageCleanupEnabled = settings.garbage_cleanup_enabled;
    originalGarbageCleanupThreshold = settings.garbage_cleanup_threshold;
    originalSourceLanguage = settings.source_language;
    originalTranslateToEnglish = settings.translate_to_english;
    originalLlmOutputLanguage = settings.llm_output_language;
  }

  async function saveSettings() {
    if (validationError) {
      toastStore.error(validationError);
      return;
    }

    saving = true;
    try {
      const updatedSettings = await updateTranscriptionSettings({
        min_speakers: minSpeakers,
        max_speakers: maxSpeakers,
        speaker_prompt_behavior: speakerBehavior,
        garbage_cleanup_enabled: garbageCleanupEnabled,
        garbage_cleanup_threshold: garbageCleanupThreshold,
        source_language: sourceLanguage,
        translate_to_english: translateToEnglish,
        llm_output_language: llmOutputLanguage
      });

      storeOriginalValues(updatedSettings);
      settingsModalStore.clearDirty('transcription');
      toastStore.success('Transcription settings saved successfully');
      dispatch('save');
    } catch (err) {
      console.error('Failed to save transcription settings:', err);
      toastStore.error('Failed to save transcription settings');
    } finally {
      saving = false;
    }
  }

  async function resetToDefaults() {
    resetting = true;
    try {
      const response = await resetTranscriptionSettings();
      applySettings(response.default_settings);
      storeOriginalValues(response.default_settings);
      settingsModalStore.clearDirty('transcription');
      toastStore.success('Transcription settings reset to defaults');
      dispatch('reset');
    } catch (err) {
      console.error('Failed to reset transcription settings:', err);
      toastStore.error('Failed to reset transcription settings');
    } finally {
      resetting = false;
    }
  }
</script>

<div class="transcription-settings">
  {#if loading}
    <div class="loading-state">
      <div class="spinner"></div>
      <p>Loading settings...</p>
    </div>
  {:else}
    <div class="settings-form">
      <!-- Speaker Settings Section -->
      <div class="settings-section">
        <div class="title-row">
          <h3 class="section-title">Speaker Detection</h3>
          <span class="info-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
            <span class="tooltip">Configure how many speakers the diarization model should detect. PyAnnote uses clustering with no hard upper limit - values up to 50+ are supported for large events.</span>
          </span>
        </div>
        <p class="section-desc">Configure speaker diarization behavior for transcriptions.</p>

        <!-- Speaker Behavior -->
        <div class="form-group">
          <label for="speaker-behavior" class="form-label">
            Behavior
            <span class="inline-info-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="16" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12.01" y2="8"></line>
              </svg>
              <span class="inline-tooltip">
                <strong>Always ask:</strong> Show speaker settings dialog on every upload or reprocess.<br><br>
                <strong>Use system defaults:</strong> Skip the dialog and automatically use system-wide defaults (Min: {systemDefaults?.min_speakers ?? 1}, Max: {systemDefaults?.max_speakers ?? 20}).<br><br>
                <strong>Use my saved settings:</strong> Skip the dialog and use your custom min/max values saved below.
              </span>
            </span>
          </label>
          <select
            id="speaker-behavior"
            class="form-select"
            bind:value={speakerBehavior}
          >
            {#each speakerBehaviorOptions as option}
              <option value={option}>{getSpeakerBehaviorLabel(option)}</option>
            {/each}
          </select>
          <p class="input-hint">{getSpeakerBehaviorDescription(speakerBehavior)}</p>
        </div>

        <!-- Min/Max Speakers -->
        {#if speakerBehavior === 'use_custom'}
          <div class="speaker-range-row">
            <div class="form-group compact">
              <label for="min-speakers" class="form-label">Min Speakers</label>
              <input
                id="min-speakers"
                type="number"
                min="1"
                max="50"
                class="form-input number-input"
                bind:value={minSpeakers}
              />
            </div>
            <div class="form-group compact">
              <label for="max-speakers" class="form-label">Max Speakers</label>
              <input
                id="max-speakers"
                type="number"
                min="1"
                max="50"
                class="form-input number-input"
                bind:value={maxSpeakers}
              />
            </div>
          </div>
        {/if}

        <!-- System Defaults Info -->
        {#if systemDefaults}
          <div class="defaults-info">
            <span class="defaults-label">System defaults:</span>
            <span class="defaults-value">Min: {systemDefaults.min_speakers}, Max: {systemDefaults.max_speakers}</span>
          </div>
        {/if}
      </div>

      <!-- Garbage Cleanup Section -->
      <div class="settings-section">
        <div class="title-row">
          <h3 class="section-title">Garbage Word Cleanup</h3>
          <span class="info-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
            <span class="tooltip">WhisperX can sometimes misinterpret background noise (fans, static, rumbling) as extremely long "words" with no spaces. This feature detects and replaces these artifacts with [background noise].</span>
          </span>
        </div>
        <p class="section-desc">Replace long noise artifacts with [background noise].</p>

        <div class="setting-row">
          <div class="setting-controls">
            <label class="toggle-label">
              <input type="checkbox" bind:checked={garbageCleanupEnabled} class="toggle-input" />
              <span class="toggle-switch"></span>
              <span class="toggle-text">Enable cleanup</span>
            </label>
            <div class="inline-input">
              <span class="input-label">Threshold:</span>
              <input
                type="number"
                bind:value={garbageCleanupThreshold}
                min="20"
                max="200"
                class="form-input number-input"
                disabled={!garbageCleanupEnabled}
              />
              <span class="input-suffix">chars</span>
            </div>
          </div>
        </div>

        {#if systemDefaults}
          <div class="defaults-info">
            <span class="defaults-label">System default threshold:</span>
            <span class="defaults-value">{systemDefaults.garbage_cleanup_threshold} chars</span>
          </div>
        {/if}
      </div>

      <!-- Language Settings Section -->
      <div class="settings-section">
        <div class="title-row">
          <h3 class="section-title">Language Settings</h3>
          <span class="info-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
            <span class="tooltip">Configure language options for transcription and AI summaries. Source language helps improve transcription accuracy. Translation converts foreign audio to English text.</span>
          </span>
        </div>
        <p class="section-desc">Configure language preferences for transcription and AI analysis.</p>

        <!-- Source Language -->
        <div class="form-group">
          <label for="source-language" class="form-label">
            Source Language
            <span class="inline-info-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="16" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12.01" y2="8"></line>
              </svg>
              <span class="inline-tooltip">
                <strong>Auto-detect:</strong> Let Whisper automatically identify the spoken language.<br><br>
                <strong>Specific language:</strong> Provide a hint to improve accuracy when you know the audio language.<br><br>
                Languages with word-level timestamps are marked with a checkmark.
              </span>
            </span>
          </label>
          <select
            id="source-language"
            class="form-select"
            bind:value={sourceLanguage}
          >
            <optgroup label="Common Languages">
              {#each sourceLanguageGroups.common as lang}
                <option value={lang.code}>
                  {lang.name}{languagesWithAlignment.has(lang.code) ? ' *' : ''}
                </option>
              {/each}
            </optgroup>
            <optgroup label="All Languages">
              {#each sourceLanguageGroups.other as lang}
                <option value={lang.code}>
                  {lang.name}{languagesWithAlignment.has(lang.code) ? ' *' : ''}
                </option>
              {/each}
            </optgroup>
          </select>
          <p class="input-hint">* = Word-level timestamps available</p>
        </div>

        <!-- Translate to English -->
        <div class="form-group">
          <div class="setting-row">
            <div class="setting-controls">
              <label class="toggle-label">
                <input type="checkbox" bind:checked={translateToEnglish} class="toggle-input" />
                <span class="toggle-switch"></span>
                <span class="toggle-text">Translate to English</span>
              </label>
            </div>
          </div>
          <p class="input-hint">When enabled, foreign language audio will be transcribed and translated to English. When disabled, the transcription stays in the original language.</p>
        </div>

        <!-- LLM Output Language -->
        <div class="form-group">
          <label for="llm-output-language" class="form-label">
            AI Summary Language
            <span class="inline-info-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="16" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12.01" y2="8"></line>
              </svg>
              <span class="inline-tooltip">
                Choose the language for AI-generated summaries, action items, and analysis.<br><br>
                This setting is independent of the transcription language - you can transcribe in Spanish but get summaries in English, or vice versa.
              </span>
            </span>
          </label>
          <select
            id="llm-output-language"
            class="form-select"
            bind:value={llmOutputLanguage}
          >
            {#each llmLanguageOptions as lang}
              <option value={lang.code}>{lang.name}</option>
            {/each}
          </select>
          <p class="input-hint">Language used for AI summaries and analysis</p>
        </div>

        <div class="defaults-info">
          <span class="defaults-label">Defaults:</span>
          <span class="defaults-value">Source: Auto-detect, Translate: Off, Summary: English</span>
        </div>
      </div>

      <!-- Validation Error -->
      {#if validationError}
        <div class="validation-error">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          <span>{validationError}</span>
        </div>
      {/if}

      <!-- Actions -->
      <div class="button-row">
        <button
          type="button"
          class="btn btn-secondary"
          on:click={resetToDefaults}
          disabled={saving || resetting}
        >
          {resetting ? 'Resetting...' : 'Reset to Defaults'}
        </button>
        <button
          type="button"
          class="btn btn-primary"
          on:click={saveSettings}
          disabled={saving || resetting || !settingsChanged || !!validationError}
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  {/if}
</div>

<style>
  .transcription-settings {
    padding: 0.5rem 0;
  }

  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    gap: 1rem;
    color: var(--text-secondary);
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--border-color);
    border-top-color: var(--primary-color);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .settings-form {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }

  .settings-section {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1.25rem;
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
    width: 280px;
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
    margin: 0.25rem 0 1rem 0;
  }

  .form-group {
    margin-bottom: 1rem;
  }

  .form-group.compact {
    margin-bottom: 0;
  }

  .form-label {
    display: block;
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--text-color);
    margin-bottom: 0.375rem;
  }

  .form-select {
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background-color: var(--background-color);
    color: var(--text-color);
    font-size: 0.875rem;
    cursor: pointer;
  }

  .form-select:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .input-hint {
    margin: 0.375rem 0 0 0;
    font-size: 0.75rem;
    color: var(--text-muted);
  }

  .inline-info-icon {
    position: relative;
    color: var(--text-muted);
    cursor: help;
    display: inline-flex;
    align-items: center;
    margin-left: 0.25rem;
    vertical-align: middle;
  }

  .inline-info-icon:hover {
    color: var(--primary-color);
  }

  .inline-tooltip {
    visibility: hidden;
    opacity: 0;
    position: absolute;
    left: 0;
    top: calc(100% + 8px);
    background-color: var(--surface-color, #1a1a2e);
    color: var(--text-color);
    padding: 0.75rem 1rem;
    border-radius: 8px;
    font-size: 0.75rem;
    font-weight: 400;
    line-height: 1.5;
    width: 320px;
    z-index: 1000;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    border: 1px solid var(--border-color);
    transition: opacity 0.15s ease;
  }

  .inline-tooltip strong {
    color: var(--primary-color);
  }

  .inline-info-icon:hover .inline-tooltip {
    visibility: visible;
    opacity: 1;
  }

  .speaker-range-row {
    display: flex;
    gap: 1rem;
    margin-top: 1rem;
  }

  .form-input {
    padding: 0.5rem 0.625rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background-color: var(--background-color);
    color: var(--text-color);
    font-size: 0.875rem;
  }

  .form-input:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .form-input:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .number-input {
    width: 80px;
    text-align: center;
  }

  .defaults-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px dashed var(--border-color);
    font-size: 0.75rem;
  }

  .defaults-label {
    color: var(--text-muted);
  }

  .defaults-value {
    color: var(--text-secondary);
    font-family: 'Courier New', Courier, monospace;
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

  .validation-error {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    background-color: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 6px;
    color: var(--error-color, #ef4444);
    font-size: 0.8125rem;
  }

  .button-row {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
    padding-top: 0.5rem;
  }

  .btn {
    padding: 0.5rem 1rem;
    border-radius: 6px;
    font-size: 0.8125rem;
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
    background-color: var(--primary-color-dark, #2563eb);
  }

  .btn-secondary {
    background-color: transparent;
    color: var(--text-color);
    border: 1px solid var(--border-color);
  }

  .btn-secondary:hover:not(:disabled) {
    background-color: var(--background-secondary);
  }

  /* Responsive */
  @media (max-width: 640px) {
    .setting-controls {
      flex-direction: column;
      align-items: flex-start;
      gap: 1rem;
    }

    .speaker-range-row {
      flex-direction: column;
    }

    .button-row {
      flex-direction: column;
    }

    .btn {
      width: 100%;
    }
  }
</style>
