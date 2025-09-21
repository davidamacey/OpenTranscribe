<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { getSpeakerColor } from '$lib/utils/speakerColors';

  export let fileId: number;
  export let fileName: string = '';
  export let isOpen: boolean = false;
  export let transcriptSegments: any[] = [];
  
  const dispatch = createEventDispatcher<{
    close: void;
  }>();
  
  let loading = false;
  let error: string | null = null;
  let consolidatedTranscript = '';
  let displaySegments: any[] = [];
  
  // Search functionality
  let searchQuery = '';
  let currentMatchIndex = 0;
  let totalMatches = 0;
  let copyButtonText = 'Copy';
  
  $: if (isOpen && transcriptSegments) {
    processTranscriptSegments();
  }
  
  $: if (searchQuery && displaySegments.length > 0) {
    // Count matches across all segment text for accurate search navigation
    const allText = displaySegments.map(segment => segment.text).join(' ');
    totalMatches = countMatches(searchQuery, allText);
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
  
  function processTranscriptSegments() {
    if (!transcriptSegments || !Array.isArray(transcriptSegments)) {
      consolidatedTranscript = '';
      displaySegments = [];
      return;
    }

    try {
      // Sort segments by start_time to ensure proper ordering
      const sortedSegments = [...transcriptSegments].sort((a: any, b: any) => {
        const aStart = parseFloat(a.start_time || a.start || 0);
        const bStart = parseFloat(b.start_time || b.start || 0);
        return aStart - bStart;
      });

      // Group consecutive segments from the same speaker for display
      const groupedSegments = [];
      let currentSpeaker = null;
      let currentSpeakerLabel = null;
      let currentText = [];
      let currentStartTime = null;
      let currentEndTime = null;

      sortedSegments.forEach((segment: any) => {
        const speakerName = segment.speaker_label || segment.speaker?.display_name || segment.speaker?.name || 'Unknown Speaker';
        const startTime = parseFloat(segment.start_time || segment.start || 0);
        const endTime = parseFloat(segment.end_time || segment.end || 0);

        if (speakerName !== currentSpeaker) {
          if (currentSpeaker && currentText.length > 0) {
            groupedSegments.push({
              speakerName: currentSpeaker,
              speaker_label: currentSpeakerLabel, // Preserve for color mapping
              text: currentText.join(' '),
              startTime: currentStartTime,
              endTime: currentEndTime
            });
          }
          currentSpeaker = speakerName;
          currentSpeakerLabel = segment.speaker_label || segment.speaker?.name; // Store original label
          currentText = [segment.text];
          currentStartTime = startTime;
          currentEndTime = endTime;
        } else {
          currentText.push(segment.text);
          currentEndTime = endTime; // Update end time to last segment
        }
      });

      // Add the last speaker block
      if (currentSpeaker && currentText.length > 0) {
        groupedSegments.push({
          speakerName: currentSpeaker,
          speaker_label: currentSpeakerLabel, // Preserve for color mapping
          text: currentText.join(' '),
          startTime: currentStartTime,
          endTime: currentEndTime
        });
      }

      displaySegments = groupedSegments;

      // Generate consolidated transcript for copy functionality - exactly as displayed
      consolidatedTranscript = displaySegments
        .map(block => `${block.speakerName} [${formatSimpleTimestamp(block.startTime)}-${formatSimpleTimestamp(block.endTime)}]: ${block.text}`)
        .join('\n\n');

    } catch (error) {
      console.error('TranscriptModal: Error processing transcript segments:', error);
      consolidatedTranscript = '';
      displaySegments = [];
    }
  }
  
  function countMatches(query: string, text: string): number {
    if (!query.trim() || !text) return 0;
    
    const searchTerm = query.toLowerCase();
    const escapedTerm = searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const matches = text.toLowerCase().match(new RegExp(escapedTerm, 'g'));
    return matches ? matches.length : 0;
  }
  
  function highlightSearchTerms(text: string, query: string, matchIndex: number = -1): string {
    if (!query.trim() || !text) return text;
    
    const searchTerm = query.toLowerCase();
    const escapedTerm = searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escapedTerm})`, 'gi');
    
    let currentMatch = 0;
    return text.replace(regex, (match) => {
      const isCurrentMatch = currentMatch === matchIndex;
      const matchClass = isCurrentMatch ? 'current-match' : 'search-match';
      const result = `<mark class="${matchClass}" data-match-index="${currentMatch}">${match}</mark>`;
      currentMatch++;
      return result;
    });
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
    setTimeout(() => {
      const currentMatch = document.querySelector(`[data-match-index="${currentMatchIndex}"].current-match`);
      if (currentMatch) {
        currentMatch.scrollIntoView({ 
          behavior: 'smooth', 
          block: 'center', 
          inline: 'nearest' 
        });
      }
    }, 50);
  }
  
  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      dispatch('close');
    }
  }
  
  function handleSearchKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      searchQuery = '';
    } else if (event.key === 'Enter') {
      if (event.shiftKey) {
        cycleToPreviousMatch();
      } else {
        cycleToNextMatch();
      }
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
    event.stopPropagation();
  }
  
  function handleCopy() {
    if (!consolidatedTranscript) return;

    navigator.clipboard.writeText(consolidatedTranscript).then(() => {
      copyButtonText = 'Copied!';
      setTimeout(() => {
        copyButtonText = 'Copy';
      }, 2000);
    }).catch(err => {
      console.error('TranscriptModal: Failed to copy to clipboard:', err);
      // Fallback for browsers that don't support clipboard API
      try {
        const textArea = document.createElement('textarea');
        textArea.value = consolidatedTranscript;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        copyButtonText = 'Copied!';
        setTimeout(() => {
          copyButtonText = 'Copy';
        }, 2000);
      } catch (fallbackError) {
        console.error('TranscriptModal: Fallback copy failed:', fallbackError);
        copyButtonText = 'Copy failed';
        setTimeout(() => {
          copyButtonText = 'Copy';
        }, 2000);
      }
    });
  }
  
  function clearSearch() {
    searchQuery = '';
  }

  // Helper function to get consistent speaker name for color mapping
  function getSpeakerNameForColor(segment: any): string {
    // Use the original speaker name/label for consistent color mapping
    return segment.speaker_label || segment.speaker?.name || 'Unknown';
  }

  function formatSimpleTimestamp(seconds: number): string {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  }
  
  // Clean up body overflow when component is destroyed
  onMount(() => {
    return () => {
      document.body.style.overflow = '';
    };
  });
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
        <h2 class="modal-title">Full Transcript - {fileName}</h2>
        <div class="header-actions">
          {#if consolidatedTranscript}
            <button 
              class="copy-button-header"
              class:copied={copyButtonText === 'Copied!'}
              on:click={handleCopy}
              aria-label="Copy transcript"
              title={copyButtonText === 'Copied!' ? 'Transcript copied to clipboard!' : 'Copy full transcript text'}
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
          {/if}
          <button class="close-button" on:click={handleCloseButton} aria-label="Close modal" title="Close modal (Esc)">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </button>
        </div>
      </div>
      
      <!-- Search Section -->
      {#if displaySegments.length > 0}
        <div class="search-section">
          <div class="search-container">
            <div class="search-input-wrapper">
              <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="11" cy="11" r="8"></circle>
                <path d="m21 21-4.35-4.35"></path>
              </svg>
              <input 
                type="text" 
                bind:value={searchQuery}
                placeholder="Search transcript..." 
                class="search-input"
                on:keydown={handleSearchKeydown}
                aria-label="Search transcript"
              />
              {#if searchQuery}
                <button 
                  class="clear-search-button"
                  on:click={clearSearch}
                  aria-label="Clear search"
                  title="Clear search"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                  </svg>
                </button>
              {/if}
            </div>
            
            {#if totalMatches > 0}
              <div class="search-results">
                <span class="match-count">{currentMatchIndex + 1} of {totalMatches}</span>
                <div class="navigation-buttons">
                  <button 
                    class="nav-button"
                    on:click={cycleToPreviousMatch}
                    disabled={totalMatches === 0}
                    aria-label="Previous match"
                    title="Previous match (Shift+Enter)"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="15,18 9,12 15,6"></polyline>
                    </svg>
                  </button>
                  <button 
                    class="nav-button"
                    on:click={cycleToNextMatch}
                    disabled={totalMatches === 0}
                    aria-label="Next match"
                    title="Next match (Enter)"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="9,18 15,12 9,6"></polyline>
                    </svg>
                  </button>
                </div>
              </div>
            {/if}
          </div>
        </div>
      {/if}
      
      <!-- Transcript Content -->
      <div class="modal-content">
        {#if loading}
          <div class="loading-container">
            <div class="spinner"></div>
            <p>Loading transcript...</p>
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
              <h3>Error Loading Transcript</h3>
              <p>{error}</p>
            </div>
          </div>
        {:else if displaySegments.length > 0}
          <div class="transcript-content">
            {#each displaySegments as segment}
              <div class="transcript-segment">
                <div class="segment-header">
                  <div
                    class="segment-speaker"
                    style="background-color: {getSpeakerColor(getSpeakerNameForColor(segment)).bg}; border-color: {getSpeakerColor(getSpeakerNameForColor(segment)).border}; --speaker-light: {getSpeakerColor(getSpeakerNameForColor(segment)).textLight}; --speaker-dark: {getSpeakerColor(getSpeakerNameForColor(segment)).textDark};"
                  >{segment.speakerName}</div>
                  <div class="segment-time">{formatSimpleTimestamp(segment.startTime)}-{formatSimpleTimestamp(segment.endTime)}</div>
                </div>
                <div class="segment-text">{@html highlightSearchTerms(segment.text, searchQuery, currentMatchIndex)}</div>
              </div>
            {/each}
          </div>
        {:else}
          <div class="no-transcript">
            <div class="no-transcript-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14,2 14,8 20,8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
                <polyline points="10,9 9,9 8,9"></polyline>
              </svg>
            </div>
            <h3>No Transcript Available</h3>
            <p>This file doesn't have a transcript available yet.</p>
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
    flex-shrink: 0;
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
    color: var(--primary-color);
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

  .modal-title {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
    margin-right: 1.5rem;
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

  .search-section {
    padding: 1rem 1.5rem;
    border-bottom: 1px solid var(--border-color);
    background-color: var(--bg-secondary);
    flex-shrink: 0;
  }

  .search-container {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .search-input-wrapper {
    flex: 1;
    position: relative;
    display: flex;
    align-items: center;
  }

  .search-icon {
    position: absolute;
    left: 0.75rem;
    color: var(--text-secondary);
    pointer-events: none;
    z-index: 1;
  }

  .search-input {
    width: 100%;
    padding: 0.5rem 0.75rem 0.5rem 2.5rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background-color: var(--bg-primary);
    color: var(--text-primary);
    font-size: 0.9rem;
    transition: border-color 0.2s ease;
  }

  .search-input:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
  }

  .search-input::placeholder {
    color: var(--text-secondary);
  }

  .clear-search-button {
    position: absolute;
    right: 0.5rem;
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-secondary);
    padding: 0.25rem;
    border-radius: 4px;
    transition: color 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .clear-search-button:hover {
    color: var(--text-primary);
    background-color: var(--hover-bg);
  }

  .search-results {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-shrink: 0;
  }

  .match-count {
    font-size: 0.85rem;
    color: var(--text-secondary);
    white-space: nowrap;
  }

  .navigation-buttons {
    display: flex;
    gap: 0.25rem;
  }

  .nav-button {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    padding: 0.25rem;
    cursor: pointer;
    color: var(--text-secondary);
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 28px;
    min-height: 28px;
  }

  .nav-button:hover:not(:disabled) {
    background-color: var(--hover-bg);
    border-color: var(--primary-color);
    color: var(--text-primary);
  }

  .nav-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .modal-content {
    flex: 1;
    overflow: auto;
    padding: 1.5rem;
  }

  .transcript-content {
    line-height: 1.6;
    color: var(--text-primary);
    font-size: 0.9rem;
    word-wrap: break-word;
  }

  .transcript-segment {
    margin-bottom: 1.5rem;
    display: flex;
    gap: 1rem;
    align-items: flex-start;
  }

  .transcript-segment:last-child {
    margin-bottom: 0;
  }

  .segment-header {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    flex-shrink: 0;
    min-width: fit-content;
    align-items: center;
  }

  .segment-speaker {
    font-size: 12px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 12px;
    white-space: nowrap;
    min-width: fit-content;
    max-width: 150px;
    overflow: hidden;
    text-overflow: ellipsis;
    border: 1px solid;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    transition: all 0.2s ease;
    color: var(--speaker-light);
  }

  /* Dark mode speaker colors */
  :global([data-theme='dark']) .segment-speaker {
    color: var(--speaker-dark);
  }

  .segment-time {
    font-size: 12px;
    font-weight: 600;
    color: var(--primary-color);
    font-family: monospace;
    white-space: nowrap;
  }

  .segment-text {
    font-size: 14px;
    color: var(--text-primary);
    line-height: 1.4;
    flex: 1;
    padding-top: 2px; /* Align with speaker chip top */
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
    color: var(--error-color);
  }

  .error-message h3 {
    margin: 0 0 0.5rem 0;
    color: var(--error-color);
  }

  .error-message p {
    margin: 0;
    color: var(--text-secondary);
  }

  .no-transcript {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    text-align: center;
    gap: 1rem;
  }

  .no-transcript-icon {
    color: var(--text-secondary);
    opacity: 0.7;
  }

  .no-transcript h3 {
    margin: 0;
    color: var(--text-primary);
    font-size: 1.25rem;
    font-weight: 600;
  }

  .no-transcript p {
    margin: 0;
    color: var(--text-secondary);
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* Search highlighting */
  :global(.search-match) {
    background-color: rgba(255, 255, 0, 0.3);
    padding: 0.1em 0.2em;
    border-radius: 3px;
  }

  :global(.current-match) {
    background-color: rgba(255, 165, 0, 0.6);
    padding: 0.1em 0.2em;
    border-radius: 3px;
    box-shadow: 0 0 0 1px rgba(255, 165, 0, 0.8);
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
    
    .search-section {
      padding: 1rem;
    }
    
    .search-container {
      flex-direction: column;
      align-items: stretch;
      gap: 0.75rem;
    }
    
    .search-results {
      justify-content: space-between;
    }
    
    .modal-content {
      padding: 1rem;
    }
    
    .transcript-content {
      font-size: 0.85rem;
    }
  }
</style>