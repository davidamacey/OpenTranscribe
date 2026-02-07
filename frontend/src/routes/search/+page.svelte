<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import { page } from '$app/stores';
  import { goto, beforeNavigate } from '$app/navigation';
  import axiosInstance from '$lib/axios';
  import { t } from '$stores/locale';
  import { searchStore, type SearchResponse, type SearchOccurrence } from '$stores/search';
  import SearchResultCard from '$components/search/SearchResultCard.svelte';
  import SearchTranscriptModal from '$components/search/SearchTranscriptModal.svelte';
  import SearchPagination from '$components/search/SearchPagination.svelte';
  import FilterSidebar from '$components/FilterSidebar.svelte';
  import SearchAutocomplete from '$components/search/SearchAutocomplete.svelte';
  import SearchSortDropdown from '$components/search/SearchSortDropdown.svelte';
  import Plyr from 'plyr';
  import 'plyr/dist/plyr.css';
  import WaveformPlayer from '$components/WaveformPlayer.svelte';

  let searchInput = '';
  let showFilters = true;
  let sidebarMounted = false;

  // FilterSidebar state
  let filterSearchQuery = '';
  let filterSelectedTags: string[] = [];
  let filterSelectedSpeakers: string[] = [];
  let filterDateRange: { from: Date | null; to: Date | null } = { from: null, to: null };
  let filterSelectedCollectionId: string | null = null;
  let filterDurationRange: { min: number | null; max: number | null } = { min: null, max: null };
  let filterFileSizeRange: { min: number | null; max: number | null } = { min: null, max: null };
  let filterSelectedFileTypes: string[] = [];
  let filterSelectedStatuses: string[] = [];

  // Sticky preview player state
  let previewData: { fileUuid: string; title: string; startTime: number; speaker: string; contentType: string } | null = null;
  let previewMediaElement: HTMLVideoElement | HTMLAudioElement | null = null;
  let previewPlayer: Plyr | null = null;
  let activePreview: { fileUuid: string; startTime: number } | null = null;
  let previewSeeking = false;
  let previewCurrentTime = 0;
  let previewCurrentSpeaker = '';

  // Search transcript modal state
  let transcriptModalOpen = false;
  let transcriptModalFileUuid = '';
  let transcriptModalFileName = '';
  let transcriptModalOccurrences: SearchOccurrence[] = [];

  function formatPlaybackTime(seconds: number): string {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return `${m}:${String(s).padStart(2, '0')}`;
  }

  function findSpeakerAtTime(time: number): string {
    if (!previewData) return '';
    // Find the matching file in results to get all occurrences
    const hit = $searchStore.results.find(r => r.file_uuid === previewData!.fileUuid);
    if (!hit) return previewData.speaker || '';
    // Find the occurrence whose time range contains the current time
    for (const occ of hit.occurrences) {
      if (time >= occ.start_time && time <= occ.end_time) {
        return occ.speaker || '';
      }
    }
    return previewData.speaker || '';
  }

  $: isAudioPreview = previewData?.contentType?.startsWith('audio/') ?? false;

  // Read initial state from URL
  $: urlQuery = $page.url.searchParams.get('q') || '';
  $: urlPage = parseInt($page.url.searchParams.get('page') || '1');
  $: urlSort = $page.url.searchParams.get('sort') || 'relevance';
  $: urlSortOrder = ($page.url.searchParams.get('sort_order') || 'desc') as 'asc' | 'desc';
  $: urlMode = $page.url.searchParams.get('mode') || 'hybrid';
  $: urlSpeakers = $page.url.searchParams.getAll('speakers');
  $: urlTags = $page.url.searchParams.getAll('tags');

  onMount(() => {
    // Restore search input: prefer URL param, fall back to store query
    const restoredQuery = urlQuery || $searchStore.query;
    searchInput = restoredQuery;

    searchStore.setSortBy(urlSort);
    searchStore.setSortOrder(urlSortOrder);
    searchStore.setSearchMode(urlMode);
    if (urlSpeakers.length) searchStore.setSpeakers(urlSpeakers);
    if (urlTags.length) searchStore.setTags(urlTags);

    // Restore filter sidebar state from search store
    filterSelectedTags = [...$searchStore.selectedTags];
    filterSelectedSpeakers = [...$searchStore.selectedSpeakers];
    filterSelectedFileTypes = [...$searchStore.selectedFileTypes];
    filterSelectedStatuses = [...$searchStore.selectedStatuses];
    filterSelectedCollectionId = $searchStore.selectedCollectionId;
    filterDurationRange = { ...$searchStore.durationRange };
    filterFileSizeRange = { ...$searchStore.fileSizeRange };
    filterSearchQuery = $searchStore.titleFilter;
    if ($searchStore.dateFrom || $searchStore.dateTo) {
      filterDateRange = {
        from: $searchStore.dateFrom ? new Date($searchStore.dateFrom + 'T00:00:00') : null,
        to: $searchStore.dateTo ? new Date($searchStore.dateTo + 'T00:00:00') : null,
      };
    }

    if (restoredQuery) {
      // D3: Check if we can reuse cached results
      const currentParams = buildSearchParamsString(restoredQuery, urlPage);
      if ($searchStore.lastSearchParams === currentParams && $searchStore.results.length > 0) {
        // Results match - skip API call
        searchInput = restoredQuery;

        // Restore scroll position
        if ($searchStore.scrollPosition > 0) {
          requestAnimationFrame(() => {
            const scrollable = document.querySelector('.scrollable-content');
            if (scrollable) scrollable.scrollTop = $searchStore.scrollPosition;
          });
        }
      } else if ($searchStore.results.length > 0 && $searchStore.query === restoredQuery) {
        // Store has matching results even if params string differs (e.g. back navigation)
        searchInput = restoredQuery;
      } else {
        performSearch(restoredQuery, urlPage);
      }
    }

    // Restore active preview independently of cache check
    if ($searchStore.activePreview) {
      previewData = $searchStore.activePreview;
      activePreview = {
        fileUuid: $searchStore.activePreview.fileUuid,
        startTime: $searchStore.activePreview.startTime,
      };
      previewCurrentTime = $searchStore.activePreview.startTime;
      previewCurrentSpeaker = $searchStore.activePreview.speaker || '';
      setTimeout(() => initPreviewPlayer($searchStore.activePreview!.startTime), 300);
    }

    // Enable sidebar transitions only after initial render is complete
    requestAnimationFrame(() => {
      sidebarMounted = true;
    });
  });

  function buildSearchParamsString(query: string, pageNum: number): string {
    return JSON.stringify({
      q: query, page: pageNum, sort: $searchStore.sortBy, sortOrder: $searchStore.sortOrder,
      mode: $searchStore.searchMode, speakers: $searchStore.selectedSpeakers,
      tags: $searchStore.selectedTags, dateFrom: $searchStore.dateFrom, dateTo: $searchStore.dateTo,
      fileTypes: $searchStore.selectedFileTypes, collectionId: $searchStore.selectedCollectionId,
      durationRange: $searchStore.durationRange, fileSizeRange: $searchStore.fileSizeRange,
      titleFilter: $searchStore.titleFilter,
    });
  }

  async function performSearch(query: string, pageNum: number = 1) {
    if (!query.trim()) return;

    searchStore.setQuery(query);
    searchStore.setLoading(true);

    // Update URL without navigation
    const params = new URLSearchParams();
    params.set('q', query);
    if (pageNum > 1) params.set('page', String(pageNum));
    if ($searchStore.sortBy !== 'relevance') params.set('sort', $searchStore.sortBy);
    if ($searchStore.sortOrder !== 'desc') params.set('sort_order', $searchStore.sortOrder);
    if ($searchStore.searchMode !== 'hybrid') params.set('mode', $searchStore.searchMode);
    $searchStore.selectedSpeakers.forEach((s) => params.append('speakers', s));
    $searchStore.selectedTags.forEach((tag) => params.append('tags', tag));

    goto(`/search?${params.toString()}`, { replaceState: true, keepFocus: true });

    try {
      const apiParams: Record<string, any> = {
        q: query,
        page: pageNum,
        page_size: $searchStore.pageSize,
        sort_by: $searchStore.sortBy,
        sort_order: $searchStore.sortOrder,
        search_mode: $searchStore.searchMode,
        speakers: $searchStore.selectedSpeakers.length ? $searchStore.selectedSpeakers : undefined,
        tags: $searchStore.selectedTags.length ? $searchStore.selectedTags : undefined,
        date_from: $searchStore.dateFrom || undefined,
        date_to: $searchStore.dateTo || undefined,
      };

      // Gallery filter params
      if ($searchStore.selectedFileTypes.length) {
        apiParams.file_type = $searchStore.selectedFileTypes;
      }
      if ($searchStore.selectedCollectionId) {
        apiParams.collection_id = $searchStore.selectedCollectionId;
      }
      if ($searchStore.durationRange.min !== null) {
        apiParams.min_duration = $searchStore.durationRange.min;
      }
      if ($searchStore.durationRange.max !== null) {
        apiParams.max_duration = $searchStore.durationRange.max;
      }
      if ($searchStore.fileSizeRange.min !== null) {
        apiParams.min_file_size = $searchStore.fileSizeRange.min * 1024 * 1024; // MB to bytes
      }
      if ($searchStore.fileSizeRange.max !== null) {
        apiParams.max_file_size = $searchStore.fileSizeRange.max * 1024 * 1024; // MB to bytes
      }
      if ($searchStore.titleFilter) {
        apiParams.title_filter = $searchStore.titleFilter;
      }

      const res = await axiosInstance.get('/search', {
        params: apiParams,
        paramsSerializer: (params) => {
          const searchParams = new URLSearchParams();
          Object.entries(params).forEach(([key, value]) => {
            if (value === undefined) return;
            if (Array.isArray(value)) {
              value.forEach((v) => searchParams.append(key, v));
            } else {
              searchParams.set(key, String(value));
            }
          });
          return searchParams.toString();
        },
      });

      searchStore.setResults(res.data as SearchResponse);
      // D3: Store params that produced these results
      searchStore.setLastSearchParams(buildSearchParamsString(query, pageNum));
    } catch (e: any) {
      console.error('Search failed:', e);
      searchStore.setError(e?.response?.data?.detail || 'Search failed');
      searchStore.setLoading(false);
    }
  }

  function handleSearch() {
    performSearch(searchInput, 1);
  }

  function handleClearSearch() {
    searchInput = '';
    searchStore.reset();
    // Update URL to remove search params
    const url = new URL(window.location.href);
    url.searchParams.delete('q');
    url.searchParams.delete('page');
    goto(url.toString(), { replaceState: true });
  }

  function handlePageChange(event: CustomEvent<number>) {
    performSearch($searchStore.query, event.detail);
    // Scroll to top of results
    const scrollable = document.querySelector('.scrollable-content');
    if (scrollable) {
      scrollable.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }

  function handleSortChange(event: CustomEvent<{ sortBy: string; sortOrder: 'asc' | 'desc' }>) {
    const { sortBy, sortOrder } = event.detail;
    searchStore.setSort(sortBy, sortOrder);
    if ($searchStore.query) {
      performSearch($searchStore.query, 1);
    }
  }

  function handleSearchModeChange(mode: string) {
    searchStore.setSearchMode(mode);
    if ($searchStore.query) {
      performSearch($searchStore.query, 1);
    }
  }

  function handleFilterEvent(event: CustomEvent) {
    const detail = event.detail;
    if (!detail) return;

    // Map FilterSidebar event to search store
    if (detail.tags !== undefined) {
      searchStore.setTags(detail.tags);
    }
    if (detail.speaker !== undefined) {
      searchStore.setSpeakers(detail.speaker);
    }
    if (detail.collectionId !== undefined) {
      searchStore.setCollectionId(detail.collectionId);
    }
    if (detail.dates !== undefined) {
      const dateFrom = detail.dates?.from ? detail.dates.from.toISOString().split('T')[0] : '';
      const dateTo = detail.dates?.to ? detail.dates.to.toISOString().split('T')[0] : '';
      searchStore.setDateRange(dateFrom, dateTo);
    }
    if (detail.durationRange !== undefined) {
      searchStore.setDurationRange(detail.durationRange);
    }
    if (detail.fileSizeRange !== undefined) {
      searchStore.setFileSizeRange(detail.fileSizeRange);
    }
    if (detail.fileTypes !== undefined) {
      searchStore.setFileTypes(detail.fileTypes);
    }
    if (detail.statuses !== undefined) {
      searchStore.setStatuses(detail.statuses);
    }
    if (detail.search !== undefined) {
      searchStore.setTitleFilter(detail.search);
    }

    // Re-run search with new filters
    if ($searchStore.query) {
      performSearch($searchStore.query, 1);
    }
  }

  function handleFilterReset() {
    searchStore.setSpeakers([]);
    searchStore.setTags([]);
    searchStore.setDateRange('', '');
    searchStore.setFileTypes([]);
    searchStore.setCollectionId(null);
    searchStore.setDurationRange({ min: null, max: null });
    searchStore.setFileSizeRange({ min: null, max: null });
    searchStore.setStatuses([]);
    searchStore.setTitleFilter('');
    filterSearchQuery = '';
    filterSelectedTags = [];
    filterSelectedSpeakers = [];
    filterDateRange = { from: null, to: null };
    filterSelectedCollectionId = null;
    filterDurationRange = { min: null, max: null };
    filterFileSizeRange = { min: null, max: null };
    filterSelectedFileTypes = [];
    filterSelectedStatuses = [];

    if ($searchStore.query) {
      performSearch($searchStore.query, 1);
    }
  }

  function handleSuggestionSelect(event: CustomEvent<string>) {
    searchInput = event.detail;
    performSearch(event.detail, 1);
  }

  // Sticky preview player
  async function handlePreview(event: CustomEvent) {
    const data = event.detail;
    if (!data) {
      closePreview();
      return;
    }

    // Always fully tear down and recreate to avoid stale DOM bindings
    // (Plyr's destroy moves elements, which can confuse Svelte's bind:this
    // when switching between audio/video branches)
    destroyPreviewPlayer();
    previewMediaElement = null;
    previewData = null;
    await tick();

    previewData = data;
    activePreview = { fileUuid: data.fileUuid, startTime: data.startTime };
    previewSeeking = true;
    previewCurrentTime = data.startTime;
    previewCurrentSpeaker = data.speaker || '';

    // Persist to store for back-button restoration
    searchStore.setActivePreview(data);

    // Wait for Svelte to render the media element
    await tick();
    initPreviewPlayer(data.startTime);
  }

  function handleViewTranscript(event: CustomEvent) {
    const { fileUuid, title, occurrences } = event.detail;
    transcriptModalFileUuid = fileUuid;
    transcriptModalFileName = title;
    transcriptModalOccurrences = occurrences;
    transcriptModalOpen = true;
  }

  function initPreviewPlayer(startTime: number) {
    if (!previewMediaElement) {
      previewSeeking = false;
      return;
    }

    destroyPreviewPlayer();
    previewSeeking = true;

    // Force the video element to load its source
    previewMediaElement.load();

    const audioControls = ['play', 'current-time', 'duration', 'progress', 'mute', 'volume', 'settings'];
    const videoControls = ['play-large', 'play', 'current-time', 'duration', 'progress', 'mute', 'volume', 'captions', 'settings', 'pip', 'fullscreen'];

    previewPlayer = new Plyr(previewMediaElement, {
      controls: isAudioPreview ? audioControls : videoControls,
      settings: isAudioPreview ? ['speed'] : ['captions', 'speed'],
      iconUrl: '/plyr.svg',
      keyboard: { global: false },
      tooltips: { controls: true },
      captions: { active: true, language: 'auto', update: true },
      fullscreen: { iosNative: true },
    });

    let hasStartedPlayback = false;

    function seekAndPlay() {
      if (hasStartedPlayback || !previewPlayer) return;
      hasStartedPlayback = true;

      if (startTime > 0) {
        previewPlayer.currentTime = startTime;
      }
      const playResult = previewPlayer.play();
      if (playResult && typeof playResult.catch === 'function') {
        playResult.catch(() => {
          // Autoplay may be blocked by browser - user can click play manually
          previewSeeking = false;
        });
      }
    }

    // Use the underlying media element events for reliability
    const media = (previewPlayer as any).media as HTMLMediaElement | undefined;
    if (media) {
      const onCanPlay = () => {
        seekAndPlay();
        media.removeEventListener('canplay', onCanPlay);
      };
      media.addEventListener('canplay', onCanPlay);

      media.addEventListener('seeked', () => { previewSeeking = false; }, { once: true });
      media.addEventListener('playing', () => { previewSeeking = false; }, { once: true });
      media.addEventListener('error', () => { previewSeeking = false; }, { once: true });
    }

    // Track playback time and current speaker
    previewPlayer.on('timeupdate', () => {
      if (previewPlayer) {
        previewCurrentTime = previewPlayer.currentTime;
        previewCurrentSpeaker = findSpeakerAtTime(previewCurrentTime);
      }
    });

    // Also listen via Plyr as fallback
    previewPlayer.on('playing', () => { previewSeeking = false; });
    previewPlayer.on('error', () => { previewSeeking = false; });

    // Fallback: clear spinner after timeout
    setTimeout(() => { previewSeeking = false; }, 8000);
  }

  function destroyPreviewPlayer() {
    if (previewPlayer) {
      try { previewPlayer.destroy(); } catch {}
      previewPlayer = null;
    }
  }

  function closePreview() {
    destroyPreviewPlayer();
    previewData = null;
    activePreview = null;
    previewSeeking = false;
    searchStore.setActivePreview(null);
  }

  function handleWaveformSeek(event: CustomEvent<{ time: number }>) {
    if (previewPlayer && event.detail?.time != null) {
      previewPlayer.currentTime = event.detail.time;
    }
  }

  // Save all transient state before navigating away
  function saveState() {
    // Save scroll position
    const scrollable = document.querySelector('.scrollable-content');
    if (scrollable) {
      searchStore.setScrollPosition(scrollable.scrollTop);
    }

    // Update the preview's playback time in the store so we can resume at the right spot
    if (previewData && previewCurrentTime > 0) {
      searchStore.setActivePreview({
        ...previewData,
        startTime: previewCurrentTime,
      });
    }
  }

  // Catch SvelteKit client-side navigation (e.g. clicking "Jump to" link)
  beforeNavigate(() => {
    saveState();
  });

  function formatSearchTime(ms: number): string {
    return (ms / 1000).toFixed(2);
  }

  // Split results into keyword matches and semantic-only
  $: keywordResults = $searchStore.results.filter(r => !r.semantic_only);
  $: semanticHighResults = $searchStore.results.filter(r => r.semantic_only && r.semantic_confidence === 'high');
  $: semanticLowResults = $searchStore.results.filter(r => r.semantic_only && r.semantic_confidence === 'low');
  $: allSemanticOnly = keywordResults.length === 0 && (semanticHighResults.length > 0 || semanticLowResults.length > 0);

  onDestroy(() => {
    saveState();
    destroyPreviewPlayer();
  });
</script>

<svelte:head>
  <title>{$searchStore.query ? `${$searchStore.query} - ` : ''}{$t('search.title')}</title>
</svelte:head>

<div class="search-page">
  <!-- Left Sidebar: Filters (Sticky) -->
  <div class="filter-sidebar {showFilters ? 'show' : ''}" class:animate={sidebarMounted}>
    <div class="filter-toggle-container">
      <button
        class="filter-toggle-btn {showFilters ? 'expanded' : 'collapsed'}"
        on:click={() => (showFilters = !showFilters)}
        title={showFilters ? $t('gallery.hideFiltersPanel') : $t('gallery.showFiltersPanel')}
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="4" y1="21" x2="4" y2="14"></line><line x1="4" y1="10" x2="4" y2="3"></line>
          <line x1="12" y1="21" x2="12" y2="12"></line><line x1="12" y1="8" x2="12" y2="3"></line>
          <line x1="20" y1="21" x2="20" y2="16"></line><line x1="20" y1="12" x2="20" y2="3"></line>
          <line x1="1" y1="14" x2="7" y2="14"></line><line x1="9" y1="8" x2="15" y2="8"></line>
          <line x1="17" y1="16" x2="23" y2="16"></line>
        </svg>
      </button>
    </div>

    <!-- Filter Content (hidden when collapsed) -->
    {#if showFilters}
      <div class="filter-content">
        <FilterSidebar
          bind:searchQuery={filterSearchQuery}
          bind:selectedTags={filterSelectedTags}
          bind:selectedSpeakers={filterSelectedSpeakers}
          bind:dateRange={filterDateRange}
          bind:selectedCollectionId={filterSelectedCollectionId}
          bind:durationRange={filterDurationRange}
          bind:fileSizeRange={filterFileSizeRange}
          bind:selectedFileTypes={filterSelectedFileTypes}
          bind:selectedStatuses={filterSelectedStatuses}
          on:filter={handleFilterEvent}
          on:reset={handleFilterReset}
        />
      </div>
    {/if}
  </div>

  <!-- Main Content Area -->
  <div class="content-area">
    <div class="scrollable-content">
      <!-- Search Header -->
      <header class="search-header">
        <h1 class="search-title">{$t('search.title')}</h1>
        <div class="search-bar">
          <SearchAutocomplete
            bind:value={searchInput}
            on:search={handleSearch}
            on:select={handleSuggestionSelect}
            on:clear={handleClearSearch}
            placeholder={$t('searchPage.placeholder')}
          />
          <button class="search-btn" on:click={handleSearch} disabled={$searchStore.isLoading} aria-label={$t('searchPage.search') || 'Search'}>
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
          </button>
        </div>

        <!-- Results Info Bar -->
        {#if $searchStore.query && !$searchStore.isLoading && $searchStore.totalResults >= 0 && $searchStore.results.length > 0}
          <div class="results-info">
            <span class="result-summary">
              {$t('search.results', { count: $searchStore.totalFiles, time: formatSearchTime($searchStore.searchTimeMs) })}
            </span>
            <div class="results-controls">
              <!-- Search Mode Toggle -->
              <div class="mode-toggle">
                <button
                  class="mode-btn"
                  class:active={$searchStore.searchMode === 'hybrid'}
                  on:click={() => handleSearchModeChange('hybrid')}
                  title={$t('search.smartModeDesc')}
                >
                  {$t('search.smartMode')}
                </button>
                <button
                  class="mode-btn"
                  class:active={$searchStore.searchMode === 'keyword'}
                  on:click={() => handleSearchModeChange('keyword')}
                  title={$t('search.exactModeDesc')}
                >
                  {$t('search.exactMode')}
                </button>
              </div>
              <SearchSortDropdown
                sortBy={$searchStore.sortBy}
                sortOrder={$searchStore.sortOrder}
                on:change={handleSortChange}
              />
            </div>
          </div>
        {/if}
      </header>

      <!-- Results -->
      <main class="results">
        {#if $searchStore.isLoading}
          <div class="state-container">
            <div class="loading-spinner"></div>
            <p class="state-text">{$t('search.searching') || 'Searching...'}</p>
          </div>
        {:else if $searchStore.error}
          <div class="state-container error">
            <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <p class="state-text">{$searchStore.error}</p>
          </div>
        {:else if $searchStore.query && $searchStore.results.length === 0}
          <div class="state-container">
            <svg xmlns="http://www.w3.org/2000/svg" width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round" class="empty-icon">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
            <p class="state-title">{$t('searchPage.noResults', { query: $searchStore.query })}</p>
            <p class="state-hint">{$t('search.noResultsHint')}</p>
          </div>
        {:else if !$searchStore.query}
          <div class="state-container welcome">
            <svg xmlns="http://www.w3.org/2000/svg" width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round" class="empty-icon">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
            <p class="state-title">{$t('searchPage.placeholder')}</p>
            <p class="state-hint">{$t('search.welcomeHint')}</p>
            <p class="state-hint search-tip">{$t('search.speakerSearchTip')}</p>
          </div>
        {:else}
          <div class="results-list">
              {#if allSemanticOnly}
                <div class="no-keyword-notice">
                  <p>{$t('search.noKeywordMatches')}</p>
                </div>
              {/if}

              {#each keywordResults as hit (hit.file_uuid)}
                <SearchResultCard
                  {hit}
                  {activePreview}
                  on:preview={handlePreview}
                  on:viewTranscript={handleViewTranscript}
                />
              {/each}

              {#if semanticHighResults.length > 0 && keywordResults.length > 0}
                {#each semanticHighResults as hit (hit.file_uuid)}
                  <SearchResultCard
                    {hit}
                    {activePreview}
                    on:preview={handlePreview}
                    on:viewTranscript={handleViewTranscript}
                  />
                {/each}
              {:else if semanticHighResults.length > 0}
                {#each semanticHighResults as hit (hit.file_uuid)}
                  <SearchResultCard
                    {hit}
                    {activePreview}
                    on:preview={handlePreview}
                    on:viewTranscript={handleViewTranscript}
                  />
                {/each}
              {/if}

              {#if semanticLowResults.length > 0}
                {#if keywordResults.length > 0 || semanticHighResults.length > 0}
                  <div class="related-divider">
                    <span>{$t('search.relatedResults')}</span>
                  </div>
                {/if}
                {#each semanticLowResults as hit (hit.file_uuid)}
                  <SearchResultCard
                    {hit}
                    {activePreview}
                    on:preview={handlePreview}
                    on:viewTranscript={handleViewTranscript}
                  />
                {/each}
              {/if}
          </div>

          {#if $searchStore.totalPages > 1}
            <SearchPagination
              page={$searchStore.page}
              totalPages={$searchStore.totalPages}
              on:pageChange={handlePageChange}
            />
          {/if}
        {/if}
      </main>
    </div>
  </div>

  <!-- Sticky Floating Preview Player -->
  {#if previewData}
    <div class="sticky-preview">
      <div class="preview-header">
        <div class="preview-info">
          <span class="preview-title">
            {#if isAudioPreview}
              <svg class="preview-media-icon" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                <line x1="12" y1="19" x2="12" y2="23"></line>
                <line x1="8" y1="23" x2="16" y2="23"></line>
              </svg>
            {:else}
              <svg class="preview-media-icon" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="23 7 16 12 23 17 23 7"></polygon>
                <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
              </svg>
            {/if}
            {previewData.title}
          </span>
          <span class="preview-playback-info">
            <span class="preview-time">{formatPlaybackTime(previewCurrentTime)}</span>
            {#if previewCurrentSpeaker}
              <span class="preview-separator">|</span>
              <span class="preview-speaker-name">{previewCurrentSpeaker}</span>
            {/if}
          </span>
        </div>
        <div class="preview-actions">
          <a class="preview-detail-link" href="/files/{previewData.fileUuid}?t={previewCurrentTime || previewData.startTime}">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
              <polyline points="15 3 21 3 21 9"></polyline>
              <line x1="10" y1="14" x2="21" y2="3"></line>
            </svg>
            {$t('search.jumpTo')}
          </a>
          <button class="preview-close" on:click={closePreview} title="Close">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
      </div>
      <div class="preview-player-container" class:audio-preview={isAudioPreview}>
        {#if previewSeeking}
          <div class="preview-seek-overlay">
            <div class="preview-seek-spinner"></div>
          </div>
        {/if}
        {#if isAudioPreview}
          <!-- svelte-ignore a11y-media-has-caption -->
          <audio
            bind:this={previewMediaElement}
            preload="auto"
          >
            <source src="/api/files/{previewData.fileUuid}/simple-video" />
          </audio>
          <div class="preview-waveform">
            <WaveformPlayer
              fileId={previewData.fileUuid}
              duration={previewPlayer?.duration || 0}
              currentTime={previewCurrentTime}
              height={60}
              on:seek={handleWaveformSeek}
            />
          </div>
        {:else}
          <!-- svelte-ignore a11y-media-has-caption -->
          <video
            bind:this={previewMediaElement}
            preload="auto"
          >
            <source src="/api/files/{previewData.fileUuid}/simple-video" />
          </video>
        {/if}
      </div>
    </div>
  {/if}

  <SearchTranscriptModal
    bind:isOpen={transcriptModalOpen}
    fileUuid={transcriptModalFileUuid}
    fileName={transcriptModalFileName}
    searchQuery={$searchStore.query}
    occurrences={transcriptModalOccurrences}
    on:close={() => transcriptModalOpen = false}
  />
</div>

<style>
  .search-page {
    display: flex;
    height: calc(100vh - 60px);
    overflow: hidden;
    padding-top: 0;
  }

  /* Filter Sidebar - matches gallery styling exactly */
  .filter-sidebar {
    flex-shrink: 0;
    background-color: var(--surface-color);
    border-right: 1px solid var(--border-color);
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  /* Only animate after initial mount to prevent flicker on navigation */
  .filter-sidebar.animate {
    transition: width 0.3s ease;
  }

  /* Expanded state */
  .filter-sidebar.show {
    width: 320px;
  }

  /* Collapsed state */
  .filter-sidebar:not(.show) {
    width: 50px;
  }

  .filter-toggle-container {
    padding: 0.5rem 0.5rem 0;
    margin-bottom: 0.5rem;
    flex-shrink: 0;
  }

  .filter-sidebar.show .filter-toggle-container {
    padding: 0.5rem 1rem 0;
  }

  .filter-toggle-btn {
    width: 100%;
    background-color: var(--bg-primary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 0.6rem 1rem;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    height: 40px;
    white-space: nowrap;
  }

  .filter-toggle-btn:hover {
    background-color: var(--hover-color);
    border-color: var(--primary-color);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
  }

  .filter-toggle-btn:active {
    transform: scale(0.98);
  }

  .filter-toggle-btn svg {
    flex-shrink: 0;
    opacity: 0.8;
  }

  .filter-toggle-btn.collapsed {
    justify-content: center;
    padding: 0.6rem;
    width: auto;
  }

  .filter-content {
    flex: 1;
    overflow-y: auto;
    padding: 0 1rem;
  }

  /* Content Area */
  .content-area {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  .scrollable-content {
    flex: 1;
    overflow-y: scroll;
    padding: 1.5rem;
  }

  /* Header */
  .search-header {
    margin-bottom: 1.5rem;
  }

  .search-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text-color, #111827);
    margin: 0 0 1rem;
  }

  .search-bar {
    display: flex;
    gap: 0.5rem;
  }

  .search-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 52px;
    height: 44px;
    padding: 0 1rem;
    flex-shrink: 0;
    background-color: var(--primary-color, #3b82f6);
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .search-btn:hover:not(:disabled) {
    background-color: var(--primary-color-dark, #2563eb);
    transform: translateY(-1px);
  }

  .search-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  /* Results Info */
  .results-info {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.75rem;
    margin-top: 1rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--border-color, #e5e7eb);
  }

  .result-summary {
    font-size: 0.8125rem;
    color: var(--text-secondary, #6b7280);
  }

  .results-controls {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  /* Search Mode Toggle - sliding pill style */
  .mode-toggle {
    display: flex;
    background: var(--hover-color, #f1f5f9);
    border-radius: 8px;
    padding: 2px;
    gap: 0;
  }

  .mode-btn {
    padding: 0.375rem 0.75rem;
    background: transparent;
    border: none;
    border-radius: 6px;
    color: var(--text-secondary, #6b7280);
    font-size: 0.75rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .mode-btn.active {
    background: var(--primary-color, #4f46e5);
    color: white;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
  }

  .mode-btn:hover:not(.active) {
    color: var(--text-color, #374151);
  }


  /* Results */
  .results {
    min-height: 300px;
    width: 100%;
  }

  .results-list {
    display: flex;
    flex-direction: column;
  }

  /* Empty / Loading States */
  .state-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 4rem 2rem;
    text-align: center;
  }

  .state-container.error {
    color: var(--error-color, #ef4444);
  }

  .state-container svg {
    color: var(--text-secondary, #d1d5db);
    margin-bottom: 1rem;
  }

  .state-container.error svg {
    color: var(--error-color, #ef4444);
  }

  .state-title {
    font-size: 1rem;
    font-weight: 500;
    color: var(--text-color, #374151);
    margin: 0 0 0.375rem;
  }

  .state-text {
    font-size: 0.9375rem;
    color: var(--text-secondary, #6b7280);
    margin: 0;
  }

  .state-hint {
    font-size: 0.8125rem;
    color: var(--text-secondary, #9ca3af);
    margin: 0;
  }

  .search-tip {
    margin-top: 0.75rem;
    font-size: 0.75rem;
    font-style: italic;
    opacity: 0.7;
  }

  .empty-icon {
    opacity: 0.35;
  }

  .loading-spinner {
    width: 36px;
    height: 36px;
    border: 3px solid var(--border-color, #e5e7eb);
    border-top-color: var(--primary-color, #4f46e5);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    margin-bottom: 1rem;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  /* Sticky Floating Preview Player */
  .sticky-preview {
    position: fixed;
    bottom: 1rem;
    right: 1rem;
    width: 400px;
    max-width: calc(100vw - 2rem);
    background: var(--surface-color, #fff);
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15), 0 2px 8px rgba(0, 0, 0, 0.08);
    z-index: 1000;
    overflow: hidden;
  }

  .preview-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0.75rem;
    background: var(--surface-color, #f9fafb);
    border-bottom: 1px solid var(--border-color, #e5e7eb);
  }

  .preview-info {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    min-width: 0;
    flex: 1;
  }

  .preview-title {
    font-size: 0.8125rem;
    font-weight: 600;
    color: var(--text-color, #111827);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
  }

  .preview-media-icon {
    flex-shrink: 0;
    opacity: 0.7;
  }

  .preview-playback-info {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.75rem;
  }

  .preview-time {
    font-family: monospace;
    font-weight: 600;
    color: var(--primary-color, #4f46e5);
  }

  .preview-separator {
    color: var(--text-secondary, #9ca3af);
  }

  .preview-speaker-name {
    color: var(--text-secondary, #6b7280);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .preview-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
    margin-left: 0.5rem;
  }

  .preview-detail-link {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.75rem;
    color: var(--primary-color, #4f46e5);
    text-decoration: none;
    padding: 0.25rem 0.5rem;
    border-radius: 6px;
    transition: background 0.15s;
  }

  .preview-detail-link:hover {
    background: rgba(79, 70, 229, 0.08);
  }

  .preview-close {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    padding: 0;
    border: none;
    border-radius: 6px;
    background: none;
    color: var(--text-secondary);
    cursor: pointer;
    transition: color 0.2s ease, background 0.2s ease;
  }

  .preview-close:hover {
    color: var(--text-color);
    background: var(--button-hover, var(--background-color));
  }

  .preview-player-container {
    position: relative;
  }

  .preview-seek-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.45);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
    pointer-events: none;
    border-radius: 0;
  }

  .preview-seek-spinner {
    width: 28px;
    height: 28px;
    border: 3px solid rgba(255, 255, 255, 0.2);
    border-left-color: white;
    border-radius: 50%;
    animation: preview-spin 0.8s linear infinite;
  }

  @keyframes preview-spin {
    to { transform: rotate(360deg); }
  }

  /* Audio preview layout */
  .preview-player-container.audio-preview {
    display: flex;
    flex-direction: column;
  }

  .preview-waveform {
    width: 100%;
    padding: 0.5rem 0.5rem 0;
    background: var(--surface-color);
  }

  .preview-player-container.audio-preview :global(audio) {
    width: 100%;
  }

  /* Audio Plyr styles to match file detail page */
  .preview-player-container.audio-preview :global(.plyr--audio) {
    overflow: visible !important;
    transform: none !important;
    background: var(--surface-color) !important;
    color: var(--text-color) !important;
  }

  .preview-player-container.audio-preview :global(.plyr--audio .plyr__controls) {
    background: var(--surface-color) !important;
    border-color: var(--border-color) !important;
    padding-top: 28px !important;
  }

  .preview-player-container.audio-preview :global(.plyr--audio .plyr__progress) {
    position: absolute !important;
    top: 6px !important;
    left: 8px !important;
    right: 8px !important;
    width: calc(100% - 16px) !important;
    height: auto !important;
    margin: 0 !important;
    padding: 0 !important;
    z-index: 10 !important;
  }

  .preview-player-container.audio-preview :global(.plyr--audio .plyr__progress input[type="range"]::-webkit-slider-track) {
    height: 6px !important;
    border-radius: 3px !important;
  }

  .preview-player-container.audio-preview :global(.plyr--audio .plyr__progress input[type="range"]::-moz-range-track) {
    height: 6px !important;
    border-radius: 3px !important;
  }

  .preview-player-container.audio-preview :global(.plyr--audio .plyr__progress input[type="range"]::-webkit-slider-thumb) {
    width: 16px !important;
    height: 16px !important;
    border-radius: 50% !important;
    background: var(--primary-color) !important;
    border: none !important;
    cursor: pointer !important;
  }

  .preview-player-container.audio-preview :global(.plyr--audio .plyr__progress input[type="range"]::-moz-range-thumb) {
    width: 16px !important;
    height: 16px !important;
    border-radius: 50% !important;
    background: var(--primary-color) !important;
    border: none !important;
    cursor: pointer !important;
  }

  :global(.dark) .preview-player-container.audio-preview :global(.plyr--audio .plyr__progress input[type="range"]::-webkit-slider-thumb) {
    background: white !important;
  }

  :global(.dark) .preview-player-container.audio-preview :global(.plyr--audio .plyr__progress input[type="range"]::-moz-range-thumb) {
    background: white !important;
  }

  /* When hovering a control, raise it above the progress bar (z-index: 10)
     so the tooltip is not hidden behind the progress bar */
  .preview-player-container.audio-preview :global(.plyr--audio .plyr__control:hover) {
    z-index: 20 !important;
  }

  .preview-player-container.audio-preview :global(.plyr--audio .plyr__tooltip) {
    z-index: 99999 !important;
  }

  .preview-player-container.audio-preview :global(.plyr--audio .plyr__control:not([data-plyr="speed"])) {
    color: var(--text-color) !important;
  }

  .preview-player-container.audio-preview :global(.plyr--audio .plyr__control:not([data-plyr="speed"]):hover) {
    background: var(--hover-color) !important;
    color: var(--text-color) !important;
  }

  .preview-player-container.audio-preview :global(.plyr--audio .plyr__time) {
    color: var(--text-color) !important;
    font-size: 13px !important;
  }

  .preview-player-container.audio-preview :global(.plyr--audio .plyr__volume input[type="range"]) {
    color: var(--primary-color) !important;
  }

  .preview-player-container :global(video) {
    width: 100%;
    max-height: 240px;
    display: block;
    background: #000;
  }

  /* Allow full size in fullscreen mode */
  .preview-player-container :global(.plyr--fullscreen-active video),
  .preview-player-container :global(.plyr--fullscreen-enabled video) {
    max-height: none;
  }

  :global(.plyr--fullscreen-active video),
  :global(.plyr:fullscreen video) {
    max-height: none !important;
    width: 100% !important;
    height: 100% !important;
    object-fit: contain;
  }

  .preview-player-container :global(.plyr) {
    border-radius: 0;
    overflow: hidden;
  }

  /* Video control hover backgrounds */
  .preview-player-container :global(.plyr--video .plyr__control:not([data-plyr="settings"]):hover) {
    background: rgba(255, 255, 255, 0.25) !important;
  }

  .preview-player-container :global(.plyr--video .plyr__control[data-plyr="play"]:hover) {
    background: rgba(255, 255, 255, 0.25) !important;
  }

  /* CC button - transparent background */
  .preview-player-container :global(.plyr--video .plyr__control[data-plyr="captions"]) {
    background: transparent !important;
    color: white !important;
  }

  .preview-player-container :global(.plyr--video .plyr__control[data-plyr="captions"]:hover) {
    background: rgba(255, 255, 255, 0.25) !important;
    color: white !important;
  }

  /* Settings button - transparent background with white icon */
  .preview-player-container :global(.plyr--video .plyr__control[data-plyr="settings"]) {
    background: transparent !important;
    color: white !important;
  }

  .preview-player-container :global(.plyr--video .plyr__control[data-plyr="settings"]:hover) {
    background: rgba(255, 255, 255, 0.25) !important;
    color: white !important;
  }

  .preview-player-container :global(.plyr--video .plyr__control[data-plyr="settings"] svg) {
    color: white !important;
    fill: white !important;
  }

  .preview-player-container :global(.plyr--video .plyr__controls__item.plyr__menu) {
    background: transparent !important;
    border: none !important;
  }

  /* YouTube-style progress bar positioning - above controls */
  .preview-player-container :global(.plyr--video .plyr__controls) {
    position: absolute !important;
    bottom: 0 !important;
    left: 0 !important;
    right: 0 !important;
    padding-top: 12px !important;
  }

  .preview-player-container :global(.plyr--video .plyr__progress) {
    position: absolute !important;
    top: -8px !important;
    left: 0 !important;
    right: 0 !important;
    width: 100% !important;
    height: auto !important;
    margin: 0 !important;
    padding: 0 !important;
    z-index: 10 !important;
  }

  .preview-player-container :global(.plyr--video .plyr__progress input[type="range"]) {
    width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
  }

  .preview-player-container :global(.plyr--video .plyr__progress input[type="range"]::-webkit-slider-track) {
    height: 4px !important;
  }

  .preview-player-container :global(.plyr--video .plyr__progress input[type="range"]::-moz-range-track) {
    height: 4px !important;
  }

  .preview-player-container :global(.plyr--video .plyr__progress:hover input[type="range"]::-webkit-slider-track) {
    height: 6px !important;
  }

  .preview-player-container :global(.plyr--video .plyr__progress:hover input[type="range"]::-moz-range-track) {
    height: 6px !important;
  }

  /* Time display formatting */
  .preview-player-container :global(.plyr__time) {
    margin-left: 8px !important;
    margin-right: 2px !important;
    font-size: 14px !important;
    color: rgba(255, 255, 255, 0.9) !important;
  }

  .preview-player-container :global(.plyr__time--current-time::after) {
    content: " / " !important;
    color: rgba(255, 255, 255, 0.7) !important;
  }

  .preview-player-container :global(.plyr__time--duration) {
    margin-left: 0 !important;
    margin-right: 16px !important;
  }

  .preview-player-container :global(.plyr__control) {
    margin-right: 4px !important;
  }

  /* Volume thumb hover */
  .preview-player-container :global(.plyr--video .plyr__volume input[type="range"]::-webkit-slider-thumb:hover) {
    background: #ffffff !important;
  }

  .preview-player-container :global(.plyr--video .plyr__volume input[type="range"]::-moz-range-thumb:hover) {
    background: #ffffff !important;
  }

  /* Settings menu styling for dark mode */
  .preview-player-container :global(.plyr--video .plyr__menu) {
    background: var(--surface-color) !important;
    border: none !important;
    color: var(--text-color) !important;
  }

  .preview-player-container :global(.plyr--video [role="menu"]) {
    background: var(--surface-color) !important;
  }

  .preview-player-container :global(.plyr--video .plyr__menu .plyr__control) {
    color: var(--text-color) !important;
    background: transparent !important;
  }

  .preview-player-container :global(.plyr--video .plyr__menu .plyr__control:hover) {
    background: var(--hover-color) !important;
    color: var(--text-color) !important;
  }

  .preview-player-container :global(.plyr--video button[data-plyr="speed"]),
  .preview-player-container :global(.plyr--video button[data-plyr="captions"]) {
    color: var(--text-color) !important;
    background: transparent !important;
    border: none !important;
  }

  .preview-player-container :global(.plyr--video button[data-plyr="speed"]:hover),
  .preview-player-container :global(.plyr--video button[data-plyr="captions"]:hover) {
    background: var(--hover-color) !important;
    color: var(--text-color) !important;
  }

  .preview-player-container :global(.plyr--video button[data-plyr="speed"][aria-checked="true"]),
  .preview-player-container :global(.plyr--video button[data-plyr="captions"][aria-checked="true"]) {
    background: var(--primary-color) !important;
    color: white !important;
  }

  .preview-player-container :global(.plyr--video button[data-plyr="speed"] span),
  .preview-player-container :global(.plyr--video button[data-plyr="captions"] span) {
    color: inherit !important;
  }

  .preview-player-container :global(.plyr--video .plyr__menu__value),
  .preview-player-container :global(.plyr--video .plyr__badge) {
    color: inherit !important;
  }

  .preview-player-container :global(.plyr--video button.plyr__control--back) {
    color: var(--text-color) !important;
    background: var(--surface-color) !important;
    border: none !important;
  }

  .preview-player-container :global(.plyr--video button.plyr__control--back:hover) {
    background: var(--hover-color) !important;
    color: var(--text-color) !important;
  }

  .preview-player-container :global(.plyr--video button.plyr__control--back span) {
    color: inherit !important;
  }

  .no-keyword-notice {
    padding: 12px 16px;
    margin-bottom: 12px;
    background: var(--color-warning-bg, #fef3c7);
    color: var(--color-warning-text, #92400e);
    border-radius: 8px;
    font-size: 0.9rem;
  }

  :global(.dark) .no-keyword-notice {
    background: rgba(245, 158, 11, 0.1);
    color: #fbbf24;
  }

  .related-divider {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 20px 0 12px;
    color: var(--text-secondary, #6b7280);
    font-size: 0.85rem;
  }

  .related-divider::before,
  .related-divider::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border-color, #e5e7eb);
  }

  :global(.dark) .related-divider {
    color: #9ca3af;
  }

  :global(.dark) .related-divider::before,
  :global(.dark) .related-divider::after {
    background: #374151;
  }

  /* Responsive */
  @media (max-width: 768px) {
    .search-page {
      flex-direction: column;
    }

    .filter-sidebar {
      width: 100% !important;
      min-width: 100% !important;
      height: auto;
      max-height: 50vh;
      border-right: none;
      border-bottom: 1px solid var(--border-color, #e5e7eb);
    }

    .filter-sidebar:not(.show) {
      width: 100% !important;
      min-width: 100% !important;
      max-height: none;
    }

    .scrollable-content {
      padding: 1rem;
    }

    .results-info {
      flex-direction: column;
      align-items: flex-start;
    }

    .search-title {
      font-size: 1.25rem;
    }

    .sticky-preview {
      width: calc(100vw - 1rem);
      right: 0.5rem;
      bottom: 0.5rem;
    }
  }
</style>
