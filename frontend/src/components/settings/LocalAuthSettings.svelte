<script lang="ts">
  import { createEventDispatcher } from 'svelte';

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
      requirements.push(`${formData.password_min_length}+ characters`);
    }
    if (formData.password_require_uppercase) requirements.push('uppercase');
    if (formData.password_require_lowercase) requirements.push('lowercase');
    if (formData.password_require_numbers) requirements.push('numbers');
    if (formData.password_require_special) requirements.push('special chars');
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
      <span class="toggle-text">Enable Local (Username/Password) Authentication</span>
    </label>
  </div>

  <div class="section" class:disabled={!formData.local_enabled}>
    <h3>Registration Settings</h3>

    <label class="checkbox-label">
      <input
        type="checkbox"
        bind:checked={formData.allow_registration}
        on:change={handleChange}
        disabled={!formData.local_enabled}
      />
      <span>Allow self-registration</span>
    </label>
    <span class="help-text indented">When disabled, only admins can create new accounts</span>
  </div>

  <div class="section" class:disabled={!formData.local_enabled}>
    <h3>Password Policy</h3>

    <div class="policy-preview">
      <strong>Current requirements:</strong> {getPasswordStrengthPreview()}
    </div>

    <div class="form-group">
      <label for="password_min_length">Minimum Password Length</label>
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
        <span>Require uppercase letters</span>
      </label>

      <label class="checkbox-label">
        <input
          type="checkbox"
          bind:checked={formData.password_require_lowercase}
          on:change={handleChange}
          disabled={!formData.local_enabled}
        />
        <span>Require lowercase letters</span>
      </label>

      <label class="checkbox-label">
        <input
          type="checkbox"
          bind:checked={formData.password_require_numbers}
          on:change={handleChange}
          disabled={!formData.local_enabled}
        />
        <span>Require numbers</span>
      </label>

      <label class="checkbox-label">
        <input
          type="checkbox"
          bind:checked={formData.password_require_special}
          on:change={handleChange}
          disabled={!formData.local_enabled}
        />
        <span>Require special characters</span>
      </label>
    </div>

    <div class="form-row">
      <div class="form-group">
        <label for="password_max_age_days">Password Expiry (days)</label>
        <input
          id="password_max_age_days"
          type="number"
          bind:value={formData.password_max_age_days}
          on:input={handleChange}
          min="0"
          max="365"
          disabled={!formData.local_enabled}
        />
        <span class="help-text">Set to 0 for no expiration</span>
      </div>

      <div class="form-group">
        <label for="password_history_count">Password History Count</label>
        <input
          id="password_history_count"
          type="number"
          bind:value={formData.password_history_count}
          on:input={handleChange}
          min="0"
          max="24"
          disabled={!formData.local_enabled}
        />
        <span class="help-text">Prevent reuse of recent passwords</span>
      </div>
    </div>
  </div>

  <div class="section" class:disabled={!formData.local_enabled}>
    <h3>Multi-Factor Authentication (MFA)</h3>

    <label class="checkbox-label">
      <input
        type="checkbox"
        bind:checked={formData.mfa_enabled}
        on:change={handleChange}
        disabled={!formData.local_enabled}
      />
      <span>Enable TOTP-based MFA</span>
    </label>
    <span class="help-text indented">Allow users to set up authenticator apps (Google Authenticator, Authy, etc.)</span>

    {#if formData.mfa_enabled}
      <div class="mfa-options">
        <label class="checkbox-label">
          <input
            type="checkbox"
            bind:checked={formData.mfa_required}
            on:change={handleChange}
            disabled={!formData.local_enabled}
          />
          <span>Require MFA for all users</span>
        </label>
        <span class="help-text indented">When enabled, users must set up MFA on next login</span>

        <div class="form-group">
          <label for="mfa_issuer">MFA Issuer Name</label>
          <input
            id="mfa_issuer"
            type="text"
            bind:value={formData.mfa_issuer}
            on:input={handleChange}
            placeholder="OpenTranscribe"
            disabled={!formData.local_enabled}
          />
          <span class="help-text">Displayed in authenticator apps</span>
        </div>
      </div>
    {/if}
  </div>

  <div class="section" class:disabled={!formData.local_enabled}>
    <h3>Account Lockout</h3>

    <div class="form-row">
      <div class="form-group">
        <label for="max_login_attempts">Max Login Attempts</label>
        <input
          id="max_login_attempts"
          type="number"
          bind:value={formData.max_login_attempts}
          on:input={handleChange}
          min="3"
          max="20"
          disabled={!formData.local_enabled}
        />
        <span class="help-text">Failed attempts before lockout</span>
      </div>

      <div class="form-group">
        <label for="lockout_duration_minutes">Lockout Duration (minutes)</label>
        <input
          id="lockout_duration_minutes"
          type="number"
          bind:value={formData.lockout_duration_minutes}
          on:input={handleChange}
          min="1"
          max="1440"
          disabled={!formData.local_enabled}
        />
        <span class="help-text">Time until automatic unlock</span>
      </div>
    </div>
  </div>

  <div class="actions">
    <button
      class="btn btn-primary"
      on:click={handleSave}
      disabled={saving}
    >
      {saving ? 'Saving...' : 'Save Configuration'}
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

  .btn {
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 4px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.2s, opacity 0.2s;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-primary {
    background: var(--color-primary);
    color: white;
  }

  .btn-primary:hover:not(:disabled) {
    background: var(--color-primary-dark);
  }
</style>
