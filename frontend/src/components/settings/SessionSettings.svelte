<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { t } from '$stores/locale';
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
    { value: 'oldest', labelKey: 'settings.session.policyOldestLabel', descKey: 'settings.session.policyOldestDesc' },
    { value: 'newest', labelKey: 'settings.session.policyNewestLabel', descKey: 'settings.session.policyNewestDesc' },
    { value: 'all', labelKey: 'settings.session.policyAllLabel', descKey: 'settings.session.policyAllDesc' }
  ];

  function formatDuration(minutes: number): string {
    if (minutes < 60) return `${minutes} ${$t('settings.session.minutes')}`;
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    if (remainingMinutes === 0) return `${hours} ${hours > 1 ? $t('settings.session.hours') : $t('settings.session.hour')}`;
    return `${hours}h ${remainingMinutes}m`;
  }

  function formatDays(days: number): string {
    if (days === 1) return `1 ${$t('settings.session.day')}`;
    if (days < 7) return `${days} ${$t('settings.session.days')}`;
    const weeks = Math.floor(days / 7);
    const remainingDays = days % 7;
    if (remainingDays === 0) return `${weeks} ${weeks > 1 ? $t('settings.session.weeks') : $t('settings.session.week')}`;
    return `${weeks}w ${remainingDays}d`;
  }
</script>

<div class="settings-panel">
  <div class="intro-text">
    <p>{$t('settings.session.introText')}</p>
  </div>

  <div class="section">
    <h3>{$t('settings.session.tokenLifetimes')}</h3>

    <div class="form-group">
      <label for="jwt_access_token_expire_minutes">{$t('settings.session.accessTokenLifetime')}</label>
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
      <span class="help-text">{$t('settings.session.accessTokenHelp')}</span>
    </div>

    <div class="form-group">
      <label for="jwt_refresh_token_expire_days">{$t('settings.session.refreshTokenLifetime')}</label>
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
      <span class="help-text">{$t('settings.session.refreshTokenHelp')}</span>
    </div>

    <div class="token-info">
      <strong>{$t('settings.session.howTokensWork')}</strong>
      <ul>
        <li>{$t('settings.session.tokenInfo1')}</li>
        <li>{$t('settings.session.tokenInfo2')}</li>
        <li>{$t('settings.session.tokenInfo3')}</li>
      </ul>
    </div>
  </div>

  <div class="section">
    <h3>{$t('settings.session.sessionTimeouts')}</h3>

    <div class="form-group">
      <label for="session_idle_timeout_minutes">{$t('settings.session.idleTimeout')}</label>
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
      <span class="help-text">{$t('settings.session.idleTimeoutHelp')}</span>
    </div>

    <div class="form-group">
      <label for="session_absolute_timeout_minutes">{$t('settings.session.absoluteTimeout')}</label>
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
      <span class="help-text">{$t('settings.session.absoluteTimeoutHelp')}</span>
    </div>
  </div>

  <div class="section">
    <h3>{$t('settings.session.concurrentSessions')}</h3>

    <div class="form-group">
      <label for="max_concurrent_sessions">{$t('settings.session.maxConcurrentSessions')}</label>
      <input
        id="max_concurrent_sessions"
        type="number"
        bind:value={formData.max_concurrent_sessions}
        on:input={handleChange}
        min="1"
        max="20"
      />
      <span class="help-text">{$t('settings.session.maxConcurrentSessionsHelp')}</span>
    </div>

    <div class="form-group">
      <span class="group-label">{$t('settings.session.sessionLimitPolicy')}</span>
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
              <span class="radio-title">{$t(policy.labelKey)}</span>
              <span class="radio-description">{$t(policy.descKey)}</span>
            </div>
          </label>
        {/each}
      </div>
    </div>
  </div>

  <div class="section info">
    <h3>{$t('settings.session.securityRecommendations')}</h3>
    <div class="recommendations">
      <div class="recommendation">
        <strong>{$t('settings.session.highSecurity')}</strong>
        <p>{$t('settings.session.highSecurityDesc')}</p>
      </div>
      <div class="recommendation">
        <strong>{$t('settings.session.standardSecurity')}</strong>
        <p>{$t('settings.session.standardSecurityDesc')}</p>
      </div>
      <div class="recommendation">
        <strong>{$t('settings.session.convenienceFocused')}</strong>
        <p>{$t('settings.session.convenienceFocusedDesc')}</p>
      </div>
    </div>
  </div>

  <div class="actions">
    <button
      class="btn btn-primary"
      on:click={handleSave}
      disabled={saving}
    >
      {saving ? $t('common.saving') : $t('settings.session.saveConfiguration')}
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

  @media (max-width: 768px) {
    .recommendations {
      grid-template-columns: 1fr;
    }
  }
</style>
