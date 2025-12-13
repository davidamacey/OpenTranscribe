<script lang="ts">
  import { onMount } from 'svelte';
  import { fade, slide } from 'svelte/transition';
  import axiosInstance from '$lib/axios';
  import { toastStore } from '$stores/toast';
  import { t } from '$stores/locale';
  import ConfirmationModal from './ConfirmationModal.svelte';

  // Props
  export let selectedMediaIds: string[] = [];  // UUIDs
  export let onCollectionSelect: (collectionId: string) => void = () => {};  // UUID
  export let viewMode: 'manage' | 'add' = 'manage';

  // State
  let collections: any[] = [];
  let loading = false;
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
  let selectedCollectionId: string | null = null;  // UUID
  let addingToCollection = false;

  // Fetch collections
  async function fetchCollections() {
    loading = true;

    try {
      const response = await axiosInstance.get('/api/collections/');
      collections = response.data;
    } catch (err: any) {
      console.error('Error fetching collections:', err);
      toastStore.error($t('collectionsPanel.failedToLoad'));
    } finally {
      loading = false;
    }
  }

  // Create new collection
  async function createCollection() {
    if (!newCollectionName.trim()) return;

    creating = true;

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
        toastStore.success($t('collectionsPanel.createdSuccess', { name: response.data.name }));
        // Close the create modal but keep the manage collections modal open
        showCreateModal = false;
        // Don't trigger collection selection callback in manage mode during creation
      }
    } catch (err: any) {
      console.error('Error creating collection:', err);
      toastStore.error(err.response?.data?.detail || $t('collectionsPanel.failedToCreate'));
    } finally {
      creating = false;
    }
  }

  // Update collection
  async function updateCollection() {
    if (!collectionToEdit || !editCollectionName.trim()) return;

    updating = true;

    try {
      const response = await axiosInstance.put(`/api/collections/${collectionToEdit.id}`, {
        name: editCollectionName.trim(),
        description: editCollectionDescription.trim() || null
      });

      // Update local state
      collections = collections.map(col =>
        col.id === collectionToEdit.id ? { ...col, ...response.data } : col
      );

      toastStore.success($t('collectionsPanel.updatedSuccess', { name: editCollectionName }));
      showEditModal = false;
      collectionToEdit = null;
    } catch (err: any) {
      console.error('Error updating collection:', err);
      toastStore.error(err.response?.data?.detail || $t('collectionsPanel.failedToUpdate'));
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

    try {
      await axiosInstance.delete(`/api/collections/${collectionToDelete.id}`);
      collections = collections.filter(col => col.id !== collectionToDelete.id);

      if (selectedCollectionId === collectionToDelete.id) {
        selectedCollectionId = null;
      }

      toastStore.success($t('collectionsPanel.deletedSuccess', { name: collectionToDelete.name }));
      showDeleteConfirm = false;
      collectionToDelete = null;
    } catch (err: any) {
      console.error('Error deleting collection:', err);
      toastStore.error(err.response?.data?.detail || $t('collectionsPanel.failedToDelete'));
    } finally {
      deleting = false;
    }
  }

  // Handle confirmation modal confirm
  function handleConfirmModalConfirm() {
    deleteCollection();
  }

  // Handle confirmation modal cancel
  function handleConfirmModalCancel() {
    showDeleteConfirm = false;
    collectionToDelete = null;
  }

  // Add selected media to collection
  async function addMediaToCollection(collectionId: string) {
    if (!selectedMediaIds.length) return;

    addingToCollection = true;

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
      toastStore.success($t('collectionsPanel.addedSuccess', { count: response.data.added, name: collection?.name || 'collection' }));

      // Trigger callback to close modal and refresh
      onCollectionSelect(collectionId);
    } catch (err: any) {
      console.error('Error adding media to collection:', err);
      toastStore.error(err.response?.data?.detail || $t('collectionsPanel.failedToAddMedia'));
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
    <h3>{$t('collectionsPanel.title')}</h3>
    <button
      class="btn-create"
      on:click={() => {
        showCreateModal = true;
      }}
      disabled={creating}
    >
      <span class="icon">+</span>
      {$t('collectionsPanel.newCollection')}
    </button>
  </div>

  {#if loading}
    <div class="loading">
      <div class="spinner"></div>
      {$t('collectionsPanel.loading')}
    </div>
  {:else if collections.length === 0}
    <div class="empty-state">
      <p>{$t('collectionsPanel.noCollectionsYet')}</p>
      <p class="hint">{$t('collectionsPanel.createFirstHint')}</p>
    </div>
  {:else}
    <div class="collections-list">
      {#each collections as collection (collection.id)}
        <div
          class="collection-card"
          class:selected={selectedCollectionId === collection.id}
          role="button"
          tabindex="0"
          on:click={() => handleCollectionClick(collection)}
          on:keydown={(e) => (e.key === 'Enter' || e.key === ' ') && handleCollectionClick(collection)}
          transition:slide
        >
          <div class="collection-info">
            <h4>{collection.name}</h4>
            {#if collection.description}
              <p class="description">{collection.description}</p>
            {/if}
            <div class="meta">
              <span class="media-count">{collection.media_count} {collection.media_count !== 1 ? $t('collectionsPanel.files') : $t('collectionsPanel.file')}</span>
              {#if collection.is_public}
                <span class="badge public">{$t('collectionsPanel.public')}</span>
              {/if}
            </div>
          </div>

          {#if viewMode === 'manage'}
            <div class="collection-actions">
              <button
                class="edit-button"
                title={$t('collectionsPanel.editCollection')}
                on:click|stopPropagation={() => openEditModal(collection)}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="m18.5 2.5 a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
              <button
                class="delete-config-button"
                title={$t('collectionsPanel.deleteCollection')}
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
              {selectedMediaIds.length !== 1 ? $t('collectionsPanel.addFiles', { count: selectedMediaIds.length }) : $t('collectionsPanel.addFile', { count: selectedMediaIds.length })}
            </button>
          {/if}
        </div>
      {/each}
    </div>
  {/if}

  <!-- Create Collection Modal -->
  {#if showCreateModal}
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div
      class="modal-overlay"
      role="presentation"
      on:click={() => showCreateModal = false}
      on:keydown={(e) => e.key === 'Escape' && (() => showCreateModal = false)()}
      transition:fade
    >
      <!-- svelte-ignore a11y-click-events-have-key-events -->
      <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <!-- svelte-ignore a11y_interactive_supports_focus -->
      <div
        class="modal-content"
        role="dialog"
        aria-modal="true"
        on:click|stopPropagation
        on:keydown|stopPropagation
        transition:slide
      >
        <div class="modal-header">
          <h3>{$t('collectionsPanel.createNewCollection')}</h3>
          <button
            class="close-button"
            on:click={() => showCreateModal = false}
            type="button"
            aria-label={$t('collectionsPanel.closeModal')}
          >×</button>
        </div>

        <form on:submit|preventDefault={createCollection} class="config-form">
          <div class="form-group">
            <label for="collection-name">{$t('collectionsPanel.name')}</label>
            <input
              id="collection-name"
              type="text"
              bind:value={newCollectionName}
              class="form-control"
              placeholder={$t('collectionsPanel.namePlaceholder')}
              required
              disabled={creating}
            />
          </div>

          <div class="form-group">
            <label for="collection-description">{$t('collectionsPanel.description')}</label>
            <textarea
              id="collection-description"
              bind:value={newCollectionDescription}
              class="form-control"
              placeholder={$t('collectionsPanel.descriptionPlaceholder')}
              rows="3"
              disabled={creating}
            ></textarea>
          </div>

          <div class="form-actions">
            <button
              type="button"
              class="cancel-button"
              on:click={() => showCreateModal = false}
              disabled={creating}
            >
              {$t('collectionsPanel.cancel')}
            </button>
            <button
              type="submit"
              class="save-button primary"
              disabled={creating || !newCollectionName.trim()}
            >
              {#if creating}
                <div class="spinner-mini"></div>
                {$t('collectionsPanel.creating')}
              {:else}
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                  <polyline points="17,21 17,13 7,13 7,21"/>
                  <polyline points="7,3 7,8 15,8"/>
                </svg>
                {$t('collectionsPanel.createCollection')}
              {/if}
            </button>
          </div>
        </form>
      </div>
    </div>
  {/if}

  <!-- Edit Collection Modal -->
  {#if showEditModal && collectionToEdit}
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div
      class="modal-overlay"
      role="presentation"
      on:click={() => showEditModal = false}
      on:keydown={(e) => e.key === 'Escape' && (() => showEditModal = false)()}
      transition:fade
    >
      <!-- svelte-ignore a11y-click-events-have-key-events -->
      <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <!-- svelte-ignore a11y_interactive_supports_focus -->
      <div
        class="modal-content"
        role="dialog"
        aria-modal="true"
        on:click|stopPropagation
        on:keydown|stopPropagation
        transition:slide
      >
        <div class="modal-header">
          <h3>{$t('collectionsPanel.editCollectionTitle')}</h3>
          <button
            class="close-button"
            on:click={() => showEditModal = false}
            type="button"
            aria-label={$t('collectionsPanel.closeModal')}
          >×</button>
        </div>

        <form on:submit|preventDefault={updateCollection} class="config-form">
          <div class="form-group">
            <label for="edit-collection-name">{$t('collectionsPanel.name')}</label>
            <input
              id="edit-collection-name"
              type="text"
              bind:value={editCollectionName}
              class="form-control"
              placeholder={$t('collectionsPanel.collectionName')}
              required
              disabled={updating}
            />
          </div>

          <div class="form-group">
            <label for="edit-collection-description">{$t('collectionsPanel.description')}</label>
            <textarea
              id="edit-collection-description"
              bind:value={editCollectionDescription}
              class="form-control"
              placeholder={$t('collectionsPanel.descriptionPlaceholder')}
              rows="3"
              disabled={updating}
            ></textarea>
          </div>

          <div class="form-actions">
            <button
              type="button"
              class="cancel-button"
              on:click={() => showEditModal = false}
              disabled={updating}
            >
              {$t('collectionsPanel.cancel')}
            </button>
            <button
              type="submit"
              class="save-button primary"
              disabled={updating || !editCollectionName.trim()}
            >
              {#if updating}
                <div class="spinner-mini"></div>
                {$t('collectionsPanel.updating')}
              {:else}
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                  <polyline points="17,21 17,13 7,13 7,21"/>
                  <polyline points="7,3 7,8 15,8"/>
                </svg>
                {$t('collectionsPanel.updateCollection')}
              {/if}
            </button>
          </div>
        </form>
      </div>
    </div>
  {/if}

<!-- Delete Confirmation Modal -->
<ConfirmationModal
  bind:isOpen={showDeleteConfirm}
  title={$t('collectionsPanel.deleteCollectionTitle')}
  message={collectionToDelete ? $t('collectionsPanel.deleteConfirmMessage', { name: collectionToDelete.name }) : ''}
  confirmText={deleting ? $t('collectionsPanel.deleting') : $t('collectionsPanel.deleteCollectionButton')}
  cancelText={$t('collectionsPanel.cancel')}
  confirmButtonClass="modal-delete-button"
  cancelButtonClass="modal-cancel-button"
  on:confirm={handleConfirmModalConfirm}
  on:cancel={handleConfirmModalCancel}
  on:close={handleConfirmModalCancel}
/>
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
    line-clamp: 2;
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

  /* Modal styles - updated to match LLM config modal */
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
  }

  .modal-content {
    background-color: var(--background-color);
    border-radius: 8px;
    max-width: 600px;
    width: 100%;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem 1.5rem 1rem 1.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .modal-header h3 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-color);
  }

  .close-button {
    background: none;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    color: var(--text-light);
    padding: 0;
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .close-button:hover {
    color: var(--text-color);
  }

  .config-form {
    padding: 1.5rem;
  }

  .form-group {
    margin-bottom: 1.5rem;
  }

  .form-group label {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.5rem;
    font-weight: 500;
    color: var(--text-color);
  }

  .form-control {
    width: 100%;
    padding: 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background-color: var(--input-bg);
    color: var(--text-color);
    font-size: 0.875rem;
    transition: border-color 0.2s ease;
  }

  .form-control:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
    gap: 1rem;
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border-color);
  }

  .cancel-button {
    background: var(--surface-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .cancel-button:hover:not(:disabled) {
    background: #3b82f6;
    color: white;
    border-color: #3b82f6;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .cancel-button:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .save-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: #3b82f6;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 10px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .save-button:hover:not(:disabled) {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .save-button:active:not(:disabled) {
    transform: translateY(0);
  }

  .save-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .spinner-mini {
    width: 16px;
    height: 16px;
    border: 2px solid transparent;
    border-top: 2px solid currentColor;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }


  /* Dark mode adjustments */
  :global(.dark) .modal-overlay {
    background: rgba(0, 0, 0, 0.7);
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


  :global(.dark) .badge.public {
    background: rgba(34, 197, 94, 0.2);
    color: #4ade80;
  }

  /* Modal button styling to match app design */
  :global(.modal-delete-button) {
    background-color: #ef4444 !important;
    color: white !important;
    border: none !important;
    padding: 0.6rem 1.2rem !important;
    border-radius: 10px !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2) !important;
  }

  :global(.modal-delete-button:hover) {
    background-color: #dc2626 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(239, 68, 68, 0.25) !important;
  }

  :global(.modal-cancel-button) {
    background-color: var(--card-background) !important;
    color: var(--text-color) !important;
    border: 1px solid var(--border-color) !important;
    padding: 0.6rem 1.2rem !important;
    border-radius: 10px !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    box-shadow: var(--card-shadow) !important;
    /* Ensure text is always visible */
    opacity: 1 !important;
  }

  :global(.modal-cancel-button:hover) {
    background-color: #2563eb !important;
    color: white !important;
    border-color: #2563eb !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25) !important;
  }
</style>
