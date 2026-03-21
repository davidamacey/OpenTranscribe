<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { t } from '$stores/locale';

  // All fields come from a single config object (saved under "local" category)
  export let config: Record<string, any> = {};

  const dispatch = createEventDispatcher();

  // Helper to get value with default - only use default if value is truly undefined
  function getVal<T>(key: string, defaultVal: T): T {
    const val = config[key];
    return val !== undefined ? val : defaultVal;
  }

  let formData = {
    local_enabled: getVal('local_enabled', true),
    allow_registration: getVal('allow_registration', false),
    // Password policy
    password_min_length: getVal('password_min_length', 12),
    password_require_uppercase: getVal('password_require_uppercase', true),
    password_require_lowercase: getVal('password_require_lowercase', true),
    password_require_numbers: getVal('password_require_numbers', true),
    password_require_special: getVal('password_require_special', true),
    password_max_age_days: getVal('password_max_age_days', 90),
    password_history_count: getVal('password_history_count', 5),
    // MFA
    mfa_enabled: getVal('mfa_enabled', true),
    mfa_required: getVal('mfa_required', false),
    mfa_issuer: getVal('mfa_issuer', 'OpenTranscribe'),
    // Rate limiting
    max_login_attempts: getVal('max_login_attempts', 5),
    lockout_duration_minutes: getVal('lockout_duration_minutes', 30)
  };

  let saving = false;

  // Update formData when config changes
  $: if (config) {
    formData = {
      local_enabled: getVal('local_enabled', true),
      allow_registration: getVal('allow_registration', false),
      password_min_length: getVal('password_min_length', 12),
      password_require_uppercase: getVal('password_require_uppercase', true),
      password_require_lowercase: getVal('password_require_lowercase', true),
      password_require_numbers: getVal('password_require_numbers', true),
      password_require_special: getVal('password_require_special', true),
      password_max_age_days: getVal('password_max_age_days', 90),
      password_history_count: getVal('password_history_count', 5),
      mfa_enabled: getVal('mfa_enabled', true),
      mfa_required: getVal('mfa_required', false),
      mfa_issuer: getVal('mfa_issuer', 'OpenTranscribe'),
      max_login_attempts: getVal('max_login_attempts', 5),
      lockout_duration_minutes: getVal('lockout_duration_minutes', 30)
    };
  }

  function handleChange() {
    dispatch('change');
  }

  function handleSave() {
    saving = true;
    dispatch('save', formData);
    setTimeout(() => saving = false, 500);
  }

  function getPasswordStrengthPreview(): string {
    const requirements: string[] = [];
    if (formData.password_min_length > 0) {
      requirements.push(`${formData.password_min_length}+ ${$t('settings.localAuth.characters')}`);
    }
    if (formData.password_require_uppercase) requirements.push($t('settings.localAuth.uppercase'));
    if (formData.password_require_lowercase) requirements.push($t('settings.localAuth.lowercase'));
    if (formData.password_require_numbers) requirements.push($t('settings.localAuth.numbers'));
    if (formData.password_require_special) requirements.push($t('settings.localAuth.specialChars'));
    return requirements.join(', ');
  }
</script>

<div class="settings-panel">
  <div class="enable-toggle">
    <label class="toggle-label">
      <input
        type="checkbox"
        bind:checked={formData.local_enabled}
        on:change={handleChange}
      />
      <span class="toggle-text">{$t('settings.localAuth.enableLocal')}</span>
    </label>
  </div>

  <div class="section" class:disabled={!formData.local_enabled}>
    <h3>{$t('settings.localAuth.registrationSettings')}</h3>

    <label class="checkbox-label">
      <input
        type="checkbox"
        bind:checked={formData.allow_registration}
        on:change={handleChange}
        disabled={!formData.local_enabled}
      />
      <span>{$t('settings.localAuth.allowSelfRegistration')}</span>
    </label>
    <span class="help-text indented">{$t('settings.localAuth.selfRegistrationHelp')}</span>
  </div>

  <div class="section" class:disabled={!formData.local_enabled}>
    <h3>{$t('settings.localAuth.passwordPolicy')}</h3>

    <div class="policy-preview">
      <strong>{$t('settings.localAuth.currentRequirements')}</strong> {getPasswordStrengthPreview()}
    </div>

    <div class="form-group">
      <label for="password_min_length">{$t('settings.localAuth.minPasswordLength')}</label>
      <input
        id="password_min_length"
        type="number"
        bind:value={formData.password_min_length}
        on:input={handleChange}
        min="8"
        max="128"
        disabled={!formData.local_enabled}
      />
    </div>

    <div class="checkbox-grid">
      <label class="checkbox-label">
        <input
          type="checkbox"
          bind:checked={formData.password_require_uppercase}
          on:change={handleChange}
          disabled={!formData.local_enabled}
        />
        <span>{$t('settings.localAuth.requireUppercase')}</span>
      </label>

      <label class="checkbox-label">
        <input
          type="checkbox"
          bind:checked={formData.password_require_lowercase}
          on:change={handleChange}
          disabled={!formData.local_enabled}
        />
        <span>{$t('settings.localAuth.requireLowercase')}</span>
      </label>

      <label class="checkbox-label">
        <input
          type="checkbox"
          bind:checked={formData.password_require_numbers}
          on:change={handleChange}
          disabled={!formData.local_enabled}
        />
        <span>{$t('settings.localAuth.requireNumbers')}</span>
      </label>

      <label class="checkbox-label">
        <input
          type="checkbox"
          bind:checked={formData.password_require_special}
          on:change={handleChange}
          disabled={!formData.local_enabled}
        />
        <span>{$t('settings.localAuth.requireSpecial')}</span>
      </label>
    </div>

    <div class="form-row">
      <div class="form-group">
        <label for="password_max_age_days">{$t('settings.localAuth.passwordExpiry')}</label>
        <input
          id="password_max_age_days"
          type="number"
          bind:value={formData.password_max_age_days}
          on:input={handleChange}
          min="0"
          max="365"
          disabled={!formData.local_enabled}
        />
        <span class="help-text">{$t('settings.localAuth.passwordExpiryHelp')}</span>
      </div>

      <div class="form-group">
        <label for="password_history_count">{$t('settings.localAuth.passwordHistoryCount')}</label>
        <input
          id="password_history_count"
          type="number"
          bind:value={formData.password_history_count}
          on:input={handleChange}
          min="0"
          max="24"
          disabled={!formData.local_enabled}
        />
        <span class="help-text">{$t('settings.localAuth.passwordHistoryHelp')}</span>
      </div>
    </div>
  </div>

  <div class="section" class:disabled={!formData.local_enabled}>
    <h3>{$t('settings.localAuth.mfaTitle')}</h3>

    <label class="checkbox-label">
      <input
        type="checkbox"
        bind:checked={formData.mfa_enabled}
        on:change={handleChange}
        disabled={!formData.local_enabled}
      />
      <span>{$t('settings.localAuth.enableTotp')}</span>
    </label>
    <span class="help-text indented">{$t('settings.localAuth.totpHelp')}</span>

    {#if formData.mfa_enabled}
      <div class="mfa-options">
        <label class="checkbox-label">
          <input
            type="checkbox"
            bind:checked={formData.mfa_required}
            on:change={handleChange}
            disabled={!formData.local_enabled}
          />
          <span>{$t('settings.localAuth.requireMfa')}</span>
        </label>
        <span class="help-text indented">{$t('settings.localAuth.requireMfaHelp')}</span>

        <div class="form-group">
          <label for="mfa_issuer">{$t('settings.localAuth.mfaIssuerName')}</label>
          <input
            id="mfa_issuer"
            type="text"
            bind:value={formData.mfa_issuer}
            on:input={handleChange}
            placeholder="OpenTranscribe"
            disabled={!formData.local_enabled}
          />
          <span class="help-text">{$t('settings.localAuth.mfaIssuerHelp')}</span>
        </div>
      </div>
    {/if}
  </div>

  <div class="section" class:disabled={!formData.local_enabled}>
    <h3>{$t('settings.localAuth.accountLockout')}</h3>

    <div class="form-row">
      <div class="form-group">
        <label for="max_login_attempts">{$t('settings.localAuth.maxLoginAttempts')}</label>
        <input
          id="max_login_attempts"
          type="number"
          bind:value={formData.max_login_attempts}
          on:input={handleChange}
          min="3"
          max="20"
          disabled={!formData.local_enabled}
        />
        <span class="help-text">{$t('settings.localAuth.maxLoginAttemptsHelp')}</span>
      </div>

      <div class="form-group">
        <label for="lockout_duration_minutes">{$t('settings.localAuth.lockoutDuration')}</label>
        <input
          id="lockout_duration_minutes"
          type="number"
          bind:value={formData.lockout_duration_minutes}
          on:input={handleChange}
          min="1"
          max="1440"
          disabled={!formData.local_enabled}
        />
        <span class="help-text">{$t('settings.localAuth.lockoutDurationHelp')}</span>
      </div>
    </div>
  </div>

  <div class="actions">
    <button
      class="btn btn-primary"
      on:click={handleSave}
      disabled={saving}
    >
      {saving ? $t('common.saving') : $t('settings.localAuth.saveConfiguration')}
    </button>
  </div>
</div>

<style>
  .settings-panel {
    max-width: 800px;
  }

  .enable-toggle {
    margin-bottom: 1.5rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--color-border);
  }

  .toggle-label {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    cursor: pointer;
  }

  .toggle-label input[type="checkbox"] {
    width: 1.25rem;
    height: 1.25rem;
    cursor: pointer;
  }

  .toggle-text {
    font-weight: 500;
    font-size: 1rem;
  }

  .section {
    margin-bottom: 2rem;
    padding: 1rem;
    background: var(--color-bg-secondary);
    border-radius: 8px;
    transition: opacity 0.2s;
  }

  .section.disabled {
    opacity: 0.5;
    pointer-events: none;
  }

  .section h3 {
    margin: 0 0 1rem 0;
    font-size: 0.875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-text-secondary);
  }

  .policy-preview {
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 4px;
    padding: 0.75rem;
    margin-bottom: 1rem;
    font-size: 0.875rem;
  }

  .policy-preview strong {
    color: var(--color-text);
  }

  .form-row {
    display: flex;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .form-group {
    flex: 1;
    margin-bottom: 1rem;
  }

  .form-group label {
    display: block;
    margin-bottom: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--color-text);
  }

  .form-group input[type="text"],
  .form-group input[type="number"] {
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--color-border);
    border-radius: 4px;
    background: var(--color-bg);
    color: var(--color-text);
    font-size: 0.875rem;
  }

  .form-group input:focus {
    outline: none;
    border-color: var(--color-primary);
    box-shadow: 0 0 0 2px var(--color-primary-alpha);
  }

  .form-group input:disabled {
    background: var(--color-bg-tertiary);
    cursor: not-allowed;
  }

  .help-text {
    display: block;
    margin-top: 0.25rem;
    font-size: 0.75rem;
    color: var(--color-text-tertiary);
  }

  .help-text.indented {
    margin-left: 1.5rem;
    margin-bottom: 0.75rem;
  }

  .checkbox-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.5rem;
    margin-bottom: 1rem;
  }

  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    font-size: 0.875rem;
    margin-bottom: 0.5rem;
  }

  .checkbox-label input[type="checkbox"] {
    width: 1rem;
    height: 1rem;
    cursor: pointer;
  }

  .checkbox-label input:disabled {
    cursor: not-allowed;
  }

  .mfa-options {
    margin-top: 1rem;
    padding-left: 1.5rem;
  }

  .actions {
    display: flex;
    gap: 1rem;
    justify-content: flex-end;
    padding-top: 1rem;
    border-top: 1px solid var(--color-border);
  }

  @media (max-width: 768px) {
    .form-row {
      flex-direction: column;
      gap: 0;
    }

    .checkbox-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
