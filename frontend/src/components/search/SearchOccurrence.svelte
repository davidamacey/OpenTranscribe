<script lang="ts">
  import type { SearchOccurrence } from '$stores/search';
  import { t } from '$stores/locale';

  export let occurrence: SearchOccurrence;
  export let fileUuid: string;

  function formatTimestamp(seconds: number): string {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) {
      return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
    return `${m}:${String(s).padStart(2, '0')}`;
  }
</script>

<div class="occurrence">
  <div class="occurrence-header">
    {#if occurrence.match_type === 'title'}
      <span class="match-badge title-match">{$t('search.titleMatch')}</span>
    {:else if occurrence.match_type === 'speaker'}
      <span class="match-badge speaker-match">{$t('search.speakerMatch')}</span>
    {/if}
    {#if occurrence.speaker}
      <span class="speaker">
        {#if occurrence.speaker_highlighted}
          {@html occurrence.speaker_highlighted}
        {:else}
          {occurrence.speaker}
        {/if}
      </span>
    {/if}
    <a
      class="timestamp-link"
      href="/files/{fileUuid}?t={occurrence.start_time}"
      title="{$t('search.jumpTo')} {formatTimestamp(occurrence.start_time)}"
    >
      {formatTimestamp(occurrence.start_time)}
    </a>
  </div>
  {#if occurrence.snippet}
    <div class="snippet" class:context-only={occurrence.match_type === 'title' || occurrence.match_type === 'speaker'}>
      {@html occurrence.snippet}
    </div>
  {/if}
</div>

<style>
  .occurrence {
    padding: 0.5rem 0;
    border-top: 1px solid var(--border-color, #e5e7eb);
  }

  .occurrence:first-child {
    border-top: none;
    padding-top: 0;
  }

  .occurrence-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.25rem;
  }

  .speaker {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--primary-color, #4f46e5);
    background: rgba(79, 70, 229, 0.12);
    padding: 0.125rem 0.375rem;
    border-radius: 4px;
  }

  .speaker :global(mark) {
    background: rgba(250, 204, 21, 0.5);
    color: inherit;
    padding: 0 0.1em;
    border-radius: 2px;
  }

  .timestamp-link {
    font-size: 0.75rem;
    font-family: monospace;
    color: var(--primary-color, #4f46e5);
    text-decoration: none;
    padding: 0.125rem 0.375rem;
    border-radius: 4px;
    background: var(--surface-color, #f9fafb);
    border: 1px solid var(--border-color, #e5e7eb);
    transition: all 0.15s;
  }

  .timestamp-link:hover {
    background: var(--primary-color, #4f46e5);
    color: white;
    border-color: var(--primary-color, #4f46e5);
  }

  .snippet {
    font-size: 0.8125rem;
    line-height: 1.5;
    color: var(--text-color, #374151);
  }

  .snippet :global(mark) {
    background: rgba(250, 204, 21, 0.4);
    color: inherit;
    padding: 0.05em 0.15em;
    border-radius: 2px;
    font-weight: 500;
  }

  .snippet.context-only {
    opacity: 0.7;
    font-style: italic;
  }

  .match-badge {
    font-size: 0.6875rem;
    font-weight: 600;
    padding: 0.0625rem 0.375rem;
    border-radius: 4px;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .title-match {
    color: var(--info-color, #2563eb);
    background: rgba(37, 99, 235, 0.15);
  }

  .speaker-match {
    color: var(--primary-color, #4f46e5);
    background: rgba(79, 70, 229, 0.15);
  }
</style>
