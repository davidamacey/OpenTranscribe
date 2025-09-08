<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { SummaryData, SummaryResponse } from '$lib/types/summary';
  import axiosInstance from '$lib/axios';
  import { isLLMAvailable } from '../stores/llmStatus';
  
  // Import smaller components
  import SummaryDisplay from './SummaryDisplay.svelte';
  import SummarySearch from './SummarySearch.svelte';
  import SummaryActions from './SummaryActions.svelte';
  
  export let fileId: number;
  export let fileName: string = '';
  export let isOpen: boolean = false;
  
  const dispatch = createEventDispatcher<{
    close: void;
    generateSummary: { fileId: number };
    reprocessSummary: { fileId: number };
  }>();
  
  let summary: SummaryData | null = null;
  let loading = false;
  let error: string | null = null;
  let generating = false;
  let summaryStatus: string = 'pending';
  let canRetry: boolean = false;
  
  // Get LLM availability from centralized store
  $: llmAvailable = $isLLMAvailable;
  
  // Search within summary
  let searchQuery = '';
  let currentMatchIndex = 0;
  let totalMatches = 0;
  
  $: if (isOpen && fileId) {
    loadSummary();
  }
  
  $: if (searchQuery && summary) {
    totalMatches = countMatches(searchQuery, summary);
    currentMatchIndex = 0;
  } else {
    totalMatches = 0;
    currentMatchIndex = 0;
  }
  
  // Handle body scroll prevention when modal opens/closes
  $: {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
  }
  
  async function loadSummary() {
    if (!fileId) return;
    
    loading = true;
    error = null;
    
    try {
      // First, check summary status and LLM availability
      try {
        const statusResponse = await axiosInstance.get(`/api/files/${fileId}/summary-status`);
        
        if (statusResponse.status === 200) {
          const statusData = statusResponse.data;
          summaryStatus = statusData.summary_status;
          llmAvailable = statusData.llm_available;
          canRetry = statusData.can_retry;
        }
      } catch (statusErr) {
        console.warn('Failed to load summary status:', statusErr);
        // Continue with summary loading even if status check fails
      }
      
      // Then try to load the actual summary if it exists
      try {
        const response = await axiosInstance.get(`/api/files/${fileId}/summary`);
        const data: SummaryResponse = response.data;
        summary = data.summary_data;
      } catch (summaryErr: any) {
        if (summaryErr.response?.status === 404) {
          // No summary exists yet
          summary = null;
        } else {
          throw new Error(`Failed to load summary: ${summaryErr.response?.statusText || summaryErr.message}`);
        }
      }
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load summary';
      console.error('Error loading summary:', err);
    } finally {
      loading = false;
    }
  }
  
  async function generateSummary() {
    if (!fileId) return;
    
    generating = true;
    error = null;
    
    try {
      const response = await fetch(`/api/files/${fileId}/summarize`, {
        method: 'POST',
        credentials: 'include'
      });
      
      if (response.ok) {
        // Poll for completion (simplified - you might want to use WebSockets)
        setTimeout(() => {
          loadSummary();
        }, 5000);
        
        dispatch('generateSummary', { fileId });
      } else {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to start summarization');
      }
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to generate summary';
    } finally {
      generating = false;
    }
  }

  async function retryFailedSummary() {
    if (!fileId) return;
    
    generating = true;
    error = null;
    
    try {
      const response = await fetch(`/api/files/${fileId}/retry-summary`, {
        method: 'POST',
        credentials: 'include'
      });
      
      if (response.ok) {
        // Poll for completion
        setTimeout(() => {
          loadSummary();
        }, 5000);
        
        dispatch('generateSummary', { fileId });
      } else {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to retry summary generation');
      }
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to retry summary generation';
    } finally {
      generating = false;
    }
  }

  function reprocessSummary() {
    if (!fileId) return;
    
    // Simply dispatch event to parent - parent handles everything
    dispatch('reprocessSummary', { fileId });
  }
  
  function countMatches(query: string, summaryData: SummaryData): number {
    if (!query.trim() || !summaryData) return 0;
    
    const searchTerm = query.toLowerCase();
    let count = 0;
    
    // Count in BLUF
    count += countInText(summaryData.bluf, searchTerm);
    
    // Count in brief summary
    count += countInText(summaryData.brief_summary, searchTerm);
    
    // Count in major topics
    if (summaryData.major_topics) {
      summaryData.major_topics.forEach(topic => {
        count += countInText(topic.topic, searchTerm);
        if (topic.key_points) {
          topic.key_points.forEach(point => {
            count += countInText(point, searchTerm);
          });
        }
        if (topic.participants) {
          topic.participants.forEach(participant => {
            count += countInText(participant, searchTerm);
          });
        }
      });
    }
    
    // Count in key decisions
    summaryData.key_decisions.forEach(decision => {
      count += countInText(decision, searchTerm);
    });
    
    // Count in follow-up items
    summaryData.follow_up_items.forEach(item => {
      count += countInText(item, searchTerm);
    });
    
    return count;
  }
  
  function countInText(text: string, searchTerm: string): number {
    if (!text || !searchTerm) return 0;
    const escapedTerm = searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const matches = text.toLowerCase().match(new RegExp(escapedTerm, 'g'));
    return matches ? matches.length : 0;
  }
  
  function cycleToNextMatch() {
    if (totalMatches > 0) {
      currentMatchIndex = (currentMatchIndex + 1) % totalMatches;
      scrollToCurrentMatch();
    }
  }
  
  function cycleToPreviousMatch() {
    if (totalMatches > 0) {
      currentMatchIndex = currentMatchIndex > 0 ? currentMatchIndex - 1 : totalMatches - 1;
      scrollToCurrentMatch();
    }
  }
  
  function scrollToCurrentMatch() {
    // Wait for the DOM to update with new highlighting
    setTimeout(() => {
      const currentMatch = document.querySelector(`[data-match-index="${currentMatchIndex}"].current-match`);
      if (currentMatch) {
        currentMatch.scrollIntoView({ 
          behavior: 'smooth', 
          block: 'center', 
          inline: 'nearest' 
        });
      } else {
        // Fallback: find any current-match element
        const fallbackMatch = document.querySelector('.current-match');
        if (fallbackMatch) {
          fallbackMatch.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'center', 
            inline: 'nearest' 
          });
        }
      }
    }, 50);
  }
  
  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      dispatch('close');
    }
  }
  
  function handleSearchKeydown(event: KeyboardEvent) {
    // Handle other non-Enter keys if needed
    if (event.key === 'Escape') {
      searchQuery = '';
    }
  }
  
  function handleBackdropClick() {
    dispatch('close');
  }
  
  function handleCloseButton(event: Event) {
    event.preventDefault();
    event.stopPropagation();
    dispatch('close');
  }
  
  function handleModalClick(event: Event) {
    // Prevent backdrop click when clicking inside modal
    event.stopPropagation();
  }
  
  function handleCopy() {
    if (!summary) return;
    
    const markdown = formatSummaryAsMarkdown(summary);
    
    navigator.clipboard.writeText(markdown).then(() => {
      copyButtonText = 'Copied!';
      setTimeout(() => {
        copyButtonText = 'Copy';
      }, 2000);
    }).catch(err => {
      console.error('Failed to copy:', err);
      // Fallback for browsers that don't support clipboard API
      try {
        const textArea = document.createElement('textarea');
        textArea.value = markdown;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        copyButtonText = 'Copied!';
        setTimeout(() => {
          copyButtonText = 'Copy';
        }, 2000);
      } catch (fallbackError) {
        console.error('Fallback copy failed:', fallbackError);
        copyButtonText = 'Copy failed';
        setTimeout(() => {
          copyButtonText = 'Copy';
        }, 2000);
      }
    });
  }
  
  function removeEmojis(text: string): string {
    // Remove all emoji characters using Unicode ranges
    return text.replace(/[\u{1F600}-\u{1F64F}]|[\u{1F300}-\u{1F5FF}]|[\u{1F680}-\u{1F6FF}]|[\u{1F1E0}-\u{1F1FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]/gu, '').trim();
  }
  
  function formatSummaryAsMarkdown(data: SummaryData): string {
    let markdown = `# AI Summary - ${fileName}\n\n`;
    
    // BLUF
    markdown += `## Executive Summary (BLUF)\n${removeEmojis(data.bluf)}\n\n`;
    
    // Brief Summary
    markdown += `## Brief Summary\n${removeEmojis(data.brief_summary)}\n\n`;
    
    // Major Topics
    if (data.major_topics && data.major_topics.length > 0) {
      markdown += `## Major Topics Discussed\n`;
      data.major_topics.forEach(topic => {
        // Use text indicators instead of emojis
        const importanceText = topic.importance === 'high' ? '[HIGH] ' : topic.importance === 'medium' ? '[MED] ' : '[LOW] ';
        markdown += `### ${importanceText}${removeEmojis(topic.topic)}\n`;
        if (topic.participants.length > 0) {
          markdown += `*Key participants: ${topic.participants.join(', ')}*\n\n`;
        }
        topic.key_points.forEach(point => {
          markdown += `- ${removeEmojis(point)}\n`;
        });
        markdown += '\n';
      });
    }
    
    // Key Decisions
    if (data.key_decisions.length > 0) {
      markdown += `## Key Decisions\n`;
      data.key_decisions.forEach(decision => {
        markdown += `- ${removeEmojis(decision)}\n`;
      });
      markdown += '\n';
    }
    
    // Follow-up Items
    if (data.follow_up_items.length > 0) {
      markdown += `## Follow-up Items\n`;
      data.follow_up_items.forEach(item => {
        markdown += `- ${removeEmojis(item)}\n`;
      });
      markdown += '\n';
    }
    
    // AI Disclaimer
    markdown += `---\n\n*AI-generated summary - please verify important details. `;
    markdown += `Generated by ${data.metadata.provider} (${data.metadata.model})`;
    if (data.metadata.processing_time_ms) {
      markdown += ` in ${(data.metadata.processing_time_ms / 1000).toFixed(1)}s`;
    }
    markdown += `.*\n`;
    
    return markdown;
  }
  
  let copyButtonText = 'Copy';
</script>

<svelte:window on:keydown={handleKeydown} />

{#if isOpen}
  <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <div 
    class="modal-backdrop" 
    tabindex="0"
    on:click={handleBackdropClick}
    on:keydown={handleKeydown}
  >
    <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
    <div class="modal-container" on:click={handleModalClick}>
      <div class="modal-header">
        <h2 class="modal-title">AI Summary - {fileName}</h2>
        <div class="header-actions">
          {#if summary}
            <button 
              class="copy-button-header"
              class:copied={copyButtonText === 'Copied!'}
              on:click={handleCopy}
              aria-label="Copy summary"
              title={copyButtonText === 'Copied!' ? 'Summary copied to clipboard!' : 'Copy summary as markdown'}
            >
              {#if copyButtonText === 'Copied!'}
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M10.97 4.97a.75.75 0 0 1 1.07 1.05l-3.99 4.99a.75.75 0 0 1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l2.094 2.093 3.473-4.425a.267.267 0 0 1 .02-.022z"/>
                </svg>
                Copied!
              {:else}
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1v-1z"/>
                  <path d="M9.5 1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-3a.5.5 0 0 1-.5-.5v-1a.5.5 0 0 1 .5-.5h3zm-3-1A1.5 1.5 0 0 0 5 1.5v1A1.5 1.5 0 0 0 6.5 4h3A1.5 1.5 0 0 0 11 2.5v-1A1.5 1.5 0 0 0 9.5 0h-3z"/>
                </svg>
                Copy
              {/if}
            </button>
            
            <!-- Reprocess button when summary exists and LLM is available -->
            {#if llmAvailable}
              <button 
                class="reprocess-button-header"
                on:click={reprocessSummary}
                disabled={generating}
                aria-label="Reprocess summary"
                title="Regenerate summary with current speaker names and transcript text"
              >
                {#if generating}
                  <div class="spinner-small"></div>
                {:else}
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M11.534 7h3.932a.25.25 0 0 1 .192.41l-1.966 2.36a.25.25 0 0 1-.384 0l-1.966-2.36a.25.25 0 0 1 .192-.41zm-11 2h3.932a.25.25 0 0 0 .192-.41L2.692 6.23a.25.25 0 0 0-.384 0L.342 8.59A.25.25 0 0 0 .534 9z"/>
                    <path fill-rule="evenodd" d="M8 3c-1.552 0-2.94.707-3.857 1.818a.5.5 0 1 1-.771-.636A6.002 6.002 0 0 1 13.917 7H12.9A5.002 5.002 0 0 0 8 3zM3.1 9a5.002 5.002 0 0 0 8.757 2.182.5.5 0 1 1 .771.636A6.002 6.002 0 0 1 2.083 9H3.1z"/>
                  </svg>
                {/if}
                Reprocess
              </button>
            {/if}
          {/if}
          <button class="close-button" on:click={handleCloseButton} aria-label="Close modal" title="Close modal (Esc)">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </button>
        </div>
      </div>
      
      {#if loading}
        <div class="loading-container">
          <div class="spinner"></div>
          <p>Loading summary...</p>
        </div>
      {:else if error}
        <div class="error-container">
          <div class="error-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>
              <path d="M12 9v4"/>
              <path d="m12 17 .01 0"/>
            </svg>
          </div>
          <div class="error-message">
            <h3>Error Loading Summary</h3>
            <p>{error}</p>
          </div>
        </div>
      {:else}
        {#if summary}
          <SummarySearch 
            bind:searchQuery
            {totalMatches}
            {currentMatchIndex}
            disabled={!summary}
            on:search={({ detail }) => searchQuery = detail.query}
            on:clearSearch={() => searchQuery = ''}
            on:keydown={handleSearchKeydown}
            on:nextMatch={cycleToNextMatch}
            on:previousMatch={cycleToPreviousMatch}
          />
          
          <SummaryDisplay 
            {summary} 
            {fileName}
            {searchQuery}
            {currentMatchIndex}
          />
        {/if}
        
        <SummaryActions
          {summary}
          {generating}
          {llmAvailable}
          {canRetry}
          {summaryStatus}
          {fileName}
          on:generateSummary={generateSummary}
          on:retrySummary={retryFailedSummary}
        />
      {/if}
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
    background-color: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
  }

  .modal-container {
    background-color: var(--bg-primary);
    border-radius: 12px;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
    width: 100%;
    max-width: 1200px;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem;
    border-bottom: 1px solid var(--border-color);
    background-color: var(--bg-secondary);
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .copy-button-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s ease;
    font-size: 0.85rem;
  }

  .copy-button-header:hover {
    background-color: var(--hover-bg);
    color: var(--text-primary);
    border-color: var(--primary-color);
  }

  .copy-button-header.copied {
    background-color: var(--success-bg);
    border-color: var(--success-color);
    color: var(--success-color);
  }

  .copy-button-header.copied:hover {
    background-color: var(--success-bg);
    border-color: var(--success-color);
    color: var(--success-color);
  }

  .reprocess-button-header {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background-color: var(--bg-primary);
    color: var(--text-primary);
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .reprocess-button-header:hover:not(:disabled) {
    background-color: var(--hover-bg);
    border-color: var(--primary-color);
    color: var(--primary-color);
  }

  .reprocess-button-header:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .reprocess-button-header .spinner-small {
    border: 2px solid rgba(128, 128, 128, 0.3);
    border-top: 2px solid var(--primary-color);
    border-radius: 50%;
    width: 12px;
    height: 12px;
    animation: spin 1s linear infinite;
    flex-shrink: 0;
  }

  .modal-title {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .close-button {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-secondary);
    padding: 0.5rem;
    border-radius: 6px;
    transition: all 0.2s ease;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 32px;
    min-height: 32px;
  }

  .close-button:hover {
    background-color: var(--hover-bg);
    color: var(--text-primary);
  }

  .close-button:active {
    transform: scale(0.95);
  }

  .loading-container, .error-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    gap: 1rem;
  }

  .error-container {
    flex-direction: row;
    text-align: left;
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--border-color);
    border-top: 3px solid var(--primary-color);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  .error-icon {
    font-size: 2rem;
    flex-shrink: 0;
  }

  .error-message h3 {
    margin: 0 0 0.5rem 0;
    color: var(--error-color);
  }

  .error-message p {
    margin: 0;
    color: var(--text-secondary);
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .search-summary-divider {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem 1.5rem;
    background-color: var(--bg-secondary);
  }

  .divider-line {
    flex: 1;
    border: none;
    border-top: 1px solid var(--border-color);
    margin: 0;
  }

  .divider-text {
    font-size: 0.9rem;
    color: var(--text-secondary);
    font-weight: 500;
    white-space: nowrap;
  }

  @media (max-width: 768px) {
    .modal-backdrop {
      padding: 0;
    }
    
    .modal-container {
      border-radius: 0;
      max-height: 100vh;
    }
    
    .modal-header {
      padding: 1rem;
    }
    
    .modal-title {
      font-size: 1.25rem;
    }
  }
</style>