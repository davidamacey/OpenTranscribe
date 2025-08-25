<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import type { SummaryData, SummaryResponse } from '$lib/types/summary';
  import axiosInstance from '$lib/axios';
  
  // Simple toast function without external dependency
  function showToast(message: string) {
    // Simple notification - could be replaced with a more sophisticated solution later
    console.log('Toast:', message);
  }
  
  export let fileId: number;
  export let fileName: string = '';
  export let isOpen: boolean = false;
  
  const dispatch = createEventDispatcher<{
    close: void;
    generateSummary: { fileId: number };
  }>();
  
  let summary: SummaryData | null = null;
  let loading = false;
  let error: string | null = null;
  let generating = false;
  let summaryStatus: string = 'pending';
  let llmAvailable: boolean = false;
  let canRetry: boolean = false;
  
  // Copy functionality
  let copyButtonText = 'Copy Summary';
  
  // Search within summary
  let searchQuery = '';
  let searchResults: { section: string; index: number; text: string }[] = [];
  
  // Speaker analysis expandable state
  let speakerAnalysisExpanded = false;
  
  $: if (isOpen && fileId) {
    loadSummary();
  }
  
  $: if (searchQuery) {
    performSearch();
  } else {
    searchResults = [];
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
        const data = await response.json();
        showToast('Summary generation started');
        
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
      showToast('Failed to generate summary');
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
        const data = await response.json();
        showToast('Summary generation restarted');
        
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
      showToast('Failed to retry summary generation');
    } finally {
      generating = false;
    }
  }
  
  
  function copySummaryToClipboard() {
    if (!summary) return;
    
    // Format the summary as markdown
    const markdown = formatSummaryAsMarkdown(summary);
    
    navigator.clipboard.writeText(markdown).then(() => {
      copyButtonText = 'Copied!';
      showToast('Summary copied to clipboard');
      setTimeout(() => {
        copyButtonText = 'Copy Summary';
      }, 2000);
    }).catch(err => {
      console.error('Failed to copy:', err);
      showToast('Failed to copy summary');
    });
  }
  
  function formatSummaryAsMarkdown(data: SummaryData): string {
    let markdown = `# AI Summary - ${fileName}\n\n`;
    
    // BLUF
    markdown += `## Executive Summary (BLUF)\n${data.bluf}\n\n`;
    
    // Brief Summary
    markdown += `## Brief Summary\n${data.brief_summary}\n\n`;
    
    // Speakers
    if (data.speakers.length > 0) {
      markdown += `## Speaker Analysis\n`;
      data.speakers.forEach(speaker => {
        const minutes = Math.floor(speaker.talk_time_seconds / 60);
        const seconds = speaker.talk_time_seconds % 60;
        markdown += `### ${speaker.name} - ${minutes}:${seconds.toString().padStart(2, '0')} (${speaker.percentage.toFixed(1)}%)\n`;
        speaker.key_points.forEach(point => {
          markdown += `- ${point}\n`;
        });
        markdown += '\n';
      });
    }
    
    // Content Sections
    if (data.content_sections.length > 0) {
      markdown += `## Content Sections\n`;
      data.content_sections.forEach(section => {
        markdown += `### ${section.time_range}: ${section.topic}\n`;
        section.key_points.forEach(point => {
          markdown += `- ${point}\n`;
        });
        markdown += '\n';
      });
    }
    
    // Action Items
    if (data.action_items.length > 0) {
      markdown += `## Action Items & Due Outs\n`;
      data.action_items.forEach((item, index) => {
        const status = item.status === 'completed' ? '[x]' : '[ ]';
        const priority = item.priority ? ` (${item.priority.toUpperCase()})` : '';
        const assignee = item.assigned_to ? ` - ${item.assigned_to}` : '';
        const dueDate = item.due_date ? ` - Due: ${item.due_date}` : '';
        markdown += `${index + 1}. ${status} ${item.text}${priority}${assignee}${dueDate}\n`;
        if (item.context) {
          markdown += `   *${item.context}*\n`;
        }
      });
      markdown += '\n';
    }
    
    // Key Decisions
    if (data.key_decisions.length > 0) {
      markdown += `## Key Decisions\n`;
      data.key_decisions.forEach(decision => {
        markdown += `- ${decision}\n`;
      });
      markdown += '\n';
    }
    
    // Follow-up Items
    if (data.follow_up_items.length > 0) {
      markdown += `## Follow-up Items\n`;
      data.follow_up_items.forEach(item => {
        markdown += `- ${item}\n`;
      });
      markdown += '\n';
    }
    
    // Metadata
    markdown += `---\n*Generated by ${data.metadata.provider} (${data.metadata.model})`;
    if (data.metadata.processing_time_ms) {
      markdown += ` in ${(data.metadata.processing_time_ms / 1000).toFixed(1)}s`;
    }
    markdown += `*\n`;
    
    return markdown;
  }
  
  function performSearch() {
    if (!summary || !searchQuery.trim()) {
      searchResults = [];
      return;
    }
    
    const query = searchQuery.toLowerCase();
    const results: { section: string; index: number; text: string }[] = [];
    
    // Search BLUF
    if (summary.bluf.toLowerCase().includes(query)) {
      results.push({ section: 'BLUF', index: 0, text: summary.bluf });
    }
    
    // Search brief summary
    if (summary.brief_summary.toLowerCase().includes(query)) {
      results.push({ section: 'Brief Summary', index: 0, text: summary.brief_summary });
    }
    
    // Search speakers
    summary.speakers.forEach((speaker, idx) => {
      if (speaker.name.toLowerCase().includes(query)) {
        results.push({ section: 'Speakers', index: idx, text: `${speaker.name}: ${speaker.key_points.join(', ')}` });
      }
      speaker.key_points.forEach(point => {
        if (point.toLowerCase().includes(query)) {
          results.push({ section: 'Speakers', index: idx, text: `${speaker.name}: ${point}` });
        }
      });
    });
    
    // Search content sections
    summary.content_sections.forEach((section, idx) => {
      if (section.topic.toLowerCase().includes(query)) {
        results.push({ section: 'Content', index: idx, text: `${section.topic}: ${section.key_points.join(', ')}` });
      }
      section.key_points.forEach(point => {
        if (point.toLowerCase().includes(query)) {
          results.push({ section: 'Content', index: idx, text: `${section.topic}: ${point}` });
        }
      });
    });
    
    // Search action items
    summary.action_items.forEach((item, idx) => {
      if (item.text.toLowerCase().includes(query) || 
          (item.assigned_to && item.assigned_to.toLowerCase().includes(query))) {
        results.push({ section: 'Action Items', index: idx, text: item.text });
      }
    });
    
    // Search key decisions
    summary.key_decisions.forEach((decision, idx) => {
      if (decision.toLowerCase().includes(query)) {
        results.push({ section: 'Key Decisions', index: idx, text: decision });
      }
    });
    
    // Search follow-up items
    summary.follow_up_items.forEach((item, idx) => {
      if (item.toLowerCase().includes(query)) {
        results.push({ section: 'Follow-up Items', index: idx, text: item });
      }
    });
    
    searchResults = results;
  }
  
  function formatTime(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }
  
  function getPriorityClass(priority: string): string {
    switch (priority) {
      case 'high': return 'priority-high';
      case 'medium': return 'priority-medium';
      case 'low': return 'priority-low';
      default: return 'priority-default';
    }
  }
  
  function closeModal() {
    isOpen = false;
    dispatch('close');
  }
  
  // Keyboard shortcuts
  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      closeModal();
    } else if ((event.ctrlKey || event.metaKey) && event.key === 'c' && summary) {
      copySummaryToClipboard();
    }
  }

  onMount(() => {
    return () => {
      // Cleanup: restore body scroll when component unmounts
      document.body.style.overflow = '';
    };
  });
</script>

{#if isOpen}
  <!-- Modal backdrop -->
  <div 
    class="modal-backdrop"
    role="dialog"
    aria-modal="true"
    tabindex="0"
    on:click|self={closeModal}
    on:keydown={(e) => e.key === 'Escape' && closeModal()}
  >
    <!-- Modal container -->
    <div 
      class="modal-container summary-modal"
      role="dialog"
      aria-labelledby="summary-modal-title"
      aria-modal="true"
      tabindex="-1"
      on:click|stopPropagation
      on:keydown|stopPropagation
    >
      <div class="modal-content">
        <!-- Header -->
        <div class="modal-header">
          <div>
            <h2 id="summary-modal-title">AI Summary</h2>
            <p class="file-name">{fileName || `File ${fileId}`}</p>
          </div>
          
          <div class="header-actions">
            <!-- Search -->
            <div class="search-container">
              <input
                type="text"
                placeholder="Search summary..."
                bind:value={searchQuery}
                class="search-input"
              />
              {#if searchQuery}
                <button
                  class="search-clear"
                  on:click={() => searchQuery = ''}
                  title="Clear search"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                  </svg>
                </button>
              {/if}
            </div>
            
            <!-- Action buttons -->
            {#if summary}
              <button
                on:click={copySummaryToClipboard}
                class="action-btn copy-btn icon-btn"
                title="Copy summary (Ctrl+C)"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>
                  <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
                </svg>
                {copyButtonText === 'Copied!' ? 'Copied!' : ''}
              </button>
            {/if}
            
            
            <button 
              class="modal-close" 
              on:click={closeModal}
              aria-label="Close summary dialog"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>
        </div>
        
        <!-- Body -->
        <div class="modal-body">
          {#if loading}
            <div class="loading-state">
              <div class="loading-spinner"></div>
              <span>Loading summary...</span>
            </div>
          {:else if error}
            <div class="error-state">
              <div class="error-icon">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>
                  <path d="M12 9v4"/>
                  <path d="m12 17 .01 0"/>
                </svg>
              </div>
              <p class="error-message">{error}</p>
              <button
                on:click={loadSummary}
                class="retry-btn"
              >
                Retry
              </button>
            </div>
          {:else if !summary}
            <div class="empty-state">
              {#if summaryStatus === 'processing'}
                <!-- Summary is currently being processed -->
                <div class="processing-state">
                  <div class="loading-spinner"></div>
                  <h3>Generating Summary...</h3>
                  <p>AI is analyzing the transcript and creating a comprehensive summary. This may take a few minutes.</p>
                </div>
              {:else if summaryStatus === 'failed'}
                <!-- Summary failed -->
                <div class="failed-state">
                  <div class="error-icon">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>
                      <path d="M12 9v4"/>
                      <path d="m12 17 .01 0"/>
                    </svg>
                  </div>
                  <h3>Summary Generation Failed</h3>
                  <p>
                    {#if !llmAvailable}
                      The LLM service is currently unavailable. Please try again later when the service is available.
                    {:else}
                      There was an error generating the summary. You can try again now that the LLM service is available.
                    {/if}
                  </p>
                  {#if canRetry}
                    <button
                      on:click={retryFailedSummary}
                      disabled={generating}
                      class="generate-btn"
                    >
                      {generating ? 'Generating Summary...' : 'Generate Summary'}
                    </button>
                  {:else if !llmAvailable}
                    <div class="unavailable-notice">
                      <p>LLM service is not available</p>
                    </div>
                  {/if}
                </div>
              {:else}
                <!-- Default: No summary available -->
                <div class="no-summary-state">
                  <div class="document-icon">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z"/>
                      <path d="M14 2v4a2 2 0 0 0 2 2h4"/>
                      <path d="M10 9H8"/>
                      <path d="M16 13H8"/>
                      <path d="M16 17H8"/>
                    </svg>
                  </div>
                  <h3>No Summary Available</h3>
                  <p>
                    {#if llmAvailable}
                      Generate an AI-powered summary of this transcript using your vLLM model.
                    {:else}
                      The LLM service is currently unavailable. Summary generation will happen automatically when the service becomes available.
                    {/if}
                  </p>
                  {#if llmAvailable}
                    <button
                      on:click={generateSummary}
                      disabled={generating}
                      class="generate-btn"
                    >
                      {generating ? 'Generating Summary...' : 'Generate Summary'}
                    </button>
                  {:else}
                    <div class="unavailable-notice">
                      <p>LLM service is not available</p>
                    </div>
                  {/if}
                </div>
              {/if}
            </div>
          {:else}
            <!-- Summary content -->
            <div class="summary-content">
              <!-- Search results -->
              {#if searchResults.length > 0}
                <div class="search-results">
                  <h4>Search Results ({searchResults.length})</h4>
                  <div class="search-items">
                    {#each searchResults.slice(0, 5) as result}
                      <div class="search-item">
                        <span class="search-section">{result.section}:</span>
                        <span class="search-text">{result.text.substring(0, 100)}...</span>
                      </div>
                    {/each}
                  </div>
                </div>
              {/if}
              
              <!-- BLUF -->
              <div class="summary-section">
                <h3 class="section-title bluf-title">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M13 10V3L4 14h7v7l9-11h-7z"/>
                  </svg>
                  Executive Summary (BLUF)
                </h3>
                <div class="bluf-content">
                  {summary.bluf}
                </div>
              </div>
              
              <!-- Brief Summary -->
              <div class="summary-section">
                <h3 class="section-title">Brief Summary</h3>
                <div class="section-content">
                  {summary.brief_summary}
                </div>
              </div>
              
              <!-- Content Sections -->
              {#if summary.content_sections.length > 0}
                <div class="summary-section">
                  <h3 class="section-title content-title">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 100 4m0-4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 100 4m0-4v2m0-6V4"/>
                    </svg>
                    Content Sections
                  </h3>
                  <div class="content-sections">
                    {#each summary.content_sections as section}
                      <div class="content-section">
                        <div class="section-header">
                          <h4 class="section-topic">{section.topic}</h4>
                          <span class="time-range">{section.time_range}</span>
                        </div>
                        <ul class="section-points">
                          {#each section.key_points as point}
                            <li>{point}</li>
                          {/each}
                        </ul>
                      </div>
                    {/each}
                  </div>
                </div>
              {/if}
              
              <!-- Action Items -->
              {#if summary.action_items.length > 0}
                <div class="summary-section">
                  <h3 class="section-title actions-title">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M9 5H7a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/>
                    </svg>
                    Action Items & Due Outs ({summary.action_items.length})
                  </h3>
                  <div class="section-description">Specific tasks with priorities, assignments, and deadlines</div>
                  <div class="action-items">
                    {#each summary.action_items as item, index}
                      <div class="action-item">
                        <div class="action-header">
                          <div class="action-meta">
                            <span class="action-number">#{index + 1}</span>
                            <span class="priority-badge {getPriorityClass(item.priority)}">
                              {item.priority.toUpperCase()}
                            </span>
                            {#if item.status === 'completed'}
                              <span class="status-badge completed">COMPLETED</span>
                            {/if}
                          </div>
                          <div class="action-details">
                            {#if item.assigned_to}
                              <div class="assigned-to">Assigned to: <span>{item.assigned_to}</span></div>
                            {/if}
                            {#if item.due_date}
                              <div class="due-date">Due: <span>{item.due_date}</span></div>
                            {/if}
                          </div>
                        </div>
                        <p class="action-text">{item.text}</p>
                        {#if item.context}
                          <p class="action-context">{item.context}</p>
                        {/if}
                      </div>
                    {/each}
                  </div>
                </div>
              {/if}
              
              <!-- Key Decisions -->
              {#if summary.key_decisions.length > 0}
                <div class="summary-section">
                  <h3 class="section-title decisions-title">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                    </svg>
                    Key Decisions ({summary.key_decisions.length})
                  </h3>
                  <div class="decisions-list">
                    {#each summary.key_decisions as decision}
                      <div class="decision-item">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <path d="M5 13l4 4L19 7"/>
                        </svg>
                        <span>{decision}</span>
                      </div>
                    {/each}
                  </div>
                </div>
              {/if}
              
              <!-- Follow-up Items -->
              {#if summary.follow_up_items.length > 0}
                <div class="summary-section">
                  <h3 class="section-title followup-title">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
                    </svg>
                    Follow-up Items ({summary.follow_up_items.length})
                  </h3>
                  <div class="section-description">Future discussion points and topics to revisit</div>
                  <div class="followup-list">
                    {#each summary.follow_up_items as item}
                      <div class="followup-item">
                        <span class="followup-arrow">→</span>
                        <span>{item}</span>
                      </div>
                    {/each}
                  </div>
                </div>
              {/if}
              
              <!-- Speaker Analysis - Expandable -->
              {#if summary.speakers.length > 0}
                <div class="summary-section">
                  <h3 class="section-title speakers-title expandable-title" on:click={() => speakerAnalysisExpanded = !speakerAnalysisExpanded}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/>
                    </svg>
                    Speaker Analysis ({summary.speakers.length})
                    <svg class="expand-icon" class:expanded={speakerAnalysisExpanded} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M6 9l6 6 6-6"/>
                    </svg>
                  </h3>
                  {#if speakerAnalysisExpanded}
                    <div class="speakers-grid">
                      {#each summary.speakers as speaker}
                        <div class="speaker-card">
                          <div class="speaker-header">
                            <h4 class="speaker-name">{speaker.name}</h4>
                            <div class="speaker-stats">
                              {formatTime(speaker.talk_time_seconds)} ({speaker.percentage.toFixed(1)}%)
                            </div>
                          </div>
                          <ul class="speaker-points">
                            {#each speaker.key_points as point}
                              <li>{point}</li>
                            {/each}
                          </ul>
                        </div>
                      {/each}
                    </div>
                  {/if}
                </div>
              {/if}
              
              <!-- Metadata -->
              <div class="metadata-section">
                <h4>Processing Information</h4>
                <div class="metadata-grid">
                  <div class="metadata-item">
                    <span class="metadata-label">Provider:</span>
                    <span class="metadata-value">{summary.metadata.provider}</span>
                  </div>
                  <div class="metadata-item">
                    <span class="metadata-label">Model:</span>
                    <span class="metadata-value">{summary.metadata.model}</span>
                  </div>
                  {#if summary.metadata.processing_time_ms}
                    <div class="metadata-item">
                      <span class="metadata-label">Processing:</span>
                      <span class="metadata-value">{(summary.metadata.processing_time_ms / 1000).toFixed(1)}s</span>
                    </div>
                  {/if}
                  {#if summary.metadata.usage_tokens}
                    <div class="metadata-item">
                      <span class="metadata-label">Tokens:</span>
                      <span class="metadata-value">{summary.metadata.usage_tokens.toLocaleString()}</span>
                    </div>
                  {/if}
                </div>
              </div>

              <!-- AI Disclaimer -->
              <div class="ai-disclaimer">
                <div class="disclaimer-icon">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                    <line x1="12" y1="9" x2="12" y2="13"/>
                    <line x1="12" y1="17" x2="12.01" y2="17"/>
                  </svg>
                </div>
                <div class="disclaimer-text">
                  <strong>AI-Generated:</strong> This summary may contain inaccuracies. Please verify important details.
                </div>
              </div>
            </div>
          {/if}
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  /* Modal Base Styles - matching MediaLibrary.svelte */
  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  
  :global(.dark) .modal-backdrop {
    background: rgba(0, 0, 0, 0.7);
  }
  
  .modal-container {
    background: var(--surface-color, white);
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 12px;
    max-width: 90%;
    max-height: 90vh;
    overflow: hidden;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
    display: flex;
    flex-direction: column;
  }

  .summary-modal {
    width: 1000px; /* Wider than default for summary content */
    height: 90vh; /* Set explicit height */
  }
  
  :global(.dark) .modal-container {
    background: var(--surface-color, #1f2937);
    border-color: var(--border-color, #374151);
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2);
  }
  
  .modal-content {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  
  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem;
    border-bottom: 1px solid var(--border-color, #e5e7eb);
  }
  
  .modal-header h2 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-color, #111827);
  }

  .file-name {
    margin: 0.25rem 0 0 0;
    font-size: 0.875rem;
    color: var(--text-secondary-color, #6b7280);
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .search-container {
    position: relative;
    display: flex;
    align-items: center;
  }

  .search-input {
    padding: 0.5rem 0.75rem;
    padding-right: 2.5rem;
    border: 1px solid var(--border-color, #d1d5db);
    border-radius: 6px;
    background: var(--surface-color, white);
    color: var(--text-color, #111827);
    font-size: 0.875rem;
    width: 200px;
  }

  .search-input:focus {
    outline: none;
    border-color: var(--primary-color, #3b82f6);
  }

  :global(.dark) .search-input {
    background: var(--surface-color, #374151);
    border-color: var(--border-color, #4b5563);
    color: var(--text-color, #f9fafb);
  }

  .search-clear {
    position: absolute;
    right: 0.5rem;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.25rem;
    color: var(--text-secondary-color, #6b7280);
    border-radius: 3px;
    transition: all 0.2s ease;
  }

  .search-clear:hover {
    transform: translateY(-50%) scale(1.2);
  }

  .action-btn {
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .copy-btn {
    background: var(--primary-color, #3b82f6);
    color: white;
  }

  .copy-btn:hover {
    background: var(--primary-hover-color, #2563eb);
  }

  .icon-btn {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.5rem;
    min-width: auto;
  }

  .icon-btn svg {
    flex-shrink: 0;
  }

  
  .modal-close {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.5rem;
    color: var(--text-secondary-color, #6b7280);
    transition: color 0.2s ease;
  }
  
  .modal-close:hover {
    color: var(--text-color, #111827);
  }
  
  .modal-body {
    flex: 1;
    padding: 1.5rem;
    overflow-y: auto;
    min-height: 0; /* Important for flex child scrolling */
  }

  /* Loading and Error States */
  .loading-state,
  .error-state,
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    text-align: center;
  }

  .loading-spinner {
    width: 2rem;
    height: 2rem;
    border: 2px solid var(--border-color, #e5e7eb);
    border-top: 2px solid var(--primary-color, #3b82f6);
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 1rem;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  .error-icon,
  .document-icon {
    color: var(--text-secondary-color, #6b7280);
    margin-bottom: 1rem;
  }

  .error-message {
    color: var(--text-secondary-color, #6b7280);
    margin-bottom: 1rem;
  }

  .retry-btn,
  .generate-btn {
    padding: 0.75rem 1.5rem;
    background: var(--primary-color, #3b82f6);
    color: white;
    border: none;
    border-radius: 6px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s ease;
  }

  .retry-btn:hover,
  .generate-btn:hover:not(:disabled) {
    background: var(--primary-hover-color, #2563eb);
  }

  .generate-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .unavailable-notice {
    color: var(--text-secondary-color, #6b7280);
    font-size: 0.875rem;
  }

  .processing-state h3,
  .failed-state h3,
  .no-summary-state h3 {
    margin: 0 0 0.5rem 0;
    color: var(--text-color, #111827);
  }

  .processing-state p,
  .failed-state p,
  .no-summary-state p {
    margin: 0 0 1.5rem 0;
    color: var(--text-secondary-color, #6b7280);
  }

  /* Summary Content */
  .summary-content {
    space-y: 2rem;
  }

  .search-results {
    background: var(--accent-bg, #fdf4ff);
    padding: 1rem;
    border-radius: 8px;
    margin-bottom: 1.5rem;
    border: 1px solid var(--border-color, #e5e7eb);
  }

  :global(.dark) .search-results {
    background: rgba(139, 92, 246, 0.1);
    border-color: var(--border-color, #4b5563);
  }

  .search-results h4 {
    margin: 0 0 0.75rem 0;
    color: var(--accent-color, #8b5cf6);
    font-weight: 600;
  }

  .search-items {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .search-item {
    font-size: 0.875rem;
  }

  .search-section {
    font-weight: 600;
    color: var(--accent-color, #8b5cf6);
  }

  .search-text {
    color: var(--text-secondary-color, #6b7280);
  }

  .summary-section {
    margin-bottom: 2rem;
  }

  .section-title {
    display: flex;
    align-items: center;
    margin: 0 0 1rem 0;
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--text-color, #111827);
    gap: 0.5rem;
  }

  .section-description {
    font-size: 0.875rem;
    color: var(--text-secondary-color, #6b7280);
    margin-bottom: 1rem;
    font-style: italic;
  }

  .expandable-title {
    cursor: pointer;
    transition: color 0.2s ease;
    justify-content: space-between;
  }

  .expandable-title:hover {
    color: var(--primary-color, #3b82f6);
  }

  .expand-icon {
    margin-left: auto;
    transition: transform 0.2s ease;
  }

  .expand-icon.expanded {
    transform: rotate(180deg);
  }

  .bluf-title {
    color: var(--primary-color, #3b82f6);
  }

  .bluf-content {
    padding: 1rem;
    border-radius: 6px;
    font-weight: 500;
    line-height: 1.6;
    /* Light mode */
    background: #eff6ff;
    border: 1px solid #3b82f6;
    border-left: 4px solid #3b82f6;
    color: #1e40af;
  }

  /* Dark mode with multiple selectors to ensure it works */
  :global(.dark) .bluf-content,
  :global(html.dark) .bluf-content,
  :global([data-theme="dark"]) .bluf-content {
    background: #1e40af !important;
    border: 1px solid #3b82f6 !important;
    border-left: 4px solid #3b82f6 !important;
    color: #dbeafe !important;
  }

  .section-content {
    color: var(--text-color, #111827);
    line-height: 1.6;
  }

  /* Speakers */
  .speakers-grid {
    display: grid;
    gap: 1rem;
    margin-top: 1rem;
  }

  .speaker-card {
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 8px;
    padding: 1rem;
    background: var(--surface-color, #f9fafb);
  }

  :global(.dark) .speaker-card {
    background: var(--surface-color, #374151);
    border-color: var(--border-color, #4b5563);
  }

  .speaker-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }

  .speaker-name {
    margin: 0;
    font-weight: 600;
    color: var(--text-color, #111827);
  }

  .speaker-stats {
    font-size: 0.875rem;
    color: var(--text-secondary-color, #6b7280);
    font-family: monospace;
  }

  .speaker-points {
    margin: 0;
    padding-left: 1rem;
    list-style: none;
  }

  .speaker-points li {
    position: relative;
    margin-bottom: 0.5rem;
    color: var(--text-color, #111827);
    line-height: 1.5;
  }

  .speaker-points li:before {
    content: '•';
    color: var(--text-secondary-color, #6b7280);
    position: absolute;
    left: -1rem;
  }

  /* Content Sections */
  .content-sections {
    margin-top: 1rem;
  }

  .content-section {
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
    background: var(--surface-color, #f9fafb);
  }

  :global(.dark) .content-section {
    background: var(--surface-color, #374151);
    border-color: var(--border-color, #4b5563);
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }

  .section-topic {
    margin: 0;
    font-weight: 600;
    color: var(--text-color, #111827);
  }

  .time-range {
    font-size: 0.875rem;
    font-family: monospace;
    background: var(--surface-color, #f3f4f6);
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    color: var(--text-secondary-color, #6b7280);
    border: 1px solid var(--border-color, #d1d5db);
  }

  :global(.dark) .time-range {
    background: var(--surface-color, #4b5563);
    border-color: var(--border-color, #6b7280);
  }

  .section-points {
    margin: 0;
    padding-left: 1rem;
    list-style: none;
  }

  .section-points li {
    position: relative;
    margin-bottom: 0.5rem;
    color: var(--text-color, #111827);
    line-height: 1.5;
  }

  .section-points li:before {
    content: '•';
    color: var(--text-secondary-color, #6b7280);
    position: absolute;
    left: -1rem;
  }

  /* Action Items */
  .action-items {
    margin-top: 1rem;
  }

  .action-item {
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
    background: var(--surface-color, #f9fafb);
  }

  :global(.dark) .action-item {
    background: var(--surface-color, #374151);
    border-color: var(--border-color, #4b5563);
  }

  .action-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.75rem;
  }

  .action-meta {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .action-number {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--text-secondary-color, #6b7280);
  }

  .priority-badge {
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
  }

  .priority-high {
    background: #fee2e2;
    color: #dc2626;
  }

  .priority-medium {
    background: #fef3c7;
    color: #d97706;
  }

  .priority-low {
    background: #d1fae5;
    color: #059669;
  }

  .priority-default {
    background: var(--background-tertiary);
    color: var(--text-secondary);
  }

  :global(.dark) .priority-high {
    background: #7f1d1d;
    color: #fca5a5;
  }

  :global(.dark) .priority-medium {
    background: #78350f;
    color: #fcd34d;
  }

  :global(.dark) .priority-low {
    background: #064e3b;
    color: #6ee7b7;
  }

  .status-badge {
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
  }

  .status-badge.completed {
    background: #d1fae5;
    color: #059669;
  }

  :global(.dark) .status-badge.completed {
    background: #064e3b;
    color: #6ee7b7;
  }

  .action-details {
    text-align: right;
    font-size: 0.875rem;
    color: var(--text-secondary-color, #6b7280);
  }

  .action-details span {
    font-weight: 600;
  }

  .action-text {
    margin: 0 0 0.5rem 0;
    font-weight: 600;
    color: var(--text-color, #111827);
  }

  .action-context {
    margin: 0;
    font-style: italic;
    color: var(--text-secondary-color, #6b7280);
    font-size: 0.875rem;
  }

  /* Key Decisions */
  .decisions-list {
    background: var(--error-bg, #fef2f2);
    padding: 1rem;
    border-radius: 8px;
    margin-top: 1rem;
    border: 1px solid var(--border-color, #e5e7eb);
  }

  :global(.dark) .decisions-list {
    background: rgba(239, 68, 68, 0.1);
    border-color: var(--border-color, #4b5563);
  }

  .decision-item {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
    color: var(--error-color, #dc2626);
  }

  .decision-item:last-child {
    margin-bottom: 0;
  }

  .decision-item svg {
    flex-shrink: 0;
    margin-top: 0.125rem;
  }

  /* Follow-up Items */
  .followup-list {
    background: var(--accent-bg, #fdf4ff);
    padding: 1rem;
    border-radius: 8px;
    margin-top: 1rem;
    border: 1px solid var(--border-color, #e5e7eb);
  }

  :global(.dark) .followup-list {
    background: rgba(139, 92, 246, 0.1);
    border-color: var(--border-color, #4b5563);
  }

  .followup-item {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
    color: #7c3aed;
  }

  :global(.dark) .followup-item {
    color: #c4b5fd;
  }

  .followup-item:last-child {
    margin-bottom: 0;
  }

  .followup-arrow {
    flex-shrink: 0;
    font-weight: bold;
  }

  /* Metadata */
  .metadata-section {
    border-top: 1px solid var(--border-color, #e5e7eb);
    padding-top: 1rem;
    margin-top: 2rem;
  }

  .metadata-section h4 {
    margin: 0 0 0.75rem 0;
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--text-secondary-color, #6b7280);
  }

  .metadata-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 0.75rem;
  }

  .metadata-item {
    font-size: 0.875rem;
  }

  .metadata-label {
    color: var(--text-secondary-color, #6b7280);
  }

  .metadata-value {
    font-weight: 600;
    color: var(--text-color, #111827);
    margin-left: 0.25rem;
  }

  /* AI Disclaimer */
  .ai-disclaimer {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    padding: 0.75rem;
    margin-top: 1.5rem;
    background: var(--surface-color, #f8fafc);
    border: 1px solid var(--border-color, #e2e8f0);
    border-radius: 6px;
    font-size: 0.75rem;
    line-height: 1.4;
    font-style: italic;
  }

  :global(.dark) .ai-disclaimer {
    background: var(--surface-color, #1e293b);
    border-color: var(--border-color, #475569);
  }

  .disclaimer-icon {
    flex-shrink: 0;
    color: var(--text-secondary-color, #9ca3af);
    margin-top: 0.125rem;
  }

  .disclaimer-text {
    color: var(--text-secondary-color, #6b7280);
  }

  .disclaimer-text strong {
    color: var(--text-secondary-color, #6b7280);
    font-weight: 700;
  }

  /* Responsive */
  @media (max-width: 768px) {
    .summary-modal {
      width: 95%;
      max-width: none;
    }

    .modal-header {
      flex-direction: column;
      align-items: stretch;
      gap: 1rem;
    }

    .header-actions {
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .search-input {
      width: 100%;
    }

    .speakers-grid {
      grid-template-columns: 1fr;
    }

    .metadata-grid {
      grid-template-columns: 1fr;
    }
  }
</style>