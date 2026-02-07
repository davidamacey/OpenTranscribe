<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { SessionConfig } from '$lib/api/authConfig';

  export let config: Partial<SessionConfig> = {};

  const dispatch = createEventDispatcher();

  let formData: SessionConfig = {
    jwt_access_token_expire_minutes: config.jwt_access_token_expire_minutes ?? 15,
    jwt_refresh_token_expire_days: config.jwt_refresh_token_expire_days ?? 7,
    session_idle_timeout_minutes: config.session_idle_timeout_minutes ?? 30,
    session_absolute_timeout_minutes: config.session_absolute_timeout_minutes ?? 480,
    max_concurrent_sessions: config.max_concurrent_sessions ?? 5,
    concurrent_session_policy: config.concurrent_session_policy ?? 'oldest'
  };

  let saving = false;

  $: if (config) {
    formData = {
      jwt_access_token_expire_minutes: config.jwt_access_token_expire_minutes ?? 15,
      jwt_refresh_token_expire_days: config.jwt_refresh_token_expire_days ?? 7,
      session_idle_timeout_minutes: config.session_idle_timeout_minutes ?? 30,
      session_absolute_timeout_minutes: config.session_absolute_timeout_minutes ?? 480,
      max_concurrent_sessions: config.max_concurrent_sessions ?? 5,
      concurrent_session_policy: config.concurrent_session_policy ?? 'oldest'
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

  const sessionPolicies = [
    { value: 'oldest', label: 'Terminate Oldest Session', description: 'When limit reached, oldest session is terminated' },
    { value: 'newest', label: 'Deny New Session', description: 'When limit reached, new login attempts are denied' },
    { value: 'all', label: 'Terminate All Others', description: 'New login terminates all existing sessions' }
  ];

  function formatDuration(minutes: number): string {
    if (minutes < 60) return `${minutes} minutes`;
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    if (remainingMinutes === 0) return `${hours} hour${hours > 1 ? 's' : ''}`;
    return `${hours}h ${remainingMinutes}m`;
  }

  function formatDays(days: number): string {
    if (days === 1) return '1 day';
    if (days < 7) return `${days} days`;
    const weeks = Math.floor(days / 7);
    const remainingDays = days % 7;
    if (remainingDays === 0) return `${weeks} week${weeks > 1 ? 's' : ''}`;
    return `${weeks}w ${remainingDays}d`;
  }
</script>

<div class="settings-panel">
  <div class="intro-text">
    <p>Configure session and token lifetimes to balance security with user convenience. Shorter durations improve security but may require more frequent re-authentication.</p>
  </div>

  <div class="section">
    <h3>Token Lifetimes</h3>

    <div class="form-group">
      <label for="jwt_access_token_expire_minutes">Access Token Lifetime</label>
      <div class="input-with-preview">
        <input
          id="jwt_access_token_expire_minutes"
          type="number"
          bind:value={formData.jwt_access_token_expire_minutes}
          on:input={handleChange}
          min="1"
          max="60"
        />
        <span class="preview">({formatDuration(formData.jwt_access_token_expire_minutes)})</span>
      </div>
      <span class="help-text">Short-lived tokens used for API authentication. Recommended: 15-30 minutes.</span>
    </div>

    <div class="form-group">
      <label for="jwt_refresh_token_expire_days">Refresh Token Lifetime</label>
      <div class="input-with-preview">
        <input
          id="jwt_refresh_token_expire_days"
          type="number"
          bind:value={formData.jwt_refresh_token_expire_days}
          on:input={handleChange}
          min="1"
          max="90"
        />
        <span class="preview">({formatDays(formData.jwt_refresh_token_expire_days)})</span>
      </div>
      <span class="help-text">Used to obtain new access tokens without re-authentication. Recommended: 7-30 days.</span>
    </div>

    <div class="token-info">
      <strong>How tokens work:</strong>
      <ul>
        <li>Access tokens are short-lived and automatically refreshed in the background</li>
        <li>Users stay logged in as long as refresh token is valid and they remain active</li>
        <li>Refresh tokens rotate on each use for enhanced security</li>
      </ul>
    </div>
  </div>

  <div class="section">
    <h3>Session Timeouts</h3>

    <div class="form-group">
      <label for="session_idle_timeout_minutes">Idle Timeout</label>
      <div class="input-with-preview">
        <input
          id="session_idle_timeout_minutes"
          type="number"
          bind:value={formData.session_idle_timeout_minutes}
          on:input={handleChange}
          min="5"
          max="480"
        />
        <span class="preview">({formatDuration(formData.session_idle_timeout_minutes)})</span>
      </div>
      <span class="help-text">Session expires after this period of inactivity. Set to 0 to disable.</span>
    </div>

    <div class="form-group">
      <label for="session_absolute_timeout_minutes">Absolute Timeout</label>
      <div class="input-with-preview">
        <input
          id="session_absolute_timeout_minutes"
          type="number"
          bind:value={formData.session_absolute_timeout_minutes}
          on:input={handleChange}
          min="60"
          max="1440"
        />
        <span class="preview">({formatDuration(formData.session_absolute_timeout_minutes)})</span>
      </div>
      <span class="help-text">Maximum session duration regardless of activity. Forces re-authentication.</span>
    </div>
  </div>

  <div class="section">
    <h3>Concurrent Sessions</h3>

    <div class="form-group">
      <label for="max_concurrent_sessions">Maximum Concurrent Sessions</label>
      <input
        id="max_concurrent_sessions"
        type="number"
        bind:value={formData.max_concurrent_sessions}
        on:input={handleChange}
        min="1"
        max="20"
      />
      <span class="help-text">Maximum number of simultaneous sessions per user. Set to 0 for unlimited.</span>
    </div>

    <div class="form-group">
      <span class="group-label">Session Limit Policy</span>
      <div class="radio-group">
        {#each sessionPolicies as policy}
          <label class="radio-label">
            <input
              type="radio"
              name="concurrent_session_policy"
              value={policy.value}
              bind:group={formData.concurrent_session_policy}
              on:change={handleChange}
            />
            <div class="radio-content">
              <span class="radio-title">{policy.label}</span>
              <span class="radio-description">{policy.description}</span>
            </div>
          </label>
        {/each}
      </div>
    </div>
  </div>

  <div class="section info">
    <h3>Security Recommendations</h3>
    <div class="recommendations">
      <div class="recommendation">
        <strong>High Security Environments</strong>
        <p>Access: 15min, Refresh: 1 day, Idle: 15min, Sessions: 1</p>
      </div>
      <div class="recommendation">
        <strong>Standard Security</strong>
        <p>Access: 30min, Refresh: 7 days, Idle: 30min, Sessions: 5</p>
      </div>
      <div class="recommendation">
        <strong>Convenience-Focused</strong>
        <p>Access: 60min, Refresh: 30 days, Idle: 60min, Sessions: 10</p>
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

  .intro-text {
    margin-bottom: 1.5rem;
    color: var(--color-text-secondary);
    font-size: 0.875rem;
  }

  .intro-text p {
    margin: 0;
  }

  .section {
    margin-bottom: 2rem;
    padding: 1rem;
    background: var(--color-bg-secondary);
    border-radius: 8px;
  }

  .section.info {
    background: var(--color-info-bg);
    border: 1px solid var(--color-info-border);
  }

  .section h3 {
    margin: 0 0 1rem 0;
    font-size: 0.875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-text-secondary);
  }

  .form-group {
    margin-bottom: 1rem;
  }

  .form-group label,
  .form-group .group-label {
    display: block;
    margin-bottom: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--color-text);
  }

  .form-group input[type="number"] {
    width: 120px;
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

  .input-with-preview {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .preview {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
  }

  .help-text {
    display: block;
    margin-top: 0.25rem;
    font-size: 0.75rem;
    color: var(--color-text-tertiary);
  }

  .token-info {
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 4px;
    padding: 0.75rem;
    margin-top: 1rem;
    font-size: 0.875rem;
  }

  .token-info strong {
    color: var(--color-text);
    display: block;
    margin-bottom: 0.5rem;
  }

  .token-info ul {
    margin: 0;
    padding-left: 1.25rem;
    color: var(--color-text-secondary);
  }

  .token-info li {
    margin-bottom: 0.25rem;
  }

  .radio-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
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
    font-size: 0.875rem;
  }

  .radio-description {
    font-size: 0.75rem;
    color: var(--color-text-tertiary);
  }

  .recommendations {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
  }

  .recommendation {
    background: var(--color-bg);
    border-radius: 4px;
    padding: 0.75rem;
  }

  .recommendation strong {
    display: block;
    margin-bottom: 0.25rem;
    font-size: 0.875rem;
    color: var(--color-text);
  }

  .recommendation p {
    margin: 0;
    font-size: 0.75rem;
    color: var(--color-text-secondary);
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
