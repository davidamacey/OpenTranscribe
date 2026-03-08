<script lang="ts">
  import { onMount } from 'svelte';
  import { AdminApi, type AccountStatusReport } from '$lib/api/admin';
  import { toastStore } from '$stores/toast';
  import { t } from '$stores/locale';

  let report: AccountStatusReport | null = null;
  let loading = false;
  let backendNotReady = false; // Backend is fully implemented

  onMount(async () => {
    await loadReport();
  });

  async function loadReport() {
    loading = true;
    try {
      report = await AdminApi.getAccountStatusReport();
    } catch (error) {
      console.error('Failed to load account status report:', error);
      toastStore.error($t('settings.accountStatus.loadError'));
    } finally {
      loading = false;
    }
  }

  function getPercentage(value: number, total: number): string {
    if (total === 0) return '0';
    return ((value / total) * 100).toFixed(1);
  }
</script>

<div class="account-status-dashboard">
  <h2>{$t('settings.accountStatus.overview')}</h2>

  {#if backendNotReady}
    <div class="coming-soon">
      <div class="coming-soon-icon">📊</div>
      <h3>{$t('settings.accountStatus.dashboard')}</h3>
      <p>{$t('settings.accountStatus.comingSoonDesc')}</p>
      <p class="note">
        <strong>{$t('settings.accountStatus.noteLabel')}</strong> {$t('settings.accountStatus.comingSoonNote')}
      </p>
    </div>
  {:else if loading}
    <div class="loading">{$t('settings.accountStatus.loadingStatus')}</div>
  {:else if report}
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-value">{report.total_users}</div>
        <div class="stat-label">{$t('settings.accountStatus.totalUsers')}</div>
      </div>

      <div class="stat-card success">
        <div class="stat-value">{report.active_users}</div>
        <div class="stat-label">{$t('settings.accountStatus.activeUsers')}</div>
        <div class="stat-percentage">{getPercentage(report.active_users, report.total_users)}%</div>
      </div>

      <div class="stat-card warning">
        <div class="stat-value">{report.inactive_users}</div>
        <div class="stat-label">{$t('settings.accountStatus.inactiveUsers')}</div>
        <div class="stat-percentage">{getPercentage(report.inactive_users, report.total_users)}%</div>
      </div>

      <div class="stat-card info">
        <div class="stat-value">{report.mfa_enabled_users}</div>
        <div class="stat-label">{$t('settings.accountStatus.mfaEnabled')}</div>
        <div class="stat-percentage">{getPercentage(report.mfa_enabled_users, report.total_users)}%</div>
      </div>

      <div class="stat-card danger">
        <div class="stat-value">{report.password_expired_users}</div>
        <div class="stat-label">{$t('settings.accountStatus.passwordExpired')}</div>
        <div class="stat-percentage">{getPercentage(report.password_expired_users, report.total_users)}%</div>
      </div>
    </div>

    <div class="progress-section">
      <h3>{$t('settings.accountStatus.mfaAdoption')}</h3>
      <div class="progress-bar">
        <div
          class="progress-fill"
          style="width: {getPercentage(report.mfa_enabled_users, report.total_users)}%"
        ></div>
      </div>
      <p class="progress-text">
        {$t('settings.accountStatus.mfaProgress', { enabled: report.mfa_enabled_users, total: report.total_users })}
      </p>
    </div>

    <div class="actions">
      <button class="btn-primary" on:click={loadReport}>
        {$t('settings.accountStatus.refresh')}
      </button>
    </div>
  {:else}
    <div class="error">{$t('settings.accountStatus.loadError')}</div>
  {/if}
</div>

<style>
  .account-status-dashboard {
    padding: 1rem;
  }

  h2 {
    margin: 0 0 1.5rem;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--color-text);
  }

  h3 {
    margin: 0 0 0.75rem;
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-text);
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

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
  }

  .stat-card {
    background: var(--color-bg-secondary);
    padding: 1.25rem;
    border-radius: 8px;
    text-align: center;
    border: 1px solid var(--color-border);
  }

  .stat-card.success {
    border-left: 4px solid rgb(34, 197, 94);
  }

  .stat-card.warning {
    border-left: 4px solid rgb(234, 179, 8);
  }

  .stat-card.info {
    border-left: 4px solid rgb(59, 130, 246);
  }

  .stat-card.danger {
    border-left: 4px solid rgb(239, 68, 68);
  }

  .stat-value {
    font-size: 2rem;
    font-weight: 700;
    color: var(--color-text);
  }

  .stat-label {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
    margin-top: 0.25rem;
  }

  .stat-percentage {
    font-size: 0.75rem;
    color: var(--color-text-secondary);
    margin-top: 0.25rem;
  }

  .progress-section {
    background: var(--color-bg-secondary);
    padding: 1.25rem;
    border-radius: 8px;
    margin-bottom: 1.5rem;
  }

  .progress-bar {
    height: 12px;
    background: var(--color-bg);
    border-radius: 6px;
    overflow: hidden;
    border: 1px solid var(--color-border);
  }

  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, rgb(59, 130, 246), rgb(34, 197, 94));
    border-radius: 6px;
    transition: width 0.3s ease;
  }

  .progress-text {
    margin: 0.75rem 0 0;
    font-size: 0.875rem;
    color: var(--color-text-secondary);
  }

  .actions {
    display: flex;
    gap: 0.5rem;
  }

  .btn-primary {
    background-color: #3b82f6;
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    cursor: pointer;
    font-weight: 500;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
    transition: all 0.2s ease;
  }

  .btn-primary:hover:not(:disabled) {
    background-color: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .btn-primary:active:not(:disabled) {
    transform: translateY(0);
  }

  .loading,
  .error {
    text-align: center;
    padding: 2rem;
    color: var(--color-text-secondary);
  }

  .error {
    color: rgb(239, 68, 68);
  }
</style>
