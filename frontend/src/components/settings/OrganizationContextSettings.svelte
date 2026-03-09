<script lang="ts">
  import { onMount } from 'svelte';
  import Spinner from '../ui/Spinner.svelte';
  import {
    getOrganizationContext,
    updateOrganizationContext,
    resetOrganizationContext,
  } from '$lib/api/organizationContext';
  import { settingsModalStore } from '$stores/settingsModalStore';
  import { toastStore } from '$stores/toast';
  import { t } from '$stores/locale';

  let contextText = '';
  let includeInDefaultPrompts = true;
  let includeInCustomPrompts = false;
  let loading = false;
  let saving = false;

  // Original values for change detection
  let originalContextText = '';
  let originalIncludeInDefaultPrompts = true;
  let originalIncludeInCustomPrompts = false;

  $: settingsChanged =
    contextText !== originalContextText ||
    includeInDefaultPrompts !== originalIncludeInDefaultPrompts ||
    includeInCustomPrompts !== originalIncludeInCustomPrompts;

  $: {
    settingsModalStore.setDirty('organization-context', settingsChanged);
  }

  $: charCount = contextText.length;
  $: charLimitWarning = charCount > 9000;

  onMount(async () => {
    await loadSettings();
  });

  async function loadSettings() {
    loading = true;
    try {
      const settings = await getOrganizationContext();
      contextText = settings.context_text;
      includeInDefaultPrompts = settings.include_in_default_prompts;
      includeInCustomPrompts = settings.include_in_custom_prompts;

      originalContextText = settings.context_text;
      originalIncludeInDefaultPrompts = settings.include_in_default_prompts;
      originalIncludeInCustomPrompts = settings.include_in_custom_prompts;
    } catch (err) {
      console.error('Failed to load organization context:', err);
      toastStore.error($t('settings.orgContext.loadFailed'));
    } finally {
      loading = false;
    }
  }

  async function saveSettings() {
    saving = true;
    try {
      const result = await updateOrganizationContext({
        context_text: contextText,
        include_in_default_prompts: includeInDefaultPrompts,
        include_in_custom_prompts: includeInCustomPrompts,
      });

      contextText = result.context_text;
      includeInDefaultPrompts = result.include_in_default_prompts;
      includeInCustomPrompts = result.include_in_custom_prompts;

      originalContextText = result.context_text;
      originalIncludeInDefaultPrompts = result.include_in_default_prompts;
      originalIncludeInCustomPrompts = result.include_in_custom_prompts;

      settingsModalStore.clearDirty('organization-context');
      toastStore.success($t('settings.orgContext.saved'));
    } catch (err) {
      console.error('Failed to save organization context:', err);
      toastStore.error($t('settings.orgContext.saveFailed'));
    } finally {
      saving = false;
    }
  }

  async function handleReset() {
    saving = true;
    try {
      await resetOrganizationContext();

      contextText = '';
      includeInDefaultPrompts = true;
      includeInCustomPrompts = false;

      originalContextText = '';
      originalIncludeInDefaultPrompts = true;
      originalIncludeInCustomPrompts = false;

      settingsModalStore.clearDirty('organization-context');
      toastStore.success($t('settings.orgContext.resetSuccess'));
    } catch (err) {
      console.error('Failed to reset organization context:', err);
      toastStore.error($t('settings.orgContext.resetFailed'));
    } finally {
      saving = false;
    }
  }
</script>

<div class="org-context-settings">
  {#if loading}
    <div class="loading-state">
      <Spinner size="large" />
      <p>{$t('settings.orgContext.loading')}</p>
    </div>
  {:else}
    <div class="settings-form">
      <!-- Context Text -->
      <div class="form-group">
        <label for="org-context-text" class="form-label">
          {$t('settings.orgContext.label')}
          <span class="label-hint">{$t('settings.orgContext.labelHint')}</span>
        </label>
        <textarea
          id="org-context-text"
          class="form-textarea"
          bind:value={contextText}
          maxlength="10000"
          rows="8"
          placeholder={$t('settings.orgContext.placeholder')}
        ></textarea>
        <div class="char-counter" class:char-warning={charLimitWarning}>
          {charCount.toLocaleString()} / 10,000
        </div>
      </div>

      <!-- Include in Default Prompts -->
      <div class="form-group">
        <div class="toggle-group">
          <div class="toggle-header">
            <label for="include-default" class="toggle-label">
              <span class="label-text">{$t('settings.orgContext.includeDefault')}</span>
              <span class="label-description">
                {$t('settings.orgContext.includeDefaultDesc')}
              </span>
            </label>
            <label class="toggle-switch">
              <input
                id="include-default"
                type="checkbox"
                bind:checked={includeInDefaultPrompts}
              />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>
      </div>

      <!-- Include in Custom Prompts -->
      <div class="form-group">
        <div class="toggle-group">
          <div class="toggle-header">
            <label for="include-custom" class="toggle-label">
              <span class="label-text">{$t('settings.orgContext.includeCustom')}</span>
              <span class="label-description">
                {$t('settings.orgContext.includeCustomDesc')}
              </span>
            </label>
            <label class="toggle-switch">
              <input
                id="include-custom"
                type="checkbox"
                bind:checked={includeInCustomPrompts}
              />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="form-actions">
        <button
          class="btn btn-secondary"
          on:click={handleReset}
          disabled={saving}
        >
          {$t('common.resetToDefaults')}
        </button>
        <button
          class="btn btn-primary"
          on:click={saveSettings}
          disabled={saving || !settingsChanged}
        >
          {#if saving}
            <Spinner size="small" color="white" />
            {$t('common.saving')}
          {:else}
            {$t('common.saveSettings')}
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
          <p><strong>{$t('settings.orgContext.howItWorks')}</strong></p>
          <ul>
            <li>{$t('settings.orgContext.howItWorks1')}</li>
            <li>{$t('settings.orgContext.howItWorks2')}</li>
            <li>{$t('settings.orgContext.howItWorks3')}</li>
            <li>{$t('settings.orgContext.howItWorks4')}</li>
          </ul>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .org-context-settings {
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

  .form-textarea {
    padding: 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    font-size: 0.8125rem;
    font-family: inherit;
    background: var(--background-color);
    color: var(--text-color);
    resize: vertical;
    min-height: 120px;
    transition: all 0.2s ease;
    line-height: 1.5;
  }

  .form-textarea:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .form-textarea::placeholder {
    color: var(--text-secondary);
    opacity: 0.7;
  }

  .char-counter {
    font-size: 0.75rem;
    color: var(--text-secondary);
    text-align: right;
  }

  .char-warning {
    color: var(--warning-color, #f59e0b);
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

  .form-actions {
    display: flex;
    gap: 0.75rem;
    justify-content: flex-end;
    padding-top: 0.5rem;
  }

  .btn {
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    border: none;
    font-size: 0.8125rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .btn-primary {
    background-color: #3b82f6;
    color: white;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .btn-primary:hover:not(:disabled) {
    background-color: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .btn-primary:active:not(:disabled) {
    transform: translateY(0);
  }

  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-secondary {
    background-color: var(--background-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
    margin-right: auto;
  }

  .btn-secondary:hover:not(:disabled) {
    background: var(--button-hover, #e5e7eb);
  }

  .btn-secondary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
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
    .org-context-settings {
      padding: 1rem 0;
    }

    .toggle-header {
      flex-direction: column;
    }

    .form-actions {
      flex-direction: column;
    }

    .btn {
      width: 100%;
      justify-content: center;
    }

    .info-box {
      flex-direction: column;
    }
  }
</style>
