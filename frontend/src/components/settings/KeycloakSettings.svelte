<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { KeycloakConfig } from '$lib/api/authConfig';

  export let config: Partial<KeycloakConfig> = {};

  const dispatch = createEventDispatcher();

  let formData: KeycloakConfig = {
    keycloak_enabled: config.keycloak_enabled ?? false,
    keycloak_server_url: config.keycloak_server_url ?? '',
    keycloak_internal_url: config.keycloak_internal_url ?? '',
    keycloak_realm: config.keycloak_realm ?? '',
    keycloak_client_id: config.keycloak_client_id ?? '',
    keycloak_client_secret: config.keycloak_client_secret ?? '',
    keycloak_callback_url: config.keycloak_callback_url ?? '',
    keycloak_admin_role: config.keycloak_admin_role ?? 'admin',
    keycloak_timeout: config.keycloak_timeout ?? 30,
    keycloak_verify_audience: config.keycloak_verify_audience ?? true,
    keycloak_audience: config.keycloak_audience ?? '',
    keycloak_use_pkce: config.keycloak_use_pkce ?? true,
    keycloak_verify_issuer: config.keycloak_verify_issuer ?? true
  };

  let testing = false;
  let saving = false;
  let showSecret = false;

  $: if (config) {
    formData = {
      keycloak_enabled: config.keycloak_enabled ?? false,
      keycloak_server_url: config.keycloak_server_url ?? '',
      keycloak_internal_url: config.keycloak_internal_url ?? '',
      keycloak_realm: config.keycloak_realm ?? '',
      keycloak_client_id: config.keycloak_client_id ?? '',
      keycloak_client_secret: config.keycloak_client_secret ?? '',
      keycloak_callback_url: config.keycloak_callback_url ?? '',
      keycloak_admin_role: config.keycloak_admin_role ?? 'admin',
      keycloak_timeout: config.keycloak_timeout ?? 30,
      keycloak_verify_audience: config.keycloak_verify_audience ?? true,
      keycloak_audience: config.keycloak_audience ?? '',
      keycloak_use_pkce: config.keycloak_use_pkce ?? true,
      keycloak_verify_issuer: config.keycloak_verify_issuer ?? true
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

  async function handleTest() {
    testing = true;
    dispatch('test', formData);
    setTimeout(() => testing = false, 2000);
  }

  function generateCallbackUrl() {
    if (typeof window !== 'undefined') {
      formData.keycloak_callback_url = `${window.location.origin}/api/auth/keycloak/callback`;
      handleChange();
    }
  }
</script>

<div class="settings-panel">
  <div class="enable-toggle">
    <label class="toggle-label">
      <input
        type="checkbox"
        bind:checked={formData.keycloak_enabled}
        on:change={handleChange}
      />
      <span class="toggle-text">Enable OIDC/Keycloak Authentication</span>
    </label>
  </div>

  <div class="info-box">
    <strong>OpenID Connect (OIDC)</strong>
    <p>This integration supports Keycloak and other OIDC-compliant identity providers including Azure AD, Okta, Auth0, and Google Workspace.</p>
  </div>

  <div class="section" class:disabled={!formData.keycloak_enabled}>
    <h3>Server Configuration</h3>

    <div class="form-group">
      <label for="keycloak_server_url">Server URL (Public)</label>
      <input
        id="keycloak_server_url"
        type="text"
        bind:value={formData.keycloak_server_url}
        on:input={handleChange}
        placeholder="https://keycloak.example.com"
        disabled={!formData.keycloak_enabled}
      />
      <span class="help-text">Public URL of the Keycloak/OIDC server (used by browser)</span>
    </div>

    <div class="form-group">
      <label for="keycloak_internal_url">Server URL (Internal)</label>
      <input
        id="keycloak_internal_url"
        type="text"
        bind:value={formData.keycloak_internal_url}
        on:input={handleChange}
        placeholder="http://keycloak:8080"
        disabled={!formData.keycloak_enabled}
      />
      <span class="help-text">Internal URL for server-to-server communication (leave empty to use public URL)</span>
    </div>

    <div class="form-group">
      <label for="keycloak_realm">Realm</label>
      <input
        id="keycloak_realm"
        type="text"
        bind:value={formData.keycloak_realm}
        on:input={handleChange}
        placeholder="master"
        disabled={!formData.keycloak_enabled}
      />
      <span class="help-text">Keycloak realm name (or tenant ID for Azure AD)</span>
    </div>

    <div class="form-group">
      <label for="keycloak_timeout">Request Timeout (seconds)</label>
      <input
        id="keycloak_timeout"
        type="number"
        bind:value={formData.keycloak_timeout}
        on:input={handleChange}
        min="5"
        max="120"
        disabled={!formData.keycloak_enabled}
      />
    </div>
  </div>

  <div class="section" class:disabled={!formData.keycloak_enabled}>
    <h3>Client Configuration</h3>

    <div class="form-row">
      <div class="form-group">
        <label for="keycloak_client_id">Client ID</label>
        <input
          id="keycloak_client_id"
          type="text"
          bind:value={formData.keycloak_client_id}
          on:input={handleChange}
          placeholder="opentranscribe"
          disabled={!formData.keycloak_enabled}
        />
      </div>

      <div class="form-group">
        <label for="keycloak_client_secret">Client Secret</label>
        <div class="input-with-toggle">
          <input
            id="keycloak_client_secret"
            type={showSecret ? 'text' : 'password'}
            bind:value={formData.keycloak_client_secret}
            on:input={handleChange}
            placeholder="Enter client secret"
            disabled={!formData.keycloak_enabled}
          />
          <button
            type="button"
            class="toggle-visibility"
            on:click={() => showSecret = !showSecret}
            disabled={!formData.keycloak_enabled}
          >
            {showSecret ? 'Hide' : 'Show'}
          </button>
        </div>
        <span class="help-text">Leave empty for public clients using PKCE</span>
      </div>
    </div>

    <div class="form-group">
      <label for="keycloak_callback_url">Callback URL</label>
      <div class="input-with-button">
        <input
          id="keycloak_callback_url"
          type="text"
          bind:value={formData.keycloak_callback_url}
          on:input={handleChange}
          placeholder="https://app.example.com/api/auth/keycloak/callback"
          disabled={!formData.keycloak_enabled}
        />
        <button
          type="button"
          class="btn btn-small"
          on:click={generateCallbackUrl}
          disabled={!formData.keycloak_enabled}
        >
          Auto-detect
        </button>
      </div>
      <span class="help-text">Must be registered in your OIDC provider's client configuration</span>
    </div>
  </div>

  <div class="section" class:disabled={!formData.keycloak_enabled}>
    <h3>Security Options</h3>

    <label class="checkbox-label">
      <input
        type="checkbox"
        bind:checked={formData.keycloak_use_pkce}
        on:change={handleChange}
        disabled={!formData.keycloak_enabled}
      />
      <span>Use PKCE (Proof Key for Code Exchange)</span>
    </label>
    <span class="help-text indented">Recommended for enhanced security. Required for public clients.</span>

    <label class="checkbox-label">
      <input
        type="checkbox"
        bind:checked={formData.keycloak_verify_issuer}
        on:change={handleChange}
        disabled={!formData.keycloak_enabled}
      />
      <span>Verify Token Issuer</span>
    </label>

    <label class="checkbox-label">
      <input
        type="checkbox"
        bind:checked={formData.keycloak_verify_audience}
        on:change={handleChange}
        disabled={!formData.keycloak_enabled}
      />
      <span>Verify Token Audience</span>
    </label>

    {#if formData.keycloak_verify_audience}
      <div class="form-group indented">
        <label for="keycloak_audience">Expected Audience</label>
        <input
          id="keycloak_audience"
          type="text"
          bind:value={formData.keycloak_audience}
          on:input={handleChange}
          placeholder="Leave empty to use client ID"
          disabled={!formData.keycloak_enabled}
        />
      </div>
    {/if}
  </div>

  <div class="section" class:disabled={!formData.keycloak_enabled}>
    <h3>Role Mapping</h3>

    <div class="form-group">
      <label for="keycloak_admin_role">Admin Role Name</label>
      <input
        id="keycloak_admin_role"
        type="text"
        bind:value={formData.keycloak_admin_role}
        on:input={handleChange}
        placeholder="admin"
        disabled={!formData.keycloak_enabled}
      />
      <span class="help-text">Users with this role in their token will be granted admin privileges</span>
    </div>
  </div>

  <div class="actions">
    <button
      class="btn btn-secondary"
      on:click={handleTest}
      disabled={!formData.keycloak_enabled || testing}
    >
      {testing ? 'Testing...' : 'Test Connection'}
    </button>
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

  .info-box {
    background: var(--color-info-bg);
    border: 1px solid var(--color-info-border);
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1.5rem;
  }

  .info-box strong {
    color: var(--color-text);
  }

  .info-box p {
    margin: 0.5rem 0 0 0;
    font-size: 0.875rem;
    color: var(--color-text-secondary);
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

  .form-row {
    display: flex;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .form-group {
    flex: 1;
    margin-bottom: 1rem;
  }

  .form-group.indented {
    margin-left: 1.5rem;
  }

  .form-group label {
    display: block;
    margin-bottom: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--color-text);
  }

  .form-group input[type="text"],
  .form-group input[type="password"],
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

  .input-with-toggle,
  .input-with-button {
    display: flex;
    gap: 0.5rem;
  }

  .input-with-toggle input,
  .input-with-button input {
    flex: 1;
  }

  .toggle-visibility {
    padding: 0.5rem 0.75rem;
    background: var(--color-bg-tertiary);
    border: 1px solid var(--color-border);
    border-radius: 4px;
    color: var(--color-text-secondary);
    font-size: 0.75rem;
    cursor: pointer;
    white-space: nowrap;
  }

  .toggle-visibility:hover:not(:disabled) {
    background: var(--color-bg-hover);
  }

  .toggle-visibility:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  .btn-small {
    padding: 0.5rem 0.75rem;
    font-size: 0.75rem;
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

  .actions {
    display: flex;
    gap: 1rem;
    justify-content: flex-end;
    padding-top: 1rem;
    border-top: 1px solid var(--color-border);
  }

  .actions .btn-secondary {
    margin-right: auto;
  }

  .btn {
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 4px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
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

  .btn-secondary {
    background: var(--color-bg-tertiary);
    color: var(--color-text);
    border: 1px solid var(--color-border);
  }

  .btn-secondary:hover:not(:disabled) {
    background: var(--color-bg-hover);
  }
</style>
