<script lang="ts">
  import { onMount, onDestroy, createEventDispatcher, tick } from 'svelte';
  import { goto } from '$app/navigation';
  import { cachedThumbnail } from '$lib/thumbnailCache';
  import { galleryStore } from '$stores/gallery';
  import { t } from '$stores/locale';
  import type { MediaFile } from '$lib/types/media';

  export let items: MediaFile[] = [];
  export let scrollContainer: HTMLElement | null = null;
  export let isSelecting: boolean = false;
  export let selectedFiles: Set<string> = new Set();
  export let pendingNewFiles: Set<string> = new Set();
  export let pendingDeletions: Set<string> = new Set();

  const dispatch = createEventDispatcher<{ errorclick: MediaFile }>();

  // Virtual scrolling config
  const ROW_HEIGHT = 340; // approximate card height including gap
  const CARD_MIN_WIDTH = 300;
  const GAP = 24; // 1.5rem
  const OVERSCAN = 2;

  // State
  let columnsPerRow = 1;
  let containerOffset = 0;
  let visibleStartRow = 0;
  let visibleEndRow = 0;
  let totalRows = 0;
  let rafId: number | null = null;
  let resizeObserver: ResizeObserver | null = null;
  let gridContainerEl: HTMLElement | null = null;
  let virtualContainerEl: HTMLElement | null = null;
  let boundScrollContainer: HTMLElement | null = null;

  $: totalHeight = totalRows * ROW_HEIGHT;
  // When all rows are visible, let the container auto-size to avoid dead space
  // from ROW_HEIGHT overestimating actual card height
  $: allRowsVisible = visibleStartRow === 0 && visibleEndRow >= totalRows;

  $: {
    if (items && scrollContainer) {
      // Defer to after DOM update — reading getBoundingClientRect() synchronously
      // returns stale geometry because Svelte hasn't patched the DOM yet
      tick().then(() => {
        updateColumns();
        measureOffset();
        recalculate();
      });
    }
  }

  function updateColumns() {
    if (!gridContainerEl) return;
    const width = gridContainerEl.clientWidth;
    const newCols = Math.max(1, Math.floor((width + GAP) / (CARD_MIN_WIDTH + GAP)));
    if (newCols !== columnsPerRow) {
      columnsPerRow = newCols;
    }
    // Always recalculate on resize (viewport height may have changed)
    measureOffset();
    recalculate();
  }

  function measureOffset() {
    if (virtualContainerEl && scrollContainer) {
      const containerRect = scrollContainer.getBoundingClientRect();
      const virtualRect = virtualContainerEl.getBoundingClientRect();
      containerOffset = virtualRect.top - containerRect.top + scrollContainer.scrollTop;
    }
  }

  function recalculate() {
    if (!scrollContainer) return;

    // Compute totalRows inline to avoid stale reactive values
    totalRows = Math.ceil(items.length / columnsPerRow);

    const scrollTop = scrollContainer.scrollTop;
    const viewportHeight = scrollContainer.clientHeight;
    const adjustedScrollTop = Math.max(0, scrollTop - containerOffset);

    const startRow = Math.floor(adjustedScrollTop / ROW_HEIGHT);
    const endRow = Math.ceil((adjustedScrollTop + viewportHeight) / ROW_HEIGHT);

    visibleStartRow = Math.max(0, startRow - OVERSCAN);
    visibleEndRow = Math.min(totalRows, endRow + OVERSCAN);
  }

  function onScroll() {
    if (rafId !== null) return;
    rafId = requestAnimationFrame(() => {
      rafId = null;
      recalculate();
    });
  }

  $: if (scrollContainer !== boundScrollContainer) {
    if (boundScrollContainer) {
      boundScrollContainer.removeEventListener('scroll', onScroll);
    }
    boundScrollContainer = scrollContainer;
    if (scrollContainer) {
      scrollContainer.addEventListener('scroll', onScroll, { passive: true });
      requestAnimationFrame(() => {
        measureOffset();
        recalculate();
      });
    }
  }

  onMount(() => {
    requestAnimationFrame(() => {
      updateColumns();
      measureOffset();
      recalculate();
    });

    if (gridContainerEl) {
      resizeObserver = new ResizeObserver(() => {
        updateColumns();
      });
      resizeObserver.observe(gridContainerEl);
    }
  });

  onDestroy(() => {
    if (boundScrollContainer) {
      boundScrollContainer.removeEventListener('scroll', onScroll);
    }
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
    }
    if (resizeObserver) {
      resizeObserver.disconnect();
    }
  });

  // Compute visible items from visible rows
  $: visibleStartIndex = visibleStartRow * columnsPerRow;
  $: visibleEndIndex = Math.min(items.length, visibleEndRow * columnsPerRow);
  $: visibleItems = items.slice(visibleStartIndex, visibleEndIndex);
  $: topSpacerHeight = visibleStartRow * ROW_HEIGHT;
  $: bottomSpacerHeight = Math.max(0, (totalRows - visibleEndRow) * ROW_HEIGHT);

  function handleCardClick(file: MediaFile, e: MouseEvent) {
    if (isSelecting) {
      e.preventDefault();
      if (e.shiftKey || e.ctrlKey || e.metaKey) {
        galleryStore.handleMultiSelect(file.uuid, e.ctrlKey || e.metaKey, e.shiftKey);
      } else {
        galleryStore.toggleFileSelection(file.uuid);
      }
    } else if (e.ctrlKey || e.metaKey || e.shiftKey) {
      e.preventDefault();
      galleryStore.handleMultiSelect(file.uuid, e.ctrlKey || e.metaKey, e.shiftKey);
    } else {
      e.preventDefault();
      goto(`/files/${file.uuid}`);
    }
  }

  function handleCheckboxChange(fileId: string, e: Event) {
    e.stopPropagation();
    e.preventDefault();
    galleryStore.toggleFileSelection(fileId);
  }

  function handleCheckboxLabelClick(fileId: string, e: MouseEvent) {
    if (e.shiftKey || e.ctrlKey || e.metaKey) {
      e.preventDefault();
      galleryStore.handleMultiSelect(fileId, e.ctrlKey || e.metaKey, e.shiftKey);
    }
  }

  function handleErrorClick(file: MediaFile) {
    dispatch('errorclick', file);
  }
</script>

<div
  bind:this={gridContainerEl}
  class="virtual-grid-wrapper"
  role="grid"
  aria-rowcount={totalRows}
>
  <div
    bind:this={virtualContainerEl}
    class="virtual-grid-container"
    style="{allRowsVisible ? '' : `height: ${totalHeight}px;`} position: relative;"
  >
    <!-- Top spacer -->
    <div style="height: {topSpacerHeight}px;" aria-hidden="true"></div>

    <!-- Visible items in CSS grid -->
    <div class="file-grid">
      {#each visibleItems as file, i (file.uuid)}
        {@const globalIndex = visibleStartIndex + i}
        <div
          class="file-card {selectedFiles.has(file.uuid) ? 'selected' : ''} {pendingNewFiles.has(file.uuid) ? 'new-file' : ''} {pendingDeletions.has(file.uuid) ? 'deleting' : ''} {isSelecting ? 'selecting-mode' : ''}"
          role="gridcell"
          aria-rowindex={Math.floor(globalIndex / columnsPerRow) + 1}
        >
          {#if isSelecting}
            <!-- svelte-ignore a11y-click-events-have-key-events -->
            <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
            <label
              class="file-selector"
              on:click|stopPropagation={(e) => handleCheckboxLabelClick(file.uuid, e)}
            >
              <input
                type="checkbox"
                class="file-checkbox"
                checked={selectedFiles.has(file.uuid)}
                on:change={(e) => handleCheckboxChange(file.uuid, e)}
                title={$t('gallery.selectFileTooltip')}
              />
              <span class="checkmark"></span>
            </label>
          {/if}
          <a
            href={isSelecting ? '#' : `/files/${file.uuid}`}
            class="file-card-link"
            on:click={(e) => handleCardClick(file, e)}
          >
            <div class="file-content">
              {#if file.thumbnail_url && file.content_type && file.content_type.startsWith('video/')}
                <div class="file-thumbnail">
                  <img
                    use:cachedThumbnail={{ uuid: file.uuid, url: file.thumbnail_url }}
                    alt={$t('gallery.thumbnailAlt', { title: file.title || file.filename })}
                    loading="lazy"
                    decoding="async"
                    class="thumbnail-image"
                  />
                  <div class="video-overlay">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="white" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polygon points="5 3 19 12 5 21 5 3"></polygon>
                    </svg>
                  </div>
                </div>
              {:else if file.content_type && file.content_type.startsWith('video/')}
                <div class="file-thumbnail video-placeholder">
                  <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <polygon points="23 7 16 12 23 17 23 7"></polygon>
                    <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                  </svg>
                </div>
              {:else if file.content_type && file.content_type.startsWith('audio/')}
                <div class="file-thumbnail audio-placeholder">
                  <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                    <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                    <line x1="12" y1="19" x2="12" y2="23"></line>
                    <line x1="8" y1="23" x2="16" y2="23"></line>
                  </svg>
                </div>
              {/if}

              <h2 class="file-name">{file.title || file.filename}</h2>

              <div class="file-meta">
                <span class="file-date">{file.formatted_upload_date}</span>
                {#if file.formatted_duration}
                  <span class="file-duration">{file.formatted_duration}</span>
                {/if}
                <div class="file-status status-{file.status}" class:clickable-error={file.status === 'error' && file.last_error_message}>
                  <span class="status-dot"></span>
                  {#if file.status === 'error' && file.last_error_message}
                    <!-- svelte-ignore a11y-click-events-have-key-events -->
                    <!-- svelte-ignore a11y-no-static-element-interactions -->
                    <span
                      class="error-details-trigger"
                      on:click|preventDefault|stopPropagation={() => handleErrorClick(file)}
                      title={$t('gallery.errorClickForDetails')}
                    >
                      {$t('common.error')}
                    </span>
                  {:else if file.status === 'completed'}
                    {$t('common.completed')}
                  {:else if file.status === 'processing'}
                    {$t('common.processing')}
                  {:else if file.status === 'pending'}
                    {$t('common.pending')}
                  {:else}
                    {file.display_status || file.status}
                  {/if}
                </div>
              </div>
            </div>
          </a>
        </div>
      {/each}
    </div>

    <!-- Bottom spacer -->
    <div style="height: {bottomSpacerHeight}px;" aria-hidden="true"></div>
  </div>
</div>

<style>
  .virtual-grid-wrapper {
    width: 100%;
  }

  .virtual-grid-container {
    overflow: visible;
    contain: layout style;
    padding-top: 0.5rem;
    margin-top: -0.5rem;
  }

  .file-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1.5rem;
    padding: 0 2px 0.5rem;  /* Prevent edge clipping from hover/shadow */
  }

  .file-card {
    position: relative;
    border: 1px solid var(--border-color);
    background-color: var(--surface-color);
    border-radius: 12px;
    transition: all 0.3s ease-in-out;
    cursor: pointer;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transform: translateZ(0);
  }

  .file-card.new-file {
    animation: newFileGlow 0.6s ease-out;
  }

  .file-card.deleting {
    opacity: 0.5;
    transform: scale(0.95);
    transition: all 0.25s ease-out;
    pointer-events: none;
  }

  @keyframes newFileGlow {
    0% {
      transform: scale(1);
      box-shadow: 0 0 15px rgba(59, 130, 246, 0.4);
      border-color: #60a5fa;
    }
    100% {
      transform: scale(1);
      box-shadow: none;
      border-color: var(--border-color);
    }
  }

  :global(.dark) .file-card.new-file {
    animation: newFileGlowDark 0.6s ease-out;
  }

  @keyframes newFileGlowDark {
    0% {
      box-shadow: 0 0 15px rgba(96, 165, 250, 0.3);
      border-color: #60a5fa;
    }
    100% {
      box-shadow: none;
      border-color: var(--border-color);
    }
  }

  .file-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 12px 25px -5px rgba(0, 0, 0, 0.15), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
    border-color: var(--border-hover);
  }

  .file-card:hover .thumbnail-image {
    transform: scale(1.05);
  }

  .file-card.selected {
    border: 2px solid #3b82f6;
    background-color: rgba(59, 130, 246, 0.05);
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
  }

  :global(.dark) .file-card.selected {
    background-color: rgba(59, 130, 246, 0.1);
    border-color: #60a5fa;
    box-shadow: 0 4px 12px rgba(96, 165, 250, 0.2);
  }

  .file-card.selecting-mode {
    user-select: none;
    -webkit-user-select: none;
  }

  .file-selector {
    position: absolute;
    bottom: 12px;
    right: 12px;
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .checkmark {
    width: 20px;
    height: 20px;
    background-color: var(--background-color);
    border: 2px solid var(--border-color);
    border-radius: 4px;
    position: relative;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .file-selector:hover .checkmark {
    border-color: #3b82f6;
  }

  .file-checkbox:checked ~ .checkmark {
    background-color: #3b82f6;
    border-color: #3b82f6;
  }

  .file-checkbox {
    position: absolute;
    opacity: 0;
    width: 100%;
    height: 100%;
    margin: 0;
    cursor: pointer;
  }

  .checkmark:after {
    content: "";
    position: absolute;
    display: none;
    left: 6px;
    top: 2px;
    width: 5px;
    height: 10px;
    border: solid white;
    border-width: 0 2px 2px 0;
    transform: rotate(45deg);
  }

  .file-checkbox:checked ~ .checkmark:after {
    display: block;
  }

  .file-thumbnail {
    position: relative;
    width: 100%;
    max-height: 180px;
    min-height: 100px;
    margin-bottom: 1rem;
    border-radius: 8px;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: rgba(0, 0, 0, 0.04);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  }

  :global(.dark) .file-thumbnail {
    background-color: rgba(255, 255, 255, 0.05);
  }

  .thumbnail-image {
    width: 100%;
    height: auto;
    max-height: 180px;
    object-fit: contain;
    transition: transform 0.3s ease;
  }

  .video-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.3);
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0.8;
    transition: opacity 0.3s ease;
  }

  .file-card:hover .video-overlay {
    opacity: 1;
  }

  .video-placeholder,
  .audio-placeholder {
    background-color: rgba(0, 0, 0, 0.04);
    color: var(--text-secondary);
  }

  :global(.dark) .video-placeholder,
  :global(.dark) .audio-placeholder {
    background-color: rgba(255, 255, 255, 0.05);
    color: var(--text-secondary);
  }

  .file-content {
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    flex: 1;
  }

  .file-card-link {
    display: block;
    text-decoration: none;
    color: inherit;
    height: 100%;
  }

  .file-name {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    line-height: 1.4;
  }

  .file-date {
    font-size: 0.875rem;
    color: var(--text-secondary);
    margin-top: auto;
  }

  .file-duration {
    font-size: 0.875rem;
    color: var(--text-secondary);
    font-weight: 500;
  }

  .file-meta {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
    color: var(--text-secondary);
  }

  .file-status {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.65rem;
    font-weight: 500;
    padding: 0.15rem 0.5rem;
    border-radius: 9999px;
    background-color: rgba(0, 0, 0, 0.05);
    width: fit-content;
    margin-left: auto;
    white-space: nowrap;
  }

  :global(.dark) .file-status {
    background-color: rgba(255, 255, 255, 0.05);
  }

  .status-pending,
  .status-processing {
    color: #f59e0b;
    background-color: rgba(245, 158, 11, 0.1);
  }

  .status-completed {
    color: #10b981;
    background-color: rgba(16, 185, 129, 0.1);
  }

  .status-error {
    color: #ef4444;
    background-color: rgba(239, 68, 68, 0.1);
  }

  .clickable-error {
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .clickable-error:hover {
    background-color: rgba(239, 68, 68, 0.2);
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2);
  }

  .error-details-trigger {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    text-decoration: underline;
    text-decoration-style: dotted;
  }

  .error-details-trigger:hover {
    text-decoration-style: solid;
  }

  .status-cancelling {
    color: #f59e0b;
    background-color: rgba(245, 158, 11, 0.1);
  }

  .status-cancelled {
    color: #6b7280;
    background-color: rgba(107, 114, 128, 0.1);
  }

  .status-orphaned {
    color: #dc2626;
    background-color: rgba(220, 38, 38, 0.1);
  }

  .status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background-color: currentColor;
  }

  @keyframes pulse {
    0% { opacity: 0.6; }
    50% { opacity: 1; }
    100% { opacity: 0.6; }
  }

  .status-processing .status-dot {
    animation: pulse 2s ease-in-out infinite;
  }

  :global(.dark) .file-card {
    background: var(--surface-color);
    border-color: var(--border-color);
  }

  :global(.dark) .file-card:hover {
    border-color: var(--border-hover);
  }

  :global(.dark) .file-name {
    color: var(--text-primary);
  }

  :global(.dark) .file-date,
  :global(.dark) .file-duration {
    color: var(--text-secondary);
  }

  @media (max-width: 768px) {
    .file-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .file-card,
    .file-card.new-file,
    .thumbnail-image {
      transition: none;
      animation: none;
    }

    .file-card:hover {
      transform: none;
    }

    .file-card:hover .thumbnail-image {
      transform: none;
    }
  }
</style>
