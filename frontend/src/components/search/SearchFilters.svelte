<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { t } from '$stores/locale';

  export let availableFilters: any = { speakers: [], tags: [], date_range: {} };
  export let selectedSpeakers: string[] = [];
  export let selectedTags: string[] = [];
  export let dateFrom: string = '';
  export let dateTo: string = '';

  const dispatch = createEventDispatcher();

  function toggleSpeaker(speaker: string) {
    const updated = selectedSpeakers.includes(speaker)
      ? selectedSpeakers.filter((s) => s !== speaker)
      : [...selectedSpeakers, speaker];
    dispatch('change', { speakers: updated });
  }

  function toggleTag(tag: string) {
    const updated = selectedTags.includes(tag)
      ? selectedTags.filter((t) => t !== tag)
      : [...selectedTags, tag];
    dispatch('change', { tags: updated });
  }

  function handleDateChange() {
    dispatch('change', { dateFrom, dateTo });
  }

  function clearAll() {
    dispatch('change', { speakers: [], tags: [], dateFrom: '', dateTo: '' });
  }

  $: hasActiveFilters = selectedSpeakers.length > 0 || selectedTags.length > 0 || dateFrom || dateTo;
</script>

<div class="filters">
  <div class="filters-header">
    <h3>{$t('search.filters')}</h3>
    {#if hasActiveFilters}
      <button class="clear-btn" on:click={clearAll}>{$t('search.clearAll')}</button>
    {/if}
  </div>

  {#if availableFilters.speakers?.length > 0}
    <div class="filter-group">
      <h4>{$t('search.speakers')}</h4>
      <div class="filter-list">
        {#each availableFilters.speakers as speaker}
          <label class="filter-item">
            <input
              type="checkbox"
              checked={selectedSpeakers.includes(speaker.name || speaker)}
              on:change={() => toggleSpeaker(speaker.name || speaker)}
            />
            <span class="filter-label">{speaker.name || speaker}</span>
            {#if speaker.count}
              <span class="filter-count">({speaker.count})</span>
            {/if}
          </label>
        {/each}
      </div>
    </div>
  {/if}

  {#if availableFilters.tags?.length > 0}
    <div class="filter-group">
      <h4>{$t('search.tags')}</h4>
      <div class="filter-list">
        {#each availableFilters.tags as tag}
          <label class="filter-item">
            <input
              type="checkbox"
              checked={selectedTags.includes(tag.name || tag)}
              on:change={() => toggleTag(tag.name || tag)}
            />
            <span class="filter-label">{tag.name || tag}</span>
            {#if tag.count}
              <span class="filter-count">({tag.count})</span>
            {/if}
          </label>
        {/each}
      </div>
    </div>
  {/if}

  <div class="filter-group">
    <h4>{$t('search.date')}</h4>
    <div class="date-inputs">
      <input type="date" bind:value={dateFrom} on:change={handleDateChange} placeholder="From" />
      <input type="date" bind:value={dateTo} on:change={handleDateChange} placeholder="To" />
    </div>
  </div>
</div>

<style>
  .filters {
    background: var(--surface-color, #fff);
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 8px;
    padding: 1rem;
  }

  .filters-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }

  .filters-header h3 {
    margin: 0;
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--text-color, #111827);
  }

  .clear-btn {
    background: none;
    border: none;
    color: var(--primary-color, #4f46e5);
    font-size: 0.75rem;
    cursor: pointer;
    padding: 0.125rem 0.25rem;
  }

  .clear-btn:hover {
    text-decoration: underline;
  }

  .filter-group {
    margin-bottom: 1rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--border-color, #e5e7eb);
  }

  .filter-group:last-child {
    margin-bottom: 0;
    padding-bottom: 0;
    border-bottom: none;
  }

  .filter-group h4 {
    margin: 0 0 0.5rem;
    font-size: 0.8125rem;
    font-weight: 600;
    color: var(--text-secondary, #6b7280);
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .filter-list {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    max-height: 180px;
    overflow-y: auto;
  }

  .filter-item {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.25rem 0;
    cursor: pointer;
    font-size: 0.8125rem;
    color: var(--text-color, #374151);
  }

  .filter-item input[type="checkbox"] {
    accent-color: var(--primary-color, #4f46e5);
  }

  .filter-count {
    color: var(--text-secondary, #9ca3af);
    font-size: 0.75rem;
    margin-left: auto;
  }

  .date-inputs {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .date-inputs input {
    padding: 0.375rem 0.5rem;
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 6px;
    background: var(--surface-color, #fff);
    color: var(--text-color, #374151);
    font-size: 0.8125rem;
    color-scheme: light dark;
  }
</style>
