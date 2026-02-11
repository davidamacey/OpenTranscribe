<script lang="ts">
  import { fade } from 'svelte/transition';
  import { t } from '$stores/locale';

  export let isOpen = false;
  export let section = 'performance';
  export let stats: any = {};

  function close() {
    isOpen = false;
  }

  function handleBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) {
      close();
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      close();
    }
  }

  function formatTime(seconds: number): string {
    if (!seconds) return '0s';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    let result = '';
    if (hours > 0) result += `${hours}h `;
    if (minutes > 0 || hours > 0) result += `${minutes}m `;
    result += `${secs}s`;
    return result.trim();
  }

  function formatDateTime(isoString: string | null): string {
    if (!isoString) return 'N/A';
    return new Date(isoString).toLocaleString();
  }

  const queueDescriptions: Record<string, string> = {
    gpu: 'settings.statistics.queueDescGpu',
    download: 'settings.statistics.queueDescDownload',
    nlp: 'settings.statistics.queueDescNlp',
    embedding: 'settings.statistics.queueDescEmbedding',
    cpu: 'settings.statistics.queueDescCpu'
  };
</script>

{#if isOpen}
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    class="modal-backdrop"
    transition:fade={{ duration: 200 }}
    on:click={handleBackdropClick}
    on:keydown={handleKeydown}
    tabindex="-1"
    role="dialog"
    aria-modal="true"
  >
    <div class="modal-container" transition:fade={{ duration: 200, delay: 100 }}>
      <div class="modal-header">
        <h2 class="modal-title">{$t('settings.statistics.processingDetails')}</h2>
        <button class="modal-close" on:click={close} aria-label="Close">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>

      <div class="modal-body">
        <!-- Tab navigation -->
        <div class="detail-tabs">
          <button class="tab" class:active={section === 'performance'} on:click={() => section = 'performance'}>
            {$t('settings.statistics.performance')}
          </button>
          <button class="tab" class:active={section === 'throughput'} on:click={() => section = 'throughput'}>
            {$t('settings.statistics.throughput')}
          </button>
          <button class="tab" class:active={section === 'queues'} on:click={() => section = 'queues'}>
            {$t('settings.statistics.queueDepths')}
          </button>
          <button class="tab" class:active={section === 'models'} on:click={() => section = 'models'}>
            {$t('settings.statistics.aiModels')}
          </button>
        </div>

        <!-- Performance Section -->
        {#if section === 'performance'}
          <div class="detail-section">
            <div class="detail-grid">
              <div class="detail-row">
                <span class="detail-label">{$t('settings.statistics.avgProcessTime')}</span>
                <span class="detail-value">{formatTime(stats.tasks?.avg_processing_time || 0)}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">{$t('settings.statistics.fileTimingAvg')}</span>
                <span class="detail-value">{formatTime(stats.file_timing?.avg_secs || 0)}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">{$t('settings.statistics.fileTimingMin')}</span>
                <span class="detail-value">{formatTime(stats.file_timing?.min_secs || 0)}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">{$t('settings.statistics.fileTimingMax')}</span>
                <span class="detail-value">{formatTime(stats.file_timing?.max_secs || 0)}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">{$t('settings.statistics.completed')} files</span>
                <span class="detail-value">{stats.file_timing?.files || 0}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">{$t('settings.statistics.speakers')}</span>
                <span class="detail-value">{stats.speakers?.total || 0} ({$t('settings.statistics.avgProcessTime')}: {stats.speakers?.avg_per_file || 0}/file)</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">{$t('settings.statistics.successRate')}</span>
                <span class="detail-value">{stats.tasks?.success_rate || 0}%</span>
              </div>
            </div>
          </div>
        {/if}

        <!-- Throughput Section -->
        {#if section === 'throughput'}
          <div class="detail-section">
            <div class="detail-grid">
              <div class="detail-row">
                <span class="detail-label">{$t('settings.statistics.currentRate')}</span>
                <span class="detail-value">{stats.throughput?.rate_1h || 0} {$t('settings.statistics.filesPerHour')}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">{$t('settings.statistics.avgRate3h')}</span>
                <span class="detail-value">{stats.throughput?.rate_3h || 0} {$t('settings.statistics.filesPerHour')}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">{$t('settings.statistics.completed')} (1h)</span>
                <span class="detail-value">{stats.throughput?.last_1h || 0}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">{$t('settings.statistics.completed')} (3h)</span>
                <span class="detail-value">{stats.throughput?.last_3h || 0}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">{$t('settings.statistics.completed')} ({$t('settings.statistics.total')})</span>
                <span class="detail-value">{stats.throughput?.total_completed || 0}</span>
              </div>
            </div>

            {#if stats.eta?.remaining > 0}
              <h4 class="subsection-title">{$t('settings.statistics.estimatedCompletion')}</h4>
              <div class="detail-grid">
                <div class="detail-row">
                  <span class="detail-label">{$t('settings.statistics.remaining')}</span>
                  <span class="detail-value">{stats.eta.remaining} files</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">{$t('settings.statistics.filesPerHour')}</span>
                  <span class="detail-value">{stats.eta.files_per_hour}</span>
                </div>
                {#if stats.eta.hours_remaining !== null}
                  <div class="detail-row">
                    <span class="detail-label">{$t('settings.statistics.hoursRemaining')}</span>
                    <span class="detail-value">{stats.eta.hours_remaining}h</span>
                  </div>
                {/if}
                {#if stats.eta.est_completion}
                  <div class="detail-row">
                    <span class="detail-label">{$t('settings.statistics.estimatedCompletion')}</span>
                    <span class="detail-value">{formatDateTime(stats.eta.est_completion)}</span>
                  </div>
                {/if}
              </div>
            {:else}
              <div class="empty-notice">{$t('settings.statistics.noActiveProcessing')}</div>
            {/if}
          </div>
        {/if}

        <!-- Queues Section -->
        {#if section === 'queues'}
          <div class="detail-section">
            <div class="detail-grid">
              {#each ['gpu', 'download', 'nlp', 'embedding', 'cpu'] as queueName}
                <div class="detail-row">
                  <span class="detail-label">
                    {$t(`settings.statistics.queue${queueName.charAt(0).toUpperCase() + queueName.slice(1)}`)}
                    <span class="detail-sublabel">{$t(queueDescriptions[queueName])}</span>
                  </span>
                  <span class="detail-value" class:highlight={stats.queues?.[queueName] > 0}>
                    {stats.queues?.[queueName] || 0}
                  </span>
                </div>
              {/each}
              <div class="detail-row detail-row-total">
                <span class="detail-label">{$t('settings.statistics.queueTotal')}</span>
                <span class="detail-value" class:highlight={stats.queues?.total > 0}>{stats.queues?.total || 0}</span>
              </div>
            </div>
          </div>
        {/if}

        <!-- Models Section -->
        {#if section === 'models'}
          <div class="detail-section">
            {#if stats.models}
              <div class="detail-grid">
                {#each Object.entries(stats.models) as [key, model]}
                  {@const m = model as {name?: string; description?: string; purpose?: string}}
                  <div class="detail-row model-detail-row">
                    <div class="model-detail-info">
                      <span class="detail-label">{m.purpose || key}</span>
                      <span class="detail-sublabel">{m.description || ''}</span>
                    </div>
                    <span class="detail-value model-name">{m.name || 'N/A'}</span>
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: var(--modal-backdrop, rgba(0, 0, 0, 0.5));
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1200;
    padding: 1rem;
  }

  .modal-container {
    background: var(--card-background, var(--background-color));
    border: 1px solid var(--border-color);
    border-radius: 12px;
    max-width: 600px;
    width: 100%;
    max-height: 80vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
    animation: slideIn 0.2s ease-out;
  }

  @keyframes slideIn {
    from { opacity: 0; transform: translateY(-20px) scale(0.95); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.25rem 1.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .modal-title {
    margin: 0;
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--text-color);
  }

  .modal-close {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.375rem;
    color: var(--text-secondary);
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.2s, background 0.2s;
  }

  .modal-close:hover {
    color: var(--text-color);
    background: var(--button-hover, rgba(0, 0, 0, 0.05));
  }

  .modal-body {
    padding: 1.25rem 1.5rem;
    overflow-y: auto;
    flex: 1;
  }

  .detail-tabs {
    display: flex;
    gap: 0.25rem;
    margin-bottom: 1.25rem;
    border-bottom: 1px solid var(--border-color);
    padding-bottom: 0;
  }

  .tab {
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 0.5rem 0.75rem;
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--text-secondary);
    cursor: pointer;
    transition: color 0.2s, border-color 0.2s;
  }

  .tab:hover {
    color: var(--text-color);
  }

  .tab.active {
    color: var(--primary-color);
    border-bottom-color: var(--primary-color);
  }

  .detail-section {
    animation: fadeIn 0.15s ease-out;
  }

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .detail-grid {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .detail-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.625rem 0;
    border-bottom: 1px solid var(--border-color);
  }

  .detail-row:last-child {
    border-bottom: none;
  }

  .detail-row-total {
    border-top: 2px solid var(--border-color);
    font-weight: 600;
    margin-top: 0.25rem;
    padding-top: 0.75rem;
  }

  .detail-label {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
  }

  .detail-sublabel {
    font-size: 0.6875rem;
    color: var(--text-secondary);
    opacity: 0.7;
  }

  .detail-value {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--text-color);
    text-align: right;
  }

  .detail-value.highlight {
    color: var(--primary-color);
  }

  .detail-value.model-name {
    font-family: 'Courier New', Courier, monospace;
    font-size: 0.8125rem;
  }

  .model-detail-row {
    align-items: flex-start;
    gap: 1rem;
  }

  .model-detail-info {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    flex: 1;
  }

  .subsection-title {
    font-size: 0.8125rem;
    font-weight: 600;
    color: var(--text-color);
    margin: 1.25rem 0 0.5rem 0;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .empty-notice {
    text-align: center;
    padding: 1.5rem;
    color: var(--text-secondary);
    font-size: 0.8125rem;
    font-style: italic;
  }

  :global([data-theme='dark']) .modal-backdrop {
    background: var(--modal-backdrop, rgba(0, 0, 0, 0.7));
  }

  :global([data-theme='dark']) .modal-container {
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2);
  }

  :global([data-theme='dark']) .modal-close:hover {
    background: var(--button-hover, rgba(255, 255, 255, 0.1));
  }

  @media (max-width: 480px) {
    .modal-container {
      max-width: none;
      margin: 0.5rem;
      max-height: 90vh;
    }

    .detail-tabs {
      overflow-x: auto;
    }

    .tab {
      white-space: nowrap;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .modal-container { animation: none; }
    .detail-section { animation: none; }
  }
</style>
