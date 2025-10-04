<script lang="ts">
  import { onMount } from 'svelte';
  import { createEventDispatcher } from 'svelte';
  import axiosInstance from '$lib/axios';
  
  export let selectedCollectionId: string | null = null;

  let collections: any[] = [];
  let loading = false;

  const dispatch = createEventDispatcher();

  export async function fetchCollections() {
    loading = true;
    try {
      const response = await axiosInstance.get('/api/collections/');
      collections = response.data;
    } catch (err) {
      console.error('Error fetching collections:', err);
    } finally {
      loading = false;
    }
  }

  function handleCollectionChange(event: Event) {
    const target = event.target as HTMLSelectElement;
    const value = target.value;
    selectedCollectionId = value === '' ? null : value;
  }
  
  onMount(() => {
    fetchCollections();
  });
</script>

<div class="collections-filter">
  <select 
    id="collection-select"
    bind:value={selectedCollectionId}
    on:change={handleCollectionChange}
    disabled={loading}
    class="filter-select"
  >
    <option value="">All Files</option>
    {#each collections as collection}
      <option value={collection.id}>{collection.name} ({collection.media_count || 0})</option>
    {/each}
  </select>
</div>

<style>
  .collections-filter {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .filter-select {
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 0.9rem;
    background-color: var(--background-color);
    color: var(--text-color);
    cursor: pointer;
    transition: border-color 0.2s;
  }
  
  .filter-select:hover:not(:disabled) {
    border-color: var(--primary-color);
  }
  
  .filter-select:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  }
  
  .filter-select:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  /* Dark mode support - match filter-input styling */
  :global(.dark) .filter-select {
    background-color: var(--background-color);
    color: var(--text-primary);
    border-color: var(--border-color);
  }
  
  :global(.dark) .filter-select:hover:not(:disabled) {
    border-color: var(--primary-color);
  }
  
  :global(.dark) .filter-select:focus {
    background-color: var(--background-color);
    border-color: var(--primary-color);
  }
  
  .filter-select option {
    color: var(--text-primary);
  }
  
  :global(.dark) .filter-select option {
    color: var(--text-primary);
  }
</style>