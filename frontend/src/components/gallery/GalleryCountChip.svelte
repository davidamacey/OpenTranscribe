<script lang="ts">
  import { galleryState, galleryViewMode } from '$stores/gallery';
  import { t } from '$stores/locale';
  import { fade, scale } from 'svelte/transition';

  export let loading: boolean = false;
  export let filesLoaded: number = 0;

  $: displayText = getDisplayText($galleryState.totalFiles, filesLoaded, loading);
  $: isListView = $galleryViewMode === 'list';

  function getDisplayText(total: number, loaded: number, isLoading: boolean): string {
    if (isLoading && loaded === 0) {
      return $t('gallery.loadingCount');
    }
    if (total === 0) {
      return $t('gallery.noFilesMatch');
    }
    if (loaded === total) {
      return $t('gallery.showingAllCount', { count: total });
    }
    return $t('gallery.showingPartialCount', { loaded, total });
  }
</script>

{#if !loading || filesLoaded > 0}
  <div class="count-chip" in:scale={{ duration: 200 }} out:fade={{ duration: 150 }}>
    {#if isListView}
      <!-- List icon -->
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <line x1="8" y1="6" x2="21" y2="6" />
        <line x1="8" y1="12" x2="21" y2="12" />
        <line x1="8" y1="18" x2="21" y2="18" />
        <line x1="3" y1="6" x2="3.01" y2="6" />
        <line x1="3" y1="12" x2="3.01" y2="12" />
        <line x1="3" y1="18" x2="3.01" y2="18" />
      </svg>
    {:else}
      <!-- Grid icon -->
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <rect x="3" y="3" width="7" height="7" />
        <rect x="14" y="3" width="7" height="7" />
        <rect x="14" y="14" width="7" height="7" />
        <rect x="3" y="14" width="7" height="7" />
      </svg>
    {/if}
    <span>{displayText}</span>
  </div>
{/if}

<style>
  .count-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.375rem 0.75rem;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--text-secondary);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    backdrop-filter: blur(8px);
    transition: all 0.2s ease;
    user-select: none;
  }

  :global([data-theme='light']) .count-chip,
  :global(:not([data-theme='dark'])) .count-chip {
    background: rgba(255, 255, 255, 0.9);
    border-color: rgba(0, 0, 0, 0.08);
    color: #6b7280;
  }

  :global([data-theme='dark']) .count-chip {
    background: rgba(30, 41, 59, 0.95);
    border-color: rgba(255, 255, 255, 0.1);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    color: #cbd5e1;
  }

  .count-chip svg {
    flex-shrink: 0;
  }

  @media (max-width: 768px) {
    .count-chip {
      font-size: 0.75rem;
      padding: 0.3rem 0.625rem;
      gap: 0.3rem;
    }

    .count-chip span {
      max-width: 120px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }

  @media (max-width: 480px) {
    .count-chip {
      display: none;
    }
  }
</style>
