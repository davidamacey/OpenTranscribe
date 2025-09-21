<script lang="ts">
  import { slide } from 'svelte/transition';
  import SpeakerStats from './SpeakerStats.svelte';
  
  export let file: any = null;
  export let isAnalyticsExpanded: boolean = false;
  export let speakerList: any[] = [];
  
  // Simple refresh counter to force re-rendering
  let refreshCounter = 0;
  
  // Create a unique key based on speaker list and analytics data to force re-rendering when speakers change
  $: speakerKey = speakerList.map(s => `${s.id}-${s.display_name || s.name}`).join('-');
  $: analyticsKey = file?.analytics ? 
    JSON.stringify({
      talk_time: file.analytics.overall?.talk_time,
      turn_taking: file.analytics.overall?.turn_taking,
      interruptions: file.analytics.overall?.interruptions,
      questions: file.analytics.overall?.questions
    }) : '';
  $: combinedKey = `${speakerKey}-${analyticsKey}-${refreshCounter}`;
  
  // Watch for changes and force refresh only when analytics data actually changes
  $: if (file?.analytics && analyticsKey) {
    refreshCounter++;
  }

  function toggleAnalytics() {
    isAnalyticsExpanded = !isAnalyticsExpanded;
  }
</script>

<div class="analytics-dropdown-section">
  <button 
    class="analytics-header"
    title="Show or hide detailed analytics including speaker statistics, transcript word count, and speaking time breakdown" on:click={toggleAnalytics} on:keydown={e => e.key === 'Enter' && toggleAnalytics()} aria-expanded={isAnalyticsExpanded}>
    <h4 class="section-heading">Analytics Overview</h4>
    <div class="analytics-preview">
      {#if file && file.analytics && file.analytics.overall}
        <span class="analytics-chip">
          {file.analytics.overall.word_count ? `${file.analytics.overall.word_count} words` : 'Analytics available'}
        </span>
      {:else if file && file.status === 'processing'}
        <span class="analytics-chip processing">Processing...</span>
      {:else}
        <span class="no-analytics">No analytics</span>
      {/if}
    </div>
    <span class="dropdown-toggle" aria-hidden="true">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="transform: rotate({isAnalyticsExpanded ? '180deg' : '0deg'})">
        <polyline points="6 9 12 15 18 9"></polyline>
      </svg>
    </span>
  </button>
  
  {#if isAnalyticsExpanded}
    <div class="analytics-content" transition:slide={{ duration: 200 }}>
      {#if file && file.analytics && file.analytics.overall}
        {#key combinedKey}
          <SpeakerStats 
            analytics={{
              talk_time: file.analytics.overall.talk_time || { by_speaker: {}, total: 0 },
              interruptions: file.analytics.overall.interruptions || { by_speaker: {}, total: 0 },
              turn_taking: file.analytics.overall.turn_taking || { by_speaker: {}, total_turns: 0 },
              questions: file.analytics.overall.questions || { by_speaker: {}, total: 0 },
              ...file.analytics.overall
            }}
            {speakerList}
          />
        {/key}
      {:else if file && file.status === 'processing'}
        <p>Analytics are being processed...</p>
      {:else if file && file.status === 'completed' && !file.analytics}
        <p>Analytics data is not available for this file.</p>
      {/if}
    </div>
  {/if}
</div>

<style>
  .analytics-dropdown-section {
    margin-bottom: 0;
  }

  .analytics-header {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 12px 16px;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .analytics-header:hover {
    background: var(--surface-hover);
    border-color: var(--border-hover);
  }

  .section-heading {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .analytics-preview {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .analytics-chip {
    background: var(--primary-light);
    color: var(--primary-color);
    padding: 4px 8px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 500;
  }

  .analytics-chip.processing {
    background: var(--warning-light);
    color: var(--warning-color);
  }

  .no-analytics {
    color: var(--text-secondary);
    font-size: 12px;
    font-style: italic;
  }

  .dropdown-toggle svg {
    transition: transform 0.2s ease;
  }

  .analytics-content {
    border: 1px solid var(--border-color);
    border-top: none;
    border-radius: 0 0 8px 8px;
    background: var(--surface-color);
    padding: 20px;
  }

  .analytics-content p {
    margin: 0;
    color: var(--text-secondary);
    font-style: italic;
    text-align: center;
    padding: 20px;
  }
</style>