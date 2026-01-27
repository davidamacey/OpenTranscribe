<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { SearchHit } from '$stores/search';
  import { t } from '$stores/locale';
  import SearchOccurrence from './SearchOccurrence.svelte';

  export let hit: SearchHit;
  export let query: string = '';
  export let activePreview: { fileUuid: string; startTime: number } | null = null;

  const dispatch = createEventDispatcher();

  let expanded = false;

  const MAX_VISIBLE = 2;

  $: visibleOccurrences = expanded ? hit.occurrences : hit.occurrences.slice(0, MAX_VISIBLE);
  $: hiddenCount = hit.occurrences.length - MAX_VISIBLE;

  function formatDate(dateStr: string): string {
    try {
      return new Date(dateStr).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return dateStr;
    }
  }

  function handlePreviewClick(occurrence: any) {
    const isActive = activePreview
      && activePreview.fileUuid === hit.file_uuid
      && activePreview.startTime === occurrence.start_time;

    if (isActive) {
      dispatch('preview', null);
    } else {
      dispatch('preview', {
        fileUuid: hit.file_uuid,
        title: hit.title,
        startTime: occurrence.start_time,
        speaker: occurrence.speaker,
      });
    }
  }

  function isOccurrenceActive(occurrence: any): boolean {
    return !!(activePreview
      && activePreview.fileUuid === hit.file_uuid
      && activePreview.startTime === occurrence.start_time);
  }
</script>

<article class="result-card">
  <div class="result-header">
    <a href="/files/{hit.file_uuid}" class="result-title">
      {#if hit.title_highlighted}
        {@html hit.title_highlighted}
      {:else}
        {hit.title}
      {/if}
    </a>
    <div class="result-meta">
      {#if hit.speakers?.length > 0}
        <span class="meta-item speakers">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
            <circle cx="12" cy="7" r="4"></circle>
          </svg>
          {hit.speakers.join(', ')}
        </span>
      {/if}
      {#if hit.upload_time}
        <span class="meta-item date">
          {formatDate(hit.upload_time)}
        </span>
      {/if}
      {#if hit.tags?.length > 0}
        <span class="meta-item tags">
          {#each hit.tags as tag}
            <span class="tag">{tag}</span>
          {/each}
        </span>
      {/if}
      <span class="meta-item occurrences">
        {hit.total_occurrences} {hit.total_occurrences === 1 ? $t('search.resultFound') : $t('search.resultsFound')}
      </span>
    </div>
  </div>

  <div class="result-body">
    {#each visibleOccurrences as occurrence}
      <div class="occurrence-row">
        <SearchOccurrence {occurrence} fileUuid={hit.file_uuid} />
        <button
          class="preview-btn"
          class:active={isOccurrenceActive(occurrence)}
          on:click={() => handlePreviewClick(occurrence)}
          title={isOccurrenceActive(occurrence) ? $t('search.stopPreview') : $t('search.previewClip')}
        >
          {#if isOccurrenceActive(occurrence)}
            <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="currentColor" stroke="none">
              <rect x="6" y="5" width="4" height="14" rx="1"></rect>
              <rect x="14" y="5" width="4" height="14" rx="1"></rect>
            </svg>
          {:else}
            <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="currentColor" stroke="none">
              <path d="M8 5.14v13.72a1 1 0 0 0 1.5.86l11.04-6.86a1 1 0 0 0 0-1.72L9.5 4.28a1 1 0 0 0-1.5.86z"></path>
            </svg>
          {/if}
        </button>
      </div>
    {/each}

    {#if hiddenCount > 0 && !expanded}
      <button class="show-more" on:click={() => (expanded = true)}>
        {$t('search.showMore', { count: hiddenCount })}
      </button>
    {:else if expanded && hit.occurrences.length > MAX_VISIBLE}
      <button class="show-more" on:click={() => (expanded = false)}>
        {$t('search.showLess')}
      </button>
    {/if}
  </div>
</article>

<style>
  .result-card {
    background: var(--surface-color, #fff);
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 10px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
    transition: border-color 0.15s, box-shadow 0.15s;
  }

  .result-card:hover {
    border-color: var(--primary-color, #4f46e5);
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
  }

  .result-header {
    margin-bottom: 0.5rem;
  }

  .result-title {
    font-size: 1.0625rem;
    font-weight: 600;
    color: var(--primary-color, #4f46e5);
    text-decoration: none;
    line-height: 1.3;
  }

  .result-title:hover {
    text-decoration: underline;
  }

  .result-meta {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.375rem;
    font-size: 0.8125rem;
    color: var(--text-secondary, #6b7280);
  }

  .meta-item {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }

  .meta-item.speakers svg {
    color: var(--text-secondary, #9ca3af);
  }

  .tag {
    display: inline-block;
    background: var(--surface-color, #f3f4f6);
    border: 1px solid var(--border-color, #e5e7eb);
    padding: 0.0625rem 0.375rem;
    border-radius: 4px;
    font-size: 0.6875rem;
  }

  .meta-item.occurrences {
    color: var(--text-secondary, #9ca3af);
    font-size: 0.75rem;
  }

  .occurrence-row {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .occurrence-row :global(.occurrence) {
    flex: 1;
  }

  .preview-btn {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    margin-top: 0.375rem;
    padding: 0;
    border: none;
    border-radius: 6px;
    background: none;
    color: var(--primary-color, #4f46e5);
    cursor: pointer;
    transition: all 0.15s;
  }

  .preview-btn:hover {
    background: rgba(79, 70, 229, 0.1);
    transform: scale(1.1);
  }

  .preview-btn.active {
    color: var(--error-color, #ef4444);
  }

  .preview-btn.active:hover {
    background: rgba(239, 68, 68, 0.1);
  }

  .show-more {
    display: block;
    width: 100%;
    padding: 0.5rem;
    margin-top: 0.25rem;
    background: none;
    border: none;
    color: var(--primary-color, #4f46e5);
    font-size: 0.8125rem;
    cursor: pointer;
    text-align: center;
  }

  .show-more:hover {
    text-decoration: underline;
  }
</style>
