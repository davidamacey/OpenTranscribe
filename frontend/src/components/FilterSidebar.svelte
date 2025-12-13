<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { slide } from 'svelte/transition';
  import axiosInstance from '../lib/axios';
  import CollectionsFilter from './CollectionsFilter.svelte';
  import SearchableMultiSelect from './SearchableMultiSelect.svelte';
  import { t } from '$stores/locale';
  import { translateSpeakerLabel } from '$lib/i18n';

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
  let showAllTags = false;  // Toggle for showing all tags vs top 9
  let dropdownTags: any[] = [];  // All tags for multiselect dropdown

  // Reactive: Prepare dropdown tags with proper format
  $: dropdownTags = allTags.map(tag => ({
    id: tag.id,
    name: tag.name,
    count: tag.usage_count || 0
  }));

  // Reactive: Convert selected tag names to IDs for multiselect
  $: selectedTagIds = allTags
    .filter(tag => selectedTags.includes(tag.name))
    .map(tag => tag.id);

  // Component refs
  let collectionsFilterRef: any;

  /** @type {Speaker[]} */
  let allSpeakers: any[] = [];
  let dropdownSpeakers: any[] = [];  // All speakers for multiselect dropdown

  // Reactive: Prepare dropdown speakers with proper format
  $: dropdownSpeakers = allSpeakers.map(speaker => ({
    id: speaker.id,
    name: translateSpeakerLabel(speaker.display_name || speaker.name),
    count: speaker.media_count || 0
  }));

  // Reactive: Convert selected speaker names to IDs for multiselect
  $: selectedSpeakerIds = allSpeakers
    .filter(speaker => selectedSpeakers.includes(speaker.display_name || speaker.name))
    .map(speaker => speaker.id);

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
   * Handle tag selection from multiselect dropdown
   * @param {CustomEvent} event - Event with tag id
   */
  function handleTagSelect(event: CustomEvent) {
    const tagId = event.detail.id;
    const tag = allTags.find(t => t.id === tagId);
    if (tag && !selectedTags.includes(tag.name)) {
      selectedTags = [...selectedTags, tag.name];
    }
  }

  /**
   * Handle tag deselection from multiselect dropdown
   * @param {CustomEvent} event - Event with tag id
   */
  function handleTagDeselect(event: CustomEvent) {
    const tagId = event.detail.id;
    const tag = allTags.find(t => t.id === tagId);
    if (tag) {
      selectedTags = selectedTags.filter(t => t !== tag.name);
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
   * Handle speaker selection from multiselect dropdown
   * @param {CustomEvent} event - Event with speaker id
   */
  function handleSpeakerSelect(event: CustomEvent) {
    const speakerId = event.detail.id;
    const speaker = allSpeakers.find(s => s.id === speakerId);
    if (speaker) {
      const speakerName = speaker.display_name || speaker.name;
      if (!selectedSpeakers.includes(speakerName)) {
        selectedSpeakers = [...selectedSpeakers, speakerName];
      }
    }
  }

  /**
   * Handle speaker deselection from multiselect dropdown
   * @param {CustomEvent} event - Event with speaker id
   */
  function handleSpeakerDeselect(event: CustomEvent) {
    const speakerId = event.detail.id;
    const speaker = allSpeakers.find(s => s.id === speakerId);
    if (speaker) {
      const speakerName = speaker.display_name || speaker.name;
      selectedSpeakers = selectedSpeakers.filter(s => s !== speakerName);
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
    <h2>{$t('filter.title')}</h2>
    <div class="header-buttons">
      <button
        class="apply-button-compact"
        on:click={applyFilters}
        title={$t('filter.applyTooltip')}
      >{$t('filter.apply')}</button>
      <button
        class="reset-button"
        on:click={resetFilters}
        title={$t('filter.resetTooltip')}
      >{$t('filter.reset')}</button>
    </div>
  </div>

  <div class="filter-section">
    <h3>{$t('filter.searchFiles')}</h3>
    <input
      type="text"
      bind:value={searchQuery}
      placeholder={$t('filter.searchPlaceholder')}
      class="filter-input"
      title={$t('filter.searchTooltip')}
    />
    <small class="input-help">{$t('filter.searchHelp')}</small>
  </div>

  <div class="filter-section">
    <h3>{$t('filter.tags')}</h3>
    {#if loadingTags}
      <p class="loading-text">{$t('filter.loadingTags')}</p>
    {:else if errorTags}
      <p class="empty-text">{$t('filter.noTagsAvailable')}</p>
    {:else if allTags.length === 0}
      <p class="empty-text">{$t('filter.noTagsCreated')}</p>
    {:else}
      <div class="tags-list">
        {#each allTags.slice(0, 6) as tag}
          <button
            class="tag-button {selectedTags.includes(tag.name) ? 'selected' : ''}"
            on:click={() => toggleTag(tag.name)}
            title={$t('filter.tagTooltip', { tag: tag.name, count: tag.usage_count ? $t('filter.tagUsedInFiles', { count: tag.usage_count }) : '' })}
          >
            {tag.name}
            {#if tag.usage_count}
              <span class="tag-count">{tag.usage_count}</span>
            {/if}
          </button>
        {/each}
      </div>
      {#if allTags.length > 0}
        <div class="dropdown-section">
          <SearchableMultiSelect
            options={dropdownTags}
            selectedIds={selectedTagIds}
            placeholder={$t('filter.selectTagsPlaceholder')}
            maxHeight="300px"
            showCounts={true}
            on:select={handleTagSelect}
            on:deselect={handleTagDeselect}
          />
        </div>
      {/if}
    {/if}
  </div>

  <div class="filter-section">
    <h3>{$t('filter.collections')}</h3>
    <CollectionsFilter bind:selectedCollectionId={selectedCollectionId} bind:this={collectionsFilterRef} />
  </div>

  <div class="filter-section">
    <h3>{$t('filter.speakers')}</h3>
    {#if loadingSpeakers}
      <p class="loading-text">{$t('filter.loadingSpeakers')}</p>
    {:else if errorSpeakers}
      <p class="empty-text">{$t('filter.noSpeakersAvailable')}</p>
    {:else if allSpeakers.length === 0}
      <p class="empty-text">{$t('filter.noSpeakersDetected')}</p>
    {:else}
      <div class="speakers-list">
        {#each allSpeakers.slice(0, 4) as speaker}
          <button
            class="speaker-button {selectedSpeakers.includes(speaker.display_name || speaker.name) ? 'selected' : ''}"
            on:click={() => toggleSpeaker(speaker.display_name || speaker.name)}
            title={$t('filter.speakerTooltip', { speaker: translateSpeakerLabel(speaker.display_name || speaker.name), count: speaker.media_count ? $t('filter.speakerAppearsInFiles', { count: speaker.media_count }) : '' })}
          >
            {translateSpeakerLabel(speaker.display_name || speaker.name)}
            {#if speaker.media_count}
              <span class="speaker-count">{speaker.media_count}</span>
            {/if}
          </button>
        {/each}
      </div>
      {#if allSpeakers.length > 0}
        <div class="dropdown-section">
          <SearchableMultiSelect
            options={dropdownSpeakers}
            selectedIds={selectedSpeakerIds}
            placeholder={$t('filter.selectSpeakersPlaceholder')}
            maxHeight="300px"
            showCounts={true}
            on:select={handleSpeakerSelect}
            on:deselect={handleSpeakerDeselect}
          />
        </div>
      {/if}
    {/if}
  </div>

  <div class="filter-section">
    <h3>{$t('filter.dateRange')}</h3>
    <div class="date-inputs">
      <div class="date-group">
        <label for="fromDate">{$t('common.from')}</label>
        <input
          type="date"
          id="fromDate"
          bind:value={fromDate}
          on:input={handleFromDateChange}
          class="filter-input"
          title={$t('filter.fromDateTooltip')}
        />
      </div>
      <div class="date-group">
        <label for="toDate">{$t('common.to')}</label>
        <input
          type="date"
          id="toDate"
          bind:value={toDate}
          on:input={handleToDateChange}
          class="filter-input"
          title={$t('filter.toDateTooltip')}
        />
      </div>
    </div>
  </div>

  <!-- Advanced Filters Toggle -->
  <div class="advanced-filters-divider">
    <hr class="divider-line" />
    <button
      class="advanced-toggle-compact"
      on:click={toggleAdvancedFilters}
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="toggle-icon {showAdvancedFilters ? 'rotated' : ''}">
        <polyline points="6 9 12 15 18 9"></polyline>
      </svg>
      <span>{$t('filter.advancedFilters')}</span>
    </button>
    <hr class="divider-line" />
  </div>

  <!-- Advanced Filters Section -->
  {#if showAdvancedFilters}
    <div class="advanced-filters-content" transition:slide={{ duration: 300 }}>
      <!-- Transcript Content Search -->
      <div class="filter-section">
        <h3>{$t('filter.searchTranscript')}</h3>
        <input
          type="text"
          placeholder={$t('filter.searchTranscriptPlaceholder')}
          bind:value={transcriptSearch}
          class="filter-input"
          title={$t('filter.searchTranscriptTooltip')}
        />
        <small class="input-help">{$t('filter.searchTranscriptHelp')}</small>
      </div>

      <!-- File Type -->
      <div class="filter-section">
        <h3>{$t('filter.fileType')}</h3>
        <div class="file-type-list">
          {#each availableFileTypes as fileType}
            <button
              class="file-type-button {selectedFileTypes.includes(fileType) ? 'selected' : ''}"
              on:click={() => toggleFileType(fileType)}
              title={$t('filter.fileTypeTooltip', { type: fileType })}
            >
              {fileType === 'audio' ? $t('common.audio') : $t('common.video')}
            </button>
          {/each}
        </div>
      </div>

      <!-- Duration Range -->
      <div class="filter-section">
        <h3>{$t('filter.duration')}</h3>
        <div class="range-inputs">
          <div class="range-group">
            <label for="minDuration">{$t('filter.minSeconds')}</label>
            <input
              type="number"
              id="minDuration"
              min="0"
              placeholder={$t('common.minimum')}
              class="filter-input"
              bind:value={minDurationInput}
              on:input={handleMinDurationChange}
              title={$t('filter.minDurationTooltip')}
            />
          </div>
          <div class="range-group">
            <label for="maxDuration">{$t('filter.maxSeconds')}</label>
            <input
              type="number"
              id="maxDuration"
              min="0"
              placeholder={$t('common.maximum')}
              class="filter-input"
              bind:value={maxDurationInput}
              on:input={handleMaxDurationChange}
              title={$t('filter.maxDurationTooltip')}
            />
          </div>
        </div>
      </div>

      <!-- File Size Range -->
      <div class="filter-section">
        <h3>{$t('filter.fileSize')}</h3>
        <div class="range-inputs">
          <div class="range-group">
            <label for="minFileSize">{$t('filter.minMB')}</label>
            <input
              type="number"
              id="minFileSize"
              min="0"
              placeholder={$t('common.minimum')}
              class="filter-input"
              bind:value={minFileSizeInput}
              on:input={(e) => handleFileSizeChange('min', e)}
              title={$t('filter.minFileSizeTooltip')}
            />
          </div>
          <div class="range-group">
            <label for="maxFileSize">{$t('filter.maxMB')}</label>
            <input
              type="number"
              id="maxFileSize"
              min="0"
              placeholder={$t('common.maximum')}
              class="filter-input"
              bind:value={maxFileSizeInput}
              on:input={(e) => handleFileSizeChange('max', e)}
              title={$t('filter.maxFileSizeTooltip')}
            />
          </div>
        </div>
      </div>

      <!-- Processing Status -->
      <div class="filter-section">
        <h3>{$t('filter.processingStatus')}</h3>
        <div class="status-list">
          {#each availableStatuses as status}
            <button
              class="status-button {selectedStatuses.includes(status) ? 'selected' : ''}"
              on:click={() => toggleStatus(status)}
              title={$t('filter.statusTooltip', { status })}
            >
              {status === 'pending' ? $t('common.pending') : status === 'processing' ? $t('common.processing') : status === 'completed' ? $t('common.completed') : status === 'error' ? $t('common.error') : status.charAt(0).toUpperCase() + status.slice(1)}
            </button>
          {/each}
        </div>
      </div>
    </div>
  {/if}
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
    margin-bottom: 0.5rem;
  }

  .filter-header h2 {
    font-size: 1.2rem;
    margin: 0;
  }

  .header-buttons {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  .apply-button-compact {
    background-color: #3b82f6;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 0.4rem 0.8rem;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 1px 3px rgba(59, 130, 246, 0.2);
  }

  .apply-button-compact:hover:not(:disabled) {
    background-color: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.25);
  }

  .apply-button-compact:active:not(:disabled) {
    transform: translateY(0);
  }

  .reset-button {
    background-color: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-color);
    padding: 0.4rem 0.8rem;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .reset-button:hover:not(:disabled) {
    background-color: var(--hover-color);
    border-color: var(--primary-color);
  }

  .reset-button:active:not(:disabled) {
    transform: translateY(0);
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
    color: var(--text-secondary);
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
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
  }

  .tag-button.selected,
  .speaker-button.selected {
    background-color: var(--primary-color);
    color: white;
    border-color: var(--primary-color);
  }

  .tag-count,
  .speaker-count {
    background-color: rgba(0, 0, 0, 0.2);
    border-radius: 10px;
    padding: 0.1rem 0.4rem;
    font-size: 0.7rem;
    font-weight: 500;
    margin-left: 0.2rem;
  }

  .tag-button.selected .tag-count,
  .speaker-button.selected .speaker-count {
    background-color: rgba(255, 255, 255, 0.3);
  }

  .dropdown-section {
    margin-top: 0.75rem;
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
    color: var(--text-secondary);
    margin-top: 0.25rem;
    display: block;
    font-style: italic;
  }

  .loading-text,
  .empty-text {
    font-size: 0.9rem;
    color: var(--text-secondary);
    margin: 0;
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
    background-color: var(--border-color);
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
    background-color: var(--button-hover);
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
    color: var(--text-secondary);
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
    color: var(--text-secondary);
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
