<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import axiosInstance from '$lib/axios';
  import { t } from '$stores/locale';

  export let value: string = '';
  export let placeholder: string = '';

  const dispatch = createEventDispatcher();

  let suggestions: any[] = [];
  let showSuggestions = false;
  let selectedIndex = -1;
  let debounceTimer: ReturnType<typeof setTimeout>;
  let inputEl: HTMLInputElement;
  let abortController: AbortController | null = null;
  let suppressFocusReopen = false;

  async function fetchSuggestions(query: string) {
    if (query.length < 2) {
      suggestions = [];
      showSuggestions = false;
      return;
    }

    // Cancel any in-flight request
    abortController?.abort();
    abortController = new AbortController();

    try {
      const res = await axiosInstance.get('/search/suggestions', {
        params: { q: query, limit: 8 },
        signal: abortController.signal,
      });
      suggestions = res.data || [];
      showSuggestions = suggestions.length > 0;
      selectedIndex = -1;
    } catch (e: any) {
      // Ignore cancelled requests
      if (e?.code === 'ERR_CANCELED') return;
      suggestions = [];
      showSuggestions = false;
    }
  }

  function handleInput() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => fetchSuggestions(value), 200);
  }

  function handleKeydown(e: KeyboardEvent) {
    if (!showSuggestions) {
      if (e.key === 'Enter') {
        suggestions = [];
        suppressFocusReopen = true;
        dispatch('search');
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        selectedIndex = Math.min(selectedIndex + 1, suggestions.length - 1);
        break;
      case 'ArrowUp':
        e.preventDefault();
        selectedIndex = Math.max(selectedIndex - 1, -1);
        break;
      case 'Enter':
        e.preventDefault();
        if (selectedIndex >= 0 && suggestions[selectedIndex]) {
          selectSuggestion(suggestions[selectedIndex]);
        } else {
          showSuggestions = false;
          suggestions = [];
          suppressFocusReopen = true;
          dispatch('search');
        }
        break;
      case 'Escape':
        showSuggestions = false;
        selectedIndex = -1;
        break;
    }
  }

  function selectSuggestion(suggestion: any) {
    value = suggestion.text || suggestion.title || suggestion;
    showSuggestions = false;
    selectedIndex = -1;
    dispatch('select', value);
  }

  function handleBlur() {
    // Delay to allow click on suggestion
    setTimeout(() => {
      showSuggestions = false;
    }, 200);
  }

  function handleFocus() {
    if (suppressFocusReopen) {
      suppressFocusReopen = false;
      return;
    }
    if (suggestions.length > 0 && value.length >= 2) {
      showSuggestions = true;
    }
  }

  function handleClear() {
    value = '';
    suggestions = [];
    showSuggestions = false;
    selectedIndex = -1;
    inputEl?.focus();
    dispatch('clear');
  }

  function getSuggestionIcon(type: string): string {
    switch (type) {
      case 'title': return 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z';
      case 'speaker': return 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2';
      default: return 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z';
    }
  }
</script>

<div class="autocomplete-wrapper">
  <input
    bind:this={inputEl}
    bind:value
    on:input={handleInput}
    on:keydown={handleKeydown}
    on:blur={handleBlur}
    on:focus={handleFocus}
    type="text"
    class="search-input"
    class:has-value={value.length > 0}
    {placeholder}
    autocomplete="off"
    role="combobox"
    aria-expanded={showSuggestions}
    aria-autocomplete="list"
  />

  {#if value.length > 0}
    <button class="clear-btn" on:mousedown|preventDefault={handleClear} title="Clear search" aria-label="Clear search">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="15" y1="9" x2="9" y2="15"></line>
        <line x1="9" y1="9" x2="15" y2="15"></line>
      </svg>
    </button>
  {/if}

  {#if showSuggestions}
    <div class="suggestions-dropdown" role="listbox">
      {#each suggestions as suggestion, i}
        <button
          class="suggestion-item"
          class:selected={i === selectedIndex}
          on:mousedown|preventDefault={() => selectSuggestion(suggestion)}
          role="option"
          aria-selected={i === selectedIndex}
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d={getSuggestionIcon(suggestion.type || 'content')}></path>
          </svg>
          <span class="suggestion-text">{suggestion.text || suggestion.title || suggestion}</span>
          {#if suggestion.type}
            <span class="suggestion-type">{suggestion.type}</span>
          {/if}
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .autocomplete-wrapper {
    position: relative;
    flex: 1;
  }

  .search-input {
    width: 100%;
    height: 44px;
    padding: 0 1rem;
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 12px;
    background: var(--input-background, var(--surface-color, #fff));
    color: var(--text-color, #111827);
    font-size: 0.9375rem;
    outline: none;
    transition: border-color 0.15s, box-shadow 0.15s;
    color-scheme: light dark;
  }

  .search-input.has-value {
    padding-right: 2.5rem;
  }

  .search-input:focus {
    border-color: var(--primary-color, #4f46e5);
    box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
  }

  .clear-btn {
    position: absolute;
    right: 0.5rem;
    top: 0;
    bottom: 0;
    margin: auto 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    padding: 0;
    border: none;
    border-radius: 50%;
    background: none;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
    transition: color 0.15s, background-color 0.15s;
  }

  .clear-btn:hover {
    color: var(--text-color, #374151);
    background-color: var(--hover-color, #f1f5f9);
  }

  .suggestions-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    margin-top: 4px;
    background: var(--card-background, var(--surface-color, #fff));
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 8px;
    box-shadow: var(--dropdown-shadow, 0 4px 12px rgba(0, 0, 0, 0.1));
    z-index: 100;
    overflow: hidden;
  }

  .suggestion-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: none;
    background: none;
    color: var(--text-color, #374151);
    font-size: 0.8125rem;
    text-align: left;
    cursor: pointer;
    transition: background 0.1s;
  }

  .suggestion-item:hover,
  .suggestion-item.selected {
    background: var(--hover-color, #f3f4f6);
  }

  .suggestion-item svg {
    color: var(--text-secondary, #9ca3af);
    flex-shrink: 0;
  }

  .suggestion-text {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .suggestion-type {
    font-size: 0.6875rem;
    color: var(--text-secondary, #9ca3af);
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
</style>
