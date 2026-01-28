<script lang="ts">
  import { createEventDispatcher, tick, onDestroy } from 'svelte';
  import { getSpeakerColorForSegment } from '$lib/utils/speakerColors';
  import { translateSpeakerLabel } from '$lib/i18n';
  import axiosInstance from '$lib/axios';
  import { t } from '$stores/locale';
  import type { SearchOccurrence } from '$stores/search';

  export let isOpen: boolean = false;
  export let fileUuid: string = '';
  export let fileName: string = '';
  export let searchQuery: string = '';
  export let occurrences: SearchOccurrence[] = [];

  const dispatch = createEventDispatcher<{ close: void }>();

  interface GroupedSegment {
    speakerName: string;
    speaker_label: string;
    text: string;
    startTime: number;
    endTime: number;
    isKeyword: boolean;
    isSemantic: boolean;
    highlightedText: string;
    segmentIndex: number;
  }

  interface MatchPosition {
    type: 'keyword' | 'semantic';
    segmentIndex: number;
  }

  let loading = false;
  let error: string | null = null;
  let groupedSegments: GroupedSegment[] = [];
  let matchPositions: MatchPosition[] = [];
  let currentMatchIdx = 0;
  let contentElement: HTMLElement | null = null;

  // Progressive loading state
  const SEGMENTS_PER_PAGE = 200;
  let totalSegmentCount = 0;
  let loadedSegmentOffset = 0;
  let hasMoreSegments = false;
  let loadingMoreSegments = false;
  let infiniteScrollSentinel: HTMLElement | null = null;
  let infiniteScrollObserver: IntersectionObserver | null = null;
  let scrollProgress = 0;

  // Build time ranges from occurrences
  function buildTimeRanges() {
    const keywordRanges: { start: number; end: number }[] = [];
    const semanticRanges: { start: number; end: number }[] = [];

    for (const occ of occurrences) {
      const range = { start: occ.start_time, end: occ.end_time };
      if (occ.has_keyword_match) {
        keywordRanges.push(range);
      } else {
        semanticRanges.push(range);
      }
    }
    return { keywordRanges, semanticRanges };
  }

  function overlapsAny(start: number, end: number, ranges: { start: number; end: number }[]): boolean {
    return ranges.some(r => start < r.end && end > r.start);
  }

  function escapeHtml(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#x27;');
  }

  function highlightQueryTerms(text: string, cssClass: string): string {
    if (!searchQuery.trim()) return escapeHtml(text);
    const words = searchQuery.toLowerCase().split(/\s+/).filter(w => w.length >= 3);
    if (words.length === 0) return escapeHtml(text);

    const escaped = escapeHtml(text);
    const patterns = words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const regex = new RegExp(`\\b(${patterns.join('|')})\\b`, 'gi');

    // We need to match against the escaped text but the escaped text might have entities
    // So match against original, then build result with escaping around matches
    const result: string[] = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;
    const textLower = text.toLowerCase();

    // Use regex on original text, then escape each piece
    const origRegex = new RegExp(`\\b(${patterns.join('|')})\\b`, 'gi');
    while ((match = origRegex.exec(text)) !== null) {
      // Add text before match (escaped)
      if (match.index > lastIndex) {
        result.push(escapeHtml(text.substring(lastIndex, match.index)));
      }
      // Add highlighted match
      result.push(`<mark class="${cssClass}">${escapeHtml(match[0])}</mark>`);
      lastIndex = match.index + match[0].length;
    }
    // Add remaining text
    if (lastIndex < text.length) {
      result.push(escapeHtml(text.substring(lastIndex)));
    }
    return result.length > 0 ? result.join('') : escapeHtml(text);
  }

  /**
   * Per-raw-segment text entry with its match classification.
   * Used to build inline highlights within grouped speaker blocks.
   */
  interface TextEntry {
    text: string;
    isKeyword: boolean;
    isSemantic: boolean;
  }

  /**
   * Process raw segments into grouped segments with per-segment inline highlighting.
   * Groups by speaker (merging consecutive same-speaker segments), but highlights
   * only the specific raw segments that overlap keyword/semantic time ranges.
   */
  function processSegments(
    segments: any[],
    keywordRanges: { start: number; end: number }[],
    semanticRanges: { start: number; end: number }[],
    startSegIdx: number,
    existingLastGroup: GroupedSegment | null
  ): { grouped: GroupedSegment[]; nextSegIdx: number } {
    const sorted = [...segments].sort((a: any, b: any) => {
      return parseFloat(String(a.start_time || 0)) - parseFloat(String(b.start_time || 0));
    });

    const grouped: GroupedSegment[] = [];
    let currentSpeaker: string | null = existingLastGroup ? existingLastGroup.speakerName : null;
    let currentLabel: string | null = existingLastGroup ? existingLastGroup.speaker_label : null;
    let currentEntries: TextEntry[] = [];
    let currentStart = existingLastGroup ? existingLastGroup.startTime : 0;
    let currentEnd = existingLastGroup ? existingLastGroup.endTime : 0;
    let segIdx = startSegIdx;

    function buildHighlightedText(entries: TextEntry[]): string {
      return entries.map(entry => {
        if (entry.isKeyword) {
          return highlightQueryTerms(entry.text, 'search-keyword-match');
        } else if (entry.isSemantic) {
          // Wrap entire raw segment text in semantic span (inline highlight)
          return `<span class="search-semantic-match">${escapeHtml(entry.text)}</span>`;
        } else {
          return escapeHtml(entry.text);
        }
      }).join(' ');
    }

    function flushGroup() {
      if (currentSpeaker && currentEntries.length > 0) {
        const hasKeyword = currentEntries.some(e => e.isKeyword);
        const hasSemantic = currentEntries.some(e => e.isSemantic);

        grouped.push({
          speakerName: currentSpeaker,
          speaker_label: currentLabel || 'Unknown',
          text: currentEntries.map(e => e.text).join(' '),
          startTime: currentStart,
          endTime: currentEnd,
          isKeyword: hasKeyword,
          isSemantic: hasSemantic && !hasKeyword,
          highlightedText: buildHighlightedText(currentEntries),
          segmentIndex: segIdx,
        });
        segIdx++;
      }
    }

    sorted.forEach((segment: any) => {
      const speakerName =
        segment.resolved_speaker_name ||
        segment.speaker?.display_name ||
        segment.speaker?.name ||
        segment.speaker_label ||
        'Unknown Speaker';
      const speakerLabel = segment.speaker_label || segment.speaker?.name || 'Unknown';
      const startTime = parseFloat(String(segment.start_time || 0));
      const endTime = parseFloat(String(segment.end_time || 0));

      // Classify this individual raw segment
      const segIsKw = overlapsAny(startTime, endTime, keywordRanges);
      const segIsSem = !segIsKw && overlapsAny(startTime, endTime, semanticRanges);

      const entry: TextEntry = {
        text: segment.text || '',
        isKeyword: segIsKw,
        isSemantic: segIsSem
      };

      // Group by speaker only — highlight granularity is per raw segment
      if (speakerName !== currentSpeaker) {
        flushGroup();
        currentSpeaker = speakerName;
        currentLabel = speakerLabel;
        currentEntries = [entry];
        currentStart = startTime;
        currentEnd = endTime;
      } else {
        currentEntries.push(entry);
        currentEnd = endTime;
      }
    });
    flushGroup();

    return {
      grouped,
      nextSegIdx: segIdx
    };
  }

  /** Build match positions from grouped segments */
  function buildMatchPositions(segments: GroupedSegment[]): MatchPosition[] {
    const positions: MatchPosition[] = [];
    for (const seg of segments) {
      if (seg.isKeyword) {
        const words = searchQuery.toLowerCase().split(/\s+/).filter((w: string) => w.length >= 3);
        if (words.length > 0) {
          const patterns = words.map((w: string) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
          const regex = new RegExp(`\\b(${patterns.join('|')})\\b`, 'gi');
          const matches = seg.text.match(regex);
          const count = matches ? matches.length : 0;
          for (let i = 0; i < Math.max(1, count); i++) {
            positions.push({ type: 'keyword', segmentIndex: seg.segmentIndex });
          }
        } else {
          positions.push({ type: 'keyword', segmentIndex: seg.segmentIndex });
        }
      } else if (seg.isSemantic) {
        positions.push({ type: 'semantic', segmentIndex: seg.segmentIndex });
      }
    }
    return positions;
  }

  // Track the next segment index for grouping continuity
  let nextSegIdx = 0;

  async function loadTranscript() {
    if (!fileUuid) return;
    loading = true;
    error = null;
    groupedSegments = [];
    matchPositions = [];
    currentMatchIdx = 0;
    totalSegmentCount = 0;
    loadedSegmentOffset = 0;
    hasMoreSegments = false;
    loadingMoreSegments = false;
    nextSegIdx = 0;

    try {
      const res = await axiosInstance.get(`/files/${fileUuid}`, {
        params: {
          segment_limit: SEGMENTS_PER_PAGE,
          segment_offset: 0
        }
      });

      const segments = res.data.transcript_segments || [];
      if (segments.length === 0) {
        loading = false;
        return;
      }

      // Track total and loaded counts
      totalSegmentCount = res.data.total_segments || segments.length;
      loadedSegmentOffset = segments.length;
      hasMoreSegments = loadedSegmentOffset < totalSegmentCount;

      // Group consecutive same-speaker segments
      const { keywordRanges, semanticRanges } = buildTimeRanges();
      const result = processSegments(segments, keywordRanges, semanticRanges, 0, null);
      nextSegIdx = result.nextSegIdx;

      groupedSegments = result.grouped;
      matchPositions = buildMatchPositions(result.grouped);
      currentMatchIdx = 0;

      loading = false;

      // Auto-scroll to first match
      await tick();
      scrollToCurrentMatch();

      // Set up infinite scroll for additional pages
      setupInfiniteScrollObserver();
    } catch (e: any) {
      console.error('Failed to load transcript:', e);
      error = e?.response?.data?.detail || 'Failed to load transcript';
      loading = false;
    }
  }

  async function loadMoreSegments() {
    if (loadingMoreSegments || !hasMoreSegments || !fileUuid) return;
    loadingMoreSegments = true;

    try {
      const res = await axiosInstance.get(`/files/${fileUuid}`, {
        params: {
          segment_limit: SEGMENTS_PER_PAGE,
          segment_offset: loadedSegmentOffset
        }
      });

      const newSegments = res.data.transcript_segments || [];
      if (newSegments.length === 0) {
        hasMoreSegments = false;
        loadingMoreSegments = false;
        return;
      }

      const { keywordRanges, semanticRanges } = buildTimeRanges();

      // Check if we should try to continue the last group from previous batch
      const lastExisting = groupedSegments.length > 0 ? groupedSegments[groupedSegments.length - 1] : null;
      const result = processSegments(newSegments, keywordRanges, semanticRanges, nextSegIdx, null);
      nextSegIdx = result.nextSegIdx;

      // If the first new group has the same speaker as the last existing group,
      // merge them for speaker continuity (inline highlights are preserved)
      const firstNew = result.grouped.length > 0 ? result.grouped[0] : null;
      const canMerge = lastExisting && firstNew
        && firstNew.speakerName === lastExisting.speakerName;

      if (canMerge && lastExisting && firstNew) {
        const mergedGroup: GroupedSegment = {
          ...lastExisting,
          text: lastExisting.text + ' ' + firstNew.text,
          endTime: firstNew.endTime,
          isKeyword: lastExisting.isKeyword || firstNew.isKeyword,
          isSemantic: lastExisting.isSemantic || firstNew.isSemantic,
          highlightedText: lastExisting.highlightedText + ' ' + firstNew.highlightedText
        };

        // Replace last group and append the rest
        groupedSegments = [...groupedSegments.slice(0, -1), mergedGroup, ...result.grouped.slice(1)];
      } else {
        groupedSegments = [...groupedSegments, ...result.grouped];
      }

      loadedSegmentOffset += newSegments.length;
      hasMoreSegments = loadedSegmentOffset < totalSegmentCount;

      // Rebuild all match positions
      matchPositions = buildMatchPositions(groupedSegments);
    } catch (e: any) {
      console.error('Failed to load more segments:', e);
    }
    loadingMoreSegments = false;
  }

  function setupInfiniteScrollObserver() {
    if (typeof IntersectionObserver !== 'undefined' && !infiniteScrollObserver) {
      infiniteScrollObserver = new IntersectionObserver(
        (entries) => {
          const entry = entries[0];
          if (entry?.isIntersecting && hasMoreSegments && !loadingMoreSegments) {
            loadMoreSegments();
          }
        },
        { rootMargin: '200px' }
      );
    }
    // Observe the sentinel if it exists
    if (infiniteScrollSentinel && infiniteScrollObserver) {
      infiniteScrollObserver.observe(infiniteScrollSentinel);
    }
  }

  function handleContentScroll(event: Event) {
    const target = event.target as HTMLElement;
    if (target) {
      const scrollHeight = target.scrollHeight - target.clientHeight;
      if (scrollHeight > 0) {
        scrollProgress = Math.round((target.scrollTop / scrollHeight) * 100);
      }
    }
  }

  // Observe the sentinel element when it's available
  $: if (infiniteScrollSentinel && infiniteScrollObserver) {
    infiniteScrollObserver.observe(infiniteScrollSentinel);
  }

  // Load transcript when modal opens
  $: if (isOpen && fileUuid) {
    loadTranscript();
  }

  // Reset when modal closes
  $: if (!isOpen) {
    groupedSegments = [];
    matchPositions = [];
    currentMatchIdx = 0;
    error = null;
    hasMoreSegments = false;
    loadingMoreSegments = false;
    loadedSegmentOffset = 0;
    totalSegmentCount = 0;
    scrollProgress = 0;
    nextSegIdx = 0;
    if (infiniteScrollObserver) {
      infiniteScrollObserver.disconnect();
      infiniteScrollObserver = null;
    }
  }

  // Prevent body scroll when open
  $: {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
  }

  onDestroy(() => {
    if (infiniteScrollObserver) {
      infiniteScrollObserver.disconnect();
      infiniteScrollObserver = null;
    }
  });

  function scrollToCurrentMatch() {
    if (matchPositions.length === 0) return;
    setTimeout(() => {
      if (!contentElement) return;
      const pos = matchPositions[currentMatchIdx];
      if (!pos) return;

      // Find the segment element
      const segEl = contentElement.querySelector(`[data-seg-index="${pos.segmentIndex}"]`);
      if (segEl) {
        // Try to find a specific mark element within
        const marks = segEl.querySelectorAll('mark');
        if (marks.length > 0) {
          marks[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
        } else {
          segEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }
    }, 50);
  }

  function nextMatch() {
    if (matchPositions.length === 0) return;
    currentMatchIdx = (currentMatchIdx + 1) % matchPositions.length;
    scrollToCurrentMatch();
  }

  function prevMatch() {
    if (matchPositions.length === 0) return;
    currentMatchIdx = currentMatchIdx > 0 ? currentMatchIdx - 1 : matchPositions.length - 1;
    scrollToCurrentMatch();
  }

  function handleKeydown(event: KeyboardEvent) {
    if (!isOpen) return;
    if (event.key === 'Escape') {
      dispatch('close');
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (event.shiftKey) {
        prevMatch();
      } else {
        nextMatch();
      }
    }
  }

  function handleBackdropClick() {
    dispatch('close');
  }

  function handleModalClick(event: Event) {
    event.stopPropagation();
  }

  function formatTimestamp(seconds: number): string {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return `${m}:${String(s).padStart(2, '0')}`;
  }

  $: totalMatches = matchPositions.length;
</script>

<svelte:window on:keydown={handleKeydown} />

{#if isOpen}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="modal-backdrop" on:click={handleBackdropClick}>
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
    <div
      class="modal-container"
      role="dialog"
      aria-modal="true"
      on:click={handleModalClick}
    >
      <!-- Header -->
      <div class="modal-header">
        <div class="header-left">
          <h2 class="modal-title">{$t('searchTranscript.title', { fileName })}</h2>
          <div class="match-legend">
            <span class="legend-item keyword-legend">
              <span class="legend-swatch keyword-swatch"></span>
              {$t('searchTranscript.keywordLegend')}
            </span>
            <span class="legend-item semantic-legend">
              <span class="legend-swatch semantic-swatch"></span>
              {$t('searchTranscript.semanticLegend')}
            </span>
          </div>
        </div>
        <button
          class="close-button"
          on:click={() => dispatch('close')}
          title={$t('searchTranscript.close')}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>

      <!-- Navigation Bar -->
      {#if totalMatches > 0}
        <div class="nav-bar">
          <span class="nav-query">"{searchQuery}"</span>
          <div class="nav-controls">
            <span class="nav-count">
              {$t('searchTranscript.matchCount', { current: currentMatchIdx + 1, total: totalMatches })}
            </span>
            <button
              class="nav-btn"
              on:click={prevMatch}
              title={$t('searchTranscript.previousMatch')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="15,18 9,12 15,6"></polyline>
              </svg>
            </button>
            <button
              class="nav-btn"
              on:click={nextMatch}
              title={$t('searchTranscript.nextMatch')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="9,18 15,12 9,6"></polyline>
              </svg>
            </button>
          </div>
        </div>
      {/if}

      <!-- Content -->
      <div class="modal-content-wrapper">
        <!-- Reading progress bar -->
        {#if groupedSegments.length > 0}
          <div class="reading-progress-bar">
            <div class="reading-progress-fill" style="width: {scrollProgress}%"></div>
          </div>
        {/if}

        <div class="modal-content" bind:this={contentElement} on:scroll={handleContentScroll}>
          {#if loading}
            <div class="state-container">
              <div class="spinner"></div>
              <p>{$t('searchTranscript.loading')}</p>
            </div>
          {:else if error}
            <div class="state-container error">
              <p>{$t('searchTranscript.error')}</p>
              <p class="error-detail">{error}</p>
            </div>
          {:else if groupedSegments.length === 0}
            <div class="state-container">
              <p>{$t('searchTranscript.noTranscript')}</p>
            </div>
          {:else}
            <div class="transcript-content">
              {#each groupedSegments as segment}
                <div
                  class="transcript-segment"
                  class:keyword-segment={segment.isKeyword}
                  data-seg-index={segment.segmentIndex}
                >
                  <div class="segment-header">
                    <div
                      class="segment-speaker"
                      style="background-color: {getSpeakerColorForSegment(segment).bg}; border-color: {getSpeakerColorForSegment(segment).border}; --speaker-light: {getSpeakerColorForSegment(segment).textLight}; --speaker-dark: {getSpeakerColorForSegment(segment).textDark};"
                    >{translateSpeakerLabel(segment.speakerName)}</div>
                    <div class="segment-time">
                      {formatTimestamp(segment.startTime)}-{formatTimestamp(segment.endTime)}
                    </div>
                  </div>
                  <div class="segment-text">{@html segment.highlightedText}</div>
                </div>
              {/each}

              <!-- Infinite scroll sentinel -->
              {#if hasMoreSegments}
                <div class="infinite-scroll-sentinel" bind:this={infiniteScrollSentinel}>
                  {#if loadingMoreSegments}
                    <div class="loading-more-indicator">
                      <span class="loading-spinner-small"></span>
                      <span>Loading more...</span>
                    </div>
                  {/if}
                </div>
              {/if}
            </div>
          {/if}
        </div>

        <!-- Segments loaded info -->
        {#if totalSegmentCount > 0 && hasMoreSegments}
          <div class="segments-loaded-info">
            <span>{loadedSegmentOffset} of {totalSegmentCount} segments loaded</span>
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1050;
    padding: 1rem;
  }

  .modal-container {
    background-color: var(--bg-primary);
    border-radius: 12px;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
    width: 100%;
    max-width: 1200px;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 1.25rem 1.5rem;
    border-bottom: 1px solid var(--border-color);
    background-color: var(--bg-secondary);
    flex-shrink: 0;
  }

  .header-left {
    flex: 1;
    min-width: 0;
  }

  .modal-title {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0 0 0.375rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .match-legend {
    display: flex;
    gap: 1rem;
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 0.375rem;
  }

  .legend-swatch {
    display: inline-block;
    width: 12px;
    height: 12px;
    border-radius: 2px;
  }

  .keyword-swatch {
    background: rgba(250, 204, 21, 0.5);
  }

  .semantic-swatch {
    background: rgba(245, 158, 11, 0.4);
  }

  .close-button {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-secondary);
    padding: 0.5rem;
    border-radius: 6px;
    transition: all 0.2s ease;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .close-button:hover {
    background-color: var(--hover-bg);
    color: var(--text-primary);
  }

  /* Navigation Bar */
  .nav-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.625rem 1.5rem;
    border-bottom: 1px solid var(--border-color);
    background-color: var(--bg-secondary);
    flex-shrink: 0;
  }

  .nav-query {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    font-style: italic;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 50%;
  }

  .nav-controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .nav-count {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    white-space: nowrap;
  }

  .nav-btn {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    padding: 0.25rem;
    cursor: pointer;
    color: var(--text-secondary);
    transition: all 0.15s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 28px;
    min-height: 28px;
  }

  .nav-btn:hover {
    background-color: var(--hover-bg);
    border-color: var(--primary-color);
    color: var(--text-primary);
  }

  /* Content wrapper for progress bar + scroll area + info bar */
  .modal-content-wrapper {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    position: relative;
  }

  /* Content */
  .modal-content {
    flex: 1;
    overflow-y: auto;
    padding: 1.5rem;
  }

  .state-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    text-align: center;
    color: var(--text-secondary);
  }

  .state-container.error {
    color: var(--error-color, #ef4444);
  }

  .error-detail {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    margin-top: 0.5rem;
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--border-color);
    border-top: 3px solid var(--primary-color);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-bottom: 1rem;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* Transcript segments */
  .transcript-content {
    line-height: 1.6;
    font-size: 0.9rem;
  }

  .transcript-segment {
    margin-bottom: 1.25rem;
    display: flex;
    gap: 1rem;
    align-items: flex-start;
    padding: 0.25rem 0;
    border-left: 3px solid transparent;
    padding-left: 0.75rem;
  }

  .transcript-segment:last-child {
    margin-bottom: 0;
  }

  .semantic-segment {
    border-left-color: rgba(245, 158, 11, 0.4);
    background-color: rgba(245, 158, 11, 0.04);
    border-radius: 0 6px 6px 0;
    padding: 0.5rem 0.75rem;
  }

  :global(.dark) .semantic-segment {
    border-left-color: rgba(251, 191, 36, 0.35);
    background-color: rgba(251, 191, 36, 0.06);
  }

  .keyword-segment {
    border-left-color: rgba(250, 204, 21, 0.6);
    background-color: rgba(250, 204, 21, 0.04);
    border-radius: 0 6px 6px 0;
    padding: 0.5rem 0.75rem;
  }

  :global(.dark) .keyword-segment {
    border-left-color: rgba(250, 204, 21, 0.4);
    background-color: rgba(250, 204, 21, 0.06);
  }

  .segment-header {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    flex-shrink: 0;
    min-width: fit-content;
    align-items: center;
  }

  .segment-speaker {
    font-size: 12px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 12px;
    white-space: nowrap;
    min-width: fit-content;
    max-width: 150px;
    overflow: hidden;
    text-overflow: ellipsis;
    border: 1px solid;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--speaker-light);
  }

  :global([data-theme='dark']) .segment-speaker {
    color: var(--speaker-dark);
  }

  .segment-time {
    font-size: 12px;
    font-weight: 600;
    color: var(--primary-color);
    font-family: monospace;
    white-space: nowrap;
  }

  .segment-text {
    font-size: 14px;
    color: var(--text-primary);
    line-height: 1.5;
    flex: 1;
    padding-top: 2px;
  }

  /* Keyword word-level matches - yellow */
  .segment-text :global(.search-keyword-match) {
    background-color: rgba(250, 204, 21, 0.4);
    padding: 0.05em 0.15em;
    border-radius: 2px;
  }

  :global(.dark) .segment-text :global(.search-keyword-match) {
    background-color: rgba(250, 204, 21, 0.3);
  }

  /* Semantic segment-level matches - amber */
  .segment-text :global(.search-semantic-match) {
    background-color: rgba(245, 158, 11, 0.2);
    padding: 0.05em 0.15em;
    border-radius: 2px;
  }

  :global(.dark) .segment-text :global(.search-semantic-match) {
    background-color: rgba(251, 191, 36, 0.25);
  }

  /* Reading progress bar */
  .reading-progress-bar {
    position: sticky;
    top: 0;
    z-index: 5;
    height: 3px;
    background: var(--border-color, #e5e7eb);
    border-radius: 2px;
    overflow: hidden;
    flex-shrink: 0;
  }

  .reading-progress-fill {
    height: 100%;
    background: var(--primary-color, #4f46e5);
    transition: width 0.15s ease-out;
    border-radius: 2px;
  }

  /* Infinite scroll */
  .infinite-scroll-sentinel {
    min-height: 1px;
    padding: 1rem 0;
  }

  .loading-more-indicator {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.75rem;
    color: var(--text-secondary, #6b7280);
    font-size: 0.8125rem;
  }

  .loading-spinner-small {
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid var(--border-color, #e5e7eb);
    border-top-color: var(--primary-color, #4f46e5);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  .segments-loaded-info {
    text-align: center;
    padding: 0.5rem;
    font-size: 0.75rem;
    color: var(--text-secondary, #9ca3af);
    background: var(--bg-secondary);
    border-top: 1px solid var(--border-color);
    flex-shrink: 0;
  }

  @media (max-width: 768px) {
    .modal-backdrop {
      padding: 0;
    }

    .modal-container {
      border-radius: 0;
      max-height: 100vh;
    }

    .modal-header {
      padding: 1rem;
    }

    .modal-title {
      font-size: 1.1rem;
    }

    .nav-bar {
      padding: 0.5rem 1rem;
    }

    .modal-content {
      padding: 1rem;
    }
  }
</style>
