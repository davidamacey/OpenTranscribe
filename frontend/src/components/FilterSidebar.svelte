<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import axiosInstance from '../lib/axios';
  
  // Type definitions for props and state
  /**
   * @typedef {Object} Tag
   * @property {number} id - Tag ID
   * @property {string} name - Tag name
   */
  
  /**
   * @typedef {Object} Speaker
   * @property {number} id - Speaker ID
   * @property {string} name - Speaker name
   */
  
  /**
   * @typedef {Object} DateRange
   * @property {Date|null} from - Start date
   * @property {Date|null} to - End date
   */
  
  // Props
  /** @type {string} */
  export let searchQuery = '';
  
  /** @type {string[]} */
  export let selectedTags = [];
  
  /** @type {string|null} */
  export let selectedSpeaker = null;
  
  /** @type {DateRange} */
  export let dateRange = { from: null, to: null };
  
  // State
  /** @type {Tag[]} */
  let allTags = [];
  
  /** @type {Speaker[]} */
  let allSpeakers = [];
  
  /** @type {boolean} */
  let loadingTags = false;
  
  /** @type {boolean} */
  let loadingSpeakers = false;
  
  /** @type {string|null} */
  let errorTags = null;
  
  /** @type {string|null} */
  let errorSpeakers = null;
  
  // Event dispatcher
  const dispatch = createEventDispatcher();
  
  // Date input values
  /** @type {string} */
  let fromDate = '';
  
  /** @type {string} */
  let toDate = '';
  
  // Fetch all tags
  async function fetchTags() {
    loadingTags = true;
    errorTags = null;
    
    try {
      console.log('[FilterSidebar] Fetching tags');
      const response = await axiosInstance.get('/tags/');
      console.log('[FilterSidebar] Tags response:', response.data);
      allTags = response.data;
    } catch (err) {
      console.error('[FilterSidebar] Error fetching tags:', err);
      // Don't set error message, just set empty array
      allTags = [];
    } finally {
      loadingTags = false;
    }
  }
  
  // Fetch all speakers
  async function fetchSpeakers() {
    loadingSpeakers = true;
    errorSpeakers = null;
    
    try {
      const response = await axiosInstance.get('/speakers/');
      allSpeakers = response.data;
    } catch (err) {
      console.error('Error fetching speakers:', err);
      // Don't set error message, just set empty array
      allSpeakers = [];
    } finally {
      loadingSpeakers = false;
    }
  }
  
  /**
   * Handle tag selection
   * @param {string} tag - The tag to toggle
   */
  function toggleTag(tag) {
    const index = selectedTags.indexOf(tag);
    
    if (index === -1) {
      selectedTags = [...selectedTags, tag];
    } else {
      selectedTags = selectedTags.filter(t => t !== tag);
    }
  }
  
  /**
   * Handle speaker selection
   * @param {string} speaker - The speaker to select/deselect
   */
  function selectSpeaker(speaker) {
    if (selectedSpeaker === speaker) {
      selectedSpeaker = null;
    } else {
      selectedSpeaker = speaker;
    }
  }
  
  /**
   * Handle from date input changes
   * @param {Event} event - The input event
   */
  function handleFromDateChange(event) {
    if (event.target && 'value' in event.target) {
      const date = event.target.value ? new Date(event.target.value) : null;
      dateRange = { ...dateRange, from: date };
    }
  }
  
  /**
   * Handle to date input changes
   * @param {Event} event - The input event
   */
  function handleToDateChange(event) {
    if (event.target && 'value' in event.target) {
      const date = event.target.value ? new Date(event.target.value) : null;
      dateRange = { ...dateRange, to: date };
    }
  }
  
  // Apply filters
  function applyFilters() {
    dispatch('filter', {
      search: searchQuery,
      tags: selectedTags,
      speaker: selectedSpeaker,
      dates: dateRange
    });
  }
  
  // Reset filters
  function resetFilters() {
    searchQuery = '';
    selectedTags = [];
    selectedSpeaker = null;
    dateRange = { from: null, to: null };
    fromDate = '';
    toDate = '';
    
    dispatch('reset');
  }
  
  onMount(() => {
    fetchTags();
    fetchSpeakers();
    
    // Initialize date inputs if dateRange has values
    if (dateRange.from instanceof Date) {
      fromDate = dateRange.from.toISOString().split('T')[0];
    }
    
    if (dateRange.to instanceof Date) {
      toDate = dateRange.to.toISOString().split('T')[0];
    }
  });
</script>

<div class="filter-sidebar">
  <div class="filter-header">
    <h2>Filters</h2>
    <button class="reset-button" on:click={resetFilters}>Reset</button>
  </div>
  
  <div class="filter-section">
    <h3>Search</h3>
    <input
      type="text"
      bind:value={searchQuery}
      placeholder="Search files..."
      class="filter-input"
    />
  </div>
  
  <div class="filter-section">
    <h3>Date Range</h3>
    <div class="date-inputs">
      <div class="date-group">
        <label for="fromDate">From</label>
        <input
          type="date"
          id="fromDate"
          bind:value={fromDate}
          on:change={handleFromDateChange}
          class="filter-input"
        />
      </div>
      <div class="date-group">
        <label for="toDate">To</label>
        <input
          type="date"
          id="toDate"
          bind:value={toDate}
          on:change={handleToDateChange}
          class="filter-input"
        />
      </div>
    </div>
  </div>
  
  <div class="filter-section">
    <h3>Tags</h3>
    {#if loadingTags}
      <p class="loading-text">Loading tags...</p>
    {:else if errorTags}
      <p class="empty-text">No tags available yet</p>
    {:else if allTags.length === 0}
      <p class="empty-text">No tags created yet</p>
    {:else}
      <div class="tags-list">
        {#each allTags as tag}
          <button
            class="tag-button {selectedTags.includes(tag.name) ? 'selected' : ''}"
            on:click={() => toggleTag(tag.name)}
          >
            {tag.name}
          </button>
        {/each}
      </div>
    {/if}
  </div>
  
  <div class="filter-section">
    <h3>Speakers</h3>
    {#if loadingSpeakers}
      <p class="loading-text">Loading speakers...</p>
    {:else if errorSpeakers}
      <p class="empty-text">No speakers available yet</p>
    {:else if allSpeakers.length === 0}
      <p class="empty-text">No speakers detected yet</p>
    {:else}
      <div class="speakers-list">
        {#each allSpeakers as speaker}
          <button
            class="speaker-button {selectedSpeaker === speaker.name ? 'selected' : ''}"
            on:click={() => selectSpeaker(speaker.name)}
          >
            {speaker.name}
          </button>
        {/each}
      </div>
    {/if}
  </div>
  
  <div class="filter-actions">
    <button class="apply-button" on:click={applyFilters}>Apply Filters</button>
  </div>
</div>

<style>
  .filter-sidebar {
    background-color: var(--surface-color);
    border-radius: 8px;
    padding: 1.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }
  
  .filter-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  
  .filter-header h2 {
    font-size: 1.2rem;
    margin: 0;
  }
  
  .reset-button {
    background: transparent;
    border: none;
    color: var(--primary-color);
    font-size: 0.9rem;
    cursor: pointer;
  }
  
  .filter-section {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .filter-section h3 {
    font-size: 1rem;
    margin: 0;
  }
  
  .filter-input {
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 0.9rem;
  }
  
  .date-inputs {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .date-group {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .date-group label {
    font-size: 0.8rem;
    color: var(--text-light);
  }
  
  .tags-list,
  .speakers-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  
  .tag-button,
  .speaker-button {
    background-color: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    color: var(--text-color);
    font-size: 0.8rem;
    padding: 0.25rem 0.5rem;
    cursor: pointer;
    transition: background-color 0.2s, color 0.2s, border-color 0.2s;
  }
  
  .tag-button.selected,
  .speaker-button.selected {
    background-color: var(--primary-color);
    color: white;
    border-color: var(--primary-color);
  }
  
  .loading-text,
  .empty-text {
    font-size: 0.9rem;
    color: var(--text-light);
    margin: 0;
  }
  
  .filter-actions {
    margin-top: 1rem;
  }
  
  .apply-button {
    width: 100%;
    background-color: var(--primary-color);
    color: white;
    border: none;
    border-radius: 4px;
    padding: 0.75rem 1rem;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.2s;
  }
  
  .apply-button:hover {
    background-color: var(--primary-dark);
  }
</style>
