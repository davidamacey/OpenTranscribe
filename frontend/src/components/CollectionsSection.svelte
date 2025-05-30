<script lang="ts">
  import { slide } from 'svelte/transition';
  import { createEventDispatcher } from 'svelte';
  import axiosInstance from '$lib/axios';
  import { toastStore } from '$stores/toast';
  
  export let collections: any[] = [];
  export let isExpanded: boolean = false;
  export let fileId: number;
  
  const dispatch = createEventDispatcher();
  
  function toggleExpanded() {
    isExpanded = !isExpanded;
  }
  
  async function removeFromCollection(collectionId: number, collectionName: string) {
    if (!confirm(`Remove this file from "${collectionName}"?`)) {
      return;
    }
    
    try {
      await axiosInstance.delete(`/api/collections/${collectionId}/media`, {
        data: { media_file_ids: [fileId] }
      });
      
      // Remove collection from local list
      collections = collections.filter(c => c.id !== collectionId);
      
      // Dispatch event to parent to refresh file data
      dispatch('collectionRemoved', { collectionId });
      
      toastStore.success(`Removed from "${collectionName}"`);
    } catch (error) {
      console.error('Error removing from collection:', error);
      toastStore.error('Failed to remove from collection');
    }
  }
</script>

<div class="collections-dropdown-section">
  <button 
    class="collections-header" 
    on:click={toggleExpanded} 
    on:keydown={e => e.key === 'Enter' && toggleExpanded()}
    title="Show or hide the collections this file belongs to" 
    aria-expanded={isExpanded}
  >
    <h4 class="section-heading">Collections</h4>
    <div class="collections-preview">
      {#if collections && collections.length > 0}
        {#each collections.slice(0, 3) as collection}
          <span class="collection-chip">{collection.name || 'Unnamed'}</span>
        {/each}
        {#if collections.length > 3}
          <span class="collection-chip more">+{collections.length - 3} more</span>
        {/if}
      {:else}
        <span class="no-collections">No collections</span>
      {/if}
    </div>
    <span class="dropdown-toggle" aria-hidden="true">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="transform: rotate({isExpanded ? '180deg' : '0deg'})">
        <polyline points="6 9 12 15 18 9"></polyline>
      </svg>
    </span>
  </button>
  
  {#if isExpanded}
    <div class="collections-content" transition:slide={{ duration: 200 }}>
      <div class="collections-full-list">
        {#if collections && collections.length > 0}
          {#each collections as collection}
            <div class="collection-item">
              <div class="collection-info">
                <span class="collection-name">{collection.name || 'Unnamed'}</span>
                {#if collection.description}
                  <span class="collection-description">{collection.description}</span>
                {/if}
              </div>
              <button 
                class="remove-btn"
                on:click={() => removeFromCollection(collection.id, collection.name || 'Unnamed')}
                title="Remove this file from the collection"
              >
                ✕
              </button>
            </div>
          {/each}
        {:else}
          <p class="no-collections-message">This file is not in any collections.</p>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .collections-dropdown-section {
    margin-bottom: 20px;
  }

  .collections-header {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 12px 16px;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .collections-header:hover {
    background: var(--surface-hover);
    border-color: var(--border-hover);
  }

  .section-heading {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .collections-preview {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    flex-wrap: wrap;
    flex: 1;
    margin: 0 12px;
  }

  .collection-chip {
    background: var(--primary-light);
    color: var(--primary-color);
    padding: 3px 8px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 500;
    display: inline-block;
  }

  .collection-chip.more {
    background: var(--surface-secondary);
    color: var(--text-secondary);
  }

  .no-collections {
    color: var(--text-secondary);
    font-size: 14px;
  }

  .dropdown-toggle svg {
    transition: transform 0.2s ease;
  }

  .collections-content {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-top: none;
    border-radius: 0 0 8px 8px;
    padding: 16px;
  }

  .collections-full-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .collection-item {
    padding: 10px 12px;
    background: var(--card-background);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    transition: all 0.2s;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
  }

  .collection-item:hover {
    background: var(--card-hover);
    border-color: var(--primary-color);
  }
  
  .collection-info {
    flex: 1;
    min-width: 0;
  }

  .collection-name {
    font-weight: 500;
    color: var(--text-primary);
    display: block;
  }

  .collection-description {
    font-size: 13px;
    color: var(--text-secondary);
    display: block;
    margin-top: 4px;
  }

  .no-collections-message {
    color: var(--text-secondary);
    font-size: 14px;
    text-align: center;
    padding: 8px;
    margin: 0;
  }
  
  .remove-btn {
    width: 24px;
    height: 24px;
    border: none;
    background-color: #ef4444;
    color: white;
    border-radius: 4px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    flex-shrink: 0;
  }
  
  .remove-btn:hover {
    background-color: #dc2626;
    transform: scale(1.1);
  }
  
  .remove-btn {
    font-size: 14px;
    line-height: 1;
    color: white !important;
    font-weight: bold;
  }
  
  /* Dark mode support */
  :global(.dark) .collection-chip {
    background: rgba(59, 130, 246, 0.2);
    color: #93bbfc;
  }
  
  :global(.dark) .collection-chip.more {
    background: rgba(255, 255, 255, 0.1);
  }
</style>