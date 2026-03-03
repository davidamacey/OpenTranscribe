<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte';
  import { fade, slide } from 'svelte/transition';
  import { t } from '$stores/locale';
  import { toastStore } from '$stores/toast';
  import { SharingApi } from '$lib/api/sharing';
  import { sharingStore } from '$stores/sharing';
  import ShareTargetSearch from './ShareTargetSearch.svelte';
  import CurrentSharesList from './CurrentSharesList.svelte';
  import PermissionLevelSelect from './PermissionLevelSelect.svelte';
  import type { Share, ShareTargetSearchResult, PermissionLevel } from '$lib/types/groups';

  export let collectionUuid: string;
  export let collectionName: string;

  const dispatch = createEventDispatcher();

  let shares: Share[] = [];
  let loading = true;
  let sharing = false;

  // Pending targets to share with
  let pendingTargets: Array<ShareTargetSearchResult & { permission: PermissionLevel }> = [];

  // Derived existing targets for search filtering
  $: existingShareTargets = [
    ...shares.map(s => ({ type: s.target_type, uuid: s.target_uuid })),
    ...pendingTargets.map(pt => ({ type: pt.type, uuid: pt.uuid })),
  ];

  async function loadShares() {
    loading = true;
    // Clear stale shares immediately to prevent previous collection's data from flashing
    shares = [];
    sharingStore.setCurrentShares([]);
    try {
      const data = await SharingApi.fetchCollectionShares(collectionUuid);
      shares = data;
      sharingStore.setCurrentShares(data);
    } catch (err: any) {
      console.error('Error loading shares:', err);
      toastStore.error($t('sharing.failedToLoadShares'));
    } finally {
      loading = false;
    }
  }

  function handleTargetSelect(event: CustomEvent<ShareTargetSearchResult>) {
    const target = event.detail;
    // Add to pending with default viewer permission
    pendingTargets = [...pendingTargets, { ...target, permission: 'viewer' as PermissionLevel }];
  }

  function removePendingTarget(index: number) {
    pendingTargets = pendingTargets.filter((_, i) => i !== index);
  }

  function handlePendingPermissionChange(index: number, event: CustomEvent<PermissionLevel>) {
    pendingTargets = pendingTargets.map((pt, i) =>
      i === index ? { ...pt, permission: event.detail } : pt
    );
  }

  async function shareWithTargets() {
    if (pendingTargets.length === 0) return;

    sharing = true;
    try {
      let successCount = 0;
      let errors: string[] = [];

      for (const target of pendingTargets) {
        try {
          const newShare = await SharingApi.shareCollection(collectionUuid, {
            target_type: target.type,
            target_uuid: target.uuid,
            permission: target.permission,
          });
          sharingStore.addShare(newShare);
          shares = [...shares, newShare];
          successCount++;
        } catch (err: any) {
          console.error('Error sharing with target:', target, err);
          const detail = err.response?.data?.detail || $t('sharing.failedToShare');
          errors.push(`${target.name}: ${detail}`);
        }
      }

      if (successCount > 0) {
        toastStore.success($t('sharing.sharedSuccess', { count: successCount }));
        dispatch('shared');
      }
      if (errors.length > 0) {
        toastStore.error(errors.join('\n'));
      }
    } finally {
      pendingTargets = [];
      sharing = false;
    }
  }

  function handleClose() {
    dispatch('close');
  }

  // Reactively update shares from store
  $: storeShares = $sharingStore.currentCollectionShares;
  $: if (storeShares.length > 0 || !loading) {
    shares = storeShares;
  }

  onMount(() => {
    loadShares();
  });
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div
  class="modal-overlay"
  role="presentation"
  on:click={handleClose}
  on:keydown={(e) => e.key === 'Escape' && handleClose()}
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
    aria-labelledby="share-modal-title"
    on:click|stopPropagation
    on:keydown|stopPropagation
    transition:slide
  >
    <div class="modal-header">
      <h3 id="share-modal-title">{$t('sharing.shareCollection')}</h3>
      <button
        class="close-button"
        on:click={handleClose}
        type="button"
        aria-label={$t('sharing.close')}
      >&times;</button>
    </div>

    <div class="modal-body">
      <p class="collection-name">{collectionName}</p>

      <!-- Search for users/groups to share with -->
      <div class="search-section">
        <ShareTargetSearch
          {existingShareTargets}
          on:select={handleTargetSelect}
        />
      </div>

      <!-- Pending targets to share -->
      {#if pendingTargets.length > 0}
        <div class="pending-section" transition:slide>
          <h4>{$t('sharing.pendingShares')}</h4>
          <div class="pending-list">
            {#each pendingTargets as target, index (target.type + '-' + target.uuid)}
              <div class="pending-item">
                <div class="pending-info">
                  {#if target.type === 'user'}
                    <svg class="type-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                      <circle cx="12" cy="7" r="4"/>
                    </svg>
                  {:else}
                    <svg class="type-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                      <circle cx="9" cy="7" r="4"/>
                      <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                      <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                    </svg>
                  {/if}
                  <span class="pending-name">{target.name}</span>
                </div>
                <div class="pending-actions">
                  <PermissionLevelSelect
                    value={target.permission}
                    on:change={(e) => handlePendingPermissionChange(index, e)}
                  />
                  <button
                    class="remove-btn"
                    on:click={() => removePendingTarget(index)}
                    title={$t('sharing.remove')}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18"/>
                      <line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                  </button>
                </div>
              </div>
            {/each}
          </div>

          <div class="share-action">
            <button
              class="share-btn"
              on:click={shareWithTargets}
              disabled={sharing || pendingTargets.length === 0}
            >
              {#if sharing}
                <div class="spinner-mini"></div>
                {$t('sharing.sharing')}
              {:else}
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/>
                  <polyline points="16 6 12 2 8 6"/>
                  <line x1="12" y1="2" x2="12" y2="15"/>
                </svg>
                {$t('sharing.shareButton')}
              {/if}
            </button>
          </div>
        </div>
      {/if}

      <!-- Divider -->
      {#if shares.length > 0}
        <div class="divider"></div>
      {/if}

      <!-- Existing shares -->
      {#if loading}
        <div class="loading-shares">
          <div class="spinner-mini"></div>
          {$t('sharing.loadingShares')}
        </div>
      {:else}
        <CurrentSharesList
          {shares}
          canManage={true}
          {collectionUuid}
        />
      {/if}
    </div>
  </div>
</div>

<style>
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
    max-width: 540px;
    width: 100%;
    max-height: 85vh;
    overflow-y: auto;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.25rem 1.5rem 1rem 1.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  .modal-header h3 {
    margin: 0;
    font-size: 1.15rem;
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

  .modal-body {
    padding: 1.25rem 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .collection-name {
    margin: 0;
    font-size: 0.9rem;
    color: var(--text-secondary);
    font-weight: 500;
  }

  .search-section {
    margin-bottom: 0.25rem;
  }

  .pending-section h4 {
    margin: 0 0 0.5rem 0;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-color);
  }

  .pending-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .pending-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 0.4rem 0.6rem;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
  }

  .pending-info {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    flex: 1;
  }

  .type-icon {
    flex-shrink: 0;
    color: var(--text-secondary);
  }

  .pending-name {
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--text-color);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .pending-actions {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }

  .remove-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    padding: 0;
    border: none;
    border-radius: 4px;
    background: transparent;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .remove-btn:hover {
    color: var(--error-color, #ef4444);
    background: rgba(239, 68, 68, 0.08);
  }

  .share-action {
    display: flex;
    justify-content: flex-end;
    margin-top: 0.5rem;
  }

  .share-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1.2rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .share-btn:hover:not(:disabled) {
    background: #2563eb;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.25);
  }

  .share-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .divider {
    height: 1px;
    background: var(--border-color);
    margin: 0.25rem 0;
  }

  .loading-shares {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 1rem 0;
    font-size: 0.85rem;
    color: var(--text-secondary);
    justify-content: center;
  }

  .spinner-mini {
    width: 14px;
    height: 14px;
    border: 2px solid transparent;
    border-top: 2px solid currentColor;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  :global([data-theme='dark']) .modal-overlay {
    background: rgba(0, 0, 0, 0.7);
  }

  :global([data-theme='dark']) .pending-item {
    background: rgba(255, 255, 255, 0.03);
  }
</style>
