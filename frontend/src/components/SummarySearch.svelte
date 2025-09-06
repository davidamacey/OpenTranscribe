<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  
  export let searchQuery: string = '';
  export let totalMatches: number = 0;
  export let currentMatchIndex: number = 0;
  export let disabled: boolean = false;
  
  const dispatch = createEventDispatcher<{
    search: { query: string };
    clearSearch: void;
    nextMatch: void;
    previousMatch: void;
    keydown: KeyboardEvent;
  }>();
  
  function handleInput(event: Event) {
    const target = event.target as HTMLInputElement;
    searchQuery = target.value;
    dispatch('search', { query: searchQuery });
  }
  
  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      event.preventDefault();
      event.stopPropagation();
      if (event.shiftKey) {
        previousMatch();
      } else {
        nextMatch();
      }
    } else {
      dispatch('keydown', event);
    }
  }
  
  function clearSearch() {
    searchQuery = '';
    dispatch('clearSearch');
  }
  
  function nextMatch() {
    dispatch('nextMatch');
  }
  
  function previousMatch() {
    dispatch('previousMatch');
  }
</script>

<div class="summary-search">
  <div class="search-input-container">
    <svg class="search-icon" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
      <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/>
    </svg>
    
    <input 
      type="text"
      placeholder="Search within summary... (Press Enter to cycle)"
      bind:value={searchQuery}
      on:input={handleInput}
      on:keydown={handleKeydown}
      class="search-input"
      {disabled}
    />
    
    {#if searchQuery && totalMatches > 0}
      <div class="search-controls">
        <span class="match-counter">{currentMatchIndex + 1}/{totalMatches}</span>
        <button 
          class="nav-button" 
          on:click={previousMatch}
          aria-label="Previous match"
          title="Previous match (Shift+Enter)"
          disabled={totalMatches === 0}
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
            <path d="M11.354 1.646a.5.5 0 0 1 0 .708L5.707 8l5.647 5.646a.5.5 0 0 1-.708.708l-6-6a.5.5 0 0 1 0-.708l6-6a.5.5 0 0 1 .708 0z"/>
          </svg>
        </button>
        <button 
          class="nav-button" 
          on:click={nextMatch}
          aria-label="Next match"
          title="Next match (Enter)"
          disabled={totalMatches === 0}
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
            <path d="M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708z"/>
          </svg>
        </button>
      </div>
    {/if}
    
    {#if searchQuery}
      <button 
        class="clear-button" 
        on:click={clearSearch}
        aria-label="Clear search"
        title="Clear search"
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
          <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/>
          <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>
        </svg>
      </button>
    {/if}
  </div>
  
  {#if searchQuery && totalMatches === 0}
    <div class="no-results">
      <span>No results found for "{searchQuery}"</span>
    </div>
  {/if}
</div>

<style>
  .summary-search {
    border-bottom: 1px solid var(--border-color);
    background-color: var(--bg-secondary);
  }

  .search-input-container {
    position: relative;
    padding: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .search-icon {
    color: var(--text-muted);
    flex-shrink: 0;
  }

  .search-input {
    flex: 1;
    padding: 0.75rem 1rem;
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
    box-shadow: 0 0 0 3px rgba(var(--primary-rgb), 0.1);
  }

  .search-input:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .search-controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
  }

  .match-counter {
    font-size: 0.85rem;
    color: var(--text-secondary);
    font-weight: 500;
    min-width: 3rem;
    text-align: center;
  }

  .nav-button {
    background: none;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    color: var(--text-secondary);
    padding: 0.25rem;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
  }

  .nav-button:hover:not(:disabled) {
    background-color: var(--hover-bg);
    border-color: var(--primary-color);
    color: var(--primary-color);
  }

  .nav-button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .clear-button {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-muted);
    padding: 0.25rem;
    border-radius: 3px;
    transition: color 0.2s ease, background-color 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    flex-shrink: 0;
  }

  .clear-button:hover {
    color: var(--text-primary);
    background-color: var(--hover-bg);
  }


  .no-results {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 1.5rem;
    color: var(--text-muted);
    font-size: 0.9rem;
  }
</style>