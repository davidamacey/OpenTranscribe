<script lang="ts">
  import { onMount } from 'svelte';
  import { AdminApi, type AuditLogEntry } from '$lib/api/admin';
  import { toastStore } from '$stores/toast';

  let auditLogs: AuditLogEntry[] = [];
  let loading = false;
  let backendNotReady = false; // Backend is fully implemented
  let filters = {
    startDate: '',
    endDate: '',
    eventType: '',
    outcome: ''
  };

  const eventTypes = [
    'AUTH_LOGIN_SUCCESS',
    'AUTH_LOGIN_FAILURE',
    'AUTH_LOGOUT',
    'AUTH_MFA_SETUP',
    'AUTH_MFA_VERIFY',
    'AUTH_PASSWORD_CHANGE',
    'AUTH_ACCOUNT_LOCKOUT',
    'AUTH_ACCOUNT_UNLOCK',
    'ADMIN_USER_CREATE',
    'ADMIN_USER_UPDATE',
    'ADMIN_SETTINGS_CHANGE'
  ];

  onMount(async () => {
    await loadAuditLogs();
  });

  async function loadAuditLogs() {
    loading = true;
    try {
      auditLogs = await AdminApi.getAuditLogs({
        start_date: filters.startDate || undefined,
        end_date: filters.endDate || undefined,
        event_type: filters.eventType || undefined,
        outcome: filters.outcome || undefined,
        limit: 100
      });
    } catch (error) {
      console.error('Failed to load audit logs:', error);
      toastStore.error('Failed to load audit logs');
    } finally {
      loading = false;
    }
  }

  async function exportLogs(format: 'csv' | 'json') {
    try {
      const blob = await AdminApi.exportAuditLogs(
        format,
        filters.startDate || undefined,
        filters.endDate || undefined
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit-logs-${new Date().toISOString().split('T')[0]}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
      toastStore.success(`Audit logs exported as ${format.toUpperCase()}`);
    } catch (error) {
      console.error('Failed to export audit logs:', error);
      toastStore.error('Failed to export audit logs');
    }
  }

  function formatDateTime(dateString: string): string {
    const date = new Date(dateString);
    // Compact format: MM/DD HH:MM:SS
    return date.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit' }) +
           ' ' + date.toLocaleTimeString('en-US', { hour12: false });
  }

  function getOutcomeClass(outcome: string): string {
    switch (outcome) {
      case 'SUCCESS': return 'success';
      case 'FAILURE': return 'failure';
      default: return 'partial';
    }
  }
</script>

<div class="audit-log-viewer">
  {#if backendNotReady}
    <div class="coming-soon">
      <div class="coming-soon-icon">📋</div>
      <h3>Audit Log Viewer</h3>
      <p>This feature is coming soon. The backend endpoints for audit log querying are not yet implemented.</p>
      <p class="note">
        <strong>Note:</strong> Authentication events are being logged to the database and OpenSearch.
        The admin UI for viewing and exporting logs is pending backend API implementation.
      </p>
    </div>
  {:else}
    <div class="filters">
      <div class="filter-row">
        <label>
          <span class="label-text">Start</span>
          <input type="date" bind:value={filters.startDate} />
        </label>
        <label>
          <span class="label-text">End</span>
          <input type="date" bind:value={filters.endDate} />
        </label>
        <label>
          <span class="label-text">Event</span>
          <select bind:value={filters.eventType}>
            <option value="">All</option>
            {#each eventTypes as type}
              <option value={type}>{type.replace('AUTH_', '').replace('ADMIN_', '')}</option>
            {/each}
          </select>
        </label>
        <label>
          <span class="label-text">Outcome</span>
          <select bind:value={filters.outcome}>
            <option value="">All</option>
            <option value="SUCCESS">Success</option>
            <option value="FAILURE">Failure</option>
          </select>
        </label>
        <div class="filter-actions">
          <button class="btn-primary" on:click={loadAuditLogs}>Apply</button>
          <button class="btn-secondary" on:click={() => exportLogs('csv')}>CSV</button>
          <button class="btn-secondary" on:click={() => exportLogs('json')}>JSON</button>
        </div>
      </div>
    </div>

    {#if loading}
      <div class="loading">Loading...</div>
    {:else}
      <div class="audit-table-container">
        <table class="audit-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Event</th>
              <th>User</th>
              <th>Status</th>
              <th>IP</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each auditLogs as event}
              <tr class:failure={event.outcome === 'FAILURE'}>
                <td>{formatDateTime(event.timestamp)}</td>
                <td><span class="event-type">{event.event_type.replace('AUTH_', '').replace('ADMIN_', '')}</span></td>
                <td>{event.username || '-'}</td>
                <td>
                  <span class="outcome {getOutcomeClass(event.outcome)}">
                    {event.outcome === 'SUCCESS' ? 'OK' : 'FAIL'}
                  </span>
                </td>
                <td>{event.source_ip}</td>
                <td>
                  <button class="details-btn" on:click={() => alert(JSON.stringify(event.details, null, 2))}>
                    ...
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      {#if auditLogs.length === 0}
        <div class="loading">No audit logs found</div>
      {/if}
    {/if}
  {/if}
</div>

<style>
  .audit-log-viewer {
    padding: 0.5rem;
    font-size: 0.8125rem;
  }

  /* Coming Soon Section Styles */
  .coming-soon {
    text-align: center;
    padding: 1.5rem;
    background: var(--color-surface);
    border-radius: 6px;
    border: 1px solid var(--color-border);
  }

  .coming-soon-icon {
    font-size: 2rem;
    margin-bottom: 0.5rem;
  }

  .coming-soon h3 {
    margin: 0 0 0.5rem 0;
    font-size: 1rem;
    color: var(--color-text);
  }

  .coming-soon p {
    color: var(--color-text-secondary);
    margin: 0.25rem 0;
    font-size: 0.8125rem;
  }

  .note {
    background: var(--color-info-bg, rgba(59, 130, 246, 0.1));
    border: 1px solid var(--color-info-border, rgba(59, 130, 246, 0.3));
    border-radius: 4px;
    padding: 0.75rem;
    margin-top: 0.75rem;
    text-align: left;
    font-size: 0.75rem;
  }

  .note strong {
    color: var(--color-info, #3b82f6);
  }

  /* Compact Filters */
  .filters {
    background: var(--color-bg-secondary);
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    margin-bottom: 0.5rem;
  }

  .filter-row {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
    align-items: flex-end;
  }

  .filter-row label {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    font-size: 0.75rem;
  }

  .label-text {
    color: var(--color-text-secondary);
    font-size: 0.6875rem;
    text-transform: uppercase;
    letter-spacing: 0.025em;
  }

  .filter-row input,
  .filter-row select {
    padding: 0.25rem 0.375rem;
    border: 1px solid var(--color-border);
    border-radius: 3px;
    background: var(--color-bg);
    color: var(--color-text);
    font-size: 0.75rem;
    height: 1.75rem;
  }

  .filter-row input[type="date"] {
    width: 7.5rem;
  }

  .filter-row select {
    min-width: 6rem;
  }

  .filter-actions {
    display: flex;
    gap: 0.25rem;
    margin-left: auto;
  }

  .btn-primary,
  .btn-secondary {
    padding: 0.25rem 0.5rem;
    border-radius: 3px;
    cursor: pointer;
    font-size: 0.75rem;
    height: 1.75rem;
    white-space: nowrap;
  }

  .btn-primary {
    background: var(--color-primary);
    color: white;
    border: none;
  }

  .btn-primary:hover {
    opacity: 0.9;
  }

  .btn-secondary {
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    color: var(--color-text);
  }

  .btn-secondary:hover {
    background: var(--color-bg-secondary);
  }

  /* Compact Table */
  .audit-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.75rem;
  }

  .audit-table th,
  .audit-table td {
    padding: 0.375rem 0.5rem;
    text-align: left;
    border-bottom: 1px solid var(--color-border);
    white-space: nowrap;
  }

  .audit-table th {
    background: var(--color-bg-secondary);
    font-weight: 600;
    font-size: 0.6875rem;
    text-transform: uppercase;
    letter-spacing: 0.025em;
    color: var(--color-text-secondary);
    position: sticky;
    top: 0;
    z-index: 1;
  }

  .audit-table tbody tr:hover {
    background: var(--color-bg-secondary);
  }

  .audit-table tr.failure {
    background: rgba(239, 68, 68, 0.08);
  }

  .audit-table tr.failure:hover {
    background: rgba(239, 68, 68, 0.12);
  }

  /* Compact timestamp */
  .audit-table td:first-child {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.6875rem;
    color: var(--color-text-secondary);
  }

  .event-type {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.6875rem;
    background: var(--color-bg-secondary);
    padding: 0.125rem 0.375rem;
    border-radius: 3px;
    display: inline-block;
  }

  .outcome {
    padding: 0.125rem 0.375rem;
    border-radius: 3px;
    font-size: 0.625rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.025em;
  }

  .outcome.success {
    background: rgba(34, 197, 94, 0.15);
    color: rgb(22, 163, 74);
  }

  :global(.dark) .outcome.success {
    background: rgba(34, 197, 94, 0.2);
    color: rgb(74, 222, 128);
  }

  .outcome.failure {
    background: rgba(239, 68, 68, 0.15);
    color: rgb(220, 38, 38);
  }

  :global(.dark) .outcome.failure {
    background: rgba(239, 68, 68, 0.2);
    color: rgb(248, 113, 113);
  }

  /* Source IP - compact monospace */
  .audit-table td:nth-child(5) {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.6875rem;
    color: var(--color-text-secondary);
  }

  .details-btn {
    background: none;
    border: 1px solid var(--color-border);
    padding: 0.125rem 0.375rem;
    border-radius: 3px;
    cursor: pointer;
    font-size: 0.625rem;
    color: var(--color-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.025em;
  }

  .details-btn:hover {
    background: var(--color-bg-secondary);
    color: var(--color-text);
  }

  .loading {
    text-align: center;
    padding: 1rem;
    color: var(--color-text-secondary);
    font-size: 0.8125rem;
  }

  /* Scrollable table container for many logs */
  .audit-table-container {
    max-height: 400px;
    overflow-y: auto;
    border: 1px solid var(--color-border);
    border-radius: 4px;
  }
</style>
