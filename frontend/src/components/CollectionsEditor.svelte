<script>
  // @ts-nocheck
  import { createEventDispatcher, onMount } from 'svelte';
  import axiosInstance from '../lib/axios';
  import { toastStore } from '$stores/toast';
  
  /** @type {number} */
  export let fileId = 0;
  /** @type {Array<{id: number, name: string, description?: string}>} */
  export let collections = [];
  
  // Ensure collections are always in the correct format
  $: {
    if (Array.isArray(collections)) {
      collections = collections.map(collection => {
        if (collection && typeof collection === 'object') {
          return { 
            id: collection.id || `temp-${collection.name}`,
            name: collection.name || '',
            description: collection.description || ''
          };
        }
        return collection;
      });
    }
  }
  
  /** @type {Array<{id: number, name: string, description?: string, media_count: number}>} */
  let allCollections = [];
  /** @type {string} */
  let newCollectionInput = '';
  /** @type {boolean} */
  let loading = false;
  /** @type {string|null} */
  let error = null;
  
  // Event dispatcher
  const dispatch = createEventDispatcher();
  
  // Fetch all available collections
  async function fetchAllCollections() {
    error = null;
    try {
      const response = await axiosInstance.get('/api/collections/');
      
      // Ensure all collections have valid IDs
      const validCollections = (response.data || []).filter(collection => 
        collection && typeof collection === 'object' && 
        collection.id !== undefined && collection.id !== null && 
        collection.name !== undefined && collection.name !== null
      );
      
      allCollections = validCollections;
    } catch (err) { 
      console.error('[CollectionsEditor] Error fetching collections:', err);
      console.error('[CollectionsEditor] Error details:', {
        message: err.message,
        status: err.response?.status,
        data: err.response?.data
      });
      
      if (err.response && err.response.status === 401) {
        error = 'Unauthorized: Please log in.';
      } else if (err.code === 'ERR_NETWORK') {
        error = 'Network error: Cannot connect to server';
      } else {
        error = 'Failed to load collections';
      }
    }
  }
  
  // Add file to an existing collection
  async function addToCollection(collectionId) {
    loading = true;
    error = null;
    try {
      const collectionToAdd = allCollections.find(c => c.id === collectionId);
      if (!collectionToAdd) {
        console.error(`[CollectionsEditor] Collection with ID ${collectionId} not found`);
        throw new Error('Collection not found');
      }
      
      // Add file to collection
      const payload = { media_file_ids: [fileId] };
      const addUrl = `/api/collections/${collectionId}/media`;
      const response = await axiosInstance.post(addUrl, payload);
      
      // Add collection to local list if not already present
      if (!collections.some(c => c.id === collectionToAdd.id)) {
        collections = [...collections, collectionToAdd];
        dispatch('collectionsUpdated', { collections });
        toastStore.success(`Added to "${collectionToAdd.name}"`);
      }
    } catch (err) {
      console.error('[CollectionsEditor] Error adding to collection:', err);
      if (err.response && err.response.status === 401) {
        error = 'Unauthorized: Please log in.';
      } else {
        error = 'Failed to add to collection';
      }
      toastStore.error('Failed to add to collection');
    } finally {
      loading = false;
    }
  }
  
  // Create a new collection and optionally add current file to it
  async function createAndAddCollection() {
    if (!newCollectionInput.trim()) return;
    loading = true;
    error = null;
    try {
      // Step 1: Create the collection
      const createPayload = { 
        name: newCollectionInput.trim()
      };
      
      const createResponse = await axiosInstance.post('/api/collections/', createPayload);
      const newCollection = createResponse.data;
      
      if (!newCollection || typeof newCollection.id === 'undefined') {
        console.error('[CollectionsEditor] Invalid collection received from server:', newCollection);
        throw new Error('Server returned an invalid collection');
      }
      
      // Add to allCollections if it's not already present
      if (!allCollections.some(c => c.id === newCollection.id)) {
        allCollections = [...allCollections, { ...newCollection, media_count: 0 }];
      }
      
      // Step 2: Add current file to the new collection
      const addPayload = { media_file_ids: [fileId] };
      const addResponse = await axiosInstance.post(`/api/collections/${newCollection.id}/media`, addPayload);
      
      // Add to collections if it's not already present
      if (!collections.some(c => c.id === newCollection.id)) {
        collections = [...collections, newCollection];
        newCollectionInput = '';
        dispatch('collectionsUpdated', { collections });
        toastStore.success(`Created collection "${newCollection.name}" and added file`);
      } else {
        newCollectionInput = '';
        toastStore.success(`Created collection "${newCollection.name}"`);
      }
    } catch (err) {
      console.error('[CollectionsEditor] Error creating collection:', err);
      if (err && typeof err === 'object') {
        if (err.response && err.response.status === 401) {
          error = 'Unauthorized: Please log in.';
        } else if (
          err.response && 
          err.response.data && 
          typeof err.response.data === 'object' && 
          'detail' in err.response.data
        ) {
          error = `Failed to create collection: ${err.response.data.detail}`;
        } else {
          error = 'Failed to create collection';
        }
      } else {
        error = 'Failed to create collection';
      }
      toastStore.error(error || 'Failed to create collection');
    } finally {
      loading = false;
    }
  }
  
  // Remove file from a collection
  async function removeFromCollection(collectionId) {
    loading = true;
    error = null;
    try {
      const collectionToRemove = collections.find(c => c.id === collectionId);
      if (!collectionToRemove) {
        console.error(`[CollectionsEditor] Collection with ID ${collectionId} not found in collections list`);
        throw new Error('Collection not found');
      }
      
      // Remove file from collection
      const deleteUrl = `/api/collections/${collectionId}/media`;
      const payload = { media_file_ids: [fileId] };
      await axiosInstance.delete(deleteUrl, { data: payload });
      
      // Update the local collections array
      const updatedCollections = collections.filter(c => 
        c.id !== undefined && c.id !== null && c.id !== collectionId
      );
      
      if (updatedCollections.length !== collections.length) {
        collections = updatedCollections;
        dispatch('collectionsUpdated', { collections });
        toastStore.success(`Removed from "${collectionToRemove.name}"`);
      }
    } catch (err) {
      console.error('[CollectionsEditor] Error removing from collection:', err);
      if (err.response && err.response.status === 401) {
        error = 'Unauthorized: Please log in.';
      } else if (err.code === 'ERR_NETWORK') {
        error = 'Network error: Cannot connect to server';
      } else {
        error = 'Failed to remove from collection';
      }
      toastStore.error('Failed to remove from collection');
    } finally {
      loading = false;
    }
  }
  
  // Handle keydown event in the input field
  function handleInputKeydown(event) {
    if (event.key === 'Enter' && newCollectionInput.trim()) {
      event.preventDefault();
      createAndAddCollection();
    }
  }
  
  let suggestedCollections = [];
  
  // Get suggested collections (those that the file isn't already in)
  // Show only the 5 most recently created collections as suggestions
  $: suggestedCollections = allCollections
    .filter(collection => !collections.some(c => 
      (c.id === collection.id) || (c.name === collection.name)
    ))
    .sort((a, b) => b.id - a.id) // Sort by ID descending (newer collections first)
    .slice(0, 5); // Limit to only 5 most recent collections
  
  onMount(() => {
    fetchAllCollections();
  });
</script>

<div class="collections-editor">
  {#if error && !(error === 'Failed to load collections' && collections.length === 0)}
    <div class="error-message">
      {error}
    </div>
  {/if}
  
  <div class="collections-list">
    {#if collections.length === 0}
      <span class="no-collections">No collections yet.</span>
    {/if}
    {#each collections.filter(c => c && c.id !== undefined) as collection (collection.id)}
      <span class="collection">
        {collection.name}
        <button class="collection-remove" on:click={() => removeFromCollection(collection.id)} title="Remove from collection">×</button>
      </span>
    {/each}
    
    <div class="collection-input-container">
      <input
        type="text"
        placeholder="Add collection..."
        bind:value={newCollectionInput}
        on:keydown={handleInputKeydown}
        class="collection-input"
        disabled={loading}
        title="Type a new collection name and press Enter or click Add to create and apply it to this file"
      >
      {#if newCollectionInput.trim()}
        <button 
          class="collection-add-button"
          on:click={createAndAddCollection}
          disabled={loading}
          title="Create and add the collection '{newCollectionInput.trim()}' to this file"
        >
          Add
        </button>
      {/if}
    </div>
  </div>
  
  {#if suggestedCollections.length > 0}
    <div class="suggested-collections">
      <span class="suggested-label">Suggested:</span>
      {#each suggestedCollections.filter(c => c && c.id !== undefined) as collection (collection.id)}
        <button 
          class="suggested-collection"
          on:click={() => addToCollection(collection.id)}
          disabled={loading}
          title="Add to existing collection '{collection.name}'"
        >
          {collection.name}
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .collections-editor {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .collections-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: center;
  }
  
  .collection {
    background-color: rgba(59, 130, 246, 0.1);
    color: var(--primary-color);
    padding: 0.35rem 0.5rem;
    border-radius: 4px;
    font-size: 0.8rem;
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }
  
  .collection-remove {
    background: none;
    border: none;
    color: var(--text-light);
    font-size: 1rem;
    cursor: pointer;
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
  }
  
  .collection-remove:hover {
    color: var(--error-color);
  }
  
  .collection-input-container {
    display: flex;
    align-items: center;
  }
  
  .collection-input {
    background: transparent;
    border: none;
    border-bottom: 1px dashed var(--border-color);
    padding: 0.35rem 0;
    font-size: 0.8rem;
    width: 100px;
    color: var(--text-color);
  }
  
  .collection-input:focus {
    border-bottom-color: var(--primary-color);
    outline: none;
  }
  
  .collection-add-button {
    background-color: var(--primary-color);
    color: white;
    border: none;
    border-radius: 4px;
    padding: 0.25rem 0.5rem;
    font-size: 0.8rem;
    cursor: pointer;
    margin-left: 0.5rem;
  }
  
  .collection-add-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  .suggested-collections {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: center;
    font-size: 0.8rem;
  }
  
  .suggested-label {
    color: var(--text-light);
  }
  
  .suggested-collection {
    background: none;
    border: 1px dashed var(--border-color);
    border-radius: 4px;
    padding: 0.25rem 0.5rem;
    font-size: 0.8rem;
    cursor: pointer;
    color: var(--text-light);
  }
  
  .suggested-collection:hover {
    border-color: var(--primary-color);
    color: var(--primary-color);
    background-color: rgba(59, 130, 246, 0.05);
  }
  
  .suggested-collection:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  .error-message {
    background-color: rgba(239, 68, 68, 0.1);
    color: var(--error-color);
    padding: 0.6rem;
    border-radius: 4px;
    font-size: 0.85rem;
    border: 1px solid rgba(239, 68, 68, 0.2);
  }
  
  .no-collections {
    color: var(--text-secondary);
    font-size: 0.85rem;
    font-style: italic;
    padding: 0.5rem 0;
  }
  
  /* Dark mode support */
  :global(.dark) .collection {
    background: rgba(59, 130, 246, 0.2);
    color: #93bbfc;
  }
  
  :global(.dark) .suggested-collection:hover {
    background-color: rgba(59, 130, 246, 0.1);
  }
</style>