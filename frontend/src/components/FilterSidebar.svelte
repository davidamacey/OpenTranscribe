<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import { slide } from 'svelte/transition';
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
  export let selectedTags = [];
  
  /** @type {string|null} */
  export let selectedSpeaker = null;
  
  /** @type {DateRange} */
  export let dateRange = { from: null, to: null };

  // Duration range for filtering
  /** @type {{ min: number|null, max: number|null }} */
  export let durationRange = {
    min: null,
    max: null
  };
  
  // Server-provided min/max values for duration
  /** @type {{ min: number, max: number }} */
  let durationRangeMinMax = {
    min: 0,
    max: 0
  };

  /** @type {string[]} */
  export let selectedFormats = [];

  /** @type {string[]} */
  export let selectedCodecs = [];

  // Resolution range for filtering
  /** @type {{ minWidth: number|null, maxWidth: number|null, minHeight: number|null, maxHeight: number|null }} */
  export let resolutionRange = {
    minWidth: null,
    maxWidth: null,
    minHeight: null,
    maxHeight: null
  };
  
  // Server-provided min/max values for resolution
  /** @type {{ width: { min: number, max: number }, height: { min: number, max: number } }} */
  let resolutionRangeMinMax = {
    width: { min: 0, max: 0 },
    height: { min: 0, max: 0 }
  };

  /** @type {boolean} */
  export let showAdvancedFilters = false;
  
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
  
  /** @type {string[]} */
  let availableFormats = [];
  /** @type {string[]} */
  let availableCodecs = [];
  /** @type {boolean} */
  let loadingFormats = false;
  /** @type {boolean} */
  let loadingCodecs = false;
  
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
   * @param {Event & { currentTarget: HTMLInputElement }} event - The input event
   */
  function handleFromDateChange(event) {
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
  function handleToDateChange(event) {
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
  
  // Fetch media formats and codecs
  async function fetchMediaMetadata() {
    try {
      loadingFormats = true;
      loadingCodecs = true;
      
      const response = await axiosInstance.get('/files/metadata-filters');
      const metadataFilters = response.data;
      
      // Update available formats and codecs
      availableFormats = metadataFilters.formats || [];
      availableCodecs = metadataFilters.codecs || [];
      
      // Update duration range with min/max values from server
      if (metadataFilters.duration) {
        durationRangeMinMax = {
          min: metadataFilters.duration.min || 0,
          max: metadataFilters.duration.max || 0
        };
      }
      
      // Update resolution range with min/max values from server
      if (metadataFilters.resolution) {
        resolutionRangeMinMax = {
          width: {
            min: metadataFilters.resolution.width?.min || 0,
            max: metadataFilters.resolution.width?.max || 0
          },
          height: {
            min: metadataFilters.resolution.height?.min || 0,
            max: metadataFilters.resolution.height?.max || 0
          }
        };
      }
      
      loadingFormats = false;
      loadingCodecs = false;
    } catch (error) {
      console.error('Error fetching media metadata:', error);
      loadingFormats = false;
      loadingCodecs = false;
    }
  }
  
  /**
   * Toggle a media format in the filter
   * @param {string} format - The format to toggle
   */
  function toggleFormat(format) {
    const index = selectedFormats.indexOf(format);
    
    if (index === -1) {
      selectedFormats = [...selectedFormats, format];
    } else {
      selectedFormats = selectedFormats.filter(f => f !== format);
    }
  }
  
  /**
   * Toggle a codec in the filter
   * @param {string} codec - The codec to toggle
   */
  function toggleCodec(codec) {
    const index = selectedCodecs.indexOf(codec);
    
    if (index === -1) {
      selectedCodecs = [...selectedCodecs, codec];
    } else {
      selectedCodecs = selectedCodecs.filter(c => c !== codec);
    }
  }
  
  /**
   * Handle min duration input change
   * @param {Event & { currentTarget: HTMLInputElement }} event - The input event
   */
  function handleMinDurationChange(event) {
    const value = event.currentTarget?.value;
    durationRange.min = value ? parseFloat(value) : null;
  }
  
  /**
   * Handle max duration input change
   * @param {Event & { currentTarget: HTMLInputElement }} event - The input event
   */
  function handleMaxDurationChange(event) {
    const value = event.currentTarget?.value;
    durationRange.max = value ? parseFloat(value) : null;
  }
  
  /**
   * Handle resolution input changes
   * @param {'minWidth'|'maxWidth'|'minHeight'|'maxHeight'} field - The field to update
   * @param {Event & { currentTarget: HTMLInputElement }} event - The input event
   */
  function handleResolutionChange(field, event) {
    const value = event.currentTarget?.value;
    resolutionRange[field] = value ? parseInt(value, 10) : null;
  }
  
  // Toggle advanced filters visibility
  function toggleAdvancedFilters() {
    showAdvancedFilters = !showAdvancedFilters;
  }
  
  // Apply filters
  function applyFilters() {
    dispatch('filter', {
      search: searchQuery,
      tags: selectedTags,
      speaker: selectedSpeaker,
      dates: dateRange,
      durationRange,
      formats: selectedFormats,
      codecs: selectedCodecs,
      resolution: resolutionRange
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
          on:input={handleFromDateChange}
          class="filter-input"
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
  
  <!-- Advanced Filters Toggle -->
  <div class="filter-section">
    <button class="advanced-toggle" on:click={toggleAdvancedFilters}>
      {showAdvancedFilters ? 'Hide Advanced Filters' : 'Show Advanced Filters'}
      <span class="toggle-icon">{showAdvancedFilters ? '▲' : '▼'}</span>
    </button>
  </div>
  
  <!-- Advanced Filters Section -->
  {#if showAdvancedFilters}
    <div class="advanced-filters" transition:slide={{ duration: 300 }}>
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
              on:input={handleMinDurationChange}
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
              on:input={handleMaxDurationChange}
            />
          </div>
        </div>
      </div>

      <!-- Media Format -->
      <div class="filter-section">
        <h3>Media Format</h3>
        {#if loadingFormats}
          <p class="loading-text">Loading formats...</p>
        {:else if availableFormats.length === 0}
          <p class="empty-text">No formats available</p>
        {:else}
          <div class="format-list">
            {#each availableFormats as format}
              <button
                class="format-button {selectedFormats.includes(format) ? 'selected' : ''}"
                on:click={() => toggleFormat(format)}
              >
                {format}
              </button>
            {/each}
          </div>
        {/if}
      </div>

      <!-- Codec -->
      <div class="filter-section">
        <h3>Codec</h3>
        {#if loadingCodecs}
          <p class="loading-text">Loading codecs...</p>
        {:else if availableCodecs.length === 0}
          <p class="empty-text">No codecs available</p>
        {:else}
          <div class="codec-list">
            {#each availableCodecs as codec}
              <button
                class="codec-button {selectedCodecs.includes(codec) ? 'selected' : ''}"
                on:click={() => toggleCodec(codec)}
              >
                {codec}
              </button>
            {/each}
          </div>
        {/if}
      </div>

      <!-- Resolution -->
      <div class="filter-section">
        <h3>Resolution</h3>
        <div class="resolution-filters">
          <div class="resolution-group">
            <h4>Width (pixels)</h4>
            <div class="range-inputs">
              <div class="range-group">
                <label for="minWidth">Min</label>
                <input 
                  type="number" 
                  id="minWidth" 
                  min="0" 
                  placeholder="Min width" 
                  class="filter-input" 
                  on:input={(e) => handleResolutionChange('minWidth', e)}
                />
              </div>
              <div class="range-group">
                <label for="maxWidth">Max</label>
                <input 
                  type="number" 
                  id="maxWidth" 
                  min="0" 
                  placeholder="Max width" 
                  class="filter-input" 
                  on:input={(e) => handleResolutionChange('maxWidth', e)}
                />
              </div>
            </div>
          </div>
          
          <div class="resolution-group">
            <h4>Height (pixels)</h4>
            <div class="range-inputs">
              <div class="range-group">
                <label for="minHeight">Min</label>
                <input 
                  type="number" 
                  id="minHeight" 
                  min="0" 
                  placeholder="Min height" 
                  class="filter-input" 
                  on:input={(e) => handleResolutionChange('minHeight', e)}
                />
              </div>
              <div class="range-group">
                <label for="maxHeight">Max</label>
                <input 
                  type="number" 
                  id="maxHeight" 
                  min="0" 
                  placeholder="Max height" 
                  class="filter-input" 
                  on:input={(e) => handleResolutionChange('maxHeight', e)}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  {/if}
  
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
  /* Advanced filters styles */
  .advanced-toggle {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background-color: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    color: var(--text-color);
    font-size: 0.9rem;
    font-weight: 500;
    padding: 0.75rem 1rem;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  
  .advanced-toggle:hover {
    background-color: var(--hover-color);
    border-color: var(--primary-color);
  }
  
  .toggle-icon {
    font-size: 0.8rem;
    color: var(--primary-color);
  }
  
  .advanced-filters {
    background-color: var(--surface-color);
    border-radius: 8px;
    padding: 1rem;
    margin-top: 0.5rem;
    border: 1px solid var(--border-color);
    box-shadow: var(--shadow-sm);
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
  
  .range-group input[type="number"],
  .resolution-group input[type="number"] {
    padding: 0.5rem;
    border-radius: 4px;
    border: 1px solid var(--border-color);
    background-color: var(--input-background, var(--surface-color));
    color: var(--text-color);
    font-size: 0.9rem;
    transition: border-color 0.2s, box-shadow 0.2s;
  }
  
  .range-group input[type="number"]:focus,
  .resolution-group input[type="number"]:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px var(--primary-color-light, rgba(59, 130, 246, 0.2));
  }
  
  .range-group label,
  .resolution-group label {
    font-size: 0.85rem;
    color: var(--text-color-light, var(--text-color));
    margin-bottom: 0.25rem;
  }
  
  .resolution-filters {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  
  .resolution-group h4 {
    font-size: 0.9rem;
    margin: 0 0 0.5rem 0;
    color: var(--text-color);
  }
  
  .format-list,
  .codec-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }
  
  .format-button,
  .codec-button {
    background-color: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    color: var(--text-color);
    font-size: 0.8rem;
    padding: 0.25rem 0.5rem;
    cursor: pointer;
    transition: background-color 0.2s, color 0.2s, border-color 0.2s;
  }
  
  .format-button:hover,
  .codec-button:hover {
    background-color: var(--hover-color);
    border-color: var(--primary-color-light);
  }
  
  .format-button.selected,
  .codec-button.selected {
    background-color: var(--primary-color);
    color: var(--on-primary-color, white);
    border-color: var(--primary-color);
  }
</style>
