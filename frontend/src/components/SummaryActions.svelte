<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { SummaryData } from '$lib/types/summary';
  
  export let summary: SummaryData | null;
  export let generating: boolean = false;
  export let llmAvailable: boolean = false;
  export let canRetry: boolean = false;
  export let summaryStatus: string = 'pending';
  export let fileName: string = '';
  
  const dispatch = createEventDispatcher<{
    generateSummary: void;
    retrySummary: void;
  }>();

  
</script>

<div class="summary-actions">
  {#if !summary && llmAvailable && summaryStatus === 'pending'}
    <button 
      class="action-button primary"
      on:click={() => dispatch('generateSummary')}
      disabled={generating}
    >
      {#if generating}
        <div class="spinner"></div>
        Generating Summary...
      {:else}
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <path d="M8 4a.5.5 0 0 1 .5.5v3h3a.5.5 0 0 1 0 1h-3v3a.5.5 0 0 1-1 0v-3h-3a.5.5 0 0 1 0-1h3v-3A.5.5 0 0 1 8 4z"/>
        </svg>
        Generate AI Summary
      {/if}
    </button>
  {:else if !summary && canRetry && (summaryStatus === 'failed' || summaryStatus === 'error')}
    <button 
      class="action-button warning"
      on:click={() => dispatch('retrySummary')}
      disabled={generating}
    >
      {#if generating}
        <div class="spinner"></div>
        Retrying...
      {:else}
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <path d="M11.534 7h3.932a.25.25 0 0 1 .192.41l-1.966 2.36a.25.25 0 0 1-.384 0l-1.966-2.36a.25.25 0 0 1 .192-.41zm-11 2h3.932a.25.25 0 0 0 .192-.41L2.692 6.23a.25.25 0 0 0-.384 0L.342 8.59A.25.25 0 0 0 .534 9z"/>
          <path fill-rule="evenodd" d="M8 3c-1.552 0-2.94.707-3.857 1.818a.5.5 0 1 1-.771-.636A6.002 6.002 0 0 1 13.917 7H12.9A5.002 5.002 0 0 0 8 3zM3.1 9a5.002 5.002 0 0 0 8.757 2.182.5.5 0 1 1 .771.636A6.002 6.002 0 0 1 2.083 9H3.1z"/>
        </svg>
        Retry Summary Generation
      {/if}
    </button>
  {:else if !llmAvailable}
    <div class="status-message info">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
        <path d="m8.93 6.588-2.29.287-.082.38.45.083c.294.07.352.176.288.469l-.738 3.468c-.194.897.105 1.319.808 1.319.545 0 1.178-.252 1.465-.598l.088-.416c-.2.176-.492.246-.686.246-.275 0-.375-.193-.304-.533L8.93 6.588zM9 4.5a1 1 0 1 1-2 0 1 1 0 0 1 2 0z"/>
      </svg>
      LLM service is not available. AI summarization requires an LLM provider to be configured.
    </div>
  {/if}
  
</div>

<style>
  .summary-actions {
    display: flex;
    gap: 1rem;
    padding: 1rem;
    background-color: var(--bg-secondary);
    border-top: 1px solid var(--border-color);
  }

  .action-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.25rem;
    border: none;
    border-radius: 6px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .action-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .action-button.primary {
    background-color: var(--primary-color);
    color: white;
  }

  .action-button.primary:hover:not(:disabled) {
    background-color: var(--primary-dark);
  }

  .action-button.secondary {
    background-color: var(--bg-primary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
  }

  .action-button.secondary:hover:not(:disabled) {
    background-color: var(--hover-bg);
  }

  .action-button.warning {
    background-color: var(--warning-color);
    color: white;
  }

  .action-button.warning:hover:not(:disabled) {
    background-color: var(--warning-dark);
  }

  .status-message {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    border-radius: 6px;
    font-size: 0.9rem;
    flex: 1;
  }

  .status-message.info {
    background-color: var(--info-bg);
    color: var(--info-color);
    border: 1px solid var(--info-color);
  }

  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top: 2px solid currentColor;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  @media (max-width: 768px) {
    .summary-actions {
      flex-direction: column;
    }
  }
</style>