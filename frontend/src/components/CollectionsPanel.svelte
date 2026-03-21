<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { fade, slide } from 'svelte/transition';
  import axiosInstance from '$lib/axios';
  import { toastStore } from '$stores/toast';
  import { t } from '$stores/locale';
  import ConfirmationModal from './ConfirmationModal.svelte';
  import ShareBadge from './sharing/ShareBadge.svelte';
  import SharedByAttribution from './sharing/SharedByAttribution.svelte';
  import ShareCollectionModal from './sharing/ShareCollectionModal.svelte';
  import { SharingApi } from '$lib/api/sharing';
  import type { SharedCollection } from '$lib/types/groups';
  import Spinner from './ui/Spinner.svelte';
  import EmptyState from './ui/EmptyState.svelte';

  // Props
  export let selectedMediaIds: string[] = [];  // UUIDs
  export let onCollectionSelect: (collectionId: string) => void = () => {};  // UUID
  export let viewMode: 'manage' | 'add' = 'manage';

  // State
  let collections: any[] = [];
  let sharedCollections: SharedCollection[] = [];
  let loadingShared = false;
  let showShareModal = false;
  let shareModalCollectionUuid = '';
  let shareModalCollectionName = '';
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

  // Search state
  let searchQuery = '';

  // Filtered collections based on search
  $: filteredCollections = searchQuery.trim()
    ? collections.filter(c =>
        c.name.toLowerCase().includes(searchQuery.trim().toLowerCase()) ||
        (c.description && c.description.toLowerCase().includes(searchQuery.trim().toLowerCase()))
      )
    : collections;

  $: filteredSharedCollections = searchQuery.trim()
    ? sharedCollections.filter(c =>
        c.name.toLowerCase().includes(searchQuery.trim().toLowerCase()) ||
        (c.description && c.description.toLowerCase().includes(searchQuery.trim().toLowerCase()))
      )
    : sharedCollections;

  // Prompt selection state
  let availablePrompts: any[] = [];
  let newCollectionPromptId: string | null = null;
  let editCollectionPromptId: string | null = null;
  let loadingPrompts = false;

  // Fetch collections
  async function fetchCollections() {
    loading = true;

    try {
      const response = await axiosInstance.get('/collections');
      collections = response.data;
    } catch (err: any) {
      console.error('Error fetching collections:', err);
      toastStore.error($t('collectionsPanel.failedToLoad'));
    } finally {
      loading = false;
    }
  }

  // Fetch available prompts for dropdown
  async function fetchPrompts() {
    loadingPrompts = true;
    try {
      const response = await axiosInstance.get('/prompts');
      availablePrompts = response.data.prompts || [];
    } catch (err: any) {
      console.error('Error fetching prompts:', err);
      // Non-critical: prompts dropdown will just be empty
    } finally {
      loadingPrompts = false;
    }
  }

  // Fetch shared collections
  async function fetchSharedCollections() {
    loadingShared = true;
    try {
      sharedCollections = await SharingApi.fetchSharedCollections();
    } catch (err: any) {
      console.error('Error fetching shared collections:', err);
    } finally {
      loadingShared = false;
    }
  }

  // Open share modal for a collection
  function openShareModal(collection: any) {
    shareModalCollectionUuid = collection.uuid;
    shareModalCollectionName = collection.name;
    showShareModal = true;
  }

  // Handle share completion - refresh collections
  function handleShared() {
    fetchCollections();
    fetchSharedCollections();
  }

  // Create new collection
  async function createCollection() {
    if (!newCollectionName.trim()) return;

    creating = true;

    try {
      const response = await axiosInstance.post('/collections', {
        name: newCollectionName.trim(),
        description: newCollectionDescription.trim() || null,
        default_prompt_id: newCollectionPromptId || null
      });

      collections = [...collections, { ...response.data, media_count: 0 }];

      // Reset form for potential next collection
      newCollectionName = '';
      newCollectionDescription = '';
      newCollectionPromptId = null;

      // If in add mode and media is selected, add to new collection
      if (viewMode === 'add' && selectedMediaIds.length > 0) {
        await addMediaToCollection(response.data.uuid);
        // Close create modal after adding media since the workflow is complete
        showCreateModal = false;
        // Trigger callback to refresh filters after adding media
        onCollectionSelect(response.data.uuid);
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
      const response = await axiosInstance.put(`/collections/${collectionToEdit.uuid}`, {
        name: editCollectionName.trim(),
        description: editCollectionDescription.trim() || null,
        default_prompt_id: editCollectionPromptId || null
      });

      // Update local state
      collections = collections.map(col =>
        col.uuid === collectionToEdit.uuid ? { ...col, ...response.data } : col
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
    editCollectionPromptId = collection.default_prompt_id || null;
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
      await axiosInstance.delete(`/collections/${collectionToDelete.uuid}`);
      collections = collections.filter(col => col.uuid !== collectionToDelete.uuid);

      if (selectedCollectionId === collectionToDelete.uuid) {
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
      const response = await axiosInstance.post(`/collections/${collectionId}/media`, {
        media_file_ids: selectedMediaIds
      });

      // Update media count
      collections = collections.map(col =>
        col.uuid === collectionId
          ? { ...col, media_count: col.media_count + (response.data.added || 0) }
          : col
      );

      // Show success message
      const collection = collections.find(c => c.uuid === collectionId);
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
      selectedCollectionId = collection.uuid;
      onCollectionSelect(collection.uuid);
    } else if (viewMode === 'add' && selectedMediaIds.length > 0) {
      addMediaToCollection(collection.uuid);
    }
  }

  function handleShareWsEvent() {
    fetchCollections();
    fetchSharedCollections();
  }

  onMount(() => {
    window.addEventListener('collection-shared', handleShareWsEvent);
    window.addEventListener('share-revoked', handleShareWsEvent);
    window.addEventListener('share-updated', handleShareWsEvent);
    fetchCollections();
    fetchPrompts();
    fetchSharedCollections();
  });

  onDestroy(() => {
    window.removeEventListener('collection-shared', handleShareWsEvent);
    window.removeEventListener('share-revoked', handleShareWsEvent);
    window.removeEventListener('share-updated', handleShareWsEvent);
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

  <!-- Search -->
  {#if !loading && (collections.length > 0 || sharedCollections.length > 0)}
    <div class="search-wrapper">
      <svg class="search-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="11" cy="11" r="8"></circle>
        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
      </svg>
      <input
        type="text"
        class="search-input"
        placeholder={$t('collectionsPanel.searchPlaceholder')}
        bind:value={searchQuery}
      />
      {#if searchQuery}
        <button
          class="search-clear"
          on:click={() => searchQuery = ''}
          title={$t('collectionsPanel.clearSearch')}
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      {/if}
    </div>
  {/if}

  {#if loading}
    <div class="loading">
      <Spinner size="large" />
      {$t('collectionsPanel.loading')}
    </div>
  {:else if collections.length === 0 && sharedCollections.length === 0}
    <EmptyState title={$t('collectionsPanel.noCollectionsYet')} description={$t('collectionsPanel.createFirstHint')} padding="40px 20px" />
  {:else}
    <div class="collections-list">
      {#if searchQuery && filteredCollections.length === 0 && filteredSharedCollections.length === 0}
        <div class="no-results">
          <p>{$t('collectionsPanel.noSearchResults')}</p>
        </div>
      {/if}

      <!-- My Collections -->
      {#if filteredCollections.length > 0}
        <div class="section-label">{$t('sharing.myCollections')}</div>
      {/if}
      {#each filteredCollections as collection (collection.uuid)}
        <div
          class="collection-card"
          class:selected={selectedCollectionId === collection.uuid}
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
              {#if collection.default_prompt_name}
                <span class="badge prompt">{collection.default_prompt_name}</span>
              {/if}
              {#if collection.share_count > 0}
                <ShareBadge shareCount={collection.share_count} isShared={true} />
              {/if}
            </div>
          </div>

          {#if viewMode === 'manage'}
            <div class="collection-actions">
              <button
                class="share-button"
                title={$t('sharing.shareCollection')}
                on:click|stopPropagation={() => openShareModal(collection)}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/>
                  <polyline points="16 6 12 2 8 6"/>
                  <line x1="12" y1="2" x2="12" y2="15"/>
                </svg>
              </button>
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
              on:click|stopPropagation={() => addMediaToCollection(collection.uuid)}
            >
              {selectedMediaIds.length !== 1 ? $t('collectionsPanel.addFiles', { count: selectedMediaIds.length }) : $t('collectionsPanel.addFile', { count: selectedMediaIds.length })}
            </button>
          {/if}
        </div>
      {/each}

      <!-- Shared with Me -->
      {#if filteredSharedCollections.length > 0}
        <div class="section-label shared-label">{$t('sharing.sharedWithMe')}</div>
        {#each filteredSharedCollections as shared (shared.uuid)}
          <div
            class="collection-card shared-card"
            class:selected={selectedCollectionId === shared.uuid}
            role="button"
            tabindex="0"
            on:click={() => handleCollectionClick(shared)}
            on:keydown={(e) => (e.key === 'Enter' || e.key === ' ') && handleCollectionClick(shared)}
            transition:slide
          >
            <div class="collection-info">
              <h4>{shared.name}</h4>
              {#if shared.description}
                <p class="description">{shared.description}</p>
              {/if}
              <div class="meta">
                <span class="media-count">{shared.media_count} {shared.media_count !== 1 ? $t('collectionsPanel.files') : $t('collectionsPanel.file')}</span>
                <span class="badge shared-permission">{$t('sharing.permission' + shared.my_permission.charAt(0).toUpperCase() + shared.my_permission.slice(1))}</span>
              </div>
              <SharedByAttribution sharedBy={shared.shared_by} />
            </div>

            {#if viewMode === 'add' && selectedMediaIds.length > 0 && shared.my_permission !== 'viewer'}
              <button
                class="btn-add"
                disabled={addingToCollection}
                on:click|stopPropagation={() => addMediaToCollection(shared.uuid)}
              >
                {selectedMediaIds.length !== 1 ? $t('collectionsPanel.addFiles', { count: selectedMediaIds.length }) : $t('collectionsPanel.addFile', { count: selectedMediaIds.length })}
              </button>
            {/if}
          </div>
        {/each}
      {/if}
    </div>
  {/if}

  <!-- Create Collection Modal -->
  {#if showCreateModal}
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div
      class="modal-backdrop"
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
        class="modal-container"
        role="dialog"
        aria-modal="true"
        on:click|stopPropagation
        on:keydown|stopPropagation
        transition:slide
      >
        <div class="modal-content">
          <div class="modal-header">
            <h2>{$t('collectionsPanel.createNewCollection')}</h2>
            <button
              class="modal-close-button"
              on:click={() => showCreateModal = false}
              type="button"
              aria-label={$t('collectionsPanel.closeModal')}
              title={$t('collectionsPanel.closeModal')}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
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

            <div class="form-group">
              <label for="collection-prompt">{$t('collectionsPanel.defaultPrompt')}</label>
              <select
                id="collection-prompt"
                bind:value={newCollectionPromptId}
                class="form-control"
                disabled={creating || loadingPrompts}
              >
                <option value={null}>{$t('collectionsPanel.noDefaultPrompt')}</option>
                {#each availablePrompts as prompt}
                  <option value={prompt.uuid}>
                    {prompt.name}{prompt.is_system_default ? ` (${$t('collectionsPanel.system')})` : ''}
                  </option>
                {/each}
              </select>
              <span class="form-hint">{$t('collectionsPanel.defaultPromptHint')}</span>
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
                  <Spinner size="small" />
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
    </div>
  {/if}

  <!-- Edit Collection Modal -->
  {#if showEditModal && collectionToEdit}
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div
      class="modal-backdrop"
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
        class="modal-container"
        role="dialog"
        aria-modal="true"
        on:click|stopPropagation
        on:keydown|stopPropagation
        transition:slide
      >
        <div class="modal-content">
          <div class="modal-header">
            <h2>{$t('collectionsPanel.editCollectionTitle')}</h2>
            <button
              class="modal-close-button"
              on:click={() => showEditModal = false}
              type="button"
              aria-label={$t('collectionsPanel.closeModal')}
              title={$t('collectionsPanel.closeModal')}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
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

            <div class="form-group">
              <label for="edit-collection-prompt">{$t('collectionsPanel.defaultPrompt')}</label>
              <select
                id="edit-collection-prompt"
                bind:value={editCollectionPromptId}
                class="form-control"
                disabled={updating || loadingPrompts}
              >
                <option value={null}>{$t('collectionsPanel.noDefaultPrompt')}</option>
                {#each availablePrompts as prompt}
                  <option value={prompt.uuid}>
                    {prompt.name}{prompt.is_system_default ? ` (${$t('collectionsPanel.system')})` : ''}
                  </option>
                {/each}
              </select>
              <span class="form-hint">{$t('collectionsPanel.defaultPromptHint')}</span>
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
                  <Spinner size="small" />
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
    </div>
  {/if}

<!-- Share Collection Modal -->
{#if showShareModal}
  <ShareCollectionModal
    collectionUuid={shareModalCollectionUuid}
    collectionName={shareModalCollectionName}
    on:shared={handleShared}
    on:close={() => showShareModal = false}
  />
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
    border-radius: 8px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .btn-create:hover:not(:disabled) {
    background-color: #2563eb;
    color: white;
    transform: scale(1.02);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
    text-decoration: none;
  }

  .btn-create:active:not(:disabled) {
    transform: scale(1);
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

  .search-wrapper {
    position: relative;
    margin-bottom: 12px;
  }

  .search-icon {
    position: absolute;
    left: 10px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-secondary);
    pointer-events: none;
  }

  .search-input {
    width: 100%;
    padding: 0.5rem 2rem 0.5rem 2.25rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background-color: var(--surface-color);
    color: var(--text-color);
    font-size: 0.875rem;
    transition: border-color 0.15s, box-shadow 0.15s;
    box-sizing: border-box;
  }

  .search-input:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px var(--primary-light, rgba(59, 130, 246, 0.1));
  }

  .search-input::placeholder {
    color: var(--text-secondary);
    opacity: 0.7;
  }

  .search-clear {
    position: absolute;
    right: 6px;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    cursor: pointer;
    padding: 4px;
    color: var(--text-secondary);
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.15s;
  }

  .search-clear:hover {
    color: var(--text-color);
  }

  .no-results {
    text-align: center;
    padding: 1.5rem 0;
    color: var(--text-secondary);
    font-size: 0.875rem;
  }

  .no-results p {
    margin: 0;
  }

  .loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px;
    color: var(--text-secondary);
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
    background: var(--primary-bg, rgba(59, 130, 246, 0.05));
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

  .badge.prompt {
    background: rgba(59, 130, 246, 0.1);
    color: var(--primary-color);
  }

  .collection-actions {
    display: flex;
    gap: 8px;
  }

  .section-label {
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--text-secondary);
    padding: 4px 0;
  }

  .section-label.shared-label {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--border-color);
  }

  .shared-card {
    border-left: 3px solid var(--primary-color);
  }

  .badge.shared-permission {
    background: rgba(139, 92, 246, 0.1);
    color: #8b5cf6;
    text-transform: capitalize;
  }

  :global([data-theme='dark']) .badge.shared-permission {
    background: rgba(139, 92, 246, 0.2);
    color: #a78bfa;
  }

  .share-button {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.5rem 0.75rem;
    border-radius: 4px;
    font-size: 0.8rem;
    cursor: pointer;
    transition: all 0.2s ease;
    border: 1px solid;
    background-color: transparent;
    border-color: var(--border-color);
    color: var(--text-color);
  }

  .share-button:hover:not(:disabled) {
    background-color: #3b82f6;
    border-color: var(--primary-color);
    color: white;
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
    border-color: var(--primary-color);
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
    transform: scale(1.02);
  }

  .btn-add {
    padding: 6px 12px;
    background: #3b82f6;
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
    background: #2563eb;
  }

  .btn-add:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  /* Modal styles - standard pattern */
  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: var(--modal-backdrop, rgba(0, 0, 0, 0.5));
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1200;
    padding: 1rem;
    overscroll-behavior: contain;
  }

  .modal-container {
    background: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    max-width: 600px;
    width: 100%;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
    animation: slideIn 0.2s ease-out;
  }

  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateY(-20px) scale(0.95);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }

  .modal-content {
    display: flex;
    flex-direction: column;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .modal-header h2 {
    margin: 0;
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--text-color);
    line-height: 1.4;
  }

  .modal-close-button {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.5rem;
    color: var(--text-secondary);
    transition: color 0.2s ease;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .modal-close-button:hover {
    color: var(--text-color);
    background: var(--button-hover);
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

  .form-hint {
    display: block;
    margin-top: 0.35rem;
    font-size: 0.8rem;
    color: var(--text-secondary);
    font-style: italic;
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
    border-radius: 8px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .cancel-button:hover:not(:disabled) {
    background: var(--button-hover, #e5e7eb);
    border-color: var(--border-color);
  }

  .save-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: #3b82f6;
    color: white;
    border: none;
    padding: 0.6rem 1.2rem;
    border-radius: 8px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .save-button:hover:not(:disabled) {
    background: #2563eb;
    transform: scale(1.02);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .save-button:active:not(:disabled) {
    transform: scale(1);
  }

  .save-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  /* Dark mode adjustments */
  :global([data-theme='dark']) .modal-backdrop {
    background: rgba(0, 0, 0, 0.7);
  }

  :global([data-theme='dark']) .modal-container {
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2);
  }

  @media (prefers-reduced-motion: reduce) {
    .modal-container {
      animation: none;
    }
  }

  :global([data-theme='dark']) .form-group input,
  :global([data-theme='dark']) .form-group textarea {
    background: rgba(255, 255, 255, 0.03);
    color: var(--text-primary);
    border-color: var(--border-color);
  }

  :global([data-theme='dark']) .form-group input:focus,
  :global([data-theme='dark']) .form-group textarea:focus {
    background: rgba(255, 255, 255, 0.05);
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  }

  :global([data-theme='dark']) .form-group input:hover,
  :global([data-theme='dark']) .form-group textarea:hover {
    background: rgba(255, 255, 255, 0.04);
    border-color: var(--primary-color);
  }

  :global([data-theme='dark']) .collection-card {
    background: var(--card-background);
    border-color: var(--border-color);
  }


  :global([data-theme='dark']) .badge.public {
    background: rgba(34, 197, 94, 0.2);
    color: #4ade80;
  }

  :global([data-theme='dark']) .badge.prompt {
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
  }

  /* Mobile: fullscreen modals and tap-friendly buttons */
  @media (max-width: 768px) {
    .modal-backdrop {
      align-items: stretch;
      padding: 0;
    }

    .modal-container {
      width: 100%;
      max-width: 100% !important;
      max-height: 100%;
      max-height: 100dvh;
      border-radius: 0;
      margin: 0;
    }

    .modal-header {
      padding: 1rem;
      padding-top: calc(1rem + env(safe-area-inset-top, 0px));
    }

    .modal-header h2 {
      font-size: 1.1rem;
    }

    .config-form {
      padding: 1rem;
    }

    .form-actions {
      flex-direction: column;
      gap: 0.75rem;
      padding-bottom: calc(1rem + env(safe-area-inset-bottom, 0px));
    }

    .cancel-button,
    .save-button {
      width: 100%;
      min-height: 44px;
      justify-content: center;
    }

    .modal-close-button {
      min-width: 44px;
      min-height: 44px;
    }

    /* Collections panel itself */
    .collection-actions button {
      min-width: 44px;
      min-height: 44px;
    }

    .btn-add {
      min-height: 44px;
      padding: 0.5rem 1rem;
    }
  }

</style>
