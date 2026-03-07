<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import axiosInstance from '$lib/axios';
  import { t } from '$stores/locale';
  import { toastStore } from '$stores/toast';
  import ConfirmationModal from '../ConfirmationModal.svelte';
  import StatusChip from './StatusChip.svelte';

  let showModelChangeModal = false;
  let showRepairModal = false;

  interface EmbeddingModel {
    model_id: string;
    name: string;
    dimension: number;
    description: string;
    size_mb: number;
  }

  interface IndexStatus {
    total_files: number;
    indexed_files: number;
    pending_files: number;
    in_progress: boolean;
    current_model: string;
    current_dimension: number;
    last_indexed_at: string | null;
  }

  interface ReindexProgress {
    progress: number;
    indexed_files: number;
    total_files: number;
    eta_seconds?: number | null;
  }

  interface IndexHealthEntry {
    status: 'green' | 'red';
    doc_count: number;
    error: string | null;
  }

  let models: EmbeddingModel[] = [];
  let selectedModelId = '';
  let currentModelId = '';
  let indexStatus: IndexStatus | null = null;
  let isLoading = true;
  let isReindexing = false;
  let isSwitchingModel = false;
  let isStopping = false;
  let isRepairing = false;
  let indexHealth: Record<string, IndexHealthEntry> | null = null;

  // Live reindex progress
  let reindexProgress: ReindexProgress | null = null;

  function formatEta(seconds: number | null | undefined): string {
    if (seconds == null || seconds <= 0) return '';
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    if (m < 60) return s > 0 ? `${m}m ${s}s` : `${m}m`;
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}m`;
  }

  // Event handlers for WebSocket events
  function handleReindexProgress(event: CustomEvent<ReindexProgress>) {
    reindexProgress = event.detail;
    isReindexing = true;
  }

  function handleReindexComplete(event: CustomEvent<{ stats: any }>) {
    reindexProgress = null;
    isReindexing = false;
    // Reload status to get updated counts
    loadStatus();
    toastStore.success($t('search.reindexComplete') || 'Re-indexing complete!');
  }

  function handleReindexStopped(event: CustomEvent<{ stats: any; reason: string }>) {
    reindexProgress = null;
    isReindexing = false;
    isStopping = false;
    loadStatus();
    toastStore.success($t('search.reindexStopped') || 'Re-indexing stopped.');
  }

  onMount(async () => {
    await Promise.all([loadModels(), loadStatus(), loadIndexHealth()]);
    isLoading = false;

    // Listen for WebSocket events
    window.addEventListener('reindex-progress', handleReindexProgress as EventListener);
    window.addEventListener('reindex-complete', handleReindexComplete as EventListener);
    window.addEventListener('reindex-stopped', handleReindexStopped as EventListener);
  });

  onDestroy(() => {
    window.removeEventListener('reindex-progress', handleReindexProgress as EventListener);
    window.removeEventListener('reindex-complete', handleReindexComplete as EventListener);
    window.removeEventListener('reindex-stopped', handleReindexStopped as EventListener);
  });

  async function loadModels() {
    try {
      const res = await axiosInstance.get('/search/models');
      models = res.data.models;
      currentModelId = res.data.current_model_id;
      selectedModelId = currentModelId;
    } catch (e) {
      console.error('Failed to load models:', e);
    }
  }

  async function loadStatus() {
    try {
      const res = await axiosInstance.get('/search/reindex/status');
      indexStatus = res.data;
      // Check if reindex is currently in progress (from backend status)
      if (indexStatus?.in_progress && !reindexProgress) {
        isReindexing = true;
      }
    } catch (e) {
      console.error('Failed to load index status:', e);
    }
  }

  function handleModelChange() {
    if (selectedModelId === currentModelId) return;
    showModelChangeModal = true;
  }

  async function confirmModelChange() {
    showModelChangeModal = false;
    isSwitchingModel = true;
    try {
      const res = await axiosInstance.post('/search/models', {
        model_id: selectedModelId,
      });
      currentModelId = selectedModelId;
      toastStore.success(res.data.message);
      isReindexing = true;
      await loadStatus();
    } catch (e: any) {
      toastStore.error(e?.response?.data?.detail || 'Failed to switch model');
      selectedModelId = currentModelId;
    } finally {
      isSwitchingModel = false;
    }
  }

  function cancelModelChange() {
    showModelChangeModal = false;
    selectedModelId = currentModelId;
  }

  async function handleReindexAll() {
    isReindexing = true;
    try {
      const res = await axiosInstance.post('/search/reindex');
      toastStore.success(res.data.message);
      await loadStatus();
      // Don't set isReindexing = false here - WebSocket 'reindex-complete' event handles that
    } catch (e: any) {
      toastStore.error(e?.response?.data?.detail || 'Failed to start re-indexing');
      isReindexing = false; // Only reset on error
    }
  }

  async function handleReindexPending() {
    isReindexing = true;
    try {
      const res = await axiosInstance.post('/search/reindex?pending_only=true');
      toastStore.success(res.data.message);
      await loadStatus();
      // Don't set isReindexing = false here - WebSocket 'reindex-complete' event handles that
    } catch (e: any) {
      toastStore.error(e?.response?.data?.detail || 'Failed to start re-indexing');
      isReindexing = false; // Only reset on error
    }
  }

  async function handleStopReindex() {
    isStopping = true;
    try {
      const res = await axiosInstance.post('/search/reindex/stop');
      if (res.data.status === 'not_running') {
        isReindexing = false;
        isStopping = false;
        reindexProgress = null;
        await loadStatus();
      }
      toastStore.info(res.data.message);
    } catch (e: any) {
      toastStore.error(e?.response?.data?.detail || 'Failed to stop re-indexing');
      isStopping = false;
    }
  }

  async function loadIndexHealth() {
    try {
      const res = await axiosInstance.get('/search/index-health');
      indexHealth = res.data;
    } catch (e) {
      console.error('Failed to load index health:', e);
      indexHealth = {};
    }
  }

  function handleRepairIndices() {
    showRepairModal = true;
  }

  async function confirmRepairIndices() {
    showRepairModal = false;
    isRepairing = true;
    try {
      const res = await axiosInstance.post('/search/repair-indices');
      toastStore.success($t('settings.search.repairSuccess'));
      await loadIndexHealth();
    } catch (e: any) {
      toastStore.error(e?.response?.data?.detail || $t('settings.search.repairError'));
    } finally {
      isRepairing = false;
    }
  }

  function formatDate(dateStr: string | null): string {
    if (!dateStr) return 'Never';
    try {
      return new Date(dateStr).toLocaleString();
    } catch {
      return dateStr;
    }
  }

  $: progressPercent = indexStatus
    ? Math.round((indexStatus.indexed_files / Math.max(indexStatus.total_files, 1)) * 100)
    : 0;

  $: modelChanged = selectedModelId !== currentModelId;

  $: selectedModel = models.find(m => m.model_id === selectedModelId);

  // Derive overall health status for the chip
  $: healthAllGreen = indexHealth
    ? Object.values(indexHealth).every(i => i.status === 'green')
    : true;
  $: hasRedIndices = indexHealth
    ? Object.values(indexHealth).some(i => i.status === 'red')
    : false;
</script>

{#if isLoading}
  <div class="loading-state">{$t('search.settingsTitle') || 'Loading search settings...'}</div>
{:else}
  <!-- Status Chips Row -->
  {#if indexStatus}
    <div class="status-chips-row">
      <StatusChip
        label={$t('settings.search.chipIndexed')}
        value="{indexStatus.indexed_files}/{indexStatus.total_files}"
        status={progressPercent === 100 ? 'green' : progressPercent > 0 ? 'yellow' : 'neutral'}
      />
      <StatusChip
        label={$t('settings.search.chipModel')}
        value={indexStatus.current_model}
        status="blue"
      />
      <StatusChip
        label={$t('settings.search.chipHealth')}
        value={hasRedIndices ? $t('settings.search.chipHealthNeedsRepair') : $t('settings.search.chipHealthOk')}
        status={hasRedIndices ? 'red' : 'green'}
      />
      {#if indexStatus.pending_files > 0}
        <StatusChip
          label={$t('settings.search.chipPending')}
          value={indexStatus.pending_files !== 1 ? $t('settings.search.chipFileCountPlural', { count: indexStatus.pending_files }) : $t('settings.search.chipFileCount', { count: indexStatus.pending_files })}
          status="yellow"
        />
      {/if}
    </div>
  {/if}

  <!-- Live reindex progress -->
  {#if isReindexing}
    <div class="reindex-live-progress">
      <div class="reindex-header">
        <span class="reindex-label">
          <span class="spinner"></span>
          {isStopping
            ? ($t('search.stoppingReindex') || 'Stopping...')
            : ($t('search.reindexingInProgress') || 'Re-indexing in progress...')}
        </span>
        {#if reindexProgress}
          <span class="reindex-count">
            {reindexProgress.indexed_files} / {reindexProgress.total_files} files
          </span>
        {/if}
      </div>
      {#if reindexProgress}
        <div class="progress-container">
          <div class="progress-bar reindexing">
            <div class="progress-fill" style="width: {Math.round(reindexProgress.progress * 100)}%"></div>
          </div>
          <span class="progress-text">
            {Math.round(reindexProgress.progress * 100)}%
            {#if formatEta(reindexProgress.eta_seconds)}
              ({formatEta(reindexProgress.eta_seconds)} remaining)
            {/if}
          </span>
        </div>
      {:else}
        <div class="progress-container">
          <div class="progress-bar reindexing">
            <div class="progress-fill indeterminate"></div>
          </div>
          <span class="progress-text">{$t('search.reindexStarting') || 'Starting...'}</span>
        </div>
      {/if}
      <div class="reindex-actions">
        <button
          class="btn btn-danger-outline btn-sm"
          on:click={handleStopReindex}
          disabled={isStopping}
        >
          {isStopping ? ($t('search.stoppingReindex') || 'Stopping...') : ($t('search.stopReindex') || 'Stop')}
        </button>
      </div>
    </div>
  {:else if indexStatus && indexStatus.total_files > 0 && progressPercent < 100}
    <div class="progress-container">
      <div class="progress-bar">
        <div class="progress-fill" style="width: {progressPercent}%"></div>
      </div>
      <span class="progress-text">{progressPercent}% indexed</span>
    </div>
  {/if}

  <!-- Re-index Actions -->
  {#if indexStatus}
    <div class="form-actions">
      {#if indexStatus.pending_files > 0 && !isReindexing}
        <button
          class="btn btn-secondary"
          on:click={handleReindexPending}
          disabled={isReindexing}
        >
          {$t('settings.search.reindexPending')}
        </button>
      {/if}
      <button
        class="btn btn-primary"
        on:click={handleReindexAll}
        disabled={isReindexing}
      >
        {isReindexing ? ($t('search.reindexing') || 'Re-indexing...') : ($t('search.reindexAll') || 'Re-index All')}
      </button>
    </div>
  {/if}

  <!-- Embedding Model Selection (directly below actions) -->
  <div class="section-divider"></div>
  <h4 class="subsection-title">{$t('search.embeddingModel') || 'Embedding Model'}</h4>

  <div class="form-group">
    <label for="embedding-model-select">{$t('settings.search.modelLabel')}</label>
    <select
      id="embedding-model-select"
      class="form-control"
      bind:value={selectedModelId}
      disabled={isSwitchingModel || isReindexing || models.length === 0}
    >
      {#if models.length === 0}
        <option value="">Loading models...</option>
      {:else}
        {#each models as model}
          <option value={model.model_id}>
            {model.name} — {model.dimension}d, ~{model.size_mb}MB{model.model_id === currentModelId ? ' (Current)' : ''}
          </option>
        {/each}
      {/if}
    </select>
    {#if selectedModel}
      <small class="form-text">{selectedModel.description}</small>
    {/if}
  </div>

  {#if modelChanged}
    <div class="form-actions">
      <button
        class="btn btn-secondary"
        on:click={() => (selectedModelId = currentModelId)}
      >
        {$t('settings.search.cancel')}
      </button>
      <button
        class="btn btn-primary"
        on:click={handleModelChange}
        disabled={isSwitchingModel}
      >
        {isSwitchingModel ? $t('settings.search.applying') : $t('settings.search.applyAndReindex')}
      </button>
    </div>
  {/if}

  <!-- Index Health -->
  <div class="section-divider"></div>
  <h4 class="subsection-title">{$t('settings.search.indexHealth') || 'Index Health'}</h4>

  {#if indexHealth}
    <div class="health-cards">
      {#each Object.entries(indexHealth) as [indexName, info]}
        <div class="health-card" class:healthy={info.status === 'green'} class:error={info.status === 'red'}>
          <span class="health-card-dot"></span>
          <span class="health-card-name">{indexName}</span>
          <span class="health-card-detail">
            {#if info.status === 'green'}
              {info.doc_count} {$t('settings.search.docs')}
            {:else}
              {$t('settings.search.indexRed') || 'Error'}
            {/if}
          </span>
        </div>
      {/each}
    </div>

    {#if hasRedIndices}
      <div class="form-actions">
        <button
          class="btn btn-primary"
          on:click={handleRepairIndices}
          disabled={isRepairing}
        >
          {#if isRepairing}
            <span class="spinner"></span>
            {$t('settings.search.repairing') || 'Repairing...'}
          {:else}
            {$t('settings.search.repairIndices') || 'Repair Indices'}
          {/if}
        </button>
      </div>
    {/if}
  {:else}
    <p class="health-desc">{$t('settings.search.loadingHealth')}</p>
  {/if}
{/if}

<ConfirmationModal
  isOpen={showModelChangeModal}
  title={$t('settings.search.modelChangeTitle')}
  message={$t('search.modelChangeWarning')}
  confirmText={$t('settings.search.applyAndReindex')}
  on:confirm={confirmModelChange}
  on:cancel={cancelModelChange}
  on:close={cancelModelChange}
/>

<ConfirmationModal
  isOpen={showRepairModal}
  title={$t('settings.search.repairTitle')}
  message={$t('settings.search.repairConfirm')}
  confirmText={$t('settings.search.repairIndices')}
  on:confirm={confirmRepairIndices}
  on:cancel={() => showRepairModal = false}
  on:close={() => showRepairModal = false}
/>

<style>
  .loading-state {
    padding: 1.5rem 0;
    text-align: center;
    color: var(--text-secondary);
    font-size: 0.8125rem;
  }

  .subsection-title {
    font-size: 0.9375rem;
    font-weight: 600;
    margin: 0 0 0.75rem 0;
    color: var(--text-color);
  }

  .status-chips-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }

  .progress-container {
    display: flex;
    align-items: center;
    gap: 0.625rem;
    margin-bottom: 0.5rem;
  }

  .progress-bar {
    flex: 1;
    height: 6px;
    background: var(--border-color);
    border-radius: 3px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: var(--primary-color);
    border-radius: 3px;
    transition: width 0.3s;
  }

  .progress-text {
    font-size: 0.75rem;
    color: var(--text-secondary);
    white-space: nowrap;
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
    margin-bottom: 0.75rem;
  }

  .form-group label {
    font-weight: 500;
    color: var(--text-color);
    font-size: 0.8125rem;
  }

  .form-control {
    padding: 0.5rem 0.625rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background-color: var(--surface-color);
    color: var(--text-color);
    font-size: 0.8125rem;
    transition: border-color 0.15s, box-shadow 0.15s;
  }

  .form-control:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px var(--primary-light);
  }

  .form-control:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    background-color: var(--background-color);
  }

  .form-text {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin-top: 0.125rem;
  }

  .form-actions {
    display: flex;
    gap: 0.75rem;
    margin-top: 0.75rem;
    justify-content: flex-end;
  }

  .form-actions .btn-secondary {
    margin-right: auto;
  }

  .btn {
    padding: 0.5rem 1rem;
    border-radius: 6px;
    border: none;
    font-size: 0.8125rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
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

  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-secondary {
    background-color: var(--background-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
  }

  .btn-secondary:hover:not(:disabled) {
    background-color: var(--border-color);
  }

  .section-divider {
    margin: 1.25rem 0;
    border-top: 1px solid var(--border-color);
  }

  /* Live reindex progress styles */
  .reindex-live-progress {
    margin-bottom: 0.75rem;
    padding: 0.75rem;
    background: var(--primary-light, rgba(59, 130, 246, 0.08));
    border-radius: 8px;
    border: 1px solid var(--primary-border, rgba(59, 130, 246, 0.2));
  }

  .reindex-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }

  .reindex-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--primary-color);
  }

  .reindex-count {
    font-size: 0.75rem;
    color: var(--text-secondary);
    font-weight: 500;
  }

  .spinner {
    width: 14px;
    height: 14px;
    border: 2px solid var(--primary-light, rgba(59, 130, 246, 0.3));
    border-top-color: var(--primary-color);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .progress-bar.reindexing {
    background: var(--primary-light, rgba(59, 130, 246, 0.2));
  }

  .progress-bar.reindexing .progress-fill {
    background: var(--primary-color);
    animation: pulse 1.5s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% {
      opacity: 1;
    }
    50% {
      opacity: 0.7;
    }
  }

  .reindex-actions {
    display: flex;
    justify-content: flex-end;
    margin-top: 0.5rem;
  }

  .btn-danger-outline {
    background: transparent;
    color: var(--danger-color, #dc2626);
    border: 1px solid var(--danger-color, #dc2626);
  }

  .btn-danger-outline:hover:not(:disabled) {
    background: var(--danger-bg, rgba(220, 38, 38, 0.08));
  }

  .btn-danger-outline:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-sm {
    padding: 0.25rem 0.75rem;
    font-size: 0.75rem;
  }

  .progress-bar.reindexing .progress-fill.indeterminate {
    width: 30%;
    animation: indeterminate 1.5s ease-in-out infinite;
  }

  @keyframes indeterminate {
    0% {
      margin-left: 0%;
      width: 30%;
    }
    50% {
      margin-left: 35%;
      width: 30%;
    }
    100% {
      margin-left: 0%;
      width: 30%;
    }
  }

  /* Index Health styles */
  .health-desc {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    margin: 0 0 0.75rem;
  }

  .health-cards {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }

  .health-card {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.375rem 0.625rem;
    border-radius: 6px;
    font-size: 0.75rem;
    border: 1px solid var(--border-color);
    background: var(--surface-color);
  }

  .health-card.healthy {
    border-color: rgba(34, 197, 94, 0.25);
    background: rgba(34, 197, 94, 0.06);
  }

  .health-card.error {
    border-color: rgba(239, 68, 68, 0.3);
    background: rgba(239, 68, 68, 0.08);
  }

  .health-card-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
    background: var(--text-secondary);
  }

  .health-card.healthy .health-card-dot {
    background: #22c55e;
  }

  .health-card.error .health-card-dot {
    background: #ef4444;
  }

  .health-card-name {
    font-weight: 500;
    color: var(--text-color);
  }

  .health-card-detail {
    color: var(--text-secondary);
  }
</style>
