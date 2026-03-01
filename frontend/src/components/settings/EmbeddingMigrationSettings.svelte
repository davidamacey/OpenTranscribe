<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { toastStore } from '$stores/toast';
  import { t } from '$stores/locale';

  // Migration status state
  let currentMode = 'v3';
  let migrationNeeded = false;
  let migrationInProgress = false;
  let v3DocumentCount = 0;
  let v4DocumentCount = 0;

  // Progress tracking state
  let totalFiles = 0;
  let processedFiles = 0;
  let failedFiles: string[] = [];
  let stoppingMigration = false;

  let transcriptionPaused = false;
  let estimatedMinutes = 0;

  let loading = true;
  let error = '';

  // WebSocket event handlers
  interface MigrationProgress {
    processed_files: number;
    total_files: number;
    failed_files: string[];
    progress: number;
    running: boolean;
  }

  interface MigrationComplete {
    status: string;
    total_files: number;
    failed_files: string[];
    success_count: number;
  }

  function handleMigrationProgress(event: CustomEvent<MigrationProgress>) {
    const data = event.detail;
    processedFiles = data.processed_files;
    totalFiles = data.total_files;
    failedFiles = data.failed_files || [];
    migrationInProgress = data.running;

  }

  function handleMigrationComplete(event: CustomEvent<MigrationComplete>) {
    const data = event.detail;
    migrationInProgress = false;
    processedFiles = data.total_files;
    totalFiles = data.total_files;
    failedFiles = data.failed_files || [];

    // Reload full status to get updated mode
    loadMigrationStatus();

    if (data.failed_files.length === 0) {
      toastStore.success($t('settings.embeddingMigration.migrationComplete'));
    } else {
      toastStore.warning(
        $t('settings.embeddingMigration.migrationCompleteWithErrors', {
          failed: data.failed_files.length
        }) || `Migration complete with ${data.failed_files.length} errors`
      );
    }
  }

  async function loadMigrationStatus() {
    loading = true;
    error = '';

    try {
      const response = await fetch('/api/embeddings/migration/status', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });

      if (!response.ok) {
        if (response.status === 403) {
          error = $t('settings.embeddingMigration.adminRequired');
          return;
        }
        throw new Error($t('settings.embeddingMigration.statusLoadFailed'));
      }

      const data = await response.json();
      currentMode = data.current_mode;
      migrationNeeded = data.migration_needed;
      v3DocumentCount = data.v3_document_count || 0;
      v4DocumentCount = data.v4_document_count || 0;
      transcriptionPaused = data.transcription_paused || false;

      // Estimate migration time: ~0.6s/file with pipelined multi-model extraction
      const fileCount = v3DocumentCount || 0;
      estimatedMinutes = Math.max(1, Math.ceil((fileCount * 0.6 + 60) / 60));

      // Also fetch progress if migration might be running
      await loadMigrationProgress();

    } catch (err) {
      console.error('Failed to load migration status:', err);
      error = $t('settings.embeddingMigration.loadFailed');
    } finally {
      loading = false;
    }
  }

  async function loadMigrationProgress() {
    try {
      const response = await fetch('/api/embeddings/migration/progress', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });

      if (!response.ok) {
        return; // Progress endpoint might not be available
      }

      const data = await response.json();
      migrationInProgress = data.running || false;
      totalFiles = data.total_files || 0;
      processedFiles = data.processed_files || 0;
      failedFiles = data.failed_files || [];

      // WebSocket will provide real-time updates once migration starts

    } catch (err) {
      console.error('Failed to load migration progress:', err);
    }
  }

  async function startMigration() {
    migrationInProgress = true;

    try {
      const response = await fetch('/api/embeddings/migration/start', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error($t('settings.embeddingMigration.migrationStartFailed'));
      }

      const data = await response.json();

      // Handle "already_running" response
      if (data.status === 'already_running') {
        // Migration is already running, WebSocket will provide updates
        return;
      }

      toastStore.success($t('settings.embeddingMigration.migrationStarted'));

      // WebSocket will provide real-time updates

    } catch (err) {
      console.error('Failed to start migration:', err);
      toastStore.error($t('settings.embeddingMigration.migrationStartFailed'));
      migrationInProgress = false;
    }
  }

  async function stopMigration() {
    stoppingMigration = true;

    try {
      const response = await fetch('/api/embeddings/migration/stop', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });

      if (!response.ok) {
        throw new Error($t('settings.embeddingMigration.stopFailed'));
      }

      toastStore.success($t('settings.embeddingMigration.migrationStopped'));

      // Refresh status after stopping
      await loadMigrationStatus();

    } catch (err) {
      console.error('Failed to stop migration:', err);
      toastStore.error($t('settings.embeddingMigration.stopFailed'));
    } finally {
      stoppingMigration = false;
    }
  }

  async function finalizeMigration() {
    try {
      const response = await fetch('/api/embeddings/migration/finalize', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });

      if (!response.ok) {
        throw new Error($t('settings.embeddingMigration.migrationFinalizeFailed'));
      }

      toastStore.success($t('settings.embeddingMigration.migrationFinalized'));
      await loadMigrationStatus();
      migrationInProgress = false;

    } catch (err) {
      console.error('Failed to finalize migration:', err);
      toastStore.error($t('settings.embeddingMigration.migrationFinalizeFailed'));
    }
  }

  onMount(() => {
    loadMigrationStatus();

    // Listen for WebSocket events
    window.addEventListener('migration-progress', handleMigrationProgress as EventListener);
    window.addEventListener('migration-complete', handleMigrationComplete as EventListener);
  });

  onDestroy(() => {
    // Remove WebSocket event listeners
    window.removeEventListener('migration-progress', handleMigrationProgress as EventListener);
    window.removeEventListener('migration-complete', handleMigrationComplete as EventListener);
  });
</script>

<div class="migration-settings">
  {#if loading}
    <div class="loading-state">
      <div class="spinner"></div>
      <p>{$t('settings.embeddingMigration.loading')}</p>
    </div>
  {:else if error}
    <div class="error-state">
      <p>{error}</p>
    </div>
  {:else}
    <div class="settings-section">
      <div class="title-row">
        <h3 class="section-title">{$t('settings.embeddingMigration.title')}</h3>
      </div>
      <p class="section-desc">
        {$t('settings.embeddingMigration.description')}
      </p>

      <!-- Current Status -->
      <div class="status-card" class:v3={currentMode === 'v3'} class:v4={currentMode === 'v4'}>
        <div class="status-label">{$t('settings.embeddingMigration.currentMode')}</div>
        <div class="status-value">
          <span class="mode-badge" class:v3={currentMode === 'v3'} class:v4={currentMode === 'v4'}>
            {currentMode.toUpperCase()}
          </span>
          <span class="mode-desc">
            {#if currentMode === 'v3'}
              {$t('settings.embeddingMigration.v3Description')}
            {:else}
              {$t('settings.embeddingMigration.v4Description')}
            {/if}
          </span>
        </div>
      </div>

      <!-- Document Counts -->
      <div class="stats-row">
        <div class="stat-item">
          <span class="stat-label">{$t('settings.embeddingMigration.v3Documents')}</span>
          <span class="stat-value">{v3DocumentCount}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">{$t('settings.embeddingMigration.v4Documents')}</span>
          <span class="stat-value">{v4DocumentCount}</span>
        </div>
      </div>

      <!-- Migration Status -->
      {#if migrationNeeded}
        <div class="migration-box upgrade">
          <div class="migration-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 5v14M19 12l-7 7-7-7"/>
            </svg>
          </div>
          <div class="migration-content">
            <h4>{$t('settings.embeddingMigration.upgradeAvailable')}</h4>
            <ul class="benefit-list">
              <li>{$t('settings.embeddingMigration.benefit1')}</li>
              <li>{$t('settings.embeddingMigration.benefit2')}</li>
              <li>{$t('settings.embeddingMigration.benefit3')}</li>
            </ul>
            <p class="migration-note">
              {$t('settings.embeddingMigration.migrationNote')}
            </p>
            {#if v3DocumentCount > 0}
              <p class="migration-estimate">
                {$t('settings.embeddingMigration.migrationEstimate', {
                  minutes: estimatedMinutes,
                  count: v3DocumentCount
                })}
              </p>
            {/if}
          </div>
          <div class="migration-actions">
            {#if migrationInProgress}
              <div class="migration-controls">
                <button class="btn btn-primary" disabled>
                  <span class="spinner-small"></span>
                  {$t('settings.embeddingMigration.migrating')}
                </button>
                <button
                  class="btn btn-danger"
                  on:click={stopMigration}
                  disabled={stoppingMigration}
                >
                  {#if stoppingMigration}
                    <span class="spinner-small"></span>
                  {/if}
                  {$t('settings.embeddingMigration.stopMigration')}
                </button>
              </div>
            {:else}
              <button class="btn btn-primary" on:click={startMigration}>
                {$t('settings.embeddingMigration.startMigration')}
              </button>
            {/if}
          </div>
        </div>

        <!-- Transcription Paused Notice -->
        {#if transcriptionPaused || migrationInProgress}
          <div class="paused-notice">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="10" y1="15" x2="10" y2="9"/>
              <line x1="14" y1="15" x2="14" y2="9"/>
            </svg>
            <span>{$t('settings.embeddingMigration.transcriptionPaused')}</span>
          </div>
        {/if}

        <!-- Progress Section (shown when migration is in progress) -->
        {#if migrationInProgress && totalFiles > 0}
          <div class="progress-section">
            <div class="progress-header">
              <span class="progress-text">
                {$t('settings.embeddingMigration.processingFiles', { processed: processedFiles, total: totalFiles })}
              </span>
              <span class="progress-percent">
                {Math.round((processedFiles / totalFiles) * 100)}%
              </span>
            </div>
            <div class="progress-bar-container">
              <div
                class="progress-bar-fill"
                style="width: {(processedFiles / totalFiles) * 100}%"
              ></div>
            </div>
            {#if failedFiles.length > 0}
              <div class="failed-files-info">
                <span class="failed-icon">
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="12" y1="8" x2="12" y2="12"/>
                    <line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                </span>
                <span>{$t('settings.embeddingMigration.failedFiles', { count: failedFiles.length })}</span>
              </div>
            {/if}
          </div>
        {/if}
      {:else if currentMode === 'v4'}
        <div class="migration-box complete">
          <div class="migration-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
          </div>
          <div class="migration-content">
            <h4>{$t('settings.embeddingMigration.usingV4Mode')}</h4>
            <p>{$t('settings.embeddingMigration.v4ModeActive')}</p>
          </div>
        </div>
      {/if}

      <!-- Finalize Button (if v4 index exists but not yet swapped) -->
      {#if v4DocumentCount > 0 && currentMode === 'v3'}
        <div class="finalize-section">
          <p>{$t('settings.embeddingMigration.finalizePrompt')}</p>
          <button class="btn btn-secondary" on:click={finalizeMigration}>
            {$t('settings.embeddingMigration.finalizeMigration')}
          </button>
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .migration-settings {
    padding: 0.5rem 0;
  }

  .loading-state,
  .error-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    gap: 1rem;
    color: var(--text-secondary);
  }

  .error-state {
    color: var(--error-color);
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--border-color);
    border-top-color: var(--primary-color);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  .spinner-small {
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    display: inline-block;
    margin-right: 0.5rem;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .settings-section {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1.25rem;
  }

  .title-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .section-title {
    font-size: 0.95rem;
    font-weight: 600;
    margin: 0;
    color: var(--text-color);
  }

  .section-desc {
    font-size: 0.8rem;
    color: var(--text-muted);
    margin: 0.25rem 0 1rem 0;
  }

  .status-card {
    padding: 1rem;
    border-radius: 6px;
    border: 1px solid var(--border-color);
    margin-bottom: 1rem;
  }

  .status-card.v3 {
    background: rgba(251, 191, 36, 0.1);
    border-color: rgba(251, 191, 36, 0.3);
  }

  .status-card.v4 {
    background: rgba(34, 197, 94, 0.1);
    border-color: rgba(34, 197, 94, 0.3);
  }

  .status-label {
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-bottom: 0.25rem;
  }

  .status-value {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .mode-badge {
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
  }

  .mode-badge.v3 {
    background: #fbbf24;
    color: #78350f;
  }

  .mode-badge.v4 {
    background: #22c55e;
    color: #14532d;
  }

  .mode-desc {
    font-size: 0.875rem;
    color: var(--text-secondary);
  }

  .stats-row {
    display: flex;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .stat-item {
    flex: 1;
    padding: 0.75rem;
    background: var(--background-color);
    border-radius: 6px;
    border: 1px solid var(--border-color);
  }

  .stat-label {
    display: block;
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-bottom: 0.25rem;
  }

  .stat-value {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-color);
  }

  .migration-box {
    display: flex;
    gap: 1rem;
    padding: 1rem;
    border-radius: 8px;
    margin-bottom: 1rem;
  }

  .migration-box.upgrade {
    background: rgba(59, 130, 246, 0.1);
    border: 1px solid rgba(59, 130, 246, 0.3);
  }

  .migration-box.complete {
    background: rgba(34, 197, 94, 0.1);
    border: 1px solid rgba(34, 197, 94, 0.3);
  }

  .migration-icon {
    flex-shrink: 0;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .migration-box.upgrade .migration-icon {
    background: rgba(59, 130, 246, 0.2);
    color: #3b82f6;
  }

  .migration-box.complete .migration-icon {
    background: rgba(34, 197, 94, 0.2);
    color: #22c55e;
  }

  .migration-content {
    flex: 1;
  }

  .migration-content h4 {
    margin: 0 0 0.5rem 0;
    font-size: 0.9rem;
    color: var(--text-color);
  }

  .migration-content p {
    margin: 0;
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  .benefit-list {
    margin: 0.5rem 0;
    padding-left: 1.25rem;
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  .benefit-list li {
    margin-bottom: 0.25rem;
  }

  .migration-note {
    margin-top: 0.5rem !important;
    font-style: italic;
  }

  .migration-estimate {
    margin-top: 0.25rem !important;
    font-size: 0.75rem;
    color: var(--text-muted);
  }

  .paused-notice {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 0.875rem;
    background: rgba(251, 191, 36, 0.1);
    border: 1px solid rgba(251, 191, 36, 0.3);
    border-radius: 6px;
    margin-bottom: 0.75rem;
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  .paused-notice svg {
    flex-shrink: 0;
    color: #f59e0b;
  }

  .migration-actions {
    display: flex;
    align-items: flex-start;
  }

  .finalize-section {
    padding: 1rem;
    background: var(--background-color);
    border-radius: 6px;
    border: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .finalize-section p {
    margin: 0;
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  .btn {
    padding: 0.5rem 1rem;
    border-radius: 6px;
    font-size: 0.8125rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .btn:disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }

  .btn-primary {
    background-color: var(--primary-color);
    color: white;
  }

  .btn-primary:hover:not(:disabled) {
    background-color: var(--primary-color-dark, #2563eb);
  }

  .btn-secondary {
    background-color: transparent;
    color: var(--text-color);
    border: 1px solid var(--border-color);
  }

  .btn-secondary:hover:not(:disabled) {
    background-color: var(--background-secondary);
  }

  .btn-danger {
    background-color: #ef4444;
    color: white;
  }

  .btn-danger:hover:not(:disabled) {
    background-color: #dc2626;
  }

  .migration-controls {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .progress-section {
    margin-top: 1rem;
    padding: 1rem;
    background: var(--background-color);
    border-radius: 6px;
    border: 1px solid var(--border-color);
  }

  .progress-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }

  .progress-text {
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  .progress-percent {
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--primary-color);
  }

  .progress-bar-container {
    height: 8px;
    background: var(--border-color);
    border-radius: 4px;
    overflow: hidden;
  }

  .progress-bar-fill {
    height: 100%;
    background: var(--primary-color);
    border-radius: 4px;
    transition: width 0.3s ease;
  }

  .failed-files-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.75rem;
    padding: 0.5rem 0.75rem;
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 4px;
    font-size: 0.75rem;
    color: #ef4444;
  }

  .failed-icon {
    display: flex;
    align-items: center;
  }
</style>
