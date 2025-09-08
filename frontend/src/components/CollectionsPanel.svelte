<script lang="ts">
  import { onMount } from 'svelte';
  import { fade, slide } from 'svelte/transition';
  import axiosInstance from '$lib/axios';
  import { toastStore } from '$stores/toast';
  
  // Props
  export let selectedMediaIds: number[] = [];
  export let onCollectionSelect: (collectionId: number) => void = () => {};
  export let viewMode: 'manage' | 'add' = 'manage';
  
  // State
  let collections: any[] = [];
  let loading = false;
  let error = '';
  let showCreateModal = false;
  let showEditModal = false;
  let showDeleteConfirm = false;
  let collectionToEdit: any = null;
  let collectionToDelete: any = null;
  let newCollectionName = '';
  let newCollectionDescription = '';
  let editCollectionName = '';
  let editCollectionDescription = '';
  let creating = false;
  let updating = false;
  let deleting = false;
  let selectedCollectionId: number | null = null;
  let addingToCollection = false;
  
  // Fetch collections
  async function fetchCollections() {
    loading = true;
    error = '';
    
    try {
      const response = await axiosInstance.get('/api/collections/');
      collections = response.data;
    } catch (err: any) {
      console.error('Error fetching collections:', err);
      error = 'Failed to load collections';
    } finally {
      loading = false;
    }
  }
  
  // Create new collection
  async function createCollection() {
    if (!newCollectionName.trim()) return;
    
    creating = true;
    error = '';
    
    try {
      const response = await axiosInstance.post('/api/collections/', {
        name: newCollectionName.trim(),
        description: newCollectionDescription.trim() || null
      });
      
      collections = [...collections, { ...response.data, media_count: 0 }];
      
      // Reset form for potential next collection
      newCollectionName = '';
      newCollectionDescription = '';
      
      // If in add mode and media is selected, add to new collection
      if (viewMode === 'add' && selectedMediaIds.length > 0) {
        await addMediaToCollection(response.data.id);
        // Close create modal after adding media since the workflow is complete
        showCreateModal = false;
        // Trigger callback to refresh filters after adding media
        onCollectionSelect(response.data.id);
      } else {
        toastStore.success(`Collection "${response.data.name}" created successfully`);
        // Close the create modal but keep the manage collections modal open
        showCreateModal = false;
        // Don't trigger collection selection callback in manage mode during creation
      }
    } catch (err: any) {
      console.error('Error creating collection:', err);
      error = err.response?.data?.detail || 'Failed to create collection';
    } finally {
      creating = false;
    }
  }
  
  // Update collection
  async function updateCollection() {
    if (!collectionToEdit || !editCollectionName.trim()) return;
    
    updating = true;
    error = '';
    
    try {
      const response = await axiosInstance.put(`/api/collections/${collectionToEdit.id}`, {
        name: editCollectionName.trim(),
        description: editCollectionDescription.trim() || null
      });
      
      // Update local state
      collections = collections.map(col => 
        col.id === collectionToEdit.id ? { ...col, ...response.data } : col
      );
      
      toastStore.success(`Collection "${editCollectionName}" updated successfully`);
      showEditModal = false;
      collectionToEdit = null;
    } catch (err: any) {
      console.error('Error updating collection:', err);
      toastStore.error(err.response?.data?.detail || 'Failed to update collection');
    } finally {
      updating = false;
    }
  }
  
  // Open edit modal
  function openEditModal(collection: any) {
    collectionToEdit = collection;
    editCollectionName = collection.name;
    editCollectionDescription = collection.description || '';
    showEditModal = true;
  }
  
  // Open delete confirmation
  function openDeleteConfirm(collection: any) {
    collectionToDelete = collection;
    showDeleteConfirm = true;
  }
  
  // Delete collection
  async function deleteCollection() {
    if (!collectionToDelete) return;
    
    deleting = true;
    error = '';
    
    try {
      await axiosInstance.delete(`/api/collections/${collectionToDelete.id}`);
      collections = collections.filter(col => col.id !== collectionToDelete.id);
      
      if (selectedCollectionId === collectionToDelete.id) {
        selectedCollectionId = null;
      }
      
      toastStore.success(`Collection "${collectionToDelete.name}" deleted successfully`);
      showDeleteConfirm = false;
      collectionToDelete = null;
    } catch (err: any) {
      console.error('Error deleting collection:', err);
      toastStore.error(err.response?.data?.detail || 'Failed to delete collection');
    } finally {
      deleting = false;
    }
  }
  
  // Add selected media to collection
  async function addMediaToCollection(collectionId: number) {
    if (!selectedMediaIds.length) return;
    
    addingToCollection = true;
    error = '';
    
    try {
      const response = await axiosInstance.post(`/api/collections/${collectionId}/media`, {
        media_file_ids: selectedMediaIds
      });
      
      // Update media count
      collections = collections.map(col => 
        col.id === collectionId 
          ? { ...col, media_count: col.media_count + (response.data.added || 0) }
          : col
      );
      
      // Show success message
      const collection = collections.find(c => c.id === collectionId);
      toastStore.success(`Added ${response.data.added} file(s) to "${collection?.name || 'collection'}"`);
      
      // Trigger callback to close modal and refresh
      onCollectionSelect(collectionId);
    } catch (err: any) {
      console.error('Error adding media to collection:', err);
      error = err.response?.data?.detail || 'Failed to add media to collection';
    } finally {
      addingToCollection = false;
    }
  }
  
  // Handle collection click
  function handleCollectionClick(collection: any) {
    if (viewMode === 'manage') {
      selectedCollectionId = collection.id;
      onCollectionSelect(collection.id);
    } else if (viewMode === 'add' && selectedMediaIds.length > 0) {
      addMediaToCollection(collection.id);
    }
  }
  
  onMount(() => {
    fetchCollections();
  });
</script>

<div class="collections-panel" transition:fade>
  <div class="panel-header">
    <h3>Collections</h3>
    <button 
      class="btn-create"
      on:click={() => {
        error = '';
        showCreateModal = true;
      }}
      disabled={creating}
    >
      <span class="icon">+</span>
      New Collection
    </button>
  </div>
  
  {#if error}
    <div class="error-message" transition:slide>
      {error}
    </div>
  {/if}
  
  {#if loading}
    <div class="loading">
      <div class="spinner"></div>
      Loading collections...
    </div>
  {:else if collections.length === 0}
    <div class="empty-state">
      <p>No collections yet</p>
      <p class="hint">Create your first collection to organize your media files</p>
    </div>
  {:else}
    <div class="collections-list">
      {#each collections as collection (collection.id)}
        <div 
          class="collection-card"
          class:selected={selectedCollectionId === collection.id}
          on:click={() => handleCollectionClick(collection)}
          transition:slide
        >
          <div class="collection-info">
            <h4>{collection.name}</h4>
            {#if collection.description}
              <p class="description">{collection.description}</p>
            {/if}
            <div class="meta">
              <span class="media-count">{collection.media_count} file{collection.media_count !== 1 ? 's' : ''}</span>
              {#if collection.is_public}
                <span class="badge public">Public</span>
              {/if}
            </div>
          </div>
          
          {#if viewMode === 'manage'}
            <div class="collection-actions">
              <button
                class="edit-button"
                title="Edit collection"
                on:click|stopPropagation={() => openEditModal(collection)}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="m18.5 2.5 a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
              <button
                class="delete-config-button"
                title="Delete collection"
                on:click|stopPropagation={() => openDeleteConfirm(collection)}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="3,6 5,6 21,6"/>
                  <path d="m19,6v14a2,2 0 0,1 -2,2H7a2,2 0 0,1 -2,-2V6m3,0V4a2,2 0 0,1 2,-2h4a2,2 0 0,1 2,2v2"/>
                  <line x1="10" y1="11" x2="10" y2="17"/>
                  <line x1="14" y1="11" x2="14" y2="17"/>
                </svg>
              </button>
            </div>
          {:else if viewMode === 'add' && selectedMediaIds.length > 0}
            <button
              class="btn-add"
              disabled={addingToCollection}
              on:click|stopPropagation={() => addMediaToCollection(collection.id)}
            >
              Add {selectedMediaIds.length} file{selectedMediaIds.length !== 1 ? 's' : ''}
            </button>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
  
  <!-- Create Collection Modal -->
  {#if showCreateModal}
    <div class="modal-overlay" on:click={() => showCreateModal = false} transition:fade>
      <div class="modal" on:click|stopPropagation transition:slide>
        <div class="modal-header-custom">
          <h3>Create New Collection</h3>
          <button 
            class="modal-close-btn" 
            on:click={() => showCreateModal = false}
            type="button"
            aria-label="Close modal"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        
        <form on:submit|preventDefault={createCollection}>
          <div class="form-group">
            <label for="collection-name">Name</label>
            <input
              id="collection-name"
              type="text"
              bind:value={newCollectionName}
              placeholder="My Collection"
              required
              disabled={creating}
            />
          </div>
          
          <div class="form-group">
            <label for="collection-description">Description (optional)</label>
            <textarea
              id="collection-description"
              bind:value={newCollectionDescription}
              placeholder="Describe this collection..."
              rows="3"
              disabled={creating}
            />
          </div>
          
          <div class="modal-actions">
            <button
              type="button"
              class="btn-secondary"
              on:click={() => showCreateModal = false}
              disabled={creating}
            >
              Cancel
            </button>
            <button
              type="submit"
              class="btn-primary"
              disabled={creating || !newCollectionName.trim()}
            >
              {creating ? 'Creating...' : 'Create Collection'}
            </button>
          </div>
        </form>
      </div>
    </div>
  {/if}
  
  <!-- Edit Collection Modal -->
  {#if showEditModal && collectionToEdit}
    <div class="modal-overlay" on:click={() => showEditModal = false} transition:fade>
      <div class="modal" on:click|stopPropagation transition:slide>
        <div class="modal-header-custom">
          <h3>Edit Collection</h3>
          <button 
            class="modal-close-btn" 
            on:click={() => showEditModal = false}
            type="button"
            aria-label="Close modal"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        
        <form on:submit|preventDefault={updateCollection}>
          <div class="form-group">
            <label for="edit-collection-name">Name</label>
            <input
              id="edit-collection-name"
              type="text"
              bind:value={editCollectionName}
              placeholder="Collection Name"
              required
              disabled={updating}
            />
          </div>
          
          <div class="form-group">
            <label for="edit-collection-description">Description (optional)</label>
            <textarea
              id="edit-collection-description"
              bind:value={editCollectionDescription}
              placeholder="Describe this collection..."
              rows="3"
              disabled={updating}
            />
          </div>
          
          <div class="modal-actions">
            <button
              type="button"
              class="btn-secondary"
              on:click={() => showEditModal = false}
              disabled={updating}
            >
              Cancel
            </button>
            <button
              type="submit"
              class="btn-primary"
              disabled={updating || !editCollectionName.trim()}
            >
              {updating ? 'Updating...' : 'Update Collection'}
            </button>
          </div>
        </form>
      </div>
    </div>
  {/if}
  
  <!-- Delete Confirmation Modal -->
  {#if showDeleteConfirm && collectionToDelete}
    <div class="modal-overlay" on:click={() => showDeleteConfirm = false} transition:fade>
      <div class="modal confirm-modal" on:click|stopPropagation transition:slide>
        <h3>Delete Collection</h3>
        
        <p>Are you sure you want to delete the collection <strong>"{collectionToDelete.name}"</strong>?</p>
        <p class="warning-text">This action cannot be undone. The media files will not be deleted, only removed from this collection.</p>
        
        <div class="modal-actions">
          <button
            type="button"
            class="btn-secondary"
            on:click={() => showDeleteConfirm = false}
            disabled={deleting}
          >
            Cancel
          </button>
          <button
            type="button"
            class="btn-danger"
            on:click={deleteCollection}
            disabled={deleting}
          >
            {deleting ? 'Deleting...' : 'Delete Collection'}
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .collections-panel {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 20px;
    height: 100%;
    display: flex;
    flex-direction: column;
  }
  
  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
  }
  
  .panel-header h3 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
  }
  
  .btn-create {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 0.6rem 1.2rem;
    background-color: #3b82f6;
    color: white;
    border: none;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }
  
  .btn-create:hover:not(:disabled) {
    background-color: #2563eb;
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
    text-decoration: none;
  }
  
  .btn-create:active:not(:disabled) {
    transform: translateY(0);
  }
  
  .btn-create:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  .icon {
    font-size: 18px;
    line-height: 1;
    color: white;
    font-weight: bold;
  }
  
  .error-message {
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    color: var(--error-color);
    padding: 12px;
    border-radius: 6px;
    margin-bottom: 16px;
    font-size: 14px;
  }
  
  .loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px;
    color: var(--text-secondary);
  }
  
  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--border-color);
    border-top-color: var(--primary-color);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-bottom: 12px;
  }
  
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  
  .empty-state {
    text-align: center;
    padding: 40px 20px;
    color: var(--text-secondary);
  }
  
  .empty-state p {
    margin: 0 0 8px 0;
  }
  
  .hint {
    font-size: 14px;
    opacity: 0.8;
  }
  
  .collections-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
    overflow-y: auto;
    flex: 1;
    max-height: 400px;
    padding-right: 8px;
  }
  
  /* Custom scrollbar styling */
  .collections-list::-webkit-scrollbar {
    width: 6px;
  }
  
  .collections-list::-webkit-scrollbar-track {
    background: var(--surface-color);
    border-radius: 3px;
  }
  
  .collections-list::-webkit-scrollbar-thumb {
    background: var(--border-color);
    border-radius: 3px;
  }
  
  .collections-list::-webkit-scrollbar-thumb:hover {
    background: var(--text-secondary);
  }
  
  .collection-card {
    background: var(--card-background);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 16px;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    justify-content: space-between;
    align-items: start;
    gap: 12px;
  }
  
  .collection-card:hover {
    border-color: var(--primary-color);
    background: var(--card-hover);
  }
  
  .collection-card.selected {
    border-color: var(--primary-color);
    background: rgba(59, 130, 246, 0.05);
  }
  
  .collection-info {
    flex: 1;
    min-width: 0;
  }
  
  .collection-info h4 {
    margin: 0 0 4px 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  
  .description {
    margin: 0 0 8px 0;
    font-size: 14px;
    color: var(--text-secondary);
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  
  .meta {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 13px;
    color: var(--text-secondary);
  }
  
  .media-count {
    font-weight: 500;
  }
  
  .badge {
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 500;
  }
  
  .badge.public {
    background: rgba(34, 197, 94, 0.1);
    color: rgb(34, 197, 94);
  }
  
  .collection-actions {
    display: flex;
    gap: 8px;
  }
  
  .edit-button, .delete-config-button {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.5rem 0.75rem;
    border-radius: 4px;
    font-size: 0.8rem;
    cursor: pointer;
    transition: all 0.2s ease;
    border: 1px solid;
  }

  .edit-button {
    background-color: transparent;
    border-color: var(--border-color);
    color: var(--text-color);
  }

  .edit-button:hover:not(:disabled) {
    background-color: #3b82f6;
    border-color: #3b82f6;
    color: white;
  }

  .delete-config-button {
    background-color: transparent;
    border-color: var(--error-color);
    color: var(--error-color);
  }

  .delete-config-button:hover:not(:disabled) {
    background-color: var(--error-color);
    border-color: var(--error-color);
    color: white;
    transform: translateY(-1px);
  }
  
  .btn-add {
    padding: 6px 12px;
    background: var(--primary-color);
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    white-space: nowrap;
  }
  
  .btn-add:hover:not(:disabled) {
    background: var(--primary-hover);
  }
  
  .btn-add:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  /* Modal styles */
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 20px;
  }
  
  .modal {
    background: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 32px;
    max-width: 550px;
    width: 100%;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
  }
  
  .modal h3 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
    color: var(--text-primary);
  }
  
  .modal-header-custom {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
  }
  
  .modal-close-btn {
    background: none;
    border: none;
    cursor: pointer;
    padding: 8px;
    border-radius: 6px;
    color: var(--text-secondary);
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .modal-close-btn:hover {
    background: var(--hover-background);
    color: var(--text-primary);
  }
  
  .modal-close-btn svg {
    width: 20px;
    height: 20px;
  }
  
  .modal form {
    background: transparent;
    padding: 0;
    margin: 0;
  }
  
  .form-group {
    margin-bottom: 24px;
  }
  
  .form-group label {
    display: block;
    margin-bottom: 8px;
    font-size: 14px;
    font-weight: 500;
    color: var(--text-primary);
  }
  
  .form-group input,
  .form-group textarea {
    width: 100%;
    padding: 12px 16px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    font-size: 14px;
    font-family: inherit;
    background: transparent;
    color: var(--text-primary);
    transition: all 0.2s;
  }
  
  .form-group input:focus,
  .form-group textarea:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
  }
  
  .form-group input:disabled,
  .form-group textarea:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    background: var(--surface-color);
  }
  
  .form-group textarea {
    resize: vertical;
    min-height: 60px;
  }
  
  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    margin-top: 24px;
  }
  
  .btn-secondary,
  .btn-primary {
    padding: 0.6rem 1.2rem;
    border: none;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .btn-secondary {
    background-color: var(--surface-color);
    border: 1px solid var(--border-color);
    color: var(--text-color);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }
  
  .btn-secondary:hover:not(:disabled) {
    background-color: #3b82f6;
    border-color: #3b82f6;
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }
  
  .btn-secondary:active:not(:disabled) {
    transform: translateY(0);
  }
  
  .btn-primary {
    background-color: #3b82f6;
    color: white;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }
  
  .btn-primary:hover:not(:disabled) {
    background-color: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }
  
  .btn-primary:active:not(:disabled) {
    transform: translateY(0);
  }
  
  .btn-secondary:disabled,
  .btn-primary:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  .btn-danger {
    background-color: #ef4444;
    color: white;
    padding: 0.6rem 1.2rem;
    border: none;
    border-radius: 10px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2);
  }
  
  .btn-danger:hover:not(:disabled) {
    background-color: #dc2626;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(239, 68, 68, 0.25);
  }
  
  .btn-danger:active:not(:disabled) {
    transform: translateY(0);
  }
  
  .btn-danger:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  .confirm-modal p {
    margin: 0 0 16px 0;
    color: var(--text-primary);
    line-height: 1.5;
  }
  
  .warning-text {
    color: var(--text-secondary);
    font-size: 14px;
  }
  
  /* Dark mode adjustments */
  :global(.dark) .modal-overlay {
    background: rgba(0, 0, 0, 0.7);
  }
  
  :global(.dark) .modal {
    background: var(--surface-color);
    color: var(--text-primary);
  }
  
  :global(.dark) .form-group input,
  :global(.dark) .form-group textarea {
    background: rgba(255, 255, 255, 0.03);
    color: var(--text-primary);
    border-color: var(--border-color);
  }
  
  :global(.dark) .form-group input:focus,
  :global(.dark) .form-group textarea:focus {
    background: rgba(255, 255, 255, 0.05);
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  }
  
  :global(.dark) .form-group input:hover,
  :global(.dark) .form-group textarea:hover {
    background: rgba(255, 255, 255, 0.04);
    border-color: var(--primary-color);
  }
  
  :global(.dark) .collection-card {
    background: var(--card-background);
    border-color: var(--border-color);
  }
  
  :global(.dark) .btn-secondary {
    background: var(--surface-secondary);
    color: var(--text-primary);
    border-color: var(--border-color);
  }
  
  
  :global(.dark) .badge.public {
    background: rgba(34, 197, 94, 0.2);
    color: #4ade80;
  }
</style>