<script lang="ts">
  import { onMount } from 'svelte';
  import { AdminApi, type AccountStatusReport } from '$lib/api/admin';
  import { toastStore } from '$stores/toast';

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
      toastStore.error('Failed to load account status report');
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
  <h2>Account Status Overview</h2>

  {#if backendNotReady}
    <div class="coming-soon">
      <div class="coming-soon-icon">📊</div>
      <h3>Account Status Dashboard</h3>
      <p>This feature is coming soon. The backend endpoints for account status reporting are not yet implemented.</p>
      <p class="note">
        <strong>Note:</strong> User management is available in the Users section.
        Account status reporting will provide aggregated statistics about user accounts.
      </p>
    </div>
  {:else if loading}
    <div class="loading">Loading account status...</div>
  {:else if report}
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-value">{report.total_users}</div>
        <div class="stat-label">Total Users</div>
      </div>

      <div class="stat-card success">
        <div class="stat-value">{report.active_users}</div>
        <div class="stat-label">Active Users</div>
        <div class="stat-percentage">{getPercentage(report.active_users, report.total_users)}%</div>
      </div>

      <div class="stat-card warning">
        <div class="stat-value">{report.inactive_users}</div>
        <div class="stat-label">Inactive Users</div>
        <div class="stat-percentage">{getPercentage(report.inactive_users, report.total_users)}%</div>
      </div>

      <div class="stat-card info">
        <div class="stat-value">{report.mfa_enabled_users}</div>
        <div class="stat-label">MFA Enabled</div>
        <div class="stat-percentage">{getPercentage(report.mfa_enabled_users, report.total_users)}%</div>
      </div>

      <div class="stat-card danger">
        <div class="stat-value">{report.password_expired_users}</div>
        <div class="stat-label">Password Expired</div>
        <div class="stat-percentage">{getPercentage(report.password_expired_users, report.total_users)}%</div>
      </div>
    </div>

    <div class="progress-section">
      <h3>MFA Adoption</h3>
      <div class="progress-bar">
        <div
          class="progress-fill"
          style="width: {getPercentage(report.mfa_enabled_users, report.total_users)}%"
        ></div>
      </div>
      <p class="progress-text">
        {report.mfa_enabled_users} of {report.total_users} users have MFA enabled
      </p>
    </div>

    <div class="actions">
      <button class="btn-primary" on:click={loadReport}>
        Refresh
      </button>
    </div>
  {:else}
    <div class="error">Failed to load account status report</div>
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
    background: var(--color-primary);
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    cursor: pointer;
    font-weight: 500;
  }

  .btn-primary:hover {
    opacity: 0.9;
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
