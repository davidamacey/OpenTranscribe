<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { slide } from 'svelte/transition';
  import axiosInstance from '../lib/axios';
  import CollectionsFilter from './CollectionsFilter.svelte';
  
  // Type definitions for props and state
  /**
   * @typedef {Object} Tag
   * @property {number} id - Tag ID
   * @property {string} name - Tag name
   */
  
  /**
   * @typedef {Object} Speaker
   * @property {number} id - Speaker ID
   * @property {string} name - Speaker name (original name like SPEAKER_01)
   * @property {string|null} display_name - Display name set by user
   */
  
  /**
   * @typedef {Object} DateRange
   * @property {Date|null} from - Start date
   * @property {Date|null} to - End date
   */

  /**
   * @typedef {Object} DurationRange
   * @property {number|null} min - Minimum duration in seconds
   * @property {number|null} max - Maximum duration in seconds
   */

  /**
   * @typedef {Object} ResolutionRange
   * @property {number|null} minWidth - Minimum width in pixels
   * @property {number|null} maxWidth - Maximum width in pixels
   * @property {number|null} minHeight - Minimum height in pixels
   * @property {number|null} maxHeight - Maximum height in pixels
   */
  
  // Props
  /** @type {string} */
  export let searchQuery = '';
  
  /** @type {string[]} */
  export let selectedTags: string[] = [];
  
  /** @type {string[]} */
  export let selectedSpeakers: string[] = [];
  
  /** @type {DateRange} */
  export let dateRange: { from: Date | null, to: Date | null } = { from: null, to: null };
  
  /** @type {string|null} */
  export let selectedCollectionId: string | null = null;

  // Duration range for filtering
  /** @type {{ min: number|null, max: number|null }} */
  export let durationRange: { min: number | null, max: number | null } = {
    min: null,
    max: null
  };
  
  // Server-provided min/max values for duration
  /** @type {{ min: number, max: number }} */
  let durationRangeMinMax = {
    min: 0,
    max: 0
  };

  // File size range for filtering (in MB)
  /** @type {{ min: number|null, max: number|null }} */
  export let fileSizeRange: { min: number | null, max: number | null } = {
    min: null,
    max: null
  };

  /** @type {string[]} */
  export let selectedFileTypes: string[] = []; // ['audio', 'video']

  /** @type {string[]} */
  export let selectedStatuses: string[] = []; // ['pending', 'processing', 'completed', 'error']

  /** @type {string} */
  export let transcriptSearch = '';

  /** @type {boolean} */
  export let showAdvancedFilters = false;
  
  // State
  /** @type {Tag[]} */
  let allTags: any[] = [];
  
  // Component refs
  let collectionsFilterRef: any;
  
  /** @type {Speaker[]} */
  let allSpeakers: any[] = [];
  
  /** @type {boolean} */
  let loadingTags = false;
  
  /** @type {boolean} */
  let loadingSpeakers = false;
  
  /** @type {string|null} */
  let errorTags: string | null = null;
  
  /** @type {string|null} */
  let errorSpeakers: string | null = null;
  
  // Available options for filters
  /** @type {string[]} */
  let availableFileTypes = ['audio', 'video'];
  /** @type {string[]} */
  let availableStatuses = ['pending', 'processing', 'completed', 'error'];
  
  // Event dispatcher
  const dispatch = createEventDispatcher();
  
  // Date input values
  /** @type {string} */
  let fromDate = '';
  
  /** @type {string} */
  let toDate = '';
  
  // Duration input values  
  /** @type {string} */
  let minDurationInput = '';
  
  /** @type {string} */
  let maxDurationInput = '';
  
  // File size input values
  /** @type {string} */
  let minFileSizeInput = '';
  
  /** @type {string} */
  let maxFileSizeInput = '';
  
  // Fetch all tags
  async function fetchTags() {
    loadingTags = true;
    errorTags = null;
    
    try {
      const response = await axiosInstance.get('/tags/');
      allTags = response.data;
    } catch (err) {
      console.error('[FilterSidebar] Error fetching tags:', err);
      // Don't set error message, just set empty array
      allTags = [];
    } finally {
      loadingTags = false;
    }
  }
  
  // Fetch all speakers for filtering (only those with display names)
  async function fetchSpeakers() {
    loadingSpeakers = true;
    errorSpeakers = null;
    
    try {
      const response = await axiosInstance.get('/speakers/?for_filter=true');
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
  function toggleTag(tag: string) {
    const index = selectedTags.indexOf(tag);
    
    if (index === -1) {
      selectedTags = [...selectedTags, tag];
    } else {
      selectedTags = selectedTags.filter(t => t !== tag);
    }
  }
  
  /**
   * Handle speaker selection (multi-select like tags)
   * @param {string} speaker - The speaker to toggle
   */
  function toggleSpeaker(speaker: string) {
    const index = selectedSpeakers.indexOf(speaker);
    
    if (index === -1) {
      selectedSpeakers = [...selectedSpeakers, speaker];
    } else {
      selectedSpeakers = selectedSpeakers.filter(s => s !== speaker);
    }
  }
  
  /**
   * Handle from date input changes
   * @param {Event & { currentTarget: HTMLInputElement }} event - The input event
   */
  function handleFromDateChange(event: Event & { currentTarget: HTMLInputElement }) {
    const value = event.currentTarget?.value;
    if (value) {
      const date = new Date(value);
      if (!isNaN(date.getTime())) { // Check if the date is valid
        dateRange = { ...dateRange, from: date };
      }
    } else {
      dateRange = { ...dateRange, from: null };
    }
  }
  
  /**
   * Handle to date input changes
   * @param {Event & { currentTarget: HTMLInputElement }} event - The input event
   */
  function handleToDateChange(event: Event & { currentTarget: HTMLInputElement }) {
    const value = event.currentTarget?.value;
    if (value) {
      const date = new Date(value);
      if (!isNaN(date.getTime())) { // Check if the date is valid
        dateRange = { ...dateRange, to: date };
      }
    } else {
      dateRange = { ...dateRange, to: null };
    }
  }
  
  // Fetch media metadata - currently not used, reserved for future enhancement
  async function fetchMediaMetadata() {
    try {
      const response = await axiosInstance.get('/files/metadata-filters');
      const metadataFilters = response.data;
      
      // Update duration range with min/max values from server
      if (metadataFilters.duration) {
        durationRangeMinMax = {
          min: metadataFilters.duration.min || 0,
          max: metadataFilters.duration.max || 0
        };
      }
    } catch (error) {
      console.error('Error fetching media metadata:', error);
    }
  }
  
  /**
   * Toggle a file type in the filter
   * @param {string} fileType - The file type to toggle
   */
  function toggleFileType(fileType: string) {
    const index = selectedFileTypes.indexOf(fileType);
    
    if (index === -1) {
      selectedFileTypes = [...selectedFileTypes, fileType];
    } else {
      selectedFileTypes = selectedFileTypes.filter(ft => ft !== fileType);
    }
  }
  
  /**
   * Toggle a status in the filter
   * @param {string} status - The status to toggle
   */
  function toggleStatus(status: string) {
    const index = selectedStatuses.indexOf(status);
    
    if (index === -1) {
      selectedStatuses = [...selectedStatuses, status];
    } else {
      selectedStatuses = selectedStatuses.filter(s => s !== status);
    }
  }
  
  /**
   * Handle min duration input change
   * @param {Event & { currentTarget: HTMLInputElement }} event - The input event
   */
  function handleMinDurationChange(event: Event & { currentTarget: HTMLInputElement }) {
    const value = event.currentTarget?.value;
    durationRange.min = value ? parseFloat(value) : null;
  }
  
  /**
   * Handle max duration input change
   * @param {Event & { currentTarget: HTMLInputElement }} event - The input event
   */
  function handleMaxDurationChange(event: Event & { currentTarget: HTMLInputElement }) {
    const value = event.currentTarget?.value;
    durationRange.max = value ? parseFloat(value) : null;
  }

  /**
   * Handle file size range input changes
   * @param {'min'|'max'} field - The field to update
   * @param {Event & { currentTarget: HTMLInputElement }} event - The input event
   */
  function handleFileSizeChange(field: 'min' | 'max', event: Event & { currentTarget: HTMLInputElement }) {
    const value = event.currentTarget?.value;
    fileSizeRange[field] = value ? parseFloat(value) : null;
  }
  
  /**
   * Handle resolution input changes - currently not used, reserved for future enhancement
   * @param {'minWidth'|'maxWidth'|'minHeight'|'maxHeight'} field - The field to update
   * @param {Event & { currentTarget: HTMLInputElement }} event - The input event
   */
  // function handleResolutionChange(field, event) {
  //   const value = event.currentTarget?.value;
  //   resolutionRange[field] = value ? parseInt(value, 10) : null;
  // }
  
  // Toggle advanced filters visibility
  function toggleAdvancedFilters() {
    showAdvancedFilters = !showAdvancedFilters;
  }
  
  // Apply filters
  function applyFilters() {
    dispatch('filter', {
      search: searchQuery,
      tags: selectedTags,
      speaker: selectedSpeakers,
      collectionId: selectedCollectionId,
      dates: dateRange,
      durationRange,
      fileSizeRange,
      fileTypes: selectedFileTypes,
      statuses: selectedStatuses,
      transcriptSearch
    });
  }
  
  // Reset filters
  function resetFilters() {
    searchQuery = '';
    selectedTags = [];
    selectedSpeakers = [];
    selectedCollectionId = null;
    dateRange = { from: null, to: null };
    fromDate = '';
    toDate = '';
    durationRange = { min: null, max: null };
    fileSizeRange = { min: null, max: null };
    selectedFileTypes = [];
    selectedStatuses = [];
    transcriptSearch = '';
    showAdvancedFilters = false; // Collapse advanced filters on reset
    
    // Clear input field values
    minDurationInput = '';
    maxDurationInput = '';
    minFileSizeInput = '';
    maxFileSizeInput = '';
    
    dispatch('reset');
  }
  
  // Public method to refresh collections
  export function refreshCollections() {
    if (collectionsFilterRef && collectionsFilterRef.fetchCollections) {
      collectionsFilterRef.fetchCollections();
    }
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
    <button 
      class="reset-button" 
      on:click={resetFilters}
      title="Clear all filters and show all files"
    >Reset</button>
  </div>
  
  <div class="filter-section">
    <h3>Search Files</h3>
    <input
      type="text"
      bind:value={searchQuery}
      placeholder="Search filenames and titles..."
      class="filter-input"
      title="Search by file name or title - does not search transcript content"
    />
    <small class="input-help">Searches file names and titles only</small>
  </div>
  
  <div class="filter-section">
    <h3>Collection</h3>
    <CollectionsFilter bind:selectedCollectionId={selectedCollectionId} bind:this={collectionsFilterRef} />
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
          on:input={handleFromDateChange}
          class="filter-input"
          title="Filter files uploaded on or after this date"
        />
      </div>
      <div class="date-group">
        <label for="toDate">To</label>
        <input
          type="date"
          id="toDate"
          bind:value={toDate}
          on:input={handleToDateChange}
          class="filter-input"
          title="Filter files uploaded on or before this date"
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
            title="Filter files tagged with '{tag.name}'. Click to toggle selection."
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
            class="speaker-button {selectedSpeakers.includes(speaker.display_name || speaker.name) ? 'selected' : ''}"
            on:click={() => toggleSpeaker(speaker.display_name || speaker.name)}
            title="Filter files containing speaker '{speaker.display_name || speaker.name}'. Click to toggle selection."
          >
            {speaker.display_name || speaker.name}
          </button>
        {/each}
      </div>
    {/if}
  </div>
  
  <!-- Advanced Filters Toggle -->
  <div class="advanced-filters-divider">
    <hr class="divider-line" />
    <button 
      class="advanced-toggle-compact" 
      on:click={toggleAdvancedFilters}
      title="{showAdvancedFilters ? 'Hide' : 'Show'} advanced filtering options including transcript search, duration, file size, type, and status filters"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="toggle-icon {showAdvancedFilters ? 'rotated' : ''}">
        <polyline points="6 9 12 15 18 9"></polyline>
      </svg>
      <span>Advanced Filters</span>
    </button>
    <hr class="divider-line" />
  </div>
  
  <!-- Advanced Filters Section -->
  {#if showAdvancedFilters}
    <div class="advanced-filters-content" transition:slide={{ duration: 300 }}>
      <!-- Transcript Content Search -->
      <div class="filter-section">
        <h3>Search Transcript Content</h3>
        <input
          type="text"
          placeholder="Search within spoken words..."
          bind:value={transcriptSearch}
          class="filter-input"
          title="Search for specific words or phrases within the transcript content of your files"
        />
        <small class="input-help">Searches within the actual transcript text content</small>
      </div>

      <!-- Duration Range -->
      <div class="filter-section">
        <h3>Duration</h3>
        <div class="range-inputs">
          <div class="range-group">
            <label for="minDuration">Min (seconds)</label>
            <input 
              type="number" 
              id="minDuration" 
              min="0" 
              placeholder="Minimum" 
              class="filter-input" 
              bind:value={minDurationInput}
              on:input={handleMinDurationChange}
              title="Filter files with duration greater than or equal to this value (in seconds)"
            />
          </div>
          <div class="range-group">
            <label for="maxDuration">Max (seconds)</label>
            <input 
              type="number" 
              id="maxDuration" 
              min="0" 
              placeholder="Maximum" 
              class="filter-input" 
              bind:value={maxDurationInput}
              on:input={handleMaxDurationChange}
              title="Filter files with duration less than or equal to this value (in seconds)"
            />
          </div>
        </div>
      </div>

      <!-- File Size Range -->
      <div class="filter-section">
        <h3>File Size (MB)</h3>
        <div class="range-inputs">
          <div class="range-group">
            <label for="minFileSize">Min (MB)</label>
            <input 
              type="number" 
              id="minFileSize" 
              min="0" 
              placeholder="Minimum" 
              class="filter-input" 
              bind:value={minFileSizeInput}
              on:input={(e) => handleFileSizeChange('min', e)}
              title="Filter files with size greater than or equal to this value (in megabytes)"
            />
          </div>
          <div class="range-group">
            <label for="maxFileSize">Max (MB)</label>
            <input 
              type="number" 
              id="maxFileSize" 
              min="0" 
              placeholder="Maximum" 
              class="filter-input" 
              bind:value={maxFileSizeInput}
              on:input={(e) => handleFileSizeChange('max', e)}
              title="Filter files with size less than or equal to this value (in megabytes)"
            />
          </div>
        </div>
      </div>

      <!-- File Type -->
      <div class="filter-section">
        <h3>File Type</h3>
        <div class="file-type-list">
          {#each availableFileTypes as fileType}
            <button
              class="file-type-button {selectedFileTypes.includes(fileType) ? 'selected' : ''}"
              on:click={() => toggleFileType(fileType)}
              title="Filter files by type: {fileType} files only. Click to toggle selection."
            >
              {fileType.charAt(0).toUpperCase() + fileType.slice(1)}
            </button>
          {/each}
        </div>
      </div>

      <!-- Processing Status -->
      <div class="filter-section">
        <h3>Processing Status</h3>
        <div class="status-list">
          {#each availableStatuses as status}
            <button
              class="status-button {selectedStatuses.includes(status) ? 'selected' : ''}"
              on:click={() => toggleStatus(status)}
              title="Filter files by processing status: {status} files only. Click to toggle selection."
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </button>
          {/each}
        </div>
      </div>
    </div>
  {/if}
  
  <div class="filter-actions">
    <button 
      class="apply-button" 
      on:click={applyFilters}
      title="Apply all selected filters to update the file list"
    >Apply Filters</button>
  </div>
</div>

<style>
  .filter-sidebar {
    background-color: var(--surface-color);
    border-radius: 8px;
    padding: 0.75rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    display: flex;
    flex-direction: column;
    gap: 1rem;
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
    gap: 0.5rem;
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

  /* File Type and Status button styles */
  .file-type-list,
  .status-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }

  .file-type-button,
  .status-button {
    background-color: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-color);
    font-size: 0.85rem;
    padding: 0.4rem 0.8rem;
    cursor: pointer;
    transition: all 0.2s ease;
    white-space: nowrap;
  }

  .file-type-button:hover,
  .status-button:hover {
    background-color: var(--hover-color);
    border-color: var(--primary-color-light);
  }

  .file-type-button.selected,
  .status-button.selected {
    background-color: var(--primary-color);
    color: white;
    border-color: var(--primary-color);
  }

  /* Input help text */
  .input-help {
    font-size: 0.75rem;
    color: var(--text-light, rgba(255, 255, 255, 0.6));
    margin-top: 0.25rem;
    display: block;
    font-style: italic;
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
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    background-color: #3b82f6;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 0.6rem 1.2rem;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }
  
  .apply-button:hover:not(:disabled) {
    background-color: #2563eb;
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
    text-decoration: none;
  }
  
  .apply-button:active:not(:disabled) {
    transform: translateY(0);
  }
  /* Advanced filters divider and toggle styles */
  .advanced-filters-divider {
    display: flex;
    align-items: center;
    margin: 0.75rem 0 0.5rem 0;
    position: relative;
  }
  
  .divider-line {
    flex: 1;
    height: 1px;
    border: none;
    background-color: var(--border-color, #e5e7eb);
    margin: 0;
  }
  
  .advanced-toggle-compact {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background-color: var(--surface-color);
    border: none;
    color: var(--text-color);
    font-size: 0.85rem;
    font-weight: 500;
    padding: 0.5rem 1rem;
    cursor: pointer;
    transition: all 0.2s ease;
    border-radius: 20px;
    margin: 0 1rem;
    white-space: nowrap;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }
  
  .advanced-toggle-compact:hover {
    background-color: var(--hover-color, rgba(0, 0, 0, 0.05));
    color: var(--primary-color);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
  }
  
  .toggle-icon {
    transition: transform 0.2s ease;
    color: var(--primary-color);
  }
  
  .toggle-icon.rotated {
    transform: rotate(180deg);
  }
  
  .advanced-filters-content {
    /* Seamless integration with subtle visual distinction */
    padding: 0.5rem 0.25rem;
    margin: 0;
    background: linear-gradient(135deg, transparent 0%, rgba(59, 130, 246, 0.02) 100%);
    border: none;
    box-shadow: none;
    border-radius: 8px;
    position: relative;
  }
  
  
  .advanced-filters-content .filter-section {
    margin-bottom: 1rem;
  }
  
  .advanced-filters-content .filter-section:last-child {
    margin-bottom: 0;
  }
  
  .range-inputs {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .range-group {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .range-group input[type="number"] {
    padding: 0.5rem;
    border-radius: 4px;
    border: 1px solid var(--border-color);
    background-color: var(--input-background, var(--surface-color));
    color: var(--text-color);
    font-size: 0.9rem;
    transition: border-color 0.2s, box-shadow 0.2s;
  }
  
  .range-group input[type="number"]:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px var(--primary-color-light, rgba(59, 130, 246, 0.2));
  }
  
  .range-group label {
    font-size: 0.85rem;
    color: var(--text-color-light, var(--text-color));
    margin-bottom: 0.25rem;
  }

  /* Tag and Speaker button styles */
  .tags-list,
  .speakers-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }

  .tag-button,
  .speaker-button {
    background-color: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-color);
    font-size: 0.85rem;
    padding: 0.4rem 0.8rem;
    cursor: pointer;
    transition: all 0.2s ease;
    white-space: nowrap;
  }

  .tag-button:hover,
  .speaker-button:hover {
    background-color: var(--hover-color);
    border-color: var(--primary-color-light);
  }

  .tag-button.selected,
  .speaker-button.selected {
    background-color: var(--primary-color);
    color: white;
    border-color: var(--primary-color);
  }

  /* File Type and Status button styles */
  .file-type-list,
  .status-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }

  .file-type-button,
  .status-button {
    background-color: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-color);
    font-size: 0.85rem;
    padding: 0.4rem 0.8rem;
    cursor: pointer;
    transition: all 0.2s ease;
    white-space: nowrap;
  }

  .file-type-button:hover,
  .status-button:hover {
    background-color: var(--hover-color);
    border-color: var(--primary-color-light);
  }

  .file-type-button.selected,
  .status-button.selected {
    background-color: var(--primary-color);
    color: white;
    border-color: var(--primary-color);
  }

  /* Input help text */
  .input-help {
    font-size: 0.75rem;
    color: var(--text-light, rgba(255, 255, 255, 0.6));
    margin-top: 0.25rem;
    display: block;
    font-style: italic;
  }
  
  /* Responsive adjustments for advanced filters */
  @media (max-width: 768px) {
    .advanced-filters-divider {
      margin: 1rem 0 0.75rem 0;
    }
    
    .advanced-toggle-compact {
      padding: 0.4rem 0.8rem;
      font-size: 0.8rem;
      margin: 0 0.5rem;
    }
    
    .advanced-filters-content {
      padding: 0.75rem 0.25rem;
    }
    
    .advanced-filters-content .filter-section {
      margin-bottom: 1rem;
    }
  }
  
  /* Reduced motion support */
  @media (prefers-reduced-motion: reduce) {
    .toggle-icon {
      transition: none;
    }
    
    .advanced-toggle-compact {
      transition: none;
    }
  }
</style>
