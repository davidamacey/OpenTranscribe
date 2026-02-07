<script lang="ts">
  import { onMount } from 'svelte';
  import { AuthConfigApi } from '$lib/api/authConfig';
  import LDAPSettings from './LDAPSettings.svelte';
  import KeycloakSettings from './KeycloakSettings.svelte';
  import PKISettings from './PKISettings.svelte';
  import LocalAuthSettings from './LocalAuthSettings.svelte';
  import SessionSettings from './SessionSettings.svelte';
  import { toastStore } from '$stores/toast';

  let activeTab = 'local';
  let loading = false;
  let configs: Record<string, any> = {};
  let hasUnsavedChanges = false;
  let backendNotReady = false; // Backend is fully implemented

  const tabs = [
    { id: 'local', label: 'Local Auth' },
    { id: 'ldap', label: 'LDAP/AD' },
    { id: 'keycloak', label: 'OIDC/Keycloak' },
    { id: 'pki', label: 'PKI/Certificate' },
    { id: 'session', label: 'Sessions' }
  ];

  onMount(async () => {
    await loadConfigs();
  });

  // Transform array of config objects to key-value dictionary
  function transformConfigArray(configArray: any[]): Record<string, any> {
    if (!Array.isArray(configArray)) return configArray || {};
    const result: Record<string, any> = {};
    for (const item of configArray) {
      if (item.config_key && item.config_value !== undefined) {
        // Convert string values to appropriate types
        let value = item.config_value;
        if (item.data_type === 'bool') {
          value = value === 'true' || value === true;
        } else if (item.data_type === 'int') {
          value = parseInt(value, 10) || 0;
        }
        result[item.config_key] = value;
      }
    }
    return result;
  }

  async function loadConfigs() {
    loading = true;
    try {
      const allConfigs = await AuthConfigApi.getAllConfigs();
      // Transform each category's array to key-value dictionary
      configs = {};
      for (const [category, configArray] of Object.entries(allConfigs)) {
        configs[category] = transformConfigArray(configArray as any[]);
      }
      console.log('Loaded configs:', configs);
    } catch (error) {
      console.error('Failed to load auth config:', error);
      toastStore.error('Failed to load authentication configuration');
    } finally {
      loading = false;
    }
  }

  async function handleSave(category: string, config: Record<string, any>) {
    try {
      await AuthConfigApi.updateCategory(category, config);
      toastStore.success(`${category} configuration saved`);
      hasUnsavedChanges = false;
      await loadConfigs();
    } catch (error) {
      console.error(`Failed to save ${category} config:`, error);
      toastStore.error(`Failed to save ${category} configuration`);
    }
  }

  async function handleTestConnection(category: string, config: Record<string, any>) {
    try {
      const result = await AuthConfigApi.testConnection(category, config);
      if (result.success) {
        toastStore.success(result.message);
      } else {
        toastStore.error(result.message);
      }
      return result;
    } catch (error) {
      console.error(`Connection test for ${category} failed:`, error);
      toastStore.error('Connection test failed');
      return { success: false, message: 'Connection test failed' };
    }
  }

  function handleChange() {
    hasUnsavedChanges = true;
  }
</script>

<div class="auth-settings">
  <div class="settings-header">
    <h2>Authentication Configuration</h2>
  </div>

  {#if backendNotReady}
    <!-- Database-backed configuration UI - Coming Soon -->
    <div class="coming-soon">
      <div class="coming-soon-icon">🔐</div>
      <h3>Database-Backed Auth Configuration</h3>
      <p>This feature is coming soon. For now, configure authentication via environment variables:</p>

      <div class="config-methods">
        <div class="config-method">
          <h4>LDAP/Active Directory</h4>
          <code>LDAP_ENABLED=true</code>
          <p>See <a href="https://github.com/davidamacey/OpenTranscribe/blob/main/docs/LDAP_AUTH.md" target="_blank">LDAP_AUTH.md</a></p>
        </div>

        <div class="config-method">
          <h4>Keycloak/OIDC</h4>
          <code>KEYCLOAK_ENABLED=true</code>
          <p>See <a href="https://github.com/davidamacey/OpenTranscribe/blob/main/docs/KEYCLOAK_SETUP.md" target="_blank">KEYCLOAK_SETUP.md</a></p>
        </div>

        <div class="config-method">
          <h4>PKI/X.509 Certificates</h4>
          <code>PKI_ENABLED=true</code>
          <p>See <a href="https://github.com/davidamacey/OpenTranscribe/blob/main/docs/PKI_SETUP.md" target="_blank">PKI_SETUP.md</a></p>
        </div>

        <div class="config-method">
          <h4>MFA/TOTP</h4>
          <code>MFA_ENABLED=true</code>
          <p>See <a href="https://github.com/davidamacey/OpenTranscribe/blob/main/example_env.txt" target="_blank">example_env.txt</a></p>
        </div>
      </div>

      <p class="note">
        <strong>Note:</strong> The backend security fixes (FIPS 140-3, audit logging, session controls) are active.
        Only the UI configuration is pending.
      </p>
    </div>
  {:else}
    <div class="tabs">
      {#each tabs as tab}
        <button
          class="tab"
          class:active={activeTab === tab.id}
          on:click={() => activeTab = tab.id}
        >
          {tab.label}
        </button>
      {/each}
    </div>

    {#if loading}
      <div class="loading">Loading configuration...</div>
    {:else}
      <div class="tab-content">
        {#if activeTab === 'local'}
          <LocalAuthSettings
            config={configs.local || {}}
            on:save={(e) => handleSave('local', e.detail)}
            on:change={handleChange}
          />
        {:else if activeTab === 'ldap'}
          <LDAPSettings
            config={configs.ldap || {}}
            on:save={(e) => handleSave('ldap', e.detail)}
            on:test={(e) => handleTestConnection('ldap', e.detail)}
            on:change={handleChange}
          />
        {:else if activeTab === 'keycloak'}
          <KeycloakSettings
            config={configs.keycloak || {}}
            on:save={(e) => handleSave('keycloak', e.detail)}
            on:test={(e) => handleTestConnection('keycloak', e.detail)}
            on:change={handleChange}
          />
        {:else if activeTab === 'pki'}
          <PKISettings
            config={configs.pki || {}}
            on:save={(e) => handleSave('pki', e.detail)}
            on:change={handleChange}
          />
        {:else if activeTab === 'session'}
          <SessionSettings
            config={configs.session || {}}
            on:save={(e) => handleSave('session', e.detail)}
            on:change={handleChange}
          />
        {/if}
      </div>
    {/if}
  {/if}
</div>

<style>
  .auth-settings {
    padding: 1rem;
  }

  .settings-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .settings-header h2 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
  }

  .tabs {
    display: flex;
    gap: 0.5rem;
    border-bottom: 1px solid var(--color-border);
    margin-bottom: 1rem;
  }

  .tab {
    padding: 0.5rem 1rem;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    cursor: pointer;
    color: var(--color-text-secondary);
    font-size: 0.875rem;
  }

  .tab:hover {
    color: var(--color-text);
  }

  .tab.active {
    color: var(--color-primary);
    border-bottom-color: var(--color-primary);
  }

  .loading {
    text-align: center;
    padding: 2rem;
    color: var(--color-text-secondary);
  }

  .tab-content {
    padding: 1rem 0;
  }

  /* Coming Soon Section Styles */
  .coming-soon {
    text-align: center;
    padding: 2rem;
    background: var(--color-surface);
    border-radius: 8px;
    border: 1px solid var(--color-border);
  }

  .coming-soon-icon {
    font-size: 3rem;
    margin-bottom: 1rem;
  }

  .coming-soon h3 {
    margin: 0 0 0.5rem 0;
    font-size: 1.25rem;
    color: var(--color-text);
  }

  .coming-soon p {
    color: var(--color-text-secondary);
    margin: 0.5rem 0;
  }

  .config-methods {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin: 1.5rem 0;
    text-align: left;
  }

  .config-method {
    background: var(--color-background);
    padding: 1rem;
    border-radius: 6px;
    border: 1px solid var(--color-border);
  }

  .config-method h4 {
    margin: 0 0 0.5rem 0;
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--color-text);
  }

  .config-method code {
    display: block;
    background: var(--color-surface);
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    margin-bottom: 0.5rem;
    color: var(--color-primary);
  }

  .config-method p {
    font-size: 0.75rem;
    margin: 0;
  }

  .config-method a {
    color: var(--color-primary);
    text-decoration: none;
  }

  .config-method a:hover {
    text-decoration: underline;
  }

  .note {
    background: var(--color-info-bg, rgba(59, 130, 246, 0.1));
    border: 1px solid var(--color-info-border, rgba(59, 130, 246, 0.3));
    border-radius: 6px;
    padding: 1rem;
    margin-top: 1rem;
    text-align: left;
    font-size: 0.875rem;
  }

  .note strong {
    color: var(--color-info, #3b82f6);
  }
</style>
