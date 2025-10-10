<script lang="ts">
  import { onMount } from 'svelte';
  import { createEventDispatcher } from 'svelte';
  import axiosInstance from '$lib/axios';
  import SearchableMultiSelect from './SearchableMultiSelect.svelte';

  export let selectedCollectionId: string | null = null;

  let collections: any[] = [];
  let loading = false;
  let dropdownCollections: any[] = [];

  const dispatch = createEventDispatcher();

  // Reactive: Prepare dropdown collections with proper format
  $: dropdownCollections = collections.map(collection => ({
    id: collection.id,
    name: collection.name,
    count: collection.media_count || 0
  }));

  // Reactive: Convert selected collection ID to array for multiselect (single selection mode)
  $: selectedCollectionIds = selectedCollectionId ? [selectedCollectionId] : [];

  export async function fetchCollections() {
    loading = true;
    try {
      const response = await axiosInstance.get('/api/collections/');
      // Sort collections by media_count descending (most used first)
      collections = (response.data || []).sort((a: any, b: any) => {
        return (b.media_count || 0) - (a.media_count || 0);
      });
    } catch (err) {
      console.error('Error fetching collections:', err);
    } finally {
      loading = false;
    }
  }

  /**
   * Handle collection selection from multiselect dropdown
   * Single selection mode: only one collection can be selected at a time
   * @param {CustomEvent} event - Event with collection id
   */
  function handleCollectionSelect(event: CustomEvent) {
    const collectionId = event.detail.id;
    // If clicking the same collection, deselect it
    if (selectedCollectionId === collectionId) {
      selectedCollectionId = null;
    } else {
      // Otherwise, select the new collection (replacing any previous selection)
      selectedCollectionId = collectionId;
    }
  }

  /**
   * Handle collection deselection from multiselect dropdown
   * @param {CustomEvent} event - Event with collection id
   */
  function handleCollectionDeselect(event: CustomEvent) {
    selectedCollectionId = null;
  }

  onMount(() => {
    fetchCollections();
  });
</script>

<div class="collections-filter">
  {#if loading}
    <p class="loading-text">Loading collections...</p>
  {:else if collections.length === 0}
    <p class="empty-text">No collections created yet</p>
  {:else}
    <div class="dropdown-section">
      <SearchableMultiSelect
        options={dropdownCollections}
        selectedIds={selectedCollectionIds}
        placeholder="Select collection to filter..."
        maxHeight="300px"
        showCounts={true}
        on:select={handleCollectionSelect}
        on:deselect={handleCollectionDeselect}
      />
    </div>
  {/if}
</div>

<style>
  .collections-filter {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .loading-text,
  .empty-text {
    font-size: 0.9rem;
    color: var(--text-light);
    margin: 0;
  }

  .dropdown-section {
    margin-top: 0;
  }
</style>