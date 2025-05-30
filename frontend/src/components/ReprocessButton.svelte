<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  
  export let file: any = null;
  export let reprocessing: boolean = false;
  
  const dispatch = createEventDispatcher();

  function handleReprocess() {
    if (!file?.id || reprocessing) return;
    dispatch('reprocess', { fileId: file.id });
  }
</script>

{#if file && (file.status === 'error' || file.status === 'completed' || file.status === 'failed')}
  <button 
    class="reprocess-button" 
    on:click={handleReprocess}
    disabled={reprocessing}
    title="Reprocess this file with the transcription AI"
  >
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M23 4v6h-6"></path>
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
    </svg>
    {reprocessing ? 'Reprocessing...' : 'Reprocess'}
  </button>
{/if}

<style>
  .reprocess-button {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .reprocess-button:hover:not(:disabled) {
    background: var(--surface-hover);
    border-color: var(--border-hover);
  }

  .reprocess-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
</style>