<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '$stores/locale';
  import { settingsModalStore } from '$stores/settingsModalStore';
  import {
    getSpeakerAttributeSettings,
    updateSpeakerAttributeSettings,
    resetSpeakerAttributeSettings,
    type SpeakerAttributeSettings,
  } from '$lib/api/speakerAttributeSettings';

  let settings: SpeakerAttributeSettings = {
    detection_enabled: true,
    gender_detection_enabled: true,
    show_attributes_on_cards: true,
  };

  let originalSettings: SpeakerAttributeSettings = { ...settings };
  let loading = true;
  let saving = false;
  let error = '';
  let successMessage = '';

  $: isDirty =
    settings.detection_enabled !== originalSettings.detection_enabled ||
    settings.gender_detection_enabled !== originalSettings.gender_detection_enabled ||
    settings.show_attributes_on_cards !== originalSettings.show_attributes_on_cards;

  $: settingsModalStore.setDirty('speaker-attributes', isDirty);

  onMount(async () => {
    await loadSettings();
  });

  async function loadSettings() {
    loading = true;
    error = '';
    try {
      settings = await getSpeakerAttributeSettings();
      originalSettings = { ...settings };
    } catch (e) {
      error = 'Failed to load speaker attribute settings';
      console.error(e);
    } finally {
      loading = false;
    }
  }

  async function saveSettings() {
    saving = true;
    error = '';
    successMessage = '';
    try {
      settings = await updateSpeakerAttributeSettings(settings);
      originalSettings = { ...settings };
      successMessage = $t('settings.speakerAttributes.saved');
      setTimeout(() => (successMessage = ''), 3000);
    } catch (e) {
      error = 'Failed to save settings';
      console.error(e);
    } finally {
      saving = false;
    }
  }

  async function resetToDefaults() {
    saving = true;
    error = '';
    try {
      await resetSpeakerAttributeSettings();
      await loadSettings();
      successMessage = $t('settings.speakerAttributes.reset');
      setTimeout(() => (successMessage = ''), 3000);
    } catch (e) {
      error = 'Failed to reset settings';
      console.error(e);
    } finally {
      saving = false;
    }
  }
</script>

<div class="settings-section">
  <h3>{$t('settings.speakerAttributes.title')}</h3>
  <p class="section-description">{$t('settings.speakerAttributes.description')}</p>

  {#if loading}
    <div class="loading-spinner">Loading...</div>
  {:else}
    <div class="settings-group">
      <div class="setting-row">
        <div class="setting-info">
          <label class="setting-label" for="detection-enabled">
            {$t('settings.speakerAttributes.enableDetection')}
          </label>
          <p class="setting-description">
            {$t('settings.speakerAttributes.enableDetectionDesc')}
          </p>
        </div>
        <label class="toggle">
          <input
            type="checkbox"
            id="detection-enabled"
            bind:checked={settings.detection_enabled}
          />
          <span class="toggle-slider"></span>
        </label>
      </div>

      {#if settings.detection_enabled}
        <div class="setting-row sub-setting">
          <div class="setting-info">
            <label class="setting-label" for="gender-detection">
              {$t('settings.speakerAttributes.genderDetection')}
            </label>
            <p class="setting-description">
              {$t('settings.speakerAttributes.genderDetectionDesc')}
            </p>
          </div>
          <label class="toggle">
            <input
              type="checkbox"
              id="gender-detection"
              bind:checked={settings.gender_detection_enabled}
            />
            <span class="toggle-slider"></span>
          </label>
        </div>

        <div class="setting-row sub-setting">
          <div class="setting-info">
            <label class="setting-label" for="show-on-cards">
              {$t('settings.speakerAttributes.showOnCards')}
            </label>
            <p class="setting-description">
              {$t('settings.speakerAttributes.showOnCardsDesc')}
            </p>
          </div>
          <label class="toggle">
            <input
              type="checkbox"
              id="show-on-cards"
              bind:checked={settings.show_attributes_on_cards}
            />
            <span class="toggle-slider"></span>
          </label>
        </div>
      {/if}
    </div>

    {#if error}
      <div class="error-message">{error}</div>
    {/if}

    {#if successMessage}
      <div class="success-message">{successMessage}</div>
    {/if}

    <div class="button-group">
      <button class="btn btn-secondary" on:click={resetToDefaults} disabled={saving}>
        {$t('settings.speakerAttributes.resetDefaults')}
      </button>
      <button
        class="btn btn-primary"
        on:click={saveSettings}
        disabled={saving || !isDirty}
      >
        {saving ? $t('common.saving') : $t('settings.speakerAttributes.save')}
      </button>
    </div>
  {/if}
</div>

<style>
  .settings-section {
    padding: 0;
  }

  .settings-section h3 {
    font-size: 1.1rem;
    font-weight: 600;
    margin-bottom: 0.25rem;
    color: var(--text-color, #e0e0e0);
  }

  .section-description {
    font-size: 0.85rem;
    color: var(--text-secondary, #999);
    margin-bottom: 1.5rem;
    line-height: 1.4;
  }

  .settings-group {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-bottom: 1.5rem;
  }

  .setting-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
    padding: 0.75rem;
    border-radius: 8px;
    background: var(--background-color, #2a2a2a);
    border: 1px solid var(--border-color);
  }

  .setting-row.sub-setting {
    margin-left: 1.5rem;
    background: var(--surface-color, #333);
  }

  .setting-info {
    flex: 1;
  }

  .setting-label {
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--text-color, #e0e0e0);
    display: block;
    margin-bottom: 0.25rem;
  }

  .setting-description {
    font-size: 0.8rem;
    color: var(--text-secondary, #999);
    margin: 0;
    line-height: 1.3;
  }

  .toggle {
    position: relative;
    display: inline-block;
    width: 44px;
    height: 24px;
    flex-shrink: 0;
    margin-top: 0.1rem;
  }

  .toggle input {
    opacity: 0;
    width: 0;
    height: 0;
  }

  .toggle-slider {
    position: absolute;
    cursor: pointer;
    inset: 0;
    background-color: var(--border-color, #555);
    border-radius: 24px;
    transition: 0.2s;
  }

  .toggle-slider::before {
    content: '';
    position: absolute;
    height: 18px;
    width: 18px;
    left: 3px;
    bottom: 3px;
    background-color: white;
    border-radius: 50%;
    transition: 0.2s;
  }

  .toggle input:checked + .toggle-slider {
    background-color: var(--primary-color, #4a9eff);
  }

  .toggle input:checked + .toggle-slider::before {
    transform: translateX(20px);
  }

  .button-group {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
    margin-top: 1rem;
  }

  .btn {
    padding: 0.5rem 1.25rem;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.85rem;
    font-weight: 500;
    transition: opacity 0.2s;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-primary {
    background: var(--primary-color, #4a9eff);
    color: white;
  }

  .btn-primary:hover:not(:disabled) {
    background: var(--primary-hover, #3a8eef);
  }

  .btn-secondary {
    background: transparent;
    color: var(--text-color, #e0e0e0);
    border: 1px solid var(--border-color, #444);
  }

  .btn-secondary:hover:not(:disabled) {
    background: var(--background-color, #333);
  }

  .error-message {
    color: var(--error-color, #ff6b6b);
    font-size: 0.85rem;
    margin-bottom: 0.75rem;
    padding: 0.5rem 0.75rem;
    background: rgba(255, 107, 107, 0.1);
    border-radius: 6px;
  }

  .success-message {
    color: var(--success-color, #51cf66);
    font-size: 0.85rem;
    margin-bottom: 0.75rem;
    padding: 0.5rem 0.75rem;
    background: rgba(81, 207, 102, 0.1);
    border-radius: 6px;
  }

  .loading-spinner {
    text-align: center;
    padding: 2rem;
    color: var(--text-secondary, #999);
  }
</style>
