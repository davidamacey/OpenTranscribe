<script lang="ts">
  import { onMount } from 'svelte';
  import { getAudioExtractionSettings, updateAudioExtractionSettings, type AudioExtractionSettings } from '$lib/api/audioExtractionSettings';
  import { toastStore } from '$stores/toast';

  // Settings state
  let autoExtractEnabled = true;
  let extractionThresholdMb = 100;
  let rememberChoice = false;
  let showModal = true;
  let loading = false;
  let saving = false;

  // Original values for change tracking
  let originalAutoExtractEnabled = true;
  let originalExtractionThresholdMb = 100;
  let originalRememberChoice = false;
  let originalShowModal = true;

  // Track if settings have changed
  $: settingsChanged =
    autoExtractEnabled !== originalAutoExtractEnabled ||
    extractionThresholdMb !== originalExtractionThresholdMb ||
    rememberChoice !== originalRememberChoice ||
    showModal !== originalShowModal;

  onMount(async () => {
    await loadSettings();
  });

  async function loadSettings() {
    loading = true;
    try {
      const settings = await getAudioExtractionSettings();
      autoExtractEnabled = settings.auto_extract_enabled;
      extractionThresholdMb = settings.extraction_threshold_mb;
      rememberChoice = settings.remember_choice;
      showModal = settings.show_modal;

      // Store original values for change tracking
      originalAutoExtractEnabled = settings.auto_extract_enabled;
      originalExtractionThresholdMb = settings.extraction_threshold_mb;
      originalRememberChoice = settings.remember_choice;
      originalShowModal = settings.show_modal;
    } catch (err) {
      console.error('Failed to load audio extraction settings:', err);
      toastStore.error('Failed to load audio extraction settings. Using defaults.');
    } finally {
      loading = false;
    }
  }

  async function saveSettings() {
    saving = true;
    try {
      await updateAudioExtractionSettings({
        auto_extract_enabled: autoExtractEnabled,
        extraction_threshold_mb: extractionThresholdMb,
        remember_choice: rememberChoice,
        show_modal: showModal,
      });

      // Update original values after successful save
      originalAutoExtractEnabled = autoExtractEnabled;
      originalExtractionThresholdMb = extractionThresholdMb;
      originalRememberChoice = rememberChoice;
      originalShowModal = showModal;

      toastStore.success('Audio extraction settings saved successfully');
    } catch (err) {
      console.error('Failed to save audio extraction settings:', err);
      toastStore.error('Failed to save audio extraction settings');
    } finally {
      saving = false;
    }
  }
</script>

<div class="audio-extraction-settings">
  {#if loading}
    <div class="loading-state">
      <div class="spinner"></div>
      <p>Loading settings...</p>
    </div>
  {:else}
    <div class="settings-form">
      <!-- Auto Extract Enabled -->
      <div class="form-group">
        <div class="toggle-group">
          <div class="toggle-header">
            <label for="auto-extract" class="toggle-label">
              <span class="label-text">Enable Audio Extraction</span>
              <span class="label-description">
                Automatically detect large video files and offer audio extraction
              </span>
            </label>
            <label class="toggle-switch">
              <input
                id="auto-extract"
                type="checkbox"
                bind:checked={autoExtractEnabled}
              />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>
      </div>

      {#if autoExtractEnabled}
        <!-- Extraction Threshold -->
        <div class="form-group">
          <label for="threshold" class="form-label">
            File Size Threshold
            <span class="label-hint">Minimum video size to trigger extraction prompt</span>
          </label>
          <div class="threshold-input-group">
            <input
              id="threshold"
              type="number"
              min="1"
              max="10000"
              bind:value={extractionThresholdMb}
              class="form-input threshold-input"
            />
            <span class="threshold-unit">MB</span>
          </div>
          <p class="input-hint">
            Videos larger than {extractionThresholdMb}MB will prompt for audio extraction
          </p>
        </div>

        <!-- Show Modal -->
        <div class="form-group">
          <div class="toggle-group">
            <div class="toggle-header">
              <label for="show-modal" class="toggle-label">
                <span class="label-text">Show Extraction Dialog</span>
                <span class="label-description">
                  Ask before extracting audio (disable to extract automatically)
                </span>
              </label>
              <label class="toggle-switch">
                <input
                  id="show-modal"
                  type="checkbox"
                  bind:checked={showModal}
                />
                <span class="toggle-slider"></span>
              </label>
            </div>
          </div>
        </div>

        <!-- Remember Choice -->
        <div class="form-group">
          <div class="toggle-group">
            <div class="toggle-header">
              <label for="remember-choice" class="toggle-label">
                <span class="label-text">Remember Choice</span>
                <span class="label-description">
                  Remember your last extraction decision (extract vs. upload full video)
                </span>
              </label>
              <label class="toggle-switch">
                <input
                  id="remember-choice"
                  type="checkbox"
                  bind:checked={rememberChoice}
                />
                <span class="toggle-slider"></span>
              </label>
            </div>
          </div>
        </div>
      {/if}

      <!-- Save Button -->
      <div class="form-actions">
        <button
          class="save-button"
          on:click={saveSettings}
          disabled={saving || !settingsChanged}
        >
          {#if saving}
            <span class="button-spinner"></span>
            Saving...
          {:else}
            Save Settings
          {/if}
        </button>
      </div>

      <!-- Info Box -->
      <div class="info-box">
        <div class="info-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="16" x2="12" y2="12"></line>
            <line x1="12" y1="8" x2="12.01" y2="8"></line>
          </svg>
        </div>
        <div class="info-content">
          <p><strong>How it works:</strong></p>
          <ul>
            <li>Large video files are automatically detected during upload</li>
            <li>Audio is extracted client-side using your browser (nothing sent to server until complete)</li>
            <li>Original video metadata is preserved for accurate transcription</li>
            <li>Typical size reduction: 90%+ (500MB video → 45MB audio)</li>
            <li>Format: Opus @ 32kbps, 16kHz mono (optimal for Whisper ASR)</li>
          </ul>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .audio-extraction-settings {
    max-width: 800px;
    padding: 1.5rem 0;
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
    width: 40px;
    height: 40px;
    border: 3px solid var(--border-color);
    border-top-color: var(--primary-color);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
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
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .label-hint {
    font-size: 0.8125rem;
    font-weight: 400;
    color: var(--text-secondary);
  }

  .toggle-group {
    padding: 1rem;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    transition: all 0.2s ease;
  }

  .toggle-group:hover {
    border-color: var(--primary-color);
  }

  .toggle-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
  }

  .toggle-label {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    cursor: pointer;
  }

  .label-text {
    font-weight: 500;
    color: var(--text-color);
  }

  .label-description {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    line-height: 1.4;
  }

  .toggle-switch {
    position: relative;
    display: inline-block;
    width: 48px;
    height: 24px;
    flex-shrink: 0;
    cursor: pointer;
  }

  .toggle-switch input {
    opacity: 0;
    width: 0;
    height: 0;
  }

  .toggle-slider {
    position: absolute;
    cursor: pointer;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: var(--border-color);
    transition: 0.3s;
    border-radius: 24px;
  }

  .toggle-slider:before {
    position: absolute;
    content: "";
    height: 18px;
    width: 18px;
    left: 3px;
    bottom: 3px;
    background-color: white;
    transition: 0.3s;
    border-radius: 50%;
  }

  input:checked + .toggle-slider {
    background-color: var(--primary-color);
  }

  input:checked + .toggle-slider:before {
    transform: translateX(24px);
  }

  .threshold-input-group {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .threshold-input {
    width: 120px;
  }

  .threshold-unit {
    font-weight: 500;
    color: var(--text-secondary);
  }

  .form-input {
    padding: 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    font-size: 0.8125rem;
    background: var(--background-color);
    color: var(--text-color);
    transition: all 0.2s ease;
  }

  .form-input:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .input-hint {
    margin: 0;
    font-size: 0.8125rem;
    color: var(--text-secondary);
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
    padding-top: 0.5rem;
  }

  .save-button {
    padding: 0.75rem 2rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .save-button:hover:not(:disabled) {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.3);
  }

  .save-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .button-spinner {
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  .info-box {
    display: flex;
    gap: 1rem;
    padding: 1rem;
    background: rgba(59, 130, 246, 0.05);
    border: 1px solid rgba(59, 130, 246, 0.2);
    border-radius: 8px;
    margin-top: 1rem;
  }

  .info-icon {
    flex-shrink: 0;
    color: var(--primary-color);
  }

  .info-content {
    flex: 1;
  }

  .info-content p {
    margin: 0 0 0.5rem 0;
    color: var(--text-color);
  }

  .info-content ul {
    margin: 0;
    padding-left: 1.25rem;
    color: var(--text-secondary);
    font-size: 0.8125rem;
    line-height: 1.6;
  }

  .info-content li {
    margin-bottom: 0.25rem;
  }

  /* Dark mode */
  :global([data-theme='dark']) .toggle-slider:before {
    background-color: #e5e7eb;
  }

  /* Responsive */
  @media (max-width: 640px) {
    .audio-extraction-settings {
      padding: 1rem 0;
    }

    .toggle-header {
      flex-direction: column;
    }

    .threshold-input {
      width: 100%;
    }

    .info-box {
      flex-direction: column;
    }
  }
</style>
