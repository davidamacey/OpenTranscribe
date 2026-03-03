<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { PKIConfig } from '$lib/api/authConfig';

  export let config: Partial<PKIConfig> = {};

  const dispatch = createEventDispatcher();

  let formData: PKIConfig = {
    pki_enabled: config.pki_enabled ?? false,
    pki_ca_cert_path: config.pki_ca_cert_path ?? '',
    pki_verify_revocation: config.pki_verify_revocation ?? false,
    pki_cert_header: config.pki_cert_header ?? 'X-SSL-Client-Cert',
    pki_cert_dn_header: config.pki_cert_dn_header ?? 'X-SSL-Client-DN',
    pki_admin_dns: config.pki_admin_dns ?? '',
    pki_ocsp_timeout_seconds: config.pki_ocsp_timeout_seconds ?? 10,
    pki_crl_cache_seconds: config.pki_crl_cache_seconds ?? 3600,
    pki_revocation_soft_fail: config.pki_revocation_soft_fail ?? true,
    pki_trusted_proxies: config.pki_trusted_proxies ?? '',
    pki_mode: config.pki_mode ?? 'header',
    pki_allow_password_fallback: config.pki_allow_password_fallback ?? false
  };

  let saving = false;

  $: if (config) {
    formData = {
      pki_enabled: config.pki_enabled ?? false,
      pki_ca_cert_path: config.pki_ca_cert_path ?? '',
      pki_verify_revocation: config.pki_verify_revocation ?? false,
      pki_cert_header: config.pki_cert_header ?? 'X-SSL-Client-Cert',
      pki_cert_dn_header: config.pki_cert_dn_header ?? 'X-SSL-Client-DN',
      pki_admin_dns: config.pki_admin_dns ?? '',
      pki_ocsp_timeout_seconds: config.pki_ocsp_timeout_seconds ?? 10,
      pki_crl_cache_seconds: config.pki_crl_cache_seconds ?? 3600,
      pki_revocation_soft_fail: config.pki_revocation_soft_fail ?? true,
      pki_trusted_proxies: config.pki_trusted_proxies ?? '',
      pki_mode: config.pki_mode ?? 'header',
      pki_allow_password_fallback: config.pki_allow_password_fallback ?? false
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

  const pkiModes = [
    { value: 'header', label: 'Header-based (Reverse Proxy)', description: 'Certificate passed via HTTP headers from reverse proxy' },
    { value: 'mutual_tls', label: 'Mutual TLS', description: 'Direct certificate verification via TLS handshake' }
  ];
</script>

<div class="settings-panel">
  <div class="enable-toggle">
    <label class="toggle-label">
      <input
        type="checkbox"
        bind:checked={formData.pki_enabled}
        on:change={handleChange}
      />
      <span class="toggle-text">Enable PKI/Certificate Authentication</span>
    </label>
  </div>

  <div class="warning-box">
    <strong>Advanced Configuration</strong>
    <p>PKI authentication requires proper infrastructure setup including certificate management, reverse proxy configuration, and CA certificate distribution. See the documentation for detailed setup instructions.</p>
  </div>

  <div class="section" class:disabled={!formData.pki_enabled}>
    <h3>Authentication Mode</h3>

    <div class="radio-group">
      {#each pkiModes as mode}
        <label class="radio-label">
          <input
            type="radio"
            name="pki_mode"
            value={mode.value}
            bind:group={formData.pki_mode}
            on:change={handleChange}
            disabled={!formData.pki_enabled}
          />
          <div class="radio-content">
            <span class="radio-title">{mode.label}</span>
            <span class="radio-description">{mode.description}</span>
          </div>
        </label>
      {/each}
    </div>
  </div>

  <div class="section" class:disabled={!formData.pki_enabled}>
    <h3>Certificate Authority</h3>

    <div class="form-group">
      <label for="pki_ca_cert_path">CA Certificate Path</label>
      <input
        id="pki_ca_cert_path"
        type="text"
        bind:value={formData.pki_ca_cert_path}
        on:input={handleChange}
        placeholder="/etc/ssl/certs/ca-certificates.crt"
        disabled={!formData.pki_enabled}
      />
      <span class="help-text">Path to the trusted CA certificate file (PEM format). Can be a CA bundle.</span>
    </div>
  </div>

  {#if formData.pki_mode === 'header'}
    <div class="section" class:disabled={!formData.pki_enabled}>
      <h3>Header Configuration</h3>

      <div class="form-row">
        <div class="form-group">
          <label for="pki_cert_header">Certificate Header</label>
          <input
            id="pki_cert_header"
            type="text"
            bind:value={formData.pki_cert_header}
            on:input={handleChange}
            placeholder="X-SSL-Client-Cert"
            disabled={!formData.pki_enabled}
          />
          <span class="help-text">HTTP header containing the client certificate</span>
        </div>

        <div class="form-group">
          <label for="pki_cert_dn_header">DN Header</label>
          <input
            id="pki_cert_dn_header"
            type="text"
            bind:value={formData.pki_cert_dn_header}
            on:input={handleChange}
            placeholder="X-SSL-Client-DN"
            disabled={!formData.pki_enabled}
          />
          <span class="help-text">HTTP header containing the certificate DN</span>
        </div>
      </div>

      <div class="form-group">
        <label for="pki_trusted_proxies">Trusted Proxies</label>
        <input
          id="pki_trusted_proxies"
          type="text"
          bind:value={formData.pki_trusted_proxies}
          on:input={handleChange}
          placeholder="10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16"
          disabled={!formData.pki_enabled}
        />
        <span class="help-text">Comma-separated list of trusted proxy IP ranges (CIDR notation)</span>
      </div>
    </div>
  {/if}

  <div class="section" class:disabled={!formData.pki_enabled}>
    <h3>Revocation Checking</h3>

    <label class="checkbox-label">
      <input
        type="checkbox"
        bind:checked={formData.pki_verify_revocation}
        on:change={handleChange}
        disabled={!formData.pki_enabled}
      />
      <span>Enable certificate revocation checking</span>
    </label>

    {#if formData.pki_verify_revocation}
      <div class="revocation-options">
        <div class="form-row">
          <div class="form-group">
            <label for="pki_ocsp_timeout_seconds">OCSP Timeout (seconds)</label>
            <input
              id="pki_ocsp_timeout_seconds"
              type="number"
              bind:value={formData.pki_ocsp_timeout_seconds}
              on:input={handleChange}
              min="1"
              max="60"
              disabled={!formData.pki_enabled}
            />
          </div>

          <div class="form-group">
            <label for="pki_crl_cache_seconds">CRL Cache Duration (seconds)</label>
            <input
              id="pki_crl_cache_seconds"
              type="number"
              bind:value={formData.pki_crl_cache_seconds}
              on:input={handleChange}
              min="60"
              max="86400"
              disabled={!formData.pki_enabled}
            />
          </div>
        </div>

        <label class="checkbox-label">
          <input
            type="checkbox"
            bind:checked={formData.pki_revocation_soft_fail}
            on:change={handleChange}
            disabled={!formData.pki_enabled}
          />
          <span>Soft-fail on revocation check errors</span>
        </label>
        <span class="help-text indented">When enabled, authentication proceeds if OCSP/CRL servers are unreachable</span>
      </div>
    {/if}
  </div>

  <div class="section" class:disabled={!formData.pki_enabled}>
    <h3>Authorization</h3>

    <div class="form-group">
      <label for="pki_admin_dns">Admin Distinguished Names</label>
      <textarea
        id="pki_admin_dns"
        bind:value={formData.pki_admin_dns}
        on:input={handleChange}
        placeholder="CN=Admin User,OU=Admins,O=Example Corp,C=US"
        rows="3"
        disabled={!formData.pki_enabled}
      ></textarea>
      <span class="help-text">One DN per line. Users with matching certificate DNs will be granted admin privileges.</span>
    </div>
  </div>

  <div class="section" class:disabled={!formData.pki_enabled}>
    <h3>Fallback Options</h3>

    <label class="checkbox-label">
      <input
        type="checkbox"
        bind:checked={formData.pki_allow_password_fallback}
        on:change={handleChange}
        disabled={!formData.pki_enabled}
      />
      <span>Allow password fallback</span>
    </label>
    <span class="help-text indented">When enabled, users without certificates can authenticate using username/password</span>
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

  .warning-box {
    background: var(--color-warning-bg);
    border: 1px solid var(--color-warning-border);
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1.5rem;
  }

  .warning-box strong {
    color: var(--color-warning-text);
  }

  .warning-box p {
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

  .radio-group {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .radio-label {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 0.75rem;
    border: 1px solid var(--color-border);
    border-radius: 8px;
    cursor: pointer;
    transition: border-color 0.2s, background-color 0.2s;
  }

  .radio-label:hover {
    border-color: var(--color-primary);
  }

  .radio-label input[type="radio"] {
    margin-top: 0.25rem;
    width: 1rem;
    height: 1rem;
  }

  .radio-content {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .radio-title {
    font-weight: 500;
    color: var(--color-text);
  }

  .radio-description {
    font-size: 0.75rem;
    color: var(--color-text-tertiary);
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
  .form-group input[type="number"],
  .form-group textarea {
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--color-border);
    border-radius: 4px;
    background: var(--color-bg);
    color: var(--color-text);
    font-size: 0.875rem;
    font-family: inherit;
  }

  .form-group textarea {
    resize: vertical;
    min-height: 80px;
  }

  .form-group input:focus,
  .form-group textarea:focus {
    outline: none;
    border-color: var(--color-primary);
    box-shadow: 0 0 0 2px var(--color-primary-alpha);
  }

  .form-group input:disabled,
  .form-group textarea:disabled {
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

  .revocation-options {
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
</style>
