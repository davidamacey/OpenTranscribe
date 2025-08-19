<script lang="ts">
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';
  import { type TranscriptSegment } from '$lib/utils/scrollbarCalculations';
  import { type SearchMatch } from '$lib/utils/searchHighlight';
  
  export let transcriptSegments: TranscriptSegment[] = [];
  export let speakerList: any[] = [];
  export let disabled: boolean = false;
  
  const dispatch = createEventDispatcher();
  
  let searchQuery = '';
  let currentMatch = 0;
  let totalMatches = 0;
  let searchMatches: SearchMatch[] = [];
  let searchInput: HTMLInputElement;
  let isVisible = false;
  let searchTimeout: number;
  let isSearching = false;
  let lastSearchQuery = '';
  let previouslyHadResults = false;
  
  // Debounced search functionality
  $: if (searchQuery.trim()) {
    // Only show searching state if query changed significantly
    if (searchQuery !== lastSearchQuery) {
      isSearching = true;
      // Remember if we previously had results to maintain UI stability
      if (totalMatches > 0) {
        previouslyHadResults = true;
      }
    }
    
    // Clear existing timeout
    if (searchTimeout) {
      clearTimeout(searchTimeout);
    }
    // Debounce search for better performance
    searchTimeout = setTimeout(() => {
      performSearch(searchQuery);
      lastSearchQuery = searchQuery;
      isSearching = false;
      // Reset the flag once search is complete
      previouslyHadResults = false;
    }, 200);
  } else {
    if (searchTimeout) {
      clearTimeout(searchTimeout);
    }
    isSearching = false;
    previouslyHadResults = false;
    clearSearch();
  }
  
  // Keyboard shortcuts
  function handleGlobalKeydown(event: KeyboardEvent) {
    // Ctrl+F or Cmd+F to open search
    if ((event.ctrlKey || event.metaKey) && event.key === 'f') {
      event.preventDefault();
      openSearch();
    }
    
    // Escape to close search
    if (event.key === 'Escape' && isVisible) {
      closeSearch();
    }
    
    // Enter/Shift+Enter for navigation when search is focused
    if (isVisible && searchMatches.length > 0) {
      if (event.key === 'Enter') {
        event.preventDefault();
        if (event.shiftKey) {
          navigateToPrevious();
        } else {
          navigateToNext();
        }
      }
    }
  }
  
  function performSearch(query: string) {
    if (!query?.trim() || !transcriptSegments?.length) {
      searchMatches = [];
      totalMatches = 0;
      currentMatch = 0;
      return;
    }
    
    const normalizedQuery = query.toLowerCase().trim();
    const matches: SearchMatch[] = [];
    
    // Create speaker name mapping for consistent search
    const speakerMapping = new Map();
    speakerList.forEach((speaker: any) => {
      speakerMapping.set(speaker.name, speaker.display_name || speaker.name);
    });
    
    transcriptSegments.forEach((segment, segmentIndex) => {
      if (!segment || typeof segment.text !== 'string') return;
      
      // Search in transcript text
      const text = segment.text.toLowerCase();
      let textIndex = 0;
      while ((textIndex = text.indexOf(normalizedQuery, textIndex)) !== -1) {
        matches.push({
          segmentIndex,
          start: textIndex,
          length: normalizedQuery.length,
          type: 'text'
        });
        textIndex += normalizedQuery.length;
      }
      
      // Search in speaker names (both original and display names)
      const speakerLabel = segment.speaker_label || segment.speaker?.name || '';
      const displayName = speakerMapping.get(speakerLabel) || segment.speaker?.display_name || speakerLabel;
      
      // Search original speaker label
      if (speakerLabel.toLowerCase().includes(normalizedQuery)) {
        matches.push({
          segmentIndex,
          start: 0,
          length: speakerLabel.length,
          type: 'speaker'
        });
      }
      
      // Search display name if different from original
      if (displayName !== speakerLabel && displayName.toLowerCase().includes(normalizedQuery)) {
        matches.push({
          segmentIndex,
          start: 0,
          length: displayName.length,
          type: 'speaker'
        });
      }
    });
    
    searchMatches = matches;
    totalMatches = matches.length;
    currentMatch = totalMatches > 0 ? 1 : 0;
    
    // Dispatch search results
    dispatch('searchResults', {
      matches: searchMatches,
      currentMatch,
      totalMatches,
      query: normalizedQuery
    });
    
    // Navigate to first match
    if (totalMatches > 0) {
      navigateToMatch(0);
    }
  }
  
  function clearSearch() {
    searchMatches = [];
    totalMatches = 0;
    currentMatch = 0;
    isSearching = false;
    lastSearchQuery = '';
    previouslyHadResults = false;
    dispatch('searchResults', {
      matches: [],
      currentMatch: 0,
      totalMatches: 0,
      query: ''
    });
  }
  
  function navigateToNext() {
    if (totalMatches === 0) return;
    
    const nextMatch = currentMatch < totalMatches ? currentMatch + 1 : 1;
    currentMatch = nextMatch;
    navigateToMatch(currentMatch - 1);
  }
  
  function navigateToPrevious() {
    if (totalMatches === 0) return;
    
    const prevMatch = currentMatch > 1 ? currentMatch - 1 : totalMatches;
    currentMatch = prevMatch;
    navigateToMatch(currentMatch - 1);
  }
  
  function navigateToMatch(matchIndex: number, autoSeek: boolean = false) {
    if (matchIndex < 0 || matchIndex >= searchMatches.length || !searchMatches.length) return;
    
    const match = searchMatches[matchIndex];
    if (!match || match.segmentIndex < 0 || match.segmentIndex >= transcriptSegments.length) return;
    
    const segment = transcriptSegments[match.segmentIndex];
    if (!segment) return;
    
    // Dispatch navigation event with autoSeek parameter
    dispatch('navigateToMatch', {
      match,
      segment,
      segmentIndex: match.segmentIndex,
      autoSeek
    });
    
    // Scroll to the segment
    const segmentElement = document.querySelector(`[data-segment-id="${segment.id || `${segment.start_time}-${segment.end_time}`}"]`);
    if (segmentElement) {
      segmentElement.scrollIntoView({ 
        behavior: 'smooth', 
        block: 'center',
        inline: 'nearest'
      });
      
      // Add temporary highlight to the segment
      segmentElement.classList.add('search-current-match');
      setTimeout(() => {
        segmentElement.classList.remove('search-current-match');
      }, 2000);
    }
  }
  
  function seekToCurrentMatch() {
    if (totalMatches === 0 || currentMatch < 1) return;
    
    const match = searchMatches[currentMatch - 1];
    const segment = transcriptSegments[match.segmentIndex];
    
    // Dispatch with autoSeek enabled
    dispatch('navigateToMatch', {
      match,
      segment,
      segmentIndex: match.segmentIndex,
      autoSeek: true
    });
  }
  
  function openSearch() {
    isVisible = true;
    // Focus the search input after a small delay to ensure it's rendered
    setTimeout(() => {
      if (searchInput) {
        searchInput.focus();
        searchInput.select();
      }
    }, 50);
  }
  
  function closeSearch() {
    isVisible = false;
    searchQuery = '';
    if (searchTimeout) {
      clearTimeout(searchTimeout);
    }
    clearSearch();
  }
  
  function handleSearchInput() {
    // The reactive statement will handle the search
  }
  
  onMount(() => {
    if (typeof window !== 'undefined') {
      window.addEventListener('keydown', handleGlobalKeydown);
    }
  });
  
  onDestroy(() => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('keydown', handleGlobalKeydown);
    }
    if (searchTimeout) {
      clearTimeout(searchTimeout);
    }
  });
</script>

{#if isVisible}
  <div class="search-container" class:disabled>
    <div class="search-input-wrapper">
      <div class="search-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8"></circle>
          <path d="M21 21l-4.35-4.35"></path>
        </svg>
      </div>
      
      <input
        bind:this={searchInput}
        bind:value={searchQuery}
        on:input={handleSearchInput}
        type="text"
        placeholder="Search transcript and speakers... (Ctrl+F)"
        class="search-input"
        {disabled}
        aria-label="Search transcript and speaker names"
        aria-describedby={totalMatches > 0 ? "search-results-info" : undefined}
      />
      
      {#if isSearching && previouslyHadResults}
        <!-- Maintain navigation controls layout during search to prevent flicker -->
        <div class="search-results-info" id="search-results-info">
          <span class="results-count searching">Searching...</span>
          <div class="navigation-controls">
            <div class="navigation-buttons">
              <button
                class="nav-button"
                disabled={true}
                title="Previous match (Shift+Enter)"
                aria-label="Go to previous search match"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="15,18 9,12 15,6"></polyline>
                </svg>
              </button>
              <button
                class="nav-button"
                disabled={true}
                title="Next match (Enter)"
                aria-label="Go to next search match"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="9,6 15,12 9,18"></polyline>
                </svg>
              </button>
            </div>
            <button
              class="jump-button"
              disabled={true}
              title="Jump to current match in video"
              aria-label="Jump to current match timestamp in video"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
              </svg>
            </button>
          </div>
        </div>
      {:else if isSearching}
        <!-- Simple searching state for first search -->
        <div class="search-results-info" id="search-results-info">
          <span class="results-count searching">Searching...</span>
        </div>
      {:else if totalMatches > 0}
        <div class="search-results-info" id="search-results-info">
          <span class="results-count" aria-live="polite">{currentMatch} of {totalMatches}</span>
          <div class="navigation-controls">
            <div class="navigation-buttons">
              <button
                class="nav-button"
                on:click={navigateToPrevious}
                disabled={totalMatches === 0}
                title="Previous match (Shift+Enter)"
                aria-label="Go to previous search match"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="15,18 9,12 15,6"></polyline>
                </svg>
              </button>
              <button
                class="nav-button"
                on:click={navigateToNext}
                disabled={totalMatches === 0}
                title="Next match (Enter)"
                aria-label="Go to next search match"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="9,6 15,12 9,18"></polyline>
                </svg>
              </button>
            </div>
            <button
              class="jump-button"
              on:click={seekToCurrentMatch}
              disabled={totalMatches === 0}
              title="Jump to current match in video"
              aria-label="Jump to current match timestamp in video"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
              </svg>
            </button>
          </div>
        </div>
      {:else if searchQuery.trim() && !isSearching}
        <div class="search-results-info">
          <span class="results-count no-results">No matches</span>
        </div>
      {/if}
      
      <button
        class="close-button"
        on:click={closeSearch}
        title="Close search (Escape)"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M18 6L6 18M6 6l12 12"/>
        </svg>
      </button>
    </div>
  </div>
{:else}
  <div class="search-trigger">
    <button
      class="search-trigger-button"
      on:click={openSearch}
      title="Search transcript (Ctrl+F)"
      {disabled}
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="11" cy="11" r="8"></circle>
        <path d="M21 21l-4.35-4.35"></path>
      </svg>
      Search
    </button>
  </div>
{/if}

<style>
  .search-container {
    margin-bottom: 16px;
    padding: 12px;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    animation: slideDown 0.2s ease-out;
  }
  
  .search-container.disabled {
    opacity: 0.6;
    pointer-events: none;
  }
  
  @keyframes slideDown {
    from {
      opacity: 0;
      transform: translateY(-10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  
  .search-input-wrapper {
    display: flex;
    align-items: center;
    gap: 8px;
    position: relative;
  }
  
  .search-icon {
    color: var(--text-secondary);
    display: flex;
    align-items: center;
  }
  
  .search-icon svg {
    flex-shrink: 0;
    color: inherit;
  }
  
  .search-input {
    flex: 1;
    padding: 8px 12px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--background-color);
    color: var(--text-primary);
    font-size: 14px;
    outline: none;
  }
  
  .search-input:focus {
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
  }
  
  .search-results-info {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--text-secondary);
    white-space: nowrap;
  }
  
  .results-count {
    font-weight: 500;
  }
  
  .results-count.no-results {
    color: var(--error-color);
  }
  
  .results-count.searching {
    color: var(--text-secondary);
    font-style: italic;
  }
  
  .navigation-controls {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  
  .navigation-buttons {
    display: flex;
    gap: 2px;
  }
  
  .nav-button {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    background: none;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s ease;
  }
  
  .nav-button svg {
    flex-shrink: 0;
    color: inherit;
  }
  
  .nav-button:hover:not(:disabled) {
    background: var(--surface-hover);
    border-color: var(--border-hover);
    color: var(--text-primary);
  }
  
  .nav-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .nav-button:disabled svg {
    color: var(--text-secondary);
  }
  
  .jump-button {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 28px;
    padding: 0 8px;
    background: var(--primary-color);
    border: 1px solid var(--primary-color);
    border-radius: 4px;
    color: white;
    cursor: pointer;
    font-size: 11px;
    font-weight: 500;
    transition: all 0.2s ease;
  }
  
  .jump-button:hover:not(:disabled) {
    background: var(--primary-hover);
    border-color: var(--primary-hover);
  }
  
  .jump-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .close-button {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    border-radius: 4px;
    transition: all 0.2s ease;
  }
  
  .close-button svg {
    flex-shrink: 0;
    color: inherit;
  }
  
  .close-button:hover {
    background: var(--surface-hover);
    color: var(--text-primary);
  }
  
  .search-trigger {
    margin-bottom: 16px;
  }
  
  .search-trigger-button {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 14px;
    transition: all 0.2s ease;
  }
  
  .search-trigger-button svg {
    flex-shrink: 0;
    color: inherit;
  }
  
  .search-trigger-button:hover:not(:disabled) {
    background: var(--surface-hover);
    border-color: var(--border-hover);
    color: var(--text-primary);
  }
  
  .search-trigger-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  /* Global styles for search highlighting */
  :global(.search-current-match) {
    background-color: rgba(59, 130, 246, 0.2) !important;
    border: 2px solid var(--primary-color) !important;
    animation: pulse 1s ease-in-out;
  }
  
  @keyframes pulse {
    0%, 100% {
      box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4);
    }
    50% {
      box-shadow: 0 0 0 8px rgba(59, 130, 246, 0);
    }
  }
  
  /* Highlight text matches */
  :global(.transcript-search-highlight) {
    background-color: rgba(255, 235, 59, 0.7);
    padding: 1px 2px;
    border-radius: 2px;
    font-weight: 600;
  }
  
  :global(.transcript-search-highlight.current) {
    background-color: rgba(255, 152, 0, 0.8);
    color: white;
  }
  
  /* Dark mode highlighting */
  :global([data-theme='dark']) :global(.transcript-search-highlight) {
    background-color: rgba(255, 193, 7, 0.3);
    color: var(--text-primary);
  }
  
  :global([data-theme='dark']) :global(.transcript-search-highlight.current) {
    background-color: rgba(255, 152, 0, 0.6);
    color: white;
  }
</style>